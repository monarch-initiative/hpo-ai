"""Tests for role-based CHEBI fillers (CHEBI:50906) in generated EQ axioms.

A CHEBI class may be a *material chemical entity* (subsumed by CHEBI:24431)
or a *role* (subsumed by CHEBI:50906 'role'), e.g. metabolite (CHEBI:25212)
or coenzyme (CHEBI:23354). A role cannot bear a concentration, so using it as
a direct filler in ``inheres_in some (<FILLER> and part_of some <loc>)``
produces an unsatisfiable class. The correct form (HPO #4952) is
``'chemical entity' and 'has role' some <role>``.
"""

from __future__ import annotations

from hpo_ai.associate.deterministic import DeterministicAssociator
from hpo_ai.associate.models import Association, Fillers
from hpo_ai.datamodel import ChemicalEntityEvidence, EvidenceType, HPTerm
from hpo_ai.enrichment.chebi import CHEBIResolver
from hpo_ai.generate.materialize import materialize
from hpo_ai.patterns.loader import load_patterns

PATTERN_DIR = "patterns"

# --- fake CHEBI adapter -----------------------------------------------------

_ANCESTRY = {
    # metabolite is a role
    "CHEBI:25212": ["CHEBI:25212", "CHEBI:50906", "CHEBI:24431"],
    # coenzyme is a role
    "CHEBI:23354": ["CHEBI:23354", "CHEBI:50906"],
    # taurine is a material chemical entity, NOT a role
    "CHEBI:15891": ["CHEBI:15891", "CHEBI:24431"],
    # lactate is a material chemical entity
    "CHEBI:24996": ["CHEBI:24996", "CHEBI:24431"],
}


class _FakeAdapter:
    def ancestors(self, curie, predicates=None):  # noqa: ANN001, ANN201
        return _ANCESTRY.get(curie, [])

    def label(self, curie):  # noqa: ANN001, ANN201
        return {"CHEBI:25212": "metabolite", "CHEBI:15891": "taurine"}.get(curie)

    def basic_search(self, name):  # noqa: ANN001, ANN201
        return []


def _resolver() -> CHEBIResolver:
    return CHEBIResolver(adapter=_FakeAdapter())


# --- role detection ---------------------------------------------------------


def test_is_role_true_for_metabolite() -> None:
    assert _resolver().is_role("CHEBI:25212") is True


def test_is_role_true_for_coenzyme() -> None:
    assert _resolver().is_role("CHEBI:23354") is True


def test_is_role_false_for_material_entity() -> None:
    assert _resolver().is_role("CHEBI:15891") is False


def test_is_role_false_for_non_chebi() -> None:
    assert _resolver().is_role("PR:P12345") is False


# --- role-aware materialization --------------------------------------------


def _evidence(entity_id: str, label: str) -> ChemicalEntityEvidence:
    return ChemicalEntityEvidence(
        id="ev",
        entity_id=entity_id,
        entity_label=label,
        entity_source="CHEBI",
        confidence=1.0,
        evidence_type=EvidenceType.chebi_match,
    )


def _increased_blood():
    patterns = load_patterns(PATTERN_DIR)
    return next(p for p in patterns if p.id == "increasedChemicalInBlood")


def test_role_filler_emits_has_role_eq() -> None:
    """A role filler produces 'chemical entity' and has_role some <role>."""
    pattern = _increased_blood()
    term = HPTerm(id="HP:0031964", label="Elevated circulating metabolite concentration")
    fillers = Fillers(
        direction="increased",
        location_id="UBERON:0000178",
        chemical_string="metabolite",
        chemical_entity=_evidence("CHEBI:25212", "metabolite"),
        is_entity=True,
        is_role=True,
    )
    assoc = Association(term.id, term.label, pattern, fillers, 1.0, "ev")
    proposal = materialize(term, assoc)

    eq = proposal.proposed_logical_definition
    assert eq is not None
    # chemical entity genus + has_role restriction, NOT the role as direct filler
    assert "CHEBI_24431" in eq
    assert "ObjectSomeValuesFrom(<http://purl.obolibrary.org/obo/RO_0000087>" in eq
    assert "CHEBI_25212" in eq
    # the role must NOT appear as a direct member of the bearer intersection
    assert "ObjectIntersectionOf(<http://purl.obolibrary.org/obo/CHEBI_25212>" not in eq


def test_entity_filler_unchanged_direct() -> None:
    """A material entity still uses the direct-filler form (no has_role)."""
    pattern = _increased_blood()
    term = HPTerm(id="HP:0002490", label="Increased CSF lactate")
    fillers = Fillers(
        direction="increased",
        location_id="UBERON:0000178",
        chemical_string="lactate",
        chemical_entity=_evidence("CHEBI:24996", "lactate"),
        is_entity=True,
        is_role=False,
    )
    assoc = Association(term.id, term.label, pattern, fillers, 1.0, "ev")
    proposal = materialize(term, assoc)

    eq = proposal.proposed_logical_definition
    assert eq is not None
    assert "RO_0000087" not in eq  # no has_role
    assert "CHEBI_24996" in eq


# --- end-to-end wiring through the associator -------------------------------


class _RoleChebiResolver:
    """Minimal resolver: resolves any name to metabolite (a role)."""

    def resolve(self, name, max_results=5):  # noqa: ANN001, ANN201
        return [_evidence("CHEBI:25212", "metabolite")]

    def is_role(self, chebi_id):  # noqa: ANN001, ANN201
        return chebi_id == "CHEBI:25212"


def test_associator_sets_is_role() -> None:
    """A role-resolving chemical produces a role association end-to-end."""
    patterns = load_patterns(PATTERN_DIR)
    associator = DeterministicAssociator(patterns, chebi_resolver=_RoleChebiResolver())
    term = HPTerm(id="HP:0031964", label="Elevated circulating metabolite concentration")

    assoc = associator.associate(term)

    assert isinstance(assoc, Association)
    assert assoc.fillers.is_role is True
    proposal = materialize(term, assoc)
    assert "RO_0000087" in (proposal.proposed_logical_definition or "")
