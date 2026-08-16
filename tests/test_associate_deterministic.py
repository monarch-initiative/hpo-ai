"""Tests for deterministic pattern association."""

from __future__ import annotations

from pathlib import Path

from hpo_ai.associate import (
    Association,
    DeterministicAssociator,
    Unmapped,
    UnmappedReason,
)
from hpo_ai.datamodel import ChemicalEntityEvidence, HPTerm
from hpo_ai.datamodel.pattern import DirectionSelector, Pattern, Selector, Var
from hpo_ai.patterns.loader import load_patterns

PATTERNS = load_patterns(Path(__file__).parent.parent / "patterns")


class FakeResolver:
    """Resolver stub returning a fixed entity for a known name."""

    def __init__(self, mapping: dict[str, tuple[str, float]]):
        self.mapping = mapping

    def resolve(self, name: str, max_results: int = 5):
        if name in self.mapping:
            cid, conf = self.mapping[name]
            return [
                ChemicalEntityEvidence(
                    id=f"ev_{cid}",
                    entity_id=cid,
                    entity_label=name,
                    confidence=conf,
                )
            ]
        return []


def _term(hp_id, label, definition=None):
    return HPTerm(id=hp_id, label=label, definition=definition)


def test_taurine_csf_maps_to_increased_csf_pattern() -> None:
    """'taurine' contains 'urine' but must map to the CSF pattern (regression)."""
    resolver = FakeResolver({"taurine": ("CHEBI:15891", 0.95)})
    assoc = DeterministicAssociator(PATTERNS, chebi_resolver=resolver).associate(
        _term("HP:0034455", "Increased CSF taurine concentration",
              "Increased concentration of taurine in the cerebrospinal fluid.")
    )
    assert isinstance(assoc, Association)
    assert assoc.pattern.id == "increasedChemicalInCSF"
    assert assoc.fillers.location_id == "UBERON:0001359"
    assert assoc.fillers.is_entity is True
    assert assoc.fillers.chemical_entity is not None
    assert assoc.fillers.chemical_entity.entity_id == "CHEBI:15891"


def test_unresolved_chemical_falls_back_to_string() -> None:
    resolver = FakeResolver({})  # nothing resolves
    assoc = DeterministicAssociator(PATTERNS, chebi_resolver=resolver).associate(
        _term("HP:9999999", "Increased CSF interferon alpha concentration")
    )
    assert isinstance(assoc, Association)
    assert assoc.fillers.is_entity is False
    assert assoc.fillers.chemical_string == "interferon alpha"
    assert assoc.confidence == 0.6


def test_no_location_is_unmapped() -> None:
    assoc = DeterministicAssociator(PATTERNS).associate(
        _term("HP:0000001", "Elevated something concentration")
    )
    assert isinstance(assoc, Unmapped)
    assert assoc.reason == UnmappedReason.no_location


def test_string_disallowed_is_unmapped() -> None:
    """When the pattern forbids a string filler and nothing resolves."""
    strict = [
        Pattern(
            id="strictCSF",
            selector=Selector(direction=DirectionSelector.increased, location="UBERON:0001359"),
            qualifier="CSF",
            name="Elevated CSF {chemical} concentration",
            vars=[Var(name="chemical", range="CHEBI:24431", allow_string=False)],
        )
    ]
    assoc = DeterministicAssociator(strict, chebi_resolver=FakeResolver({})).associate(
        _term("HP:0000002", "Increased CSF mysteryol concentration")
    )
    assert isinstance(assoc, Unmapped)
    assert assoc.reason == UnmappedReason.chemical_unresolved


def test_clinical_route_preserves_label() -> None:
    """Hypoglycorrhachia: hypo->decreased, -rrhachia->CSF, chemical via LLM."""
    resolver = FakeResolver({"glucose": ("CHEBI:17234", 0.95)})
    assoc = DeterministicAssociator(
        PATTERNS,
        chebi_resolver=resolver,
        clinical_chemical_extractor=lambda label: "glucose",
    ).associate(_term("HP:0011972", "Hypoglycorrhachia"))
    assert isinstance(assoc, Association)
    assert assoc.pattern.id == "decreasedChemicalInCSF"
    assert assoc.route == "clinical"
    assert assoc.preserve_current_label is True
    assert assoc.fillers.chemical_string == "glucose"
    assert assoc.fillers.is_entity is True


