"""Concrete stores for the two LLM extraction decisions.

- clinical chemical grounding (clinical term label -> CHEBI/PR): an SSSOM
  literal-mappings profile, so it is interoperable with OAK/ROBOT and MeDIC.
- pattern association (HP id -> pattern id): a plain curated TSV.

Both preserve curator-owned rows across re-runs (see
:class:`~hpo_ai.provenance.store.LockedTsvStore`).
"""

from __future__ import annotations

from pathlib import Path

from hpo_ai.datamodel import ChemicalEntityEvidence
from hpo_ai.provenance.constants import (
    JUSTIFICATION_COMPOSITE,
    METHOD_LLM,
    NO_TERM,
    STATUS_MACHINE,
)
from hpo_ai.provenance.store import LockedTsvStore

# --- clinical chemical grounding (SSSOM literal-mappings) --------------------

CLINICAL_TOOL = "hpo-ai-clinical"
_CLINICAL_COLUMNS = [
    "subject_type", "subject_label", "subject_id", "predicate_id",
    "object_id", "object_label", "match_string", "mapping_justification",
    "method", "agent_version", "confidence", "status", "mapping_tool", "comment",
]


def clinical_grounding_store(path: str | Path) -> LockedTsvStore:
    """Build the clinical-chemical grounding store (loads from disk)."""
    store = LockedTsvStore(
        path,
        columns=_CLINICAL_COLUMNS,
        key_column="subject_label",
        header_comments=(
            "mapping_set_id: https://w3id.org/hpo-ai/mappings/clinical_chemical",
            f"mapping_tool: {CLINICAL_TOOL}",
            "license: https://creativecommons.org/publicdomain/zero/1.0/",
        ),
        sort_key="object_id",
    )
    store.load()
    return store


def read_grounding(
    store: LockedTsvStore, label: str
) -> tuple[str, ChemicalEntityEvidence | None] | None:
    """Return a stored ``(chemical_name, entity|None)`` for a clinical label.

    Returns None if the store has no row for the label. The entity is None when
    the stored row is an explicit unresolved decision (``sssom:NoTermFound``).
    """
    rows = store.get(label)
    if not rows:
        return None
    row = rows[0]
    chemical_name = row.get("match_string") or row.get("object_label") or ""
    object_id = row.get("object_id") or ""
    if not object_id or row.get("predicate_id") == NO_TERM:
        return (chemical_name, None)
    confidence = float(row["confidence"]) if row.get("confidence") else None
    entity = ChemicalEntityEvidence(
        id=f"ev_{object_id.replace(':', '_')}",
        entity_id=object_id,
        entity_label=row.get("object_label") or chemical_name,
        confidence=confidence,
    )
    return (chemical_name, entity)


def machine_grounding_rows(
    hp_id: str,
    label: str,
    chemical_name: str,
    entity: ChemicalEntityEvidence | None,
    agent_version: str,
) -> list[dict[str, str]]:
    """Build the machine grounding row for a clinical term (a complete audit).

    Records the resolved CHEBI/PR when available, or an explicit
    ``sssom:NoTermFound`` decision otherwise.
    """
    object_id = entity.entity_id if entity is not None else ""
    object_label = (entity.entity_label if entity is not None else "") or ""
    conf = entity.confidence if entity is not None else None
    return [{
        "subject_type": "rdfs literal",
        "subject_label": label,
        "subject_id": hp_id,
        "predicate_id": "skos:exactMatch" if entity is not None else NO_TERM,
        "object_id": object_id,
        "object_label": object_label,
        "match_string": chemical_name,
        "mapping_justification": JUSTIFICATION_COMPOSITE,
        "method": METHOD_LLM,
        "agent_version": agent_version,
        "confidence": f"{conf:.4f}" if conf else "",
        "status": STATUS_MACHINE,
        "mapping_tool": CLINICAL_TOOL,
        "comment": "",
    }]


# --- pattern association (curated TSV) --------------------------------------

_PATTERN_COLUMNS = [
    "hpo_id", "label", "pattern_id", "chemical", "method", "agent_version",
    "confidence", "status", "comment",
]


def pattern_association_store(path: str | Path) -> LockedTsvStore:
    """Build the pattern-association store (loads from disk)."""
    store = LockedTsvStore(
        path,
        columns=_PATTERN_COLUMNS,
        key_column="hpo_id",
        header_comments=(
            "hpo-ai pattern association decisions",
            "edit pattern_id and set status=CONFIRMED (or method=HUMAN) to lock a row",
        ),
    )
    store.load()
    return store


def pattern_row(
    hp_id: str, label: str, pattern_id: str, chemical: str, method: str,
    agent_version: str, confidence: float, status: str = STATUS_MACHINE,
) -> dict[str, str]:
    """Build a pattern-association row."""
    return {
        "hpo_id": hp_id,
        "label": label,
        "pattern_id": pattern_id,
        "chemical": chemical,
        "method": method,
        "agent_version": agent_version,
        "confidence": f"{confidence:.2f}",
        "status": status,
        "comment": "",
    }


# --- preferred clinical term (curated TSV, keyed on the concept) -------------

_PREFERRED_COLUMNS = [
    "subject", "direction", "chemical", "fluid", "clinical_term", "common",
    "method", "agent_version", "confidence", "status", "comment",
]


def preferred_key(direction: str, chemical: str, fluid: str) -> str:
    """Concept key shared across all terms with the same (direction, chemical, fluid).

    >>> preferred_key("increased", "Glucose", "blood")
    'increased|glucose|blood'
    """
    return f"{direction}|{chemical.strip().lower()}|{fluid}"


def preferred_term_store(path: str | Path) -> LockedTsvStore:
    """Build the preferred-clinical-term store (loads from disk)."""
    store = LockedTsvStore(
        path,
        columns=_PREFERRED_COLUMNS,
        key_column="subject",
        header_comments=(
            "hpo-ai preferred clinical term decisions (keyed on direction|chemical|fluid)",
            "empty clinical_term = 'no established clinical term' (negative cache)",
            "common=true -> term becomes the primary label; common=false -> kept as an exact synonym",
            "edit clinical_term/common and set status=CONFIRMED (or method=HUMAN) to lock a row",
        ),
    )
    store.load()
    return store


def preferred_term_row(
    direction: str, chemical: str, fluid: str, clinical_term: str, common: bool,
    method: str, agent_version: str, confidence: float,
    status: str = STATUS_MACHINE,
) -> dict[str, str]:
    """Build a preferred-clinical-term row (empty ``clinical_term`` = negative)."""
    return {
        "subject": preferred_key(direction, chemical, fluid),
        "direction": direction,
        "chemical": chemical,
        "fluid": fluid,
        "clinical_term": clinical_term,
        "common": "true" if common else "false",
        "method": method,
        "agent_version": agent_version,
        "confidence": f"{confidence:.2f}",
        "status": status,
        "comment": "",
    }
