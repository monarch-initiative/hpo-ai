"""Tests for HPO-AI data models."""


from hpo_ai.datamodel import (
    ChangeType,
    ChemicalEntityEvidence,
    CurationProposal,
    Direction,
    EvidencePacket,
    EvidenceType,
    HPTerm,
    PatternAssignment,
    PatternType,
    ReviewStatus,
    Synonym,
    SynonymScope,
)


class TestHPTerm:
    """Tests for HPTerm model."""

    def test_create_basic_term(self):
        """Test creating a basic HP term."""
        term = HPTerm(
            id="HP:0001943",
            label="Hypoglycemia",
            definition="A decreased concentration of glucose in the blood.",
        )
        assert term.id == "HP:0001943"
        assert term.label == "Hypoglycemia"
        assert "glucose" in term.definition

    def test_create_term_with_synonyms(self):
        """Test creating a term with synonyms."""
        term = HPTerm(
            id="HP:0001943",
            label="Hypoglycemia",
            synonyms=[
                Synonym(value="Low blood sugar", scope=SynonymScope.exact),
                Synonym(value="Low glucose level", scope=SynonymScope.related),
            ],
        )
        assert len(term.synonyms) == 2
        assert term.synonyms[0].value == "Low blood sugar"
        assert term.synonyms[0].scope == SynonymScope.exact

    def test_term_with_existing_annotation(self):
        """Test term with existing chemical entity annotation."""
        term = HPTerm(
            id="HP:0002149",
            label="Hyperuricemia",
            existing_chemical_entity="CHEBI:27226",
            existing_location="UBERON:0000178",
        )
        assert term.existing_chemical_entity == "CHEBI:27226"
        assert term.existing_location == "UBERON:0000178"


class TestChemicalEntityEvidence:
    """Tests for ChemicalEntityEvidence model."""

    def test_create_chebi_evidence(self):
        """Test creating CHEBI evidence."""
        evidence = ChemicalEntityEvidence(
            id="ev_chebi_12345",
            entity_id="CHEBI:17234",
            entity_label="glucose",
            entity_source="CHEBI",
            confidence=0.95,
            evidence_type=EvidenceType.chebi_match,
            match_description="Direct CHEBI match",
        )
        assert evidence.entity_id == "CHEBI:17234"
        assert evidence.confidence == 0.95
        assert evidence.evidence_type == EvidenceType.chebi_match

    def test_evidence_with_abbreviation(self):
        """Test evidence with preferred abbreviation."""
        evidence = ChemicalEntityEvidence(
            id="ev_abbrev_ldl",
            entity_id="CHEBI:47774",
            entity_label="low-density lipoprotein cholesterol",
            entity_source="CHEBI",
            confidence=0.98,
            evidence_type=EvidenceType.chebi_match,
            preferred_abbreviation="LDL",
        )
        assert evidence.preferred_abbreviation == "LDL"

    def test_evidence_with_protonation_info(self):
        """Test evidence with protonation state info."""
        evidence = ChemicalEntityEvidence(
            id="ev_calcium",
            entity_id="CHEBI:22984",
            entity_label="calcium atom",
            entity_source="CHEBI",
            confidence=0.9,
            evidence_type=EvidenceType.chebi_match,
            is_protonated_form=False,
            alternative_forms=["CHEBI:29108"],  # calcium(2+)
        )
        assert evidence.is_protonated_form is False
        assert "CHEBI:29108" in evidence.alternative_forms


class TestPatternAssignment:
    """Tests for PatternAssignment model."""

    def test_blood_increased_pattern(self):
        """Test assignment of blood increased pattern."""
        assignment = PatternAssignment(
            pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood,
            direction=Direction.increased,
            location_id="UBERON:0000178",
            location_label="blood",
            confidence=0.9,
            rationale="Detected increased pattern with blood location",
        )
        assert assignment.pattern_name == PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood
        assert assignment.direction == Direction.increased
        assert assignment.location_label == "blood"

    def test_modifier_pattern(self):
        """Test assignment of modifier pattern."""
        assignment = PatternAssignment(
            pattern_name=PatternType.modifier,
            confidence=0.7,
            rationale="Detected modifier keyword: recurrent",
        )
        assert assignment.pattern_name == PatternType.modifier


class TestCurationProposal:
    """Tests for CurationProposal model."""

    def test_create_proposal(self):
        """Test creating a curation proposal."""
        proposal = CurationProposal(
            id="prop_abc123",
            proposed_label="Elevated circulating glucose concentration",
            proposed_definition="The concentration of glucose in the blood is above the upper limit of normal.",
            proposed_chemical_entity="CHEBI:17234",
            proposed_location="UBERON:0000178",
            change_type=ChangeType.full_refactor,
            label_diff="'Hyperglycemia' -> 'Elevated circulating glucose concentration'",
        )
        assert proposal.proposed_label == "Elevated circulating glucose concentration"
        assert proposal.change_type == ChangeType.full_refactor

    def test_no_change_proposal(self):
        """Test proposal with no changes needed."""
        proposal = CurationProposal(
            id="prop_no_change",
            change_type=ChangeType.no_change,
        )
        assert proposal.change_type == ChangeType.no_change


class TestEvidencePacket:
    """Tests for EvidencePacket model."""

    def test_create_packet(self):
        """Test creating an evidence packet."""
        term = HPTerm(id="HP:0002149", label="Hyperuricemia")
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
        proposal = CurationProposal(
            id="prop_1",
            proposed_label="Elevated circulating uric acid concentration",
            change_type=ChangeType.label_only,
        )

        packet = EvidencePacket(
            id="pkt_abc123",
            hp_term=term,
            chemical_evidence=[evidence],
            pattern_assignment=pattern,
            proposal=proposal,
            overall_confidence=0.88,
            review_status=ReviewStatus.needs_review,
        )

        assert packet.id == "pkt_abc123"
        assert packet.hp_term.label == "Hyperuricemia"
        assert len(packet.chemical_evidence) == 1
        assert packet.overall_confidence == 0.88
        assert packet.review_status == ReviewStatus.needs_review

    def test_packet_auto_approved(self):
        """Test packet with auto-approved status."""
        term = HPTerm(id="HP:0003072", label="Hypercalcemia")
        packet = EvidencePacket(
            id="pkt_auto",
            hp_term=term,
            overall_confidence=0.95,
            review_status=ReviewStatus.auto_approved,
        )
        assert packet.review_status == ReviewStatus.auto_approved
