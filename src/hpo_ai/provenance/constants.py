"""Provenance vocabulary, aligned with the vendored ``schema/provenance.yaml``.

Reused from the MeDIC transformation-provenance model so the two projects speak
the same language: ``method`` distinguishes how a decision was made, ``status``
carries the human-review lifecycle, and a small set of "locked" markers make a
row curator-owned (never overwritten by a re-run).
"""

from __future__ import annotations

# TransformationMethod (provenance.yaml)
METHOD_LLM = "LLM"
METHOD_LEXICAL = "LEXICAL_MATCH"
METHOD_RULE = "DETERMINISTIC_RULE"
METHOD_HUMAN = "HUMAN"

# StepStatus lifecycle (provenance.yaml)
STATUS_MACHINE = "MACHINE"
STATUS_CANDIDATE = "CANDIDATE"
STATUS_UNDER_REVIEW = "UNDER_REVIEW"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_REJECTED = "REJECTED"

# SSSOM mapping justifications (SEMAPV)
JUSTIFICATION_MANUAL = "semapv:ManualMappingCuration"
JUSTIFICATION_COMPOSITE = "semapv:CompositeMatching"  # LLM extraction + lexical grounding
NO_TERM = "sssom:NoTermFound"

# A row is "locked" (curator-owned) when any of these hold — the pipeline
# refuses to overwrite it on a re-run, mirroring MeDIC's LOCKED_JUSTIFICATIONS.
LOCKED_JUSTIFICATIONS = frozenset({JUSTIFICATION_MANUAL})
LOCKED_STATUSES = frozenset({STATUS_CONFIRMED, STATUS_REJECTED})


def is_row_locked(row: dict[str, str]) -> bool:
    """Return True if a row is curator-owned and must not be overwritten.

    Locking is available three ways so a curator can use whichever is natural:
    change the justification to manual, set a terminal status, or set the method
    to HUMAN.

    >>> is_row_locked({"mapping_justification": "semapv:ManualMappingCuration"})
    True
    >>> is_row_locked({"status": "CONFIRMED"})
    True
    >>> is_row_locked({"method": "HUMAN"})
    True
    >>> is_row_locked({"method": "LLM", "status": "MACHINE"})
    False
    """
    return (
        row.get("mapping_justification") in LOCKED_JUSTIFICATIONS
        or row.get("status") in LOCKED_STATUSES
        or row.get("method") == METHOD_HUMAN
    )
