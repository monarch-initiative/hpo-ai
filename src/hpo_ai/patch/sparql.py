"""Compile annotation-level changes into a SPARQL update (the stop-gap apply).

Applied via ``robot query --update``. Labels and synonyms are simple triple
edits; definitions are **reification-aware** -- they update both the direct
``IAO:0000115`` triple and any reified ``owl:annotatedTarget`` (HPO definitions
carry a dbxref axiom annotation), so an annotated definition is not duplicated.
"""

from __future__ import annotations

from hpo_ai.datamodel import CurationProposal
from hpo_ai.read.current_state import TermState

_PREFIXES = """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX oio: <http://www.geneontology.org/formats/oboInOwl#>
PREFIX IAO: <http://purl.obolibrary.org/obo/IAO_>
"""

_OBO = "http://purl.obolibrary.org/obo/"


def _iri(curie: str) -> str:
    prefix, local = curie.split(":", 1)
    return f"<{_OBO}{prefix}_{local}>"


def _sparql_str(text: str) -> str:
    r"""Escape a value for a SPARQL string literal.

    >>> _sparql_str('a "b" \\ c')
    'a \\"b\\" \\\\ c'
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _rename_op(iri: str, old: str, new: str) -> str:
    return (
        f"DELETE {{ {iri} rdfs:label ?l }}\n"
        f'INSERT {{ {iri} rdfs:label "{_sparql_str(new)}" }}\n'
        f'WHERE  {{ {iri} rdfs:label ?l . FILTER(str(?l) = "{_sparql_str(old)}") }}'
    )


def _synonym_op(iri: str, value: str) -> str:
    return f'INSERT DATA {{ {iri} oio:hasExactSynonym "{_sparql_str(value)}" }}'


def _definition_op(iri: str, old: str | None, new: str) -> str:
    if old is None:
        return f'INSERT DATA {{ {iri} IAO:0000115 "{_sparql_str(new)}" }}'
    return (
        f"DELETE {{ {iri} IAO:0000115 ?d . ?ax owl:annotatedTarget ?d }}\n"
        f'INSERT {{ {iri} IAO:0000115 "{_sparql_str(new)}" . '
        f'?ax owl:annotatedTarget "{_sparql_str(new)}" }}\n'
        f"WHERE  {{\n"
        f'  {iri} IAO:0000115 ?d . FILTER(str(?d) = "{_sparql_str(old)}")\n'
        f"  OPTIONAL {{ ?ax owl:annotatedSource {iri} ; "
        f"owl:annotatedProperty IAO:0000115 ; owl:annotatedTarget ?d }}\n"
        f"}}"
    )


def compile_term(state: TermState, proposal: CurationProposal) -> list[str]:
    """Compile the SPARQL update operations for one term's annotation deltas."""
    iri = _iri(state.id)
    ops: list[str] = []

    new_label = proposal.proposed_label
    if new_label and state.label and new_label != state.label:
        ops.append(_rename_op(iri, state.label, new_label))

    existing = {s.lower() for s in state.synonyms}
    label_lower = (new_label or state.label or "").lower()
    for syn in proposal.proposed_synonyms or []:
        if not syn.value:
            continue
        if syn.value.lower() in existing or syn.value.lower() == label_lower:
            continue
        ops.append(_synonym_op(iri, syn.value))
        existing.add(syn.value.lower())

    new_def = proposal.proposed_definition
    if new_def and new_def != (state.definition or ""):
        ops.append(_definition_op(iri, state.definition, new_def))

    return ops


def compile_sparql(items: list[tuple[TermState, CurationProposal]]) -> str:
    """Compile a full SPARQL update file for a batch of (state, proposal) pairs.

    Args:
        items: (current state, proposal) pairs.

    Returns:
        A SPARQL update string (empty operations omitted).
    """
    ops: list[str] = []
    for state, proposal in items:
        ops.extend(compile_term(state, proposal))
    if not ops:
        return _PREFIXES + "\n# no annotation-level changes\n"
    return _PREFIXES + "\n" + " ;\n\n".join(ops) + "\n"
