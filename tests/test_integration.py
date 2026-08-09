"""Integration tests for the HPO-AI pipeline.

These tests run the full pipeline on a specific branch of HPO
to verify end-to-end functionality.
"""

import json
from pathlib import Path

import pytest

from hpo_ai.datamodel import (
    EvidencePacket,
    HPTerm,
    PatternType,
)
from hpo_ai.extraction import HPOExtractor
from hpo_ai.packets import EvidencePacketBuilder
from hpo_ai.patterns import PatternAssigner


# Test branch: HP:0010876 - Abnormal circulating protein concentration
TEST_BRANCH_ID = "HP:0010876"
TEST_BRANCH_LABEL = "Abnormal circulating protein concentration"

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestBranchExtraction:
    """Test extraction of a specific branch."""

    @pytest.fixture(scope="class")
    def extractor(self):
        """Create extractor instance (cached across tests in class)."""
        return HPOExtractor()

    def test_extract_branch_descendants(self, extractor):
        """Test extracting all descendants of the test branch."""
        terms = extractor.extract_all_descendants(TEST_BRANCH_ID)

        assert len(terms) > 0
        assert all(isinstance(t, HPTerm) for t in terms)

        # Check we got reasonable data
        assert any(t.label for t in terms)

    def test_extract_branch_as_chemical_phenotypes(self, extractor):
        """Test extracting branch as chemical phenotypes."""
        terms = extractor.extract_chemical_phenotypes(
            root_ids=[TEST_BRANCH_ID],
            filter_keywords=True,
        )

        # Should get most terms since this is a chemical phenotype branch
        assert len(terms) > 50

    def test_all_terms_have_labels(self, extractor):
        """Test that all extracted terms have labels."""
        terms = extractor.extract_all_descendants(TEST_BRANCH_ID)

        for term in terms:
            assert term.label is not None, f"Term {term.id} has no label"


class TestBranchPatternAssignment:
    """Test pattern assignment for the test branch."""

    @pytest.fixture(scope="class")
    def terms(self):
        """Extract terms for testing."""
        extractor = HPOExtractor()
        return extractor.extract_all_descendants(TEST_BRANCH_ID)

    @pytest.fixture
    def assigner(self):
        """Create pattern assigner."""
        return PatternAssigner()

    def test_assign_patterns_to_branch(self, terms, assigner):
        """Test assigning patterns to all terms in branch."""
        for term in terms[:20]:  # Test first 20
            pattern = assigner.assign(term)
            assert pattern is not None
            assert pattern.pattern_name is not None

    def test_most_are_blood_patterns(self, terms, assigner):
        """Test that most protein concentration terms are blood patterns."""
        blood_patterns = [
            PatternType.abnormalLevelOfChemicalEntityInBlood.value,
            PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood.value,
            PatternType.abnormallyDecreasedLevelOfChemicalEntityInBlood.value,
        ]

        blood_count = 0
        for term in terms[:50]:
            pattern = assigner.assign(term)
            pattern_value = (
                pattern.pattern_name.value
                if hasattr(pattern.pattern_name, "value")
                else pattern.pattern_name
            )
            if pattern_value in blood_patterns:
                blood_count += 1

        # At least 50% should be blood patterns for this branch
        assert blood_count >= 25, f"Only {blood_count}/50 were blood patterns"


