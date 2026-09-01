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


# ---------------------------------------------------------------------------
# The production conf rules (the full update-chemical-labels.ru port)
# ---------------------------------------------------------------------------

CONF_RULES = Path(__file__).resolve().parents[1] / "conf" / "name_normalization_rules.yaml"


class TestConfPortedRules:
    """Rules ported from the current update-chemical-labels.ru into conf/."""

    @pytest.fixture
    def normalizer(self) -> NameNormalizer:
        return NameNormalizer(load_name_normalization_rules(CONF_RULES))

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("alpha-2-HS-glycoprotein", "fetuin-A"),
            ("calcium(2+)", "calcium"),
            ("sodium(1+)", "sodium"),
            ("diphosphate(4-)", "pyrophosphate"),
            ("mucin-16", "CA-125"),
            ("N-benzoylglycine", "hippuric acid"),
            ("choriogonadotropin subunit beta", "beta-hCG"),
            ("phenylalanine", "L-phenylalanine"),
            ("O-octanoylcarnitine", "octanoylcarnitine"),
            # order-sensitive: rename must beat the " molecular entity$" strip
            ("nitrogen molecular entity", "nitrogen compound"),
        ],
    )
    def test_conf_rule(self, normalizer: NameNormalizer, raw: str, expected: str) -> None:
        assert normalizer.normalize(raw) == expected


class TestEnzymeActivityRule:
    """The -ase/protease concentration->activity trigger."""

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("creatine kinase", True),
            ("beta-hexosaminidase", True),
            ("amylase", True),
            ("thrombin", True),
            ("trypsinogen", False),   # zymogen excluded
            ("antitrypsin", False),   # inhibitor excluded
            ("nucleobase", False),    # -base excluded
            ("fetuin-A", False),      # not an enzyme
        ],
    )
    def test_is_enzyme_activity(self, name: str, expected: bool) -> None:
        from hpo_ai.enrichment.name_normalizer import is_enzyme_activity
        assert is_enzyme_activity(name) is expected


class TestMaterializeWiring:
    """materialize() applies normalisation + the enzyme rule when given a normalizer."""

    def _assoc(self, chemical: str):
        from hpo_ai.associate.models import Association, Fillers
        from hpo_ai.datamodel import ChemicalEntityEvidence, EvidenceType
        from hpo_ai.patterns.loader import load_patterns

        pattern = next(
            p for p in load_patterns("patterns") if p.id == "increasedChemicalInBlood"
        )
        ev = ChemicalEntityEvidence(
            id="ev", entity_id="CHEBI:00", entity_label=chemical,
            entity_source="CHEBI", confidence=1.0,
            evidence_type=EvidenceType.chebi_match,
        )
        fillers = Fillers("increased", "UBERON:0000178", chemical, ev, True, False)
        return Association("HP:0000001", "x", pattern, fillers, 1.0, "ev")

    def test_enzyme_label_uses_activity(self) -> None:
        from hpo_ai.datamodel import HPTerm
        from hpo_ai.enrichment.name_normalizer import (
            NameNormalizer,
            load_name_normalization_rules,
        )
        from hpo_ai.generate.materialize import materialize

        norm = NameNormalizer(load_name_normalization_rules(CONF_RULES))
        term = HPTerm(id="HP:0000001", label="Increased creatine kinase")
        proposal = materialize(term, self._assoc("creatine kinase"), normalizer=norm)
        assert proposal.proposed_label == "Elevated circulating creatine kinase activity"
        assert "activity" in (proposal.proposed_definition or "")

    def test_non_enzyme_keeps_concentration(self) -> None:
        from hpo_ai.datamodel import HPTerm
        from hpo_ai.enrichment.name_normalizer import (
            NameNormalizer,
            load_name_normalization_rules,
        )
        from hpo_ai.generate.materialize import materialize

        norm = NameNormalizer(load_name_normalization_rules(CONF_RULES))
        term = HPTerm(id="HP:0000001", label="Increased glucose")
        proposal = materialize(term, self._assoc("glucose"), normalizer=norm)
        assert proposal.proposed_label == "Elevated circulating glucose concentration"
