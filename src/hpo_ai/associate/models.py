"""Data models for pattern association."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from hpo_ai.datamodel import ChemicalEntityEvidence
from hpo_ai.datamodel.pattern import Pattern


class UnmappedReason(str, Enum):
    """Why a term could not be cleanly mapped to a pattern."""

    no_direction = "no_direction"
    no_location = "no_location"
    no_chemical = "no_chemical"
    no_pattern = "no_pattern"
    ambiguous = "ambiguous"
    chemical_unresolved = "chemical_unresolved"
    agentic_declined = "agentic_declined"


@dataclass
class Fillers:
    """Resolved fillers for a pattern's variables."""

    direction: str
    location_id: str | None
    chemical_string: str
    chemical_entity: ChemicalEntityEvidence | None
    is_entity: bool
    # True when the resolved chemical is a CHEBI *role* (subsumed by CHEBI:50906)
    # rather than a material entity; the EQ then uses ``has role`` (RO:0000087).
    is_role: bool = False


@dataclass
class Association:
    """A term successfully associated with a pattern."""

    hp_id: str
    label: str
    pattern: Pattern
    fillers: Fillers
    confidence: float
    evidence: str
    tier: str = "deterministic"
    route: str = "compositional"
    # When True, keep the term's current (clinical) label as primary and demote
    # the pattern-generated label to an exact synonym (rather than renaming).
    preserve_current_label: bool = False
    # A preferred clinical term to use as the primary label (e.g. "Hyperglycemia"),
    # demoting both the pattern label and the current label to exact synonyms.
    # Only set when the clinical term is judged *common*.
    preferred_label: str | None = None
    # Where preferred_label came from: current_clinical | synonym | llm.
    preferred_source: str = ""
    # An *obscure* clinical term (e.g. "Hyperlactatorachia") to ensure is present
    # as an exact synonym, without promoting it to the primary label.
    clinical_synonym_to_add: str | None = None


@dataclass
class Unmapped:
    """A term that could not be cleanly associated with a pattern."""

    hp_id: str
    label: str
    reason: UnmappedReason
    detail: str = ""
