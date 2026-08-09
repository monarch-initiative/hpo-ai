"""Build a KGCL patch (annotation-level changes) from a proposal.

KGCL is the interoperable, reviewable artifact. It covers label renames,
synonym additions, and definition changes. Logical (EquivalentClasses) axioms
are handled separately (see :mod:`hpo_ai.apply.eq_editor`), because KGCL cannot
express a nested class expression.
"""

from __future__ import annotations

import logging

from hpo_ai.datamodel import CurationProposal
from hpo_ai.read.current_state import TermState

logger = logging.getLogger(__name__)


def _q(text: str) -> str:
    """Single-quote a value for the KGCL DSL (single quotes only, no escaping)."""
    return f"'{text}'"


def _scope_value(scope: object) -> str:
    if scope is None:
        return "exact"
    return scope.value if hasattr(scope, "value") else str(scope)


def build_kgcl(state: TermState, proposal: CurationProposal) -> list[str]:
    """Build KGCL statements for the annotation-level deltas.

    Only genuine differences between ``state`` and ``proposal`` are emitted.

    Args:
        state: The term's current on-file state.
        proposal: The generated proposal.

    Returns:
        A list of KGCL statement strings.
    """
    statements: list[str] = []
    new_label = proposal.proposed_label

    # Label rename
    if new_label and state.label and new_label != state.label:
        statements.append(
            f"rename {state.id} from {_q(state.label)} to {_q(new_label)}"
        )

    # Synonyms: add proposed synonyms not already present (and not equal to label)
    existing = {s.lower() for s in state.synonyms}
    label_lower = (new_label or state.label or "").lower()
    for syn in proposal.proposed_synonyms or []:
        value = syn.value
        if not value:
            continue
        if value.lower() in existing or value.lower() == label_lower:
            continue
        scope = _scope_value(syn.scope)
        statements.append(f"create {scope} synonym {_q(value)} for {state.id}")
        existing.add(value.lower())

    # Definition
    new_def = proposal.proposed_definition
    if new_def and new_def != (state.definition or ""):
        if state.definition:
            statements.append(
                f"change definition of {state.id} "
                f"from {_q(state.definition)} to {_q(new_def)}"
            )
        else:
            statements.append(f"add definition {_q(new_def)} to {state.id}")

    return statements


def validate_kgcl(statements: list[str]) -> list[str]:
    """Return the subset of statements the KGCL parser cannot parse.

    Used to flag values that the single-quote-only KGCL grammar cannot
    represent (e.g. an ASCII apostrophe in a chemical name). Such changes are
    still applied through the SPARQL path; this only guards the artifact.

    Args:
        statements: KGCL statement strings.

    Returns:
        The statements that failed to parse (empty if all valid).
    """
    from kgcl_schema.grammar.parser import parse_statement

    bad = []
    for stmt in statements:
        try:
            parse_statement(stmt)
        except Exception:  # noqa: BLE001 - parser raises a variety of types
            bad.append(stmt)
    return bad