class TestBranchPipeline:
    """Integration tests for the full pipeline on the test branch."""

    @pytest.fixture(scope="class")
    def pipeline_results(self):
        """Run pipeline and cache results."""
        extractor = HPOExtractor()
        terms = extractor.extract_all_descendants(TEST_BRANCH_ID)

        # Only test subset for speed
        terms = terms[:30]

        builder = EvidencePacketBuilder(
            chebi_resolver=None,  # Skip CHEBI for speed
            pro_resolver=None,
            llm_enricher=None,
            auto_approve_threshold=0.9,
            review_threshold=0.5,
        )

        packets = builder.build_batch(terms, use_llm=False)
        return packets

    def test_pipeline_produces_packets(self, pipeline_results):
        """Test that pipeline produces evidence packets."""
        assert len(pipeline_results) > 0
        assert all(isinstance(p, EvidencePacket) for p in pipeline_results)

    def test_packets_have_patterns(self, pipeline_results):
        """Test that all packets have pattern assignments."""
        for packet in pipeline_results:
            assert packet.pattern_assignment is not None

    def test_packets_have_confidence_scores(self, pipeline_results):
        """Test that all packets have confidence scores."""
        for packet in pipeline_results:
            assert packet.overall_confidence is not None
            assert 0 <= packet.overall_confidence <= 1

    def test_packets_have_review_status(self, pipeline_results):
        """Test that all packets have review status."""
        for packet in pipeline_results:
            assert packet.review_status is not None

    def test_some_packets_have_proposals(self, pipeline_results):
        """Test that at least some packets have proposals."""
        packets_with_proposals = [
            p for p in pipeline_results if p.proposal is not None
        ]
        assert len(packets_with_proposals) > 0

    def test_confidence_distribution(self, pipeline_results):
        """Test confidence score distribution."""
        scores = [p.overall_confidence for p in pipeline_results]

        avg_score = sum(scores) / len(scores)
        assert avg_score > 0.3, f"Average score {avg_score} is too low"

        # Should have some variation
        min_score = min(scores)
        max_score = max(scores)
        assert max_score > min_score, "All scores are identical"


@pytest.mark.slow
class TestFullBranchPipeline:
    """Full pipeline test on entire branch (slower)."""

    @pytest.fixture(scope="class")
    def full_results(self):
        """Run full pipeline on entire branch."""
        extractor = HPOExtractor()
        terms = extractor.extract_all_descendants(TEST_BRANCH_ID)

        builder = EvidencePacketBuilder(
            auto_approve_threshold=0.9,
            review_threshold=0.5,
        )

        packets = builder.build_batch(terms, use_llm=False)
        return packets, terms

    def test_all_terms_processed(self, full_results):
        """Test that all terms are processed."""
        packets, terms = full_results
        assert len(packets) == len(terms)

    def test_save_results(self, full_results):
        """Save results to fixtures for reference."""
        packets, terms = full_results

        # Save to fixtures
        FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

        # Save summary statistics
        # Helper to get review status value (handles both enum and string)
        def get_status(p):
            if not p.review_status:
                return None
            return p.review_status.value if hasattr(p.review_status, 'value') else p.review_status

        stats = {
            "branch_id": TEST_BRANCH_ID,
            "branch_label": TEST_BRANCH_LABEL,
            "total_terms": len(terms),
            "total_packets": len(packets),
            "auto_approved": sum(
                1 for p in packets
                if get_status(p) == "auto_approved"
            ),
            "needs_review": sum(
                1 for p in packets
                if get_status(p) == "needs_review"
            ),
            "skipped": sum(
                1 for p in packets
                if get_status(p) == "skipped"
            ),
            "avg_confidence": sum(p.overall_confidence or 0 for p in packets) / len(packets),
            "pattern_distribution": {},
        }

        # Count patterns
        for packet in packets:
            if packet.pattern_assignment:
                pattern_name = (
                    packet.pattern_assignment.pattern_name.value
                    if hasattr(packet.pattern_assignment.pattern_name, "value")
                    else packet.pattern_assignment.pattern_name
                )
                stats["pattern_distribution"][pattern_name] = (
                    stats["pattern_distribution"].get(pattern_name, 0) + 1
                )

        stats_path = FIXTURES_DIR / "branch_pipeline_stats.json"
        with open(stats_path, "w") as f:
            json.dump(stats, f, indent=2)

        # Save first 10 packets as sample
        sample_packets = packets[:10]
        sample_path = FIXTURES_DIR / "sample_packets.json"
        with open(sample_path, "w") as f:
            json.dump(
                [p.model_dump(mode="json", exclude_none=True) for p in sample_packets],
                f,
                indent=2,
            )

        # Verify files were created
        assert stats_path.exists()
        assert sample_path.exists()

        # Print summary
        print(f"\nBranch Pipeline Results for {TEST_BRANCH_ID}:")
        print(f"  Total terms: {stats['total_terms']}")
        print(f"  Auto-approved: {stats['auto_approved']}")
        print(f"  Needs review: {stats['needs_review']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Avg confidence: {stats['avg_confidence']:.2f}")
