"""Materialise pattern-conformant content for an associated term."""

from __future__ import annotations

import logging

from hpo_ai.associate.models import Association
from hpo_ai.datamodel import (
    ChangeType,
    CurationProposal,
    HPTerm,
    Synonym,
    SynonymScope,
)

logger = logging.getLogger(__name__)

_OBO = "http://purl.obolibrary.org/obo/"


def _iri(curie: str) -> str:
    """Full OBO IRI (angle-bracketed) for a CURIE.

    >>> _iri("CHEBI:15891")
    '<http://purl.obolibrary.org/obo/CHEBI_15891>'
    """
    prefix, local = curie.split(":", 1)
    return f"<{_OBO}{prefix}_{local}>"


def _fill_text(template: str, chemical: str, qualifier: str | None) -> str:
    """Fill a text template's named placeholders.

    >>> _fill_text("Elevated {qualifier} {chemical} concentration", "taurine", "CSF")
    'Elevated CSF taurine concentration'
    """
    return (
        template.replace("{chemical}", chemical)
        .replace("{qualifier}", qualifier or "")
        .strip()
    )


def materialize(term: HPTerm, association: Association) -> CurationProposal:
    """Build a curation proposal by filling the associated pattern.

    Text (label, definition, synonyms) is always produced. The logical
    definition (``equivalentTo``) is produced only when the chemical resolved
    to an entity; for a bare-string filler it is omitted (the twist).

    Args:
        term: The HP term being curated.
        association: The pattern association with resolved fillers.

    Returns:
        A :class:`CurationProposal`.
    """
    pattern = association.pattern
    fillers = association.fillers
    chemical_text = fillers.chemical_string

    pattern_label = _fill_text(pattern.name, chemical_text, pattern.qualifier)

    # Choose the primary label: a preferred clinical term wins (e.g.
    # "Hyperglycemia"); otherwise an opaque clinical term keeps its current
    # label; otherwise we rename to the descriptive pattern label. Whatever is
    # not primary (the pattern label and the current label) is demoted to an
    # exact synonym so nothing is lost.
    if association.preferred_label:
        proposed_label = association.preferred_label
    elif association.preserve_current_label and term.label:
        proposed_label = term.label
    else:
        proposed_label = pattern_label

    proposed_definition = None
    if pattern.definition:
        proposed_definition = _fill_text(pattern.definition, chemical_text, pattern.qualifier)

    synonyms: list[Synonym] = []
    seen: set[str] = {proposed_label.lower()}
    # The pattern label, the current label, and any obscure clinical term (kept
    # as a synonym rather than promoted) are all demoted here.
    for demoted_label in (pattern_label, term.label, association.clinical_synonym_to_add):
        if demoted_label and demoted_label.lower() not in seen:
            synonyms.append(Synonym(value=demoted_label, scope=SynonymScope.exact))
            seen.add(demoted_label.lower())
    for syn in pattern.synonyms or []:
        value = _fill_text(syn.text, chemical_text, pattern.qualifier)
        scope = syn.scope.value if hasattr(syn.scope, "value") else syn.scope
        if value.lower() not in seen:
            synonyms.append(Synonym(value=value, scope=SynonymScope(scope)))
            seen.add(value.lower())

    # Logical definition only in the entity case.
    proposed_logical_definition = None
    proposed_chemical_entity = None
    if fillers.is_entity and fillers.chemical_entity is not None and pattern.equivalentTo:
        chemical_iri = _iri(fillers.chemical_entity.entity_id)
        location_iri = _iri(fillers.location_id) if fillers.location_id else ""
        proposed_logical_definition = (
            pattern.equivalentTo.replace("{chemical}", chemical_iri)
            .replace("{location}", location_iri)
        )
        proposed_chemical_entity = fillers.chemical_entity.entity_id

    change_type = _classify_change(term, proposed_label, proposed_definition,
                                   proposed_logical_definition)
    label_diff = None
    if term.label and term.label != proposed_label:
        label_diff = f"'{term.label}' -> '{proposed_label}'"

    return CurationProposal(
        id=f"prop_{term.id.replace(':', '_')}",
        proposed_label=proposed_label,
        proposed_definition=proposed_definition,
        proposed_synonyms=synonyms or None,
        proposed_chemical_entity=proposed_chemical_entity,
        proposed_location=fillers.location_id,
        proposed_logical_definition=proposed_logical_definition,
        change_type=change_type,
        label_diff=label_diff,
    )


def _classify_change(
    term: HPTerm,
    label: str,
    definition: str | None,
    logical: str | None,
) -> ChangeType:
    label_changed = bool(term.label and term.label != label)
    def_changed = bool(definition and definition != (term.definition or ""))
    signals = sum([label_changed, def_changed, bool(logical)])
    if signals == 0:
        return ChangeType.no_change
    if signals > 1:
        return ChangeType.full_refactor
    if label_changed:
        return ChangeType.label_only
    if def_changed:
        return ChangeType.definition_only
    return ChangeType.axiom_only
