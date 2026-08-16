"""Deterministic, label-aware pattern association (Tier 1)."""

from __future__ import annotations

import logging
import re

from hpo_ai.associate.models import (
    Association,
    Fillers,
    Unmapped,
    UnmappedReason,
)
from hpo_ai.datamodel import HPTerm
from hpo_ai.datamodel.pattern import Pattern
from hpo_ai.associate.preferred import FIND_FLUIDS, clinical_synonym, fluid_label
from hpo_ai.patterns.assigner import PatternAssigner
from hpo_ai.provenance.constants import is_row_locked
from hpo_ai.provenance.stores import machine_grounding_rows, read_grounding

logger = logging.getLogger(__name__)

# Fluid/location qualifiers stripped when isolating the chemical span.
_QUALIFIER = (
    r"cerebrospinal fluid|cerebrospinal|circulating|blood|serum|plasma|urinary|urine|csf"
)
# "abnormality of" must precede "abnormal" so the longer phrase wins.
_DIRECTION = (
    r"elevated|increased|decreased|reduced|diminished|low|high|abnormality of|abnormal"
)
_NOUN = r"concentration|concentrations|level|levels|amount"

_DIRECTION_RE = re.compile(rf"^(?:{_DIRECTION})\b\s*", re.IGNORECASE)
_LEADING_QUALIFIER_RE = re.compile(rf"^(?:{_QUALIFIER})\b\s*", re.IGNORECASE)
_TRAILING_NOUN_RE = re.compile(rf"\s+(?:{_NOUN})\b\.?$", re.IGNORECASE)


def _enum_value(val: object) -> str | None:
    if val is None:
        return None
    return val.value if hasattr(val, "value") else str(val)


def extract_chemical(label: str) -> str | None:
    """Extract the chemical span from a level-phenotype label.

    Handles the common HPO forms with or without a trailing measurement noun,
    requiring either a fluid qualifier or a measurement noun to be confident the
    label really is a chemical-level phenotype.

    >>> extract_chemical("Increased CSF taurine concentration")
    'taurine'
    >>> extract_chemical("Increased CSF lactate")
    'lactate'
    >>> extract_chemical("Decreased circulating L-arginine level")
    'L-arginine'
    >>> extract_chemical("Diminished circulating cationic trypsinogen concentration")
    'cationic trypsinogen'
    >>> extract_chemical("Abnormality of circulating beta-2-microglobulin level")
    'beta-2-microglobulin'
    >>> extract_chemical("Abnormality of the cerebellum") is None
    True
    >>> extract_chemical("Elevated potassium") is None
    True
    """
    m = _DIRECTION_RE.match(label.strip())
    if not m:
        return None
    rest = label.strip()[m.end():]

    mq = _LEADING_QUALIFIER_RE.match(rest)
    had_qualifier = bool(mq)
    if mq:
        rest = rest[mq.end():]

    mn = _TRAILING_NOUN_RE.search(rest)
    had_noun = bool(mn)
    if mn:
        rest = rest[: mn.start()]

    chemical = rest.strip()
    # Require a fluid qualifier or a measurement noun to avoid matching
    # arbitrary "Increased X" labels that are not chemical-level phenotypes.
    if not (had_qualifier or had_noun):
        return None
    return chemical if len(chemical) > 2 else None


