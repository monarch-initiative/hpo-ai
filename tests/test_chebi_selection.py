"""Tests for CHEBI selection rules system."""

from pathlib import Path

import pytest
import yaml

from hpo_ai.enrichment.selection_rules import (
    AbbreviationMapping,
    CHEBISelectionFilter,
    CHEBISelectionRules,
    CuratedMapping,
    load_chebi_selection_rules,
    load_selection_guide,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_RULES_PATH = FIXTURES_DIR / "test_chebi_rules.yaml"


class TestCuratedMapping:
    """Tests for CuratedMapping data model."""

    def test_basic_construction(self):
        """Test creating a CuratedMapping with required fields."""
        mapping = CuratedMapping(
            chemical_name="calcium",
            chebi_id="CHEBI:22984",
            chebi_label="calcium atom",
        )
        assert mapping.chemical_name == "calcium"
        assert mapping.chebi_id == "CHEBI:22984"
        assert mapping.chebi_label == "calcium atom"

    def test_with_aliases(self):
        """Test CuratedMapping with aliases."""
        mapping = CuratedMapping(
            chemical_name="calcium",
            chebi_id="CHEBI:22984",
            chebi_label="calcium atom",
            aliases=["Ca", "Ca2+", "calcium ion"],
        )
        assert len(mapping.aliases) == 3
        assert "Ca" in mapping.aliases

    def test_with_rationale(self):
        """Test CuratedMapping with rationale."""
        mapping = CuratedMapping(
            chemical_name="calcium",
            chebi_id="CHEBI:22984",
            chebi_label="calcium atom",
            rationale="Per upheno#946",
        )
        assert mapping.rationale == "Per upheno#946"


class TestAbbreviationMapping:
    """Tests for AbbreviationMapping data model."""

    def test_basic_construction(self):
        """Test creating an AbbreviationMapping."""
        abbrev = AbbreviationMapping(
            entity_id="CHEBI:47774",
            entity_label="low-density lipoprotein cholesterol",
        )
        assert abbrev.entity_id == "CHEBI:47774"
        assert abbrev.entity_label == "low-density lipoprotein cholesterol"


class TestCHEBISelectionRules:
    """Tests for CHEBISelectionRules container model."""

    def test_empty_construction(self):
        """Test creating rules with no data."""
        rules = CHEBISelectionRules()
        assert rules.curated_mappings == []
        assert rules.abbreviations == {}

    def test_full_construction(self):
        """Test creating rules with all data."""
        rules = CHEBISelectionRules(
            curated_mappings=[
                CuratedMapping(
                    chemical_name="calcium",
                    chebi_id="CHEBI:22984",
                    chebi_label="calcium atom",
                ),
            ],
            abbreviations={
                "LDL": AbbreviationMapping(
                    entity_id="CHEBI:47774",
                    entity_label="low-density lipoprotein cholesterol",
                ),
            },
        )
        assert len(rules.curated_mappings) == 1
        assert "LDL" in rules.abbreviations


class TestLoadCHEBISelectionRules:
    """Tests for YAML loading."""

    def test_load_valid_yaml(self):
        """Test loading a valid rules YAML file."""
        rules = load_chebi_selection_rules(TEST_RULES_PATH)
        assert len(rules.curated_mappings) == 3
        assert "LDL" in rules.abbreviations
        assert "HDL" in rules.abbreviations
        assert "CK" in rules.abbreviations

    def test_load_curated_mapping_details(self):
        """Test that curated mapping fields parse correctly."""
        rules = load_chebi_selection_rules(TEST_RULES_PATH)
        calcium = rules.curated_mappings[0]
        assert calcium.chemical_name == "calcium"
        assert calcium.chebi_id == "CHEBI:22984"
        assert calcium.chebi_label == "calcium atom"
        assert "Ca" in calcium.aliases
        assert calcium.rationale is not None

    def test_load_abbreviation_details(self):
        """Test that abbreviation fields parse correctly."""
        rules = load_chebi_selection_rules(TEST_RULES_PATH)
        ldl = rules.abbreviations["LDL"]
        assert ldl.entity_id == "CHEBI:47774"
        assert ldl.entity_label == "low-density lipoprotein cholesterol"

    def test_load_missing_file_raises(self):
        """Test that loading a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_chebi_selection_rules(Path("/nonexistent/rules.yaml"))

    def test_load_empty_file(self, tmp_path):
        """Test loading an empty YAML file returns empty rules."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")
        rules = load_chebi_selection_rules(empty_file)
        assert rules.curated_mappings == []
        assert rules.abbreviations == {}

    def test_load_partial_file(self, tmp_path):
        """Test loading YAML with only abbreviations."""
        partial_file = tmp_path / "partial.yaml"
        partial_file.write_text(
            yaml.dump(
                {
                    "abbreviations": {
                        "LDL": {
                            "entity_id": "CHEBI:47774",
                            "entity_label": "ldl cholesterol",
                        }
                    }
                }
            )
        )
        rules = load_chebi_selection_rules(partial_file)
        assert rules.curated_mappings == []
        assert "LDL" in rules.abbreviations


