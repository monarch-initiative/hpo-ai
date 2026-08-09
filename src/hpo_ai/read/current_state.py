"""Read a term's current state from an ontology (standard reader).

The current-state reader is used to compute minimal patches: only genuine
deltas between the term's current state and the proposal become changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TermState:
    """The current, on-file state of an HP term relevant to curation."""

    id: str
    label: str | None = None
    definition: str | None = None
    def_has_annotation: bool = False
    synonyms: list[str] = field(default_factory=list)
    equivalent_to: str | None = None


def term_state_from_hpterm(term) -> TermState:
    """Build a :class:`TermState` from an extracted :class:`~hpo_ai.datamodel.HPTerm`.

    The extractor already reads label, definition, and synonyms from the
    ontology, so no separate ROBOT query is needed for annotation-level state.

    >>> from hpo_ai.datamodel import HPTerm, Synonym
    >>> t = HPTerm(id="HP:1", label="L", definition="D",
    ...            synonyms=[Synonym(value="s1")])
    >>> ts = term_state_from_hpterm(t)
    >>> ts.label, ts.definition, ts.synonyms
    ('L', 'D', ['s1'])
    """
    synonyms = [s.value for s in (term.synonyms or []) if getattr(s, "value", None)]
    return TermState(
        id=term.id,
        label=term.label,
        definition=term.definition,
        synonyms=synonyms,
        equivalent_to=getattr(term, "existing_logical_definition", None),
    )
