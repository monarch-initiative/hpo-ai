"""Test Workflow A (run_curate) end-to-end with stub resolvers (no ROBOT/network)."""

from __future__ import annotations

import csv
from pathlib import Path

from hpo_ai.datamodel import ChemicalEntityEvidence, HPTerm
from hpo_ai.patterns.loader import load_patterns
from hpo_ai.pipeline.curate import run_curate

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


def test_run_curate_produces_bundle(tmp_path: Path) -> None:
    terms = [
        HPTerm(id="HP:0002490", label="Increased CSF lactate",
               definition="Increased concentration of lactate in the cerebrospinal fluid."),
        HPTerm(id="HP:9999999", label="Increased CSF interferon alpha concentration"),
        HPTerm(id="HP:0000001", label="All"),  # unmappable
    ]
    resolver = FakeResolver({"lactate": ("CHEBI:24996", 0.95)})
    result = run_curate(terms, PATTERNS, tmp_path, chebi_resolver=resolver)

    assert result.associated == 2       # lactate (entity) + interferon (string)
    assert result.unmapped == 1         # "All"
    assert result.eq_axioms == 1        # only the entity case gets an EQ

    # bundle files exist
    for name in ["curate.kgcl", "axioms.ofn", "update.ru", "review.tsv", "unmapped.tsv"]:
        assert (tmp_path / name).exists(), name

    kgcl = (tmp_path / "curate.kgcl").read_text()
    assert "rename HP:0002490 from 'Increased CSF lactate' to 'Elevated CSF lactate concentration'" in kgcl

    axioms = (tmp_path / "axioms.ofn").read_text()
    assert "EquivalentClasses(<http://purl.obolibrary.org/obo/HP_0002490>" in axioms
    assert "CHEBI_24996" in axioms

    with open(tmp_path / "unmapped.tsv") as f:
        unmapped = list(csv.DictReader(f, delimiter="\t"))
    assert unmapped[0]["hpo_id"] == "HP:0000001"

    with open(tmp_path / "review.tsv") as f:
        review = {r["hpo_id"]: r for r in csv.DictReader(f, delimiter="\t")}
    assert review["HP:9999999"]["is_entity"] == "False"
    assert review["HP:9999999"]["eq_present"] == "False"
    assert review["HP:0002490"]["eq_present"] == "True"
    # current_definition is carried through for side-by-side review
    assert review["HP:0002490"]["current_definition"] == (
        "Increased concentration of lactate in the cerebrospinal fluid."
    )
    assert review["HP:9999999"]["current_definition"] == ""  # term had none


def test_pattern_picks_are_recorded_and_overridable(tmp_path: Path) -> None:
    from hpo_ai.provenance import pattern_association_store, pattern_row
    from hpo_ai.provenance.constants import METHOD_HUMAN, STATUS_CONFIRMED

    terms = [HPTerm(id="HP:0002490", label="Increased CSF lactate")]
    resolver = FakeResolver({"lactate": ("CHEBI:24996", 0.95)})

    # First run records the deterministic pick.
    store = pattern_association_store(tmp_path / "pattern_association.tsv")
    run_curate(terms, PATTERNS, tmp_path / "a", chebi_resolver=resolver, pattern_store=store)
    rows = store.get("HP:0002490")
    assert rows and rows[0]["pattern_id"] == "increasedChemicalInCSF"
    assert rows[0]["method"] == "DETERMINISTIC_RULE"

    # A curator locks a different pattern; the next run honours the override.
    store2 = pattern_association_store(tmp_path / "pattern_association.tsv")
    store2.record("HP:0002490", [pattern_row(
        "HP:0002490", "Increased CSF lactate", "abnormalChemicalInCSF", "lactate",
        METHOD_HUMAN, "", 1.0, status=STATUS_CONFIRMED)])
    store2.save()

    store3 = pattern_association_store(tmp_path / "pattern_association.tsv")
    run_curate(terms, PATTERNS, tmp_path / "b", chebi_resolver=resolver, pattern_store=store3)
    with open((tmp_path / "b") / "review.tsv") as f:
        review = {r["hpo_id"]: r for r in csv.DictReader(f, delimiter="\t")}
    assert review["HP:0002490"]["pattern"] == "abnormalChemicalInCSF"  # override applied
    # and the locked row was not overwritten
    assert store3.get("HP:0002490")[0]["method"] == "HUMAN"


def test_agentic_fallback_rescues_unmapped(tmp_path: Path) -> None:
    from hpo_ai.associate.agentic import PatternChoice

    # A label Tier 1 cannot parse (no direction/concentration structure).
    terms = [HPTerm(id="HP:0034455", label="CSF taurine, markedly high")]

    def selector(term, catalog):
        return PatternChoice("increasedChemicalInCSF", "taurine", 0.9, "clearly CSF")

    resolver = FakeResolver({"taurine": ("CHEBI:15891", 0.95)})
    # Without agentic: unmapped
    r1 = run_curate(terms, PATTERNS, tmp_path / "a", chebi_resolver=resolver)
    assert r1.unmapped == 1
    # With agentic: rescued
    r2 = run_curate(terms, PATTERNS, tmp_path / "b", chebi_resolver=resolver,
                    agentic_selector=selector)
    assert r2.associated == 1
    assert r2.unmapped == 0