class DeterministicAssociator:
    """Associate an HP term with a pattern using deterministic label logic."""

    def __init__(
        self,
        patterns: list[Pattern],
        chebi_resolver=None,
        pro_resolver=None,
        entity_threshold: float = 0.7,
        string_confidence: float = 0.6,
        clinical_chemical_extractor=None,
        clinical_store=None,
        clinical_agent_version: str = "",
        preferred_term_resolver=None,
        pattern_store=None,
    ) -> None:
        """Initialise the associator.

        Args:
            patterns: Available patterns.
            chebi_resolver: Resolver with ``.resolve(name) -> list`` (CHEBI).
            pro_resolver: Resolver with ``.resolve(name) -> list`` (PRO).
            entity_threshold: Minimum confidence to treat a chemical as a
                resolved entity rather than a bare string.
            string_confidence: Confidence assigned to a string-only association.
            clinical_chemical_extractor: Optional ``callable(label) -> str|None``
                that extracts the chemical concept from an opaque clinical term
                (e.g. "Hypoglycorrhachia" -> "glucose"). When it succeeds, the
                clinical label is preserved as primary (see
                :attr:`Association.preserve_current_label`).
        """
        self.patterns = patterns
        self.chebi_resolver = chebi_resolver
        self.pro_resolver = pro_resolver
        self.entity_threshold = entity_threshold
        self.string_confidence = string_confidence
        self.clinical_chemical_extractor = clinical_chemical_extractor
        self.clinical_store = clinical_store
        self.clinical_agent_version = clinical_agent_version
        self.preferred_term_resolver = preferred_term_resolver
        self.pattern_store = pattern_store
        self._assigner = PatternAssigner()

    def _pattern_override(self, hp_id: str):
        """Return a curator-forced (locked) pattern for a term, or None."""
        if self.pattern_store is None:
            return None
        for row in self.pattern_store.get(hp_id):
            if is_row_locked(row) and row.get("pattern_id"):
                return next(
                    (p for p in self.patterns if p.id == row["pattern_id"]), None
                )
        return None

    def _preferred_label(
        self, term: HPTerm, direction: str, location_id: str | None,
        chemical: str, route: str,
    ) -> tuple[str | None, str, str | None]:
        """Resolve the primary-label decision for a term.

        Returns ``(preferred_label, source, clinical_synonym_to_add)``:
        a *common* clinical term is returned as ``preferred_label`` (promoted to
        primary); an *obscure* one is returned as ``clinical_synonym_to_add``
        (kept as an exact synonym); a term with neither returns all-None.
        """
        # Opaque clinical term already the label -> keep it as primary.
        if route == "clinical" and term.label:
            return term.label, "current_clinical", None

        fluid = fluid_label(location_id)
        if fluid is None:
            return None, "", None

        # Candidate clinical term: an existing clinical-morphology exact synonym...
        exact = [
            s.value for s in (term.synonyms or [])
            if s.value and _enum_value(s.scope) in (None, "exact")
        ]
        candidate = clinical_synonym(exact, direction, location_id)
        source = "synonym" if candidate else ""

        # ...or, if none, ask the oracle to find one (blood/urine only).
        if candidate is None and self.preferred_term_resolver is not None \
                and fluid in FIND_FLUIDS:
            found, common = self.preferred_term_resolver(direction, chemical, fluid)
            if found:
                return (found, "llm", None) if common else (None, "", found)
            return None, "", None

        if candidate is None:
            return None, "", None

        # Judge the candidate's commonness (cached/curated); common -> promote,
        # obscure -> keep as an exact synonym.
        common = False
        if self.preferred_term_resolver is not None:
            _term, common = self.preferred_term_resolver(
                direction, chemical, fluid, candidate
            )
        return (candidate, source, None) if common else (None, "", candidate)

    def _select_patterns(self, direction: str, location_id: str | None) -> list[Pattern]:
        return [
            p
            for p in self.patterns
            if _enum_value(p.selector.direction) == direction
            and p.selector.location == location_id
        ]

    def _resolve_chemical(self, name: str):
        """Return the best entity evidence above threshold, or None."""
        best = None
        for resolver in (self.chebi_resolver, self.pro_resolver):
            if resolver is None:
                continue
            results = resolver.resolve(name) or []
            if results and (results[0].confidence or 0) >= self.entity_threshold:
                cand = results[0]
                if best is None or (cand.confidence or 0) > (best.confidence or 0):
                    best = cand
        return best

    def associate(self, term: HPTerm) -> Association | Unmapped:
        """Associate a term with a pattern (Tier 1).

        Args:
            term: The HP term.

        Returns:
            An :class:`Association` if cleanly mapped, else :class:`Unmapped`.
        """
        label = term.label
        text = f"{label} {term.definition or ''}"

        direction = _enum_value(self._assigner._determine_direction(label)) or "abnormal"
        location_id, _ = self._assigner._determine_location(text)

        if location_id is None:
            return Unmapped(term.id, label, UnmappedReason.no_location,
                            "no fluid/location detected")

        candidates = self._select_patterns(direction, location_id)
        if not candidates:
            return Unmapped(term.id, label, UnmappedReason.no_pattern,
                            f"no pattern for direction={direction} location={location_id}")
        if len(candidates) > 1:
            ids = ", ".join(p.id for p in candidates)
            return Unmapped(term.id, label, UnmappedReason.ambiguous,
                            f"multiple patterns match: {ids}")

        pattern = candidates[0]
        # A curator-locked pattern row redirects the pick.
        override = self._pattern_override(term.id)
        if override is not None:
            pattern = override

        # Compositional route: chemical read directly from a descriptive label.
        chemical_string = extract_chemical(label)
        route = "compositional"
        preserve = False
        entity = None
        entity_known = False  # set when the grounding came from the store
        if not chemical_string:
            # Clinical route: opaque portmanteau term (e.g. "Hypoglycorrhachia").
            # Direction + location came from prefix/suffix rules; the chemical
            # concept needs an LLM. The clinical label is kept as primary.
            # 1. Store read-through: a curated/cached grounding short-circuits the
            #    LLM (and honours a hand-edited CHEBI id).
            if self.clinical_store is not None:
                stored = read_grounding(self.clinical_store, label)
                if stored is not None and stored[0]:
                    chemical_string, entity = stored
                    route, preserve, entity_known = "clinical", True, True
            # 2. Otherwise ask the LLM, and record a MACHINE grounding row.
            if not chemical_string and self.clinical_chemical_extractor is not None:
                chemical_string = self.clinical_chemical_extractor(label)
                if chemical_string:
                    route, preserve = "clinical", True
            if not chemical_string:
                return Unmapped(term.id, label, UnmappedReason.no_chemical,
                                "could not extract a chemical span from the label")

        if not entity_known:
            entity = self._resolve_chemical(chemical_string)
            if route == "clinical" and self.clinical_store is not None:
                self.clinical_store.record(
                    label,
                    machine_grounding_rows(term.id, label, chemical_string, entity,
                                           self.clinical_agent_version),
                )

        # Is the chemical var allowed to be a bare string?
        allow_string = any(
            v.name == "chemical" and v.allow_string for v in (pattern.vars or [])
        )
        if entity is None and not allow_string:
            return Unmapped(term.id, label, UnmappedReason.chemical_unresolved,
                            f"'{chemical_string}' did not resolve and string not allowed")

        is_entity = entity is not None
        # A CHEBI *role* filler (subsumed by CHEBI:50906) must be modelled with
        # ``has role`` rather than as a direct genus, or the EQ is unsatisfiable.
        is_role = (
            entity is not None
            and entity.entity_id.startswith("CHEBI:")
            and self.chebi_resolver is not None
            and hasattr(self.chebi_resolver, "is_role")
            and self.chebi_resolver.is_role(entity.entity_id)
        )
        confidence = (entity.confidence or 0.0) if entity is not None else self.string_confidence
        evidence = (
            f"direction={direction}; location={location_id}; "
            f"chemical='{chemical_string}'"
            + (f" -> {entity.entity_id}" if entity is not None else " (string)")
        )
        fillers = Fillers(
            direction=direction,
            location_id=location_id,
            chemical_string=chemical_string,
            chemical_entity=entity,
            is_entity=is_entity,
            is_role=is_role,
        )
        preferred_label, preferred_source, clinical_syn = self._preferred_label(
            term, direction, location_id, chemical_string, route
        )
        return Association(term.id, label, pattern, fillers, confidence, evidence,
                           route=route, preserve_current_label=preserve,
                           preferred_label=preferred_label,
                           preferred_source=preferred_source,
                           clinical_synonym_to_add=clinical_syn)
