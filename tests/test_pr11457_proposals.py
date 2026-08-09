"""Tests that the pipeline produces correct labels/definitions for PR #11457 data.

PR obophenotype/human-phenotype-ontology#11457 ("Metabolism phenotypes
refactoring batch 2") covers 44 protein-related HP terms.  This module
loads the raw TSV, normalizes each chemical label, applies the label /
definition templates, and asserts that every standard entry matches.

Edge cases (HP:0012239 with ``abnormalAbsenceOfChemicalEntity`` and
HP:0004639 with ``abnormallyIncreasedLevelOfChemicalEntityInLocation``)
are tested separately.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from hpo_ai.datamodel import (
    ChangeType,
    ChemicalEntityEvidence,
    Direction,
    EvidenceType,
    HPTerm,
    PatternAssignment,
    PatternType,
)
from hpo_ai.enrichment.name_normalizer import (
    NameNormalizer,
    load_name_normalization_rules,
)
from hpo_ai.patterns.generator import (
    DEFINITION_TEMPLATES,
    LABEL_TEMPLATES,
    ProposalGenerator,
)

FIXTURES = Path(__file__).parent / "fixtures"
RULES_PATH = FIXTURES / "name_normalization_rules.yaml"
TSV_PATH = Path(__file__).parent / "raw" / "test_data.tsv"

# Standard blood patterns that use label/definition templates
STANDARD_BLOOD_PATTERNS = {
    "abnormalLevelOfChemicalEntityInBlood",
    "abnormallyIncreasedLevelOfChemicalEntityInBlood",
    "abnormallyDecreasedLevelOfChemicalEntityInBlood",
}

# Patterns excluded from the standard parametrized tests
EDGE_CASE_HP_IDS = {"HP:0012239", "HP:0004639"}


def _load_tsv_rows() -> list[dict[str, str]]:
    """Load all rows from the test TSV."""
    with open(TSV_PATH) as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return list(reader)


def _normalize_chemical(label: str) -> str:
    """Normalize a chemical label using the test fixture rules."""
    rules = load_name_normalization_rules(RULES_PATH)
    normalizer = NameNormalizer(rules)
    return normalizer.normalize(label)


def _standard_rows() -> list[dict[str, str]]:
    """Return rows for the standard blood patterns, excluding edge cases."""
    return [
        row
        for row in _load_tsv_rows()
        if row["pattern"] in STANDARD_BLOOD_PATTERNS
        and row["defined_class"] not in EDGE_CASE_HP_IDS
    ]


def _build_test_id(row: dict[str, str]) -> str:
    """Build a readable pytest ID from a TSV row."""
    return f"{row['defined_class']}-{row['pattern']}"


# ---------------------------------------------------------------------------
# Parametrized label tests
# ---------------------------------------------------------------------------

_STANDARD = _standard_rows()


@pytest.mark.parametrize(
    "row",
    _STANDARD,
    ids=[_build_test_id(r) for r in _STANDARD],
)
def test_expected_label(row: dict[str, str]):
    """Proposal label matches template + normalized chemical name."""
    pattern = PatternType(row["pattern"])
    raw_chemical = row["chemical_entity_label"]
    normalized = _normalize_chemical(raw_chemical)
    expected_label = LABEL_TEMPLATES[pattern].format(
        chemical=normalized, location="blood"
    )

    rules = load_name_normalization_rules(RULES_PATH)
    normalizer = NameNormalizer(rules)
    generator = ProposalGenerator(name_normalizer=normalizer)

    hp_term = HPTerm(id=row["defined_class"], label="placeholder")
    evidence = ChemicalEntityEvidence(
        id="ev_test",
        entity_id=row["chemical_entity"],
        entity_label=raw_chemical,
        entity_source="PRO",
        confidence=1.0,
        evidence_type=EvidenceType.pro_match,
    )
    assignment = PatternAssignment(
        pattern_name=pattern,
        direction=(
            Direction.increased
            if "Increased" in pattern.value
            else Direction.decreased
            if "Decreased" in pattern.value
            else Direction.abnormal
        ),
        location_id="UBERON:0000178",
        location_label="blood",
        confidence=1.0,
    )

    proposal = generator.generate(hp_term, evidence, assignment)

    assert proposal is not None
    assert proposal.proposed_label == expected_label


# ---------------------------------------------------------------------------
# Parametrized definition tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "row",
    _STANDARD,
    ids=[_build_test_id(r) for r in _STANDARD],
)
def test_expected_definition(row: dict[str, str]):
    """Proposal definition matches template + normalized chemical name."""
    pattern = PatternType(row["pattern"])
    raw_chemical = row["chemical_entity_label"]
    normalized = _normalize_chemical(raw_chemical)
    expected_definition = DEFINITION_TEMPLATES[pattern].format(
        chemical=normalized, location="blood"
    )

    rules = load_name_normalization_rules(RULES_PATH)
    normalizer = NameNormalizer(rules)
    generator = ProposalGenerator(name_normalizer=normalizer)

    hp_term = HPTerm(id=row["defined_class"], label="placeholder")
    evidence = ChemicalEntityEvidence(
        id="ev_test",
        entity_id=row["chemical_entity"],
        entity_label=raw_chemical,
        entity_source="PRO",
        confidence=1.0,
        evidence_type=EvidenceType.pro_match,
    )
    assignment = PatternAssignment(
        pattern_name=pattern,
        direction=(
            Direction.increased
            if "Increased" in pattern.value
            else Direction.decreased
            if "Decreased" in pattern.value
            else Direction.abnormal
        ),
        location_id="UBERON:0000178",
        location_label="blood",
        confidence=1.0,
    )

    proposal = generator.generate(hp_term, evidence, assignment)

    assert proposal is not None
    assert proposal.proposed_definition == expected_definition


# ---------------------------------------------------------------------------
# Edge case: abnormalAbsenceOfChemicalEntity (HP:0012239)
# ---------------------------------------------------------------------------


def test_absence_pattern_returns_no_change():
    """HP:0012239 uses abnormalAbsenceOfChemicalEntity -> special pattern."""
    rules = load_name_normalization_rules(RULES_PATH)
    normalizer = NameNormalizer(rules)
    generator = ProposalGenerator(name_normalizer=normalizer)

    hp_term = HPTerm(id="HP:0012239", label="Atransferrinemia")
    evidence = ChemicalEntityEvidence(
        id="ev_test",
        entity_id="http://purl.obolibrary.org/obo/PR_P02787",
        entity_label="serotransferrin (human)",
        entity_source="PRO",
        confidence=1.0,
        evidence_type=EvidenceType.pro_match,
    )
    assignment = PatternAssignment(
        pattern_name=PatternType.abnormalAbsenceOfChemicalEntity,
        confidence=1.0,
    )

    proposal = generator.generate(hp_term, evidence, assignment)

    assert proposal is not None
    assert proposal.change_type == ChangeType.no_change


# ---------------------------------------------------------------------------
# Edge case: abnormallyIncreasedLevelOfChemicalEntityInLocation (HP:0004639)
# ---------------------------------------------------------------------------


def test_location_pattern_uses_blood_location():
    """HP:0004639 uses InLocation pattern with blood location."""
    rules = load_name_normalization_rules(RULES_PATH)
    normalizer = NameNormalizer(rules)
    generator = ProposalGenerator(name_normalizer=normalizer)

    hp_term = HPTerm(id="HP:0004639", label="Elevated blood alpha-fetoprotein")
    evidence = ChemicalEntityEvidence(
        id="ev_test",
        entity_id="http://purl.obolibrary.org/obo/PR_P02771",
        entity_label="alpha-fetoprotein",
        entity_source="PRO",
        confidence=1.0,
        evidence_type=EvidenceType.pro_match,
    )
    assignment = PatternAssignment(
        pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInLocation,
        direction=Direction.increased,
        location_id="UBERON:0000178",
        location_label="blood",
        confidence=1.0,
    )

    proposal = generator.generate(hp_term, evidence, assignment)

    assert proposal is not None
    assert proposal.proposed_label == "Elevated alpha-fetoprotein concentration in blood"
    assert "alpha-fetoprotein" in proposal.proposed_definition
