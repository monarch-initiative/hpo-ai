"""Tests for the simplified DOSDP-like pattern loader."""

from __future__ import annotations

from pathlib import Path

from hpo_ai.patterns.loader import load_pattern_file, load_patterns, var_by_name

PATTERN_DIR = Path(__file__).parent.parent / "patterns"


def _val(x) -> str:
    """Enum-or-string value."""
    return x.value if hasattr(x, "value") else x


def test_loads_all_seeded_patterns() -> None:
    patterns = load_patterns(PATTERN_DIR)
    ids = {p.id for p in patterns}
    assert "increasedChemicalInCSF" in ids
    assert "decreasedChemicalInBlood" in ids
    assert len(patterns) >= 9


def test_csf_increased_pattern_shape() -> None:
    p = load_pattern_file(PATTERN_DIR / "increasedChemicalInCSF.yaml")
    assert _val(p.selector.direction) == "increased"
    assert p.selector.location == "UBERON:0001359"
    assert p.qualifier == "CSF"
    assert "{chemical}" in p.name
    assert p.name == "Elevated CSF {chemical} concentration"
    chemical = var_by_name(p, "chemical")
    assert chemical is not None
    assert chemical.allow_string is True
    assert chemical.range == "CHEBI:24431"
    # EQ template is functional syntax with placeholders for chemical + location
    assert p.equivalentTo is not None
    assert "{chemical}" in p.equivalentTo
    assert "{location}" in p.equivalentTo
    assert p.equivalentTo.startswith("ObjectSomeValuesFrom(")


def test_location_var_is_fixed() -> None:
    p = load_pattern_file(PATTERN_DIR / "increasedChemicalInCSF.yaml")
    loc = var_by_name(p, "location")
    assert loc is not None
    assert loc.fixed is True


def test_csf_definitions_spell_out_csf_abbreviation() -> None:
    """CSF pattern definitions append '(CSF)' after 'cerebrospinal fluid'."""
    for name in ("increasedChemicalInCSF", "decreasedChemicalInCSF",
                 "abnormalChemicalInCSF"):
        p = load_pattern_file(PATTERN_DIR / f"{name}.yaml")
        assert p.definition is not None
        assert "cerebrospinal fluid (CSF)" in p.definition, name
        # no bare mention left without the abbreviation
        assert "cerebrospinal fluid " not in p.definition.replace(
            "cerebrospinal fluid (CSF)", ""
        ), name
