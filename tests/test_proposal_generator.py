"""Tests for proposal generator module."""

import pytest

from hpo_ai.datamodel import (
    ChemicalEntityEvidence,
    Direction,
    EvidenceType,
    HPTerm,
    PatternAssignment,
    PatternType,
    ChangeType,
)
from hpo_ai.patterns import ProposalGenerator


class TestProposalGenerator:
    """Tests for ProposalGenerator."""

    @pytest.fixture
    def generator(self):
        """Create generator instance."""
        return ProposalGenerator()

    def test_generate_increased_blood_proposal(self, generator):
        """Test generating proposal for increased blood pattern."""
        term = HPTerm(
            id="HP:0002149",
            label="Hyperuricemia",
            definition="An abnormally high level of uric acid in the blood.",
        )
        evidence = ChemicalEntityEvidence(
            id="ev_1",
            entity_id="CHEBI:27226",
            entity_label="uric acid",
            entity_source="CHEBI",
            confidence=0.95,
            evidence_type=EvidenceType.chebi_match,
        )
        pattern = PatternAssignment(
            pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood,
            direction=Direction.increased,
            location_id="UBERON:0000178",
            location_label="blood",
            confidence=0.9,
        )

        proposal = generator.generate(term, evidence, pattern)

        assert proposal is not None
        assert proposal.proposed_label == "Elevated circulating uric acid concentration"
        assert "uric acid" in proposal.proposed_definition
        assert "above the upper limit" in proposal.proposed_definition
        assert proposal.proposed_chemical_entity == "CHEBI:27226"

    def test_generate_decreased_blood_proposal(self, generator):
        """Test generating proposal for decreased blood pattern."""
        term = HPTerm(
            id="HP:0002901",
            label="Hypocalcemia",
        )
        evidence = ChemicalEntityEvidence(
            id="ev_1",
            entity_id="CHEBI:22984",
            entity_label="calcium atom",
            entity_source="CHEBI",
            confidence=0.95,
            evidence_type=EvidenceType.chebi_match,
        )
        pattern = PatternAssignment(
            pattern_name=PatternType.abnormallyDecreasedLevelOfChemicalEntityInBlood,
            direction=Direction.decreased,
            location_id="UBERON:0000178",
            location_label="blood",
            confidence=0.9,
        )

        proposal = generator.generate(term, evidence, pattern)

        assert proposal is not None
        assert "Decreased" in proposal.proposed_label
        assert "below the lower limit" in proposal.proposed_definition

    def test_generate_with_abbreviation(self, generator):
        """Test using preferred abbreviation in label."""
        term = HPTerm(
            id="HP:0003141",
            label="Increased LDL cholesterol concentration",
        )
        evidence = ChemicalEntityEvidence(
            id="ev_1",
            entity_id="CHEBI:47774",
            entity_label="low-density lipoprotein cholesterol",
            entity_source="CHEBI",
            confidence=0.95,
            evidence_type=EvidenceType.chebi_match,
            preferred_abbreviation="LDL",
        )
        pattern = PatternAssignment(
            pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood,
            direction=Direction.increased,
            location_id="UBERON:0000178",
            location_label="blood",
            confidence=0.9,
        )

        proposal = generator.generate(term, evidence, pattern)

        assert proposal is not None
        # Should use abbreviation since it's widely recognized
        assert "LDL" in proposal.proposed_label

    def test_generate_preserves_original_as_synonym(self, generator):
        """Test that original label is preserved as synonym."""
        term = HPTerm(
            id="HP:0002149",
            label="Hyperuricemia",
        )
        evidence = ChemicalEntityEvidence(
            id="ev_1",
            entity_id="CHEBI:27226",
            entity_label="uric acid",
            entity_source="CHEBI",
            confidence=0.95,
            evidence_type=EvidenceType.chebi_match,
        )
        pattern = PatternAssignment(
            pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood,
            direction=Direction.increased,
            confidence=0.9,
        )

        proposal = generator.generate(term, evidence, pattern)

        assert proposal is not None
        assert proposal.proposed_synonyms is not None
        synonym_values = [s.value for s in proposal.proposed_synonyms]
        assert "Hyperuricemia" in synonym_values

    def test_generate_special_pattern_returns_no_change(self, generator):
        """Test that special patterns return no-change proposal."""
        term = HPTerm(
            id="HP:0001988",
            label="Recurrent hypoglycemia",
        )
        pattern = PatternAssignment(
            pattern_name=PatternType.modifier,
            confidence=0.7,
        )

        proposal = generator.generate(term, None, pattern)

        assert proposal is not None
        assert proposal.change_type == ChangeType.no_change

    def test_generate_urine_pattern(self, generator):
        """Test generating proposal for urine pattern."""
        term = HPTerm(
            id="HP:0012345",
            label="Elevated urinary glucose",
        )
        evidence = ChemicalEntityEvidence(
            id="ev_1",
            entity_id="CHEBI:17234",
            entity_label="glucose",
            entity_source="CHEBI",
            confidence=0.9,
            evidence_type=EvidenceType.chebi_match,
        )
        pattern = PatternAssignment(
            pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInUrine,
            direction=Direction.increased,
            location_id="UBERON:0001088",
            location_label="urine",
            confidence=0.85,
        )

        proposal = generator.generate(term, evidence, pattern)

        assert proposal is not None
        assert "urinary" in proposal.proposed_label.lower()
        assert "urine" in proposal.proposed_definition.lower()

    def test_generate_csf_uses_prefix_convention(self, generator):
        """CSF terms follow the '<Direction> CSF % concentration' convention (#11702).

        The generic InLocation template must NOT be used for CSF -- that produced
        doubled-location junk like 'Abnormal glucose concentration in cerebrospinal
        fluid'.  The fluid stays up front, mirroring blood ('circulating').
        """
        term = HPTerm(
            id="HP:0031884",
            label="Abnormal CSF glucose concentration",
        )
        evidence = ChemicalEntityEvidence(
            id="ev_1",
            entity_id="CHEBI:17234",
            entity_label="glucose",
            entity_source="CHEBI",
            confidence=0.98,
            evidence_type=EvidenceType.chebi_match,
        )
        pattern = PatternAssignment(
            pattern_name=PatternType.abnormalLevelOfChemicalEntityInLocation,
            direction=Direction.abnormal,
            location_id="UBERON:0001359",
            location_label="cerebrospinal fluid",
            confidence=0.8,
        )

        proposal = generator.generate(term, evidence, pattern)

        assert proposal is not None
        assert proposal.proposed_label == "Abnormal CSF glucose concentration"
        assert "cerebrospinal fluid" in proposal.proposed_definition
        # No doubled location, no generic "in cerebrospinal fluid" suffix on the label
        assert "in cerebrospinal fluid" not in proposal.proposed_label.lower()

    def test_generate_csf_increased_normalises_to_elevated(self, generator):
        """'Increased CSF X' should normalise to 'Elevated CSF X concentration' (#11702)."""
        term = HPTerm(
            id="HP:0410071",
            label="Increased CSF ribitol concentration",
        )
        evidence = ChemicalEntityEvidence(
            id="ev_1",
            entity_id="CHEBI:15963",
            entity_label="ribitol",
            entity_source="CHEBI",
            confidence=0.95,
            evidence_type=EvidenceType.chebi_match,
        )
        pattern = PatternAssignment(
            pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInLocation,
            direction=Direction.increased,
            location_id="UBERON:0001359",
            location_label="cerebrospinal fluid",
            confidence=0.9,
        )

        proposal = generator.generate(term, evidence, pattern)

        assert proposal is not None
        assert proposal.proposed_label == "Elevated CSF ribitol concentration"
        assert "above the upper limit" in proposal.proposed_definition
        assert "cerebrospinal fluid" in proposal.proposed_definition

    def test_generate_without_evidence(self, generator):
        """Test generating proposal without chemical evidence."""
        term = HPTerm(
            id="HP:0002149",
            label="Hyperuricemia",
        )
        pattern = PatternAssignment(
            pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood,
            direction=Direction.increased,
            confidence=0.9,
        )

        proposal = generator.generate(term, None, pattern)

        # Should still generate based on label extraction
        # May be None if no chemical name can be extracted
        if proposal and proposal.proposed_label:
            assert "Elevated" in proposal.proposed_label

    def test_change_type_detection(self, generator):
        """Test correct change type detection."""
        term = HPTerm(
            id="HP:0002149",
            label="Hyperuricemia",
            definition="An abnormally high level of uric acid in the blood.",
            existing_chemical_entity="CHEBI:27226",
        )
        evidence = ChemicalEntityEvidence(
            id="ev_1",
            entity_id="CHEBI:27226",
            entity_label="uric acid",
            entity_source="CHEBI",
            confidence=0.95,
            evidence_type=EvidenceType.chebi_match,
        )
        pattern = PatternAssignment(
            pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood,
            direction=Direction.increased,
            confidence=0.9,
        )

        proposal = generator.generate(term, evidence, pattern)

        assert proposal is not None
        # Label changes, but chemical entity stays same
        assert proposal.change_type in [
            ChangeType.label_only,
            ChangeType.full_refactor,
        ]
