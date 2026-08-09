"""Agentic (LLM) pattern association (Tier 2).

Used only for the residue Tier 1 cannot map. The LLM may only *select* among
existing patterns and extract fillers -- it never invents patterns or free
text. The selector call is injected so the tier is trivially testable with a
stub; a real Anthropic-backed selector is provided by :func:`make_anthropic_selector`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable

from hpo_ai.associate.models import (
    Association,
    Fillers,
    Unmapped,
    UnmappedReason,
)
from hpo_ai.datamodel import HPTerm
from hpo_ai.datamodel.pattern import Pattern

logger = logging.getLogger(__name__)


@dataclass
class PatternChoice:
    """An LLM's structured pattern choice for a term."""

    pattern_id: str
    chemical: str
    confidence: float
    rationale: str = ""


# A selector takes (term, catalog) and returns a choice or None to decline.
SelectorFn = Callable[[HPTerm, list[dict]], "PatternChoice | None"]


def build_catalog(patterns: list[Pattern]) -> list[dict]:
    """Summarise patterns for the LLM prompt (id, description, selector)."""
    catalog = []
    for p in patterns:
        direction = p.selector.direction
        catalog.append(
            {
                "id": p.id,
                "description": p.description or "",
                "direction": direction.value if hasattr(direction, "value") else direction,
                "location": p.selector.location,
                "name_template": p.name,
            }
        )
    return catalog


class AgenticAssociator:
    """Associate a term with a pattern via an injected LLM selector."""

    def __init__(
        self,
        select_fn: SelectorFn,
        chebi_resolver=None,
        pro_resolver=None,
        entity_threshold: float = 0.7,
        min_confidence: float = 0.5,
        string_confidence: float = 0.6,
        pattern_store=None,
        agent_version: str = "",
    ) -> None:
        """Initialise.

        Args:
            select_fn: Callable returning a :class:`PatternChoice` or None.
            chebi_resolver: CHEBI resolver (``.resolve(name) -> list``).
            pro_resolver: PRO resolver.
            entity_threshold: Min confidence to treat a chemical as an entity.
            min_confidence: Min LLM confidence to accept a choice.
            string_confidence: Confidence for a string-only association.
            pattern_store: Optional locked TSV store; a cached/curated row for the
                term short-circuits the LLM selection call.
            agent_version: Dated model id stamped onto machine rows.
        """
        self.select_fn = select_fn
        self.chebi_resolver = chebi_resolver
        self.pro_resolver = pro_resolver
        self.entity_threshold = entity_threshold
        self.min_confidence = min_confidence
        self.string_confidence = string_confidence
        self.pattern_store = pattern_store
        self.agent_version = agent_version

    def _resolve_chemical(self, name: str):
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

    def associate(
        self, term: HPTerm, patterns: list[Pattern]
    ) -> Association | Unmapped:
        """Associate a term via the LLM selector.

        Args:
            term: The HP term.
            patterns: Available patterns to choose among.

        Returns:
            An :class:`Association` or :class:`Unmapped`.
        """
        # Store read-through: a cached/curated selection short-circuits the LLM.
        # (Recording is done centrally by the pipeline after association.)
        choice: PatternChoice | None = None
        from_store = False
        if self.pattern_store is not None:
            rows = self.pattern_store.get(term.id)
            if rows and rows[0].get("pattern_id"):
                row = rows[0]
                choice = PatternChoice(
                    row["pattern_id"], row.get("chemical", ""),
                    float(row.get("confidence") or 0.0), "from store",
                )
                from_store = True
        if choice is None:
            choice = self.select_fn(term, build_catalog(patterns))

        # A stored decision is authoritative; only gate fresh LLM calls on confidence.
        if choice is None or (not from_store and choice.confidence < self.min_confidence):
            return Unmapped(term.id, term.label, UnmappedReason.agentic_declined,
                            "LLM declined or low confidence")

        pattern = next((p for p in patterns if p.id == choice.pattern_id), None)
        if pattern is None:
            return Unmapped(term.id, term.label, UnmappedReason.agentic_declined,
                            f"LLM chose unknown pattern '{choice.pattern_id}'")

        entity = self._resolve_chemical(choice.chemical)
        allow_string = any(
            v.name == "chemical" and v.allow_string for v in (pattern.vars or [])
        )
        if entity is None and not allow_string:
            return Unmapped(term.id, term.label, UnmappedReason.chemical_unresolved,
                            f"'{choice.chemical}' did not resolve and string not allowed")

        is_entity = entity is not None
        fillers = Fillers(
            direction=(pattern.selector.direction.value
                       if hasattr(pattern.selector.direction, "value")
                       else pattern.selector.direction),
            location_id=pattern.selector.location,
            chemical_string=choice.chemical,
            chemical_entity=entity,
            is_entity=is_entity,
        )
        confidence = choice.confidence if is_entity else min(choice.confidence,
                                                             self.string_confidence)
        return Association(term.id, term.label, pattern, fillers, confidence,
                           f"agentic: {choice.rationale}", tier="agentic")


def make_anthropic_selector(enricher) -> SelectorFn:
    """Build a selector backed by an Anthropic client (via LLMEnricher).

    The returned callable prompts the model with the term and the pattern
    catalog and parses a strict JSON reply. Not exercised in unit tests.

    Args:
        enricher: An object exposing ``.client`` (Anthropic) and ``.model``.

    Returns:
        A :data:`SelectorFn`.
    """

    def select(term: HPTerm, catalog: list[dict]) -> PatternChoice | None:
        prompt = (
            "You assign an HPO chemical-phenotype term to exactly one pattern.\n"
            f"Term: {term.id} — {term.label}\n"
            f"Definition: {term.definition or '(none)'}\n\n"
            "Available patterns (choose one id):\n"
            + json.dumps(catalog, indent=2)
            + "\n\nReturn ONLY JSON: "
            '{"pattern_id": "...", "chemical": "...", "confidence": 0.0-1.0, '
            '"rationale": "..."}. '
            'If no pattern fits, return {"pattern_id": null}.'
        )
        reply = enricher.client.messages.create(
            model=enricher.model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = reply.content[0].text.strip()
        data = json.loads(text)
        if not data.get("pattern_id"):
            return None
        return PatternChoice(
            pattern_id=data["pattern_id"],
            chemical=data.get("chemical", ""),
            confidence=float(data.get("confidence", 0.0)),
            rationale=data.get("rationale", ""),
        )

    return select
