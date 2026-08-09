"""Tests for pattern assignment module."""

import pytest

from hpo_ai.datamodel import Direction, HPTerm, PatternType
from hpo_ai.patterns import PatternAssigner


class TestPatternAssigner:
    """Tests for PatternAssigner."""

    @pytest.fixture
    def assigner(self):
        """Create pattern assigner instance."""
        return PatternAssigner()

    def test_assign_increased_blood_pattern(self, assigner):
        """Test assignment of increased blood pattern."""
        term = HPTerm(
            id="HP:0003072",
            label="Hypercalcemia",
            definition="An abnormally increased calcium concentration in the blood.",
        )
        result = assigner.assign(term)

        assert result.pattern_name == PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood
        assert result.direction == Direction.increased
        assert result.location_label == "blood"

    def test_assign_decreased_blood_pattern(self, assigner):
        """Test assignment of decreased blood pattern."""
        term = HPTerm(
            id="HP:0002901",
            label="Hypocalcemia",
            definition="An abnormally decreased calcium concentration in the blood.",
        )
        result = assigner.assign(term)

        assert result.pattern_name == PatternType.abnormallyDecreasedLevelOfChemicalEntityInBlood
        assert result.direction == Direction.decreased

    def test_assign_elevated_pattern(self, assigner):
        """Test 'Elevated' prefix is detected as increased."""
        term = HPTerm(
            id="HP:0002149",
            label="Elevated circulating uric acid concentration",
        )
        result = assigner.assign(term)

        assert result.direction == Direction.increased

    def test_assign_decreased_pattern(self, assigner):
        """Test 'Decreased' prefix is detected."""
        term = HPTerm(
            id="HP:0003233",
            label="Decreased HDL cholesterol concentration",
        )
        result = assigner.assign(term)

        assert result.direction == Direction.decreased

    def test_assign_abnormal_pattern(self, assigner):
        """Test abnormal pattern with no direction."""
        term = HPTerm(
            id="HP:0003111",
            label="Abnormal blood ion concentration",
        )
        result = assigner.assign(term)

        assert result.pattern_name == PatternType.abnormalLevelOfChemicalEntityInBlood
        assert result.direction == Direction.abnormal

    def test_assign_urine_pattern(self, assigner):
        """Test urine location detection."""
        term = HPTerm(
            id="HP:0003355",
            label="Elevated urinary amino acid concentration",
        )
        result = assigner.assign(term)

        # Handle both enum and string pattern names
        pattern_name = (
            result.pattern_name.value
            if hasattr(result.pattern_name, "value")
            else result.pattern_name
        )
        assert "Urine" in pattern_name
        assert result.location_label == "urine"

    def test_taurine_in_csf_not_misread_as_urine(self, assigner):
        """'taurine' contains the substring 'urine' but the location is CSF.

        Regression: substring matching assigned UBERON:0001088 (urine) to
        'Increased CSF taurine concentration'. Location detection must use
        word boundaries so the chemical name 'taurine' is not mistaken for
        the fluid 'urine'.
        """
        term = HPTerm(
            id="HP:0034455",
            label="Increased CSF taurine concentration",
            definition="Increased concentration of taurine in the cerebrospinal fluid (CSF).",
        )
        result = assigner.assign(term)

        assert result.location_id == "UBERON:0001359"
        assert result.location_label == "cerebrospinal fluid"

    def test_assign_emia_suffix(self, assigner):
        """Test -emia suffix detection as blood."""
        term = HPTerm(
            id="HP:0002154",
            label="Hyperglycinemia",
        )
        result = assigner.assign(term)

        assert result.location_label == "blood"
        assert result.direction == Direction.increased

    def test_assign_uria_suffix(self, assigner):
        """Test -uria suffix detection as urine."""
        term = HPTerm(
            id="HP:0003267",
            label="Glycosuria",
        )
        result = assigner.assign(term)

        assert result.location_label == "urine"

    def test_modifier_pattern(self, assigner):
        """Test modifier pattern detection."""
        term = HPTerm(
            id="HP:0001988",
            label="Recurrent hypoglycemia",
        )
        result = assigner.assign(term)

        assert result.pattern_name == PatternType.modifier

    def test_combination_pattern(self, assigner):
        """Test combination phenotype detection."""
        # Use a clearer example that triggers the combination pattern
        term = HPTerm(
            id="HP:0000825",
            label="Hyperinsulinemia with hypoglycemia",  # Uses "with" keyword
        )
        result = assigner.assign(term)

        # Handle both enum and string pattern names
        pattern_name = (
            result.pattern_name.value
            if hasattr(result.pattern_name, "value")
            else result.pattern_name
        )
        assert pattern_name == "combination_phenotype"

    def test_process_pattern(self, assigner):
        """Test process phenotype detection."""
        term = HPTerm(
            id="HP:0000816",
            label="Abnormality of Krebs cycle metabolism",
        )
        result = assigner.assign(term)

        assert result.pattern_name == PatternType.process

    @pytest.mark.parametrize(
        "hp_id, label",
        [
            ("HP:0410177", "Abnormal glucose-6-phosphate dehydrogenase level in blood"),
            ("HP:0410178", "Increased glucose-6-phosphate dehydrogenase level in blood"),
            ("HP:0410179", "Decreased glucose-6-phosphate dehydrogenase level in blood"),
            ("HP:9000001", "Decreased acid lipase level"),
            ("HP:9000002", "Abnormal hexokinase level in blood"),
        ],
        ids=["G6PD-abnormal", "G6PD-increased", "G6PD-decreased", "lipase", "hexokinase"],
    )
    def test_enzyme_terms_assigned_activity_pattern(self, assigner, hp_id, label):
        """Enzyme terms (labels containing -ase names) must get activity pattern.

        G6PD is measured as enzymatic activity, not molar concentration.
        Any label containing an enzyme name (word ending in -ase, >= 6 chars)
        should be routed to PatternType.activity.
        """
        term = HPTerm(id=hp_id, label=label)
        result = assigner.assign(term)
        assert result.pattern_name == PatternType.activity

    def test_phosphatase_is_enzyme_not_concentration(self, assigner):
        """Alkaline phosphatase is an enzyme -- should use activity pattern."""
        term = HPTerm(
            id="HP:0003155",
            label="Elevated circulating alkaline phosphatase concentration",
        )
        result = assigner.assign(term)
        assert result.pattern_name == PatternType.activity

    @pytest.mark.parametrize(
        "hp_id, label",
        [
            ("HP:0003072", "Hypercalcemia"),
            ("HP:0011015", "Abnormal blood glucose concentration"),
            ("HP:9000003", "Elevated circulating uric acid concentration"),
        ],
        ids=["calcium", "glucose", "uric-acid"],
    )
    def test_non_enzyme_terms_not_activity(self, assigner, hp_id, label):
        """Non-enzyme chemical terms must NOT be assigned activity pattern."""
        term = HPTerm(id=hp_id, label=label)
        result = assigner.assign(term)
        assert result.pattern_name != PatternType.activity

    def test_confidence_calculation(self, assigner):
        """Test confidence is calculated."""
        term = HPTerm(
            id="HP:0003072",
            label="Hypercalcemia",
            definition="An abnormally increased calcium concentration in the blood.",
        )
        result = assigner.assign(term)

        assert result.confidence is not None
        assert 0 <= result.confidence <= 1
        assert result.confidence >= 0.8  # Should be high for clear pattern