class TestCHEBISelectionFilter:
    """Tests for CHEBISelectionFilter lookup methods."""

    @pytest.fixture
    def selection_filter(self):
        """Create a filter from test fixture."""
        rules = load_chebi_selection_rules(TEST_RULES_PATH)
        return CHEBISelectionFilter(rules)

    def test_abbreviation_lookup_found(self, selection_filter):
        """Test abbreviation lookup returns correct result."""
        result = selection_filter.lookup_abbreviation("LDL")
        assert result is not None
        assert result.entity_id == "CHEBI:47774"
        assert result.entity_label == "low-density lipoprotein cholesterol"

    def test_abbreviation_lookup_case_insensitive(self, selection_filter):
        """Test abbreviation lookup is case-insensitive."""
        result = selection_filter.lookup_abbreviation("ldl")
        assert result is not None
        assert result.entity_id == "CHEBI:47774"

    def test_abbreviation_lookup_not_found(self, selection_filter):
        """Test abbreviation lookup returns None for unknown abbreviation."""
        result = selection_filter.lookup_abbreviation("UNKNOWN")
        assert result is None

    def test_curated_mapping_exact_match(self, selection_filter):
        """Test curated mapping lookup by exact chemical name."""
        result = selection_filter.lookup_curated("calcium")
        assert result is not None
        assert result.chebi_id == "CHEBI:22984"
        assert result.chebi_label == "calcium atom"

    def test_curated_mapping_case_insensitive(self, selection_filter):
        """Test curated mapping lookup is case-insensitive."""
        result = selection_filter.lookup_curated("Calcium")
        assert result is not None
        assert result.chebi_id == "CHEBI:22984"

    def test_curated_mapping_alias_match(self, selection_filter):
        """Test curated mapping lookup by alias."""
        result = selection_filter.lookup_curated("Ca")
        assert result is not None
        assert result.chebi_id == "CHEBI:22984"

    def test_curated_mapping_alias_case_insensitive(self, selection_filter):
        """Test curated mapping alias lookup is case-insensitive."""
        result = selection_filter.lookup_curated("ca2+")
        assert result is not None
        assert result.chebi_id == "CHEBI:22984"

    def test_curated_mapping_not_found(self, selection_filter):
        """Test curated mapping returns None for unknown chemical."""
        result = selection_filter.lookup_curated("unknownium")
        assert result is None

    def test_resolve_abbreviation(self, selection_filter):
        """Test full resolve with abbreviation match."""
        entity_id, entity_label, match_type = selection_filter.resolve("LDL")
        assert entity_id == "CHEBI:47774"
        assert entity_label == "low-density lipoprotein cholesterol"
        assert match_type == "abbreviation"

    def test_resolve_curated_mapping(self, selection_filter):
        """Test full resolve with curated mapping match."""
        entity_id, entity_label, match_type = selection_filter.resolve("calcium")
        assert entity_id == "CHEBI:22984"
        assert entity_label == "calcium atom"
        assert match_type == "curated"

    def test_resolve_curated_via_alias(self, selection_filter):
        """Test full resolve via alias returns curated match."""
        entity_id, entity_label, match_type = selection_filter.resolve("blood sugar")
        assert entity_id == "CHEBI:17234"
        assert entity_label == "glucose"
        assert match_type == "curated"

    def test_resolve_no_match(self, selection_filter):
        """Test full resolve returns None for unknown chemical."""
        result = selection_filter.resolve("unknownium")
        assert result is None

    def test_resolve_pro_abbreviation(self, selection_filter):
        """Test resolve with PRO abbreviation."""
        entity_id, entity_label, match_type = selection_filter.resolve("CK")
        assert entity_id == "PR:000050097"
        assert entity_label == "creatine kinase"
        assert match_type == "abbreviation"

    def test_abbreviation_takes_priority(self, selection_filter):
        """Test that abbreviation lookup runs before curated mapping."""
        # If a term is both an abbreviation and a curated name, abbreviation wins
        # This tests the resolution order
        entity_id, entity_label, match_type = selection_filter.resolve("HDL")
        assert match_type == "abbreviation"


class TestLoadSelectionGuide:
    """Tests for selection guide markdown loading."""

    def test_load_existing_guide(self, tmp_path):
        """Test loading an existing guide file."""
        guide_file = tmp_path / "guide.md"
        guide_file.write_text("# Test Guide\n\nSome rules here.")
        content = load_selection_guide(guide_file)
        assert "# Test Guide" in content
        assert "Some rules here." in content

    def test_load_missing_guide_raises(self):
        """Test loading a non-existent guide raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_selection_guide(Path("/nonexistent/guide.md"))
