"""Tests for confidence scoring module."""

import pytest

from hpo_ai.datamodel import (
    ChangeType,
    ChemicalEntityEvidence,
    CurationProposal,
    Direction,
    EvidenceType,
    HPTerm,
    PatternAssignment,
    PatternType,
)
from hpo_ai.scoring import ConfidenceScorer


class TestConfidenceScorer:
    """Tests for ConfidenceScorer."""

    @pytest.fixture
    def scorer(self):
        """Create scorer instance."""
        return ConfidenceScorer()

    @pytest.fixture
    def sample_term(self):
        """Create sample HP term."""
        return HPTerm(
            id="HP:0002149",
            label="Hyperuricemia",
            definition="An abnormally high level of uric acid in the blood.",
        )

    @pytest.fixture
    def sample_evidence(self):
        """Create sample chemical evidence."""
        return [
            ChemicalEntityEvidence(
                id="ev_1",
                entity_id="CHEBI:27226",
                entity_label="uric acid",
                entity_source="CHEBI",
                confidence=0.95,
                evidence_type=EvidenceType.chebi_match,
            )
        ]

    @pytest.fixture
    def sample_pattern(self):
        """Create sample pattern assignment."""
        return PatternAssignment(
            pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood,
            direction=Direction.increased,
            location_id="UBERON:0000178",
            location_label="blood",
            confidence=0.9,
        )

    @pytest.fixture
    def sample_proposal(self):
        """Create sample proposal."""
        return CurationProposal(
            id="prop_1",
            proposed_label="Elevated circulating uric acid concentration",
            proposed_definition="The concentration of uric acid in the blood is above the upper limit of normal.",
            change_type=ChangeType.full_refactor,
        )

    def test_score_high_confidence(
        self,
        scorer,
        sample_term,
        sample_evidence,
        sample_pattern,
        sample_proposal,
    ):
        """Test scoring with high confidence inputs."""
        score = scorer.score(
            hp_term=sample_term,
            chemical_evidence=sample_evidence,
            pattern_assignment=sample_pattern,
            proposal=sample_proposal,
        )

        assert 0 <= score <= 1
        assert score >= 0.7  # Should be reasonably high

    def test_score_no_chemical_evidence(self, scorer, sample_term):
        """Test scoring with no chemical evidence."""
        score = scorer.score(
            hp_term=sample_term,
            chemical_evidence=None,
            pattern_assignment=None,
            proposal=None,
        )

        assert 0 <= score <= 1
        assert score < 0.5  # Should be low without evidence

    def test_score_low_confidence_evidence(self, scorer, sample_term):
        """Test scoring with low confidence evidence."""
        low_evidence = [
            ChemicalEntityEvidence(
                id="ev_low",
                entity_id="CHEBI:12345",
                entity_label="some chemical",
                entity_source="CHEBI",
                confidence=0.3,
                evidence_type=EvidenceType.llm_extraction,
            )
        ]

        score = scorer.score(
            hp_term=sample_term,
            chemical_evidence=low_evidence,
            pattern_assignment=None,
            proposal=None,
        )

        assert score < 0.5  # Should be low

    def test_score_multiple_agreeing_evidence(self, scorer, sample_term):
        """Test boost for multiple sources agreeing."""
        agreeing_evidence = [
            ChemicalEntityEvidence(
                id="ev_1",
                entity_id="CHEBI:27226",
                entity_label="uric acid",
                entity_source="CHEBI",
                confidence=0.8,
                evidence_type=EvidenceType.chebi_match,
            ),
            ChemicalEntityEvidence(
                id="ev_2",
                entity_id="CHEBI:27226",
                entity_label="uric acid",
                entity_source="CHEBI",
                confidence=0.75,
                evidence_type=EvidenceType.llm_extraction,
            ),
        ]

        score = scorer.score(
            hp_term=sample_term,
            chemical_evidence=agreeing_evidence,
            pattern_assignment=None,
            proposal=None,
        )

        # Should get boosted confidence
        single_score = scorer.score(
            hp_term=sample_term,
            chemical_evidence=[agreeing_evidence[0]],
            pattern_assignment=None,
            proposal=None,
        )

        assert score >= single_score

    def test_score_special_pattern_lower(self, scorer, sample_term):
        """Test that special patterns get lower scores."""
        modifier_pattern = PatternAssignment(
            pattern_name=PatternType.modifier,
            confidence=0.8,
        )

        regular_pattern = PatternAssignment(
            pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood,
            confidence=0.8,
        )

        modifier_score = scorer.score(
            hp_term=sample_term,
            chemical_evidence=None,
            pattern_assignment=modifier_pattern,
            proposal=None,
        )

        regular_score = scorer.score(
            hp_term=sample_term,
            chemical_evidence=None,
            pattern_assignment=regular_pattern,
            proposal=None,
        )

        assert modifier_score < regular_score

    def test_score_existing_annotations_boost(self, scorer):
        """Test boost for terms with existing annotations."""
        term_with_annotations = HPTerm(
            id="HP:0002149",
            label="Hyperuricemia",
            existing_chemical_entity="CHEBI:27226",
            existing_location="UBERON:0000178",
        )

        term_without = HPTerm(
            id="HP:0012345",
            label="Some phenotype",
        )

        score_with = scorer.score(
            hp_term=term_with_annotations,
            chemical_evidence=None,
            pattern_assignment=None,
            proposal=None,
        )

        score_without = scorer.score(
            hp_term=term_without,
            chemical_evidence=None,
            pattern_assignment=None,
            proposal=None,
        )

        assert score_with > score_without

    def test_score_similar_labels_high(self, scorer, sample_term):
        """Test that similar proposed labels get higher scores."""
        similar_proposal = CurationProposal(
            id="prop_similar",
            proposed_label="Hyperuricemia",  # Same as original
            change_type=ChangeType.no_change,
        )

        different_proposal = CurationProposal(
            id="prop_different",
            proposed_label="Elevated circulating uric acid concentration",
            change_type=ChangeType.full_refactor,
        )

        score_similar = scorer.score(
            hp_term=sample_term,
            chemical_evidence=None,
            pattern_assignment=None,
            proposal=similar_proposal,
        )

        score_different = scorer.score(
            hp_term=sample_term,
            chemical_evidence=None,
            pattern_assignment=None,
            proposal=different_proposal,
        )

        assert score_similar > score_different

    def test_chemical_plus_pattern_yields_auto_approve(
        self,
        scorer,
        sample_term,
        sample_evidence,
        sample_pattern,
        sample_proposal,
    ):
        """Chemical match + pattern fit together should reach auto-approve."""
        score = scorer.score(
            hp_term=sample_term,
            chemical_evidence=sample_evidence,
            pattern_assignment=sample_pattern,
            proposal=sample_proposal,
        )

        assert score >= 0.9, (
            f"Chemical match + pattern fit should auto-approve, got {score}"
        )

    def test_existing_annotation_equivalent_to_chemical_match(self, scorer):
        """Existing annotations should be treated as entity evidence."""
        term_with_existing = HPTerm(
            id="HP:0002149",
            label="Hyperuricemia",
            existing_chemical_entity="CHEBI:27226",
            existing_location="UBERON:0000178",
            existing_logical_definition="some axiom",
        )

        pattern = PatternAssignment(
            pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood,
            direction=Direction.increased,
            confidence=0.9,
        )

        proposal = CurationProposal(
            id="prop_1",
            proposed_label="Elevated circulating uric acid concentration",
            change_type=ChangeType.full_refactor,
        )

        score = scorer.score(
            hp_term=term_with_existing,
            chemical_evidence=None,
            pattern_assignment=pattern,
            proposal=proposal,
        )

        # Existing annotations should count as entity evidence,
        # combined with pattern fit should give a high score.
        assert score >= 0.7, (
            f"Existing annotations + pattern should give high confidence, got {score}"
        )
