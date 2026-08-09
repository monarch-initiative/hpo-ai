"""Tests for name normalization module."""

from pathlib import Path

import pytest

from hpo_ai.enrichment.name_normalizer import (
    NameNormalizationRules,
    NameNormalizer,
    load_name_normalization_rules,
)

FIXTURES = Path(__file__).parent / "fixtures"
RULES_PATH = FIXTURES / "name_normalization_rules.yaml"


class TestLoadRules:
    """Tests for YAML rule loading."""

    def test_load_from_yaml(self):
        """Rules file loads into a NameNormalizationRules model."""
        rules = load_name_normalization_rules(RULES_PATH)
        assert isinstance(rules, NameNormalizationRules)

    def test_generic_cleanups_loaded(self):
        """Generic cleanups section is populated."""
        rules = load_name_normalization_rules(RULES_PATH)
        assert len(rules.generic_cleanups) == 3

    def test_specific_renames_loaded(self):
        """Specific renames section is populated."""
        rules = load_name_normalization_rules(RULES_PATH)
        assert len(rules.specific_renames) == 11


class TestGenericCleanups:
    """Tests for generic suffix / substring stripping."""

    @pytest.fixture
    def normalizer(self) -> NameNormalizer:
        """Normalizer loaded from the test fixture."""
        rules = load_name_normalization_rules(RULES_PATH)
        return NameNormalizer(rules)

    def test_strip_human_suffix(self, normalizer: NameNormalizer):
        """Strips ' (human)' from protein labels."""
        assert normalizer.normalize("progranulin (human)") == "progranulin"

    def test_strip_atom_suffix(self, normalizer: NameNormalizer):
        """Strips ' atom' at end of string."""
        assert normalizer.normalize("calcium atom") == "calcium"

    def test_atom_not_stripped_mid_string(self, normalizer: NameNormalizer):
        """The word 'atom' inside a string is not stripped."""
        assert normalizer.normalize("atomic mass") == "atomic mass"

    def test_strip_molecular_entity_suffix(self, normalizer: NameNormalizer):
        """Strips ' molecular entity' at end of string."""
        assert normalizer.normalize("phosphorus molecular entity") == "phosphorus"

    def test_molecular_entity_not_stripped_mid_string(self, normalizer: NameNormalizer):
        """The phrase 'molecular entity' inside a string is not stripped."""
        assert (
            normalizer.normalize("molecular entity studies")
            == "molecular entity studies"
        )


class TestSpecificRenames:
    """Parametrized tests for all specific rename rules."""

    @pytest.fixture
    def normalizer(self) -> NameNormalizer:
        """Normalizer loaded from the test fixture."""
        rules = load_name_normalization_rules(RULES_PATH)
        return NameNormalizer(rules)

    @pytest.mark.parametrize(
        "input_label, expected",
        [
            ("serotransferrin", "transferrin"),
            ("chitinase-3-like protein 1", "CHI3L1"),
            ("C-C motif chemokine 18", "CCL18"),
            ("DnaJ homolog subfamily B member 9", "DNAJB9"),
            ("72 kDa type IV collagenase", "matrix metalloproteinase 2"),
            ("serine protease 1", "cationic trypsinogen"),
            ("creatine kinase B-type", "creatine kinase BB isoform"),
            ("creatine kinase M-type", "creatine kinase MM isoform"),
            (
                "insulin-like growth factor-binding protein complex acid labile subunit",
                "insulin-like growth factor-binding protein acid labile subunit",
            ),
            ("alpha-2-HS-glycoprotein", "fetuin-A"),
            ("transthyretin", "prealbumin"),
        ],
        ids=[
            "serotransferrin",
            "chitinase3",
            "CCL18",
            "DNAJB9",
            "collagenase",
            "trypsinogen",
            "CK-B",
            "CK-M",
            "IGFBP-ALS",
            "fetuin",
            "prealbumin",
        ],
    )
    def test_specific_rename(
        self,
        normalizer: NameNormalizer,
        input_label: str,
        expected: str,
    ):
        """Each specific rename produces the correct output."""
        assert normalizer.normalize(input_label) == expected


class TestFullChain:
    """Tests that generic + specific rules chain correctly."""

    @pytest.fixture
    def normalizer(self) -> NameNormalizer:
        """Normalizer loaded from the test fixture."""
        rules = load_name_normalization_rules(RULES_PATH)
        return NameNormalizer(rules)

    def test_human_then_specific(self, normalizer: NameNormalizer):
        """'DnaJ homolog subfamily B member 9 (human)' -> 'DNAJB9'."""
        assert (
            normalizer.normalize("DnaJ homolog subfamily B member 9 (human)")
            == "DNAJB9"
        )

    def test_human_then_serotransferrin(self, normalizer: NameNormalizer):
        """'serotransferrin (human)' -> 'transferrin'."""
        assert normalizer.normalize("serotransferrin (human)") == "transferrin"

    def test_human_then_ck_b(self, normalizer: NameNormalizer):
        """'creatine kinase B-type (human)' -> 'creatine kinase BB isoform'."""
        assert (
            normalizer.normalize("creatine kinase B-type (human)")
            == "creatine kinase BB isoform"
        )

    def test_passthrough(self, normalizer: NameNormalizer):
        """Labels with no matching rules pass through unchanged."""
        assert normalizer.normalize("galectin-3") == "galectin-3"

    def test_empty_string(self, normalizer: NameNormalizer):
        """Empty string passes through."""
        assert normalizer.normalize("") == ""
