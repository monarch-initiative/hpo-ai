"""Tests for the agentic (Tier 2) associator with a stub selector."""

from __future__ import annotations

from pathlib import Path

from hpo_ai.associate.agentic import AgenticAssociator, PatternChoice
from hpo_ai.associate.models import Association, Unmapped, UnmappedReason
from hpo_ai.datamodel import ChemicalEntityEvidence, HPTerm
from hpo_ai.patterns.loader import load_patterns

PATTERNS = load_patterns(Path(__file__).parent.parent / "patterns")


class FakeResolver:
    def __init__(self, mapping):
        self.mapping = mapping

    def resolve(self, name, max_results=5):
        if name in self.mapping:
            cid, conf = self.mapping[name]
            return [ChemicalEntityEvidence(id="ev", entity_id=cid,
                                           entity_label=name, confidence=conf)]
        return []


def test_agentic_selects_pattern() -> None:
    def stub(term, catalog):
        assert any(c["id"] == "increasedChemicalInCSF" for c in catalog)
        return PatternChoice("increasedChemicalInCSF", "taurine", 0.9, "clearly CSF")

    assoc = AgenticAssociator(stub, chebi_resolver=FakeResolver({"taurine": ("CHEBI:15891", 0.95)})).associate(
        HPTerm(id="HP:0034455", label="CSF taurine, elevated"), PATTERNS
    )
    assert isinstance(assoc, Association)
    assert assoc.pattern.id == "increasedChemicalInCSF"
    assert assoc.tier == "agentic"
    assert assoc.fillers.is_entity is True


def test_agentic_declines() -> None:
    def stub(term, catalog):
        return None

    assoc = AgenticAssociator(stub).associate(
        HPTerm(id="HP:0000001", label="Something odd"), PATTERNS
    )
    assert isinstance(assoc, Unmapped)
    assert assoc.reason == UnmappedReason.agentic_declined


def test_pattern_store_short_circuits_selector(tmp_path) -> None:
    """A curated pattern row is used without calling the LLM selector."""
    from hpo_ai.provenance import pattern_association_store, pattern_row
    from hpo_ai.provenance.constants import METHOD_HUMAN, STATUS_CONFIRMED

    store = pattern_association_store(tmp_path / "pattern.tsv")
    store.record("HP:0034455", [pattern_row(
        "HP:0034455", "CSF taurine, high", "increasedChemicalInCSF", "taurine",
        METHOD_HUMAN, "", 1.0, status=STATUS_CONFIRMED)])

    calls = {"n": 0}

    def selector(term, catalog):
        calls["n"] += 1
        return None

    assoc = AgenticAssociator(
        selector, chebi_resolver=FakeResolver({"taurine": ("CHEBI:15891", 0.95)}),
        pattern_store=store,
    ).associate(HPTerm(id="HP:0034455", label="CSF taurine, high"), PATTERNS)

    assert isinstance(assoc, Association)
    assert calls["n"] == 0  # LLM selector never called
    assert assoc.pattern.id == "increasedChemicalInCSF"


def test_agentic_low_confidence_declines() -> None:
    def stub(term, catalog):
        return PatternChoice("increasedChemicalInCSF", "taurine", 0.2, "unsure")

    assoc = AgenticAssociator(stub, min_confidence=0.5).associate(
        HPTerm(id="HP:0034455", label="CSF taurine, elevated"), PATTERNS
    )
    assert isinstance(assoc, Unmapped)
    assert assoc.reason == UnmappedReason.agentic_declined
