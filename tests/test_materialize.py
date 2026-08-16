"""Tests for pattern materialisation (the entity vs string twist)."""

from __future__ import annotations

from pathlib import Path

from hpo_ai.associate.models import Association, Fillers
from hpo_ai.datamodel import ChemicalEntityEvidence, HPTerm
from hpo_ai.generate import materialize
from hpo_ai.patterns.loader import load_patterns

PATTERNS = {p.id: p for p in load_patterns(Path(__file__).parent.parent / "patterns")}


def _assoc(term, is_entity, entity=None, chemical="taurine",
           pattern_id="increasedChemicalInCSF"):
    fillers = Fillers(
        direction="increased",
        location_id="UBERON:0001359",
        chemical_string=chemical,
        chemical_entity=entity,
        is_entity=is_entity,
    )
    return Association(term.id, term.label, PATTERNS[pattern_id], fillers, 0.9, "ev")


def test_entity_case_produces_label_def_and_eq() -> None:
    term = HPTerm(id="HP:0034455", label="Increased CSF taurine concentration")
    entity = ChemicalEntityEvidence(
        id="ev", entity_id="CHEBI:15891", entity_label="taurine", confidence=0.95
    )
    proposal = materialize(term, _assoc(term, True, entity))

    assert proposal.proposed_label == "Elevated CSF taurine concentration"
    assert proposal.proposed_definition is not None
    assert "taurine" in proposal.proposed_definition
    assert proposal.proposed_definition.endswith("above the upper limit of normal.")
    assert proposal.proposed_chemical_entity == "CHEBI:15891"
    # EQ present, with the chemical + location IRIs substituted
    eq = proposal.proposed_logical_definition
    assert eq is not None
    assert "<http://purl.obolibrary.org/obo/CHEBI_15891>" in eq
    assert "<http://purl.obolibrary.org/obo/UBERON_0001359>" in eq
    assert "{chemical}" not in eq and "{location}" not in eq
    # original label preserved as exact synonym
    assert proposal.proposed_synonyms is not None
    syn_values = {s.value for s in proposal.proposed_synonyms}
    assert "Increased CSF taurine concentration" in syn_values


def test_preserve_clinical_label_demotes_pattern_label() -> None:
    """Clinical term keeps its label as primary; pattern label becomes a synonym."""
    term = HPTerm(id="HP:0011972", label="Hypoglycorrhachia")
    entity = ChemicalEntityEvidence(
        id="ev", entity_id="CHEBI:17234", entity_label="glucose", confidence=0.95
    )
    fillers = Fillers(
        direction="decreased",
        location_id="UBERON:0001359",
        chemical_string="glucose",
        chemical_entity=entity,
        is_entity=True,
    )
    assoc = Association(
        term.id, term.label, PATTERNS["decreasedChemicalInCSF"], fillers, 0.95, "ev",
        route="clinical", preserve_current_label=True,
    )
    proposal = materialize(term, assoc)

    assert proposal.proposed_label == "Hypoglycorrhachia"  # clinical label preserved
    assert proposal.proposed_synonyms is not None
    syn_values = {s.value for s in proposal.proposed_synonyms}
    assert "Decreased CSF glucose concentration" in syn_values  # pattern label demoted
    assert proposal.proposed_logical_definition is not None  # EQ still generated


def test_string_case_has_text_but_no_eq() -> None:
    term = HPTerm(id="HP:9999999", label="Increased CSF interferon alpha concentration")
    proposal = materialize(term, _assoc(term, False, chemical="interferon alpha"))

    assert proposal.proposed_label == "Elevated CSF interferon alpha concentration"
    assert proposal.proposed_definition is not None
    assert "interferon alpha" in proposal.proposed_definition
    assert proposal.proposed_logical_definition is None
    assert proposal.proposed_chemical_entity is None