def test_clinical_term_without_extractor_unmapped() -> None:
    """Without a clinical extractor, the opaque term stays unmapped."""
    assoc = DeterministicAssociator(PATTERNS).associate(
        _term("HP:0011972", "Hypoglycorrhachia")
    )
    assert isinstance(assoc, Unmapped)
    assert assoc.reason == UnmappedReason.no_chemical


def test_clinical_store_short_circuits_llm_and_honours_curation(tmp_path) -> None:
    """A curated grounding is used without calling the LLM, honouring its CHEBI."""
    from hpo_ai.provenance import clinical_grounding_store, machine_grounding_rows
    from hpo_ai.provenance.constants import JUSTIFICATION_MANUAL

    store = clinical_grounding_store(tmp_path / "clinical.sssom.tsv")
    entity = ChemicalEntityEvidence(id="e", entity_id="CHEBI:17234",
                                    entity_label="glucose", confidence=0.99)
    rows = machine_grounding_rows("HP:0011972", "Hypoglycorrhachia", "glucose", entity, "m")
    rows[0]["mapping_justification"] = JUSTIFICATION_MANUAL  # curator-locked
    store.record("Hypoglycorrhachia", rows)

    calls = {"n": 0}

    def llm(label):
        calls["n"] += 1
        return "WRONG"

    assoc = DeterministicAssociator(
        PATTERNS, chebi_resolver=FakeResolver({}),
        clinical_chemical_extractor=llm, clinical_store=store,
    ).associate(_term("HP:0011972", "Hypoglycorrhachia"))

    assert isinstance(assoc, Association)
    assert calls["n"] == 0  # LLM never called
    assert assoc.fillers.chemical_string == "glucose"
    assert assoc.fillers.chemical_entity is not None
    assert assoc.fillers.chemical_entity.entity_id == "CHEBI:17234"
    assert assoc.preserve_current_label is True


def test_clinical_store_records_machine_row_on_miss(tmp_path) -> None:
    from hpo_ai.provenance import clinical_grounding_store

    store = clinical_grounding_store(tmp_path / "clinical.sssom.tsv")
    DeterministicAssociator(
        PATTERNS, chebi_resolver=FakeResolver({"glucose": ("CHEBI:17234", 0.9)}),
        clinical_chemical_extractor=lambda label: "glucose",
        clinical_store=store, clinical_agent_version="model-x",
    ).associate(_term("HP:0011972", "Hypoglycorrhachia"))

    rows = store.get("Hypoglycorrhachia")
    assert rows and rows[0]["object_id"] == "CHEBI:17234"
    assert rows[0]["method"] == "LLM"
    assert rows[0]["agent_version"] == "model-x"
    assert rows[0]["status"] == "MACHINE"  # unlocked -> refreshable


def test_ambiguous_when_two_patterns_match() -> None:
    dup = [
        Pattern(id="a", selector=Selector(direction=DirectionSelector.increased, location="UBERON:0001359"),
                name="Elevated CSF {chemical} concentration",
                vars=[Var(name="chemical", range="CHEBI:24431", allow_string=True)]),
        Pattern(id="b", selector=Selector(direction=DirectionSelector.increased, location="UBERON:0001359"),
                name="Elevated CSF {chemical} concentration",
                vars=[Var(name="chemical", range="CHEBI:24431", allow_string=True)]),
    ]
    assoc = DeterministicAssociator(dup, chebi_resolver=FakeResolver({})).associate(
        _term("HP:0000003", "Increased CSF glucose concentration")
    )
    assert isinstance(assoc, Unmapped)
    assert assoc.reason == UnmappedReason.ambiguous
