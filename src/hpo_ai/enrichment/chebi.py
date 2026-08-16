"""CHEBI entity resolution using OAK.

Uses a two-layer resolution strategy:

1. **Deterministic rules** – abbreviation and curated-mapping lookups from
   ``conf/chebi_selection_rules.yaml`` (via :class:`CHEBISelectionFilter`).
2. **OAK search** – falls through to ``basic_search`` on CHEBI when no rule
   matches.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from oaklib import get_adapter
from oaklib.datamodels.vocabulary import IS_A

from hpo_ai.datamodel import ChemicalEntityEvidence, EvidenceType
from hpo_ai.enrichment.selection_rules import (
    CHEBISelectionFilter,
    CHEBISelectionRules,
    load_chebi_selection_rules,
)

if TYPE_CHECKING:
    from oaklib.interfaces import SearchInterface

logger = logging.getLogger(__name__)

# Default location for the production rules file
DEFAULT_RULES_PATH = Path(__file__).parents[2].parent / "conf" / "chebi_selection_rules.yaml"

# CHEBI upper-level roots used to distinguish a *material chemical entity* from
# a *role*. A role filler cannot bear a concentration, so it must be modelled
# with ``has role`` rather than as a direct genus (see issue_role_based_patterns).
CHEBI_ROLE_ROOT = "CHEBI:50906"  # 'role'
CHEBI_ENTITY_ROOT = "CHEBI:24431"  # 'chemical entity'


class CHEBIResolver:
    """Resolve chemical names to CHEBI identifiers.

    Resolution proceeds in order:

    1. Abbreviation lookup (from selection rules YAML)
    2. Curated mapping lookup (from selection rules YAML)
    3. OAK ``basic_search`` on CHEBI

    Args:
        chebi_path: Path to CHEBI or OAK selector (e.g., "sqlite:obo:chebi").
        adapter: Pre-configured OAK adapter.
        rules_path: Path to CHEBI selection rules YAML. Defaults to
            ``conf/chebi_selection_rules.yaml``.
        selection_filter: Pre-configured CHEBISelectionFilter instance.
    """

    def __init__(
        self,
        chebi_path: str | None = None,
        adapter: SearchInterface | None = None,
        rules_path: Path | None = None,
        selection_filter: CHEBISelectionFilter | None = None,
    ) -> None:
        """Initialize the CHEBI resolver.

        Args:
            chebi_path: Path to CHEBI or OAK selector (e.g., "sqlite:obo:chebi").
            adapter: Pre-configured OAK adapter.
            rules_path: Path to CHEBI selection rules YAML.
            selection_filter: Pre-configured CHEBISelectionFilter instance.
        """
        if adapter is not None:
            self.adapter = adapter
        elif chebi_path:
            self.adapter = get_adapter(chebi_path)
        else:
            self.adapter = get_adapter("sqlite:obo:chebi")

        # Set up the selection filter
        if selection_filter is not None:
            self.selection_filter = selection_filter
        else:
            resolved_path = rules_path or DEFAULT_RULES_PATH
            if resolved_path.exists():
                rules = load_chebi_selection_rules(resolved_path)
                self.selection_filter = CHEBISelectionFilter(rules)
                logger.info("Loaded CHEBI selection rules from %s", resolved_path)
            else:
                self.selection_filter = CHEBISelectionFilter(CHEBISelectionRules())
                logger.warning(
                    "No CHEBI selection rules found at %s; "
                    "abbreviation/curated lookups disabled",
                    resolved_path,
                )

    def resolve(
        self,
        chemical_name: str,
        max_results: int = 5,
    ) -> list[ChemicalEntityEvidence]:
        """Resolve a chemical name to CHEBI entities.

        Args:
            chemical_name: Name of the chemical to search for.
            max_results: Maximum number of results to return.

        Returns:
            List of ChemicalEntityEvidence objects, ranked by confidence.
        """
        results: list[ChemicalEntityEvidence] = []

        # Layer 1: deterministic rules lookup
        rule_match = self.selection_filter.resolve(chemical_name)
        if rule_match is not None:
            entity_id, entity_label, match_type = rule_match
            source = "CHEBI" if entity_id.startswith("CHEBI:") else "PRO"
            description = (
                f"Known abbreviation: {chemical_name.upper().strip()}"
                if match_type == "abbreviation"
                else f"Curated mapping: {chemical_name}"
            )
            results.append(
                ChemicalEntityEvidence(
                    id=f"ev_{match_type}_{entity_id.replace(':', '_')}",
                    entity_id=entity_id,
                    entity_label=entity_label,
                    entity_source=source,
                    confidence=0.95,
                    evidence_type=EvidenceType.chebi_match,
                    match_description=description,
                    preferred_abbreviation=(
                        chemical_name.upper().strip()
                        if match_type == "abbreviation"
                        else None
                    ),
                )
            )

        # Layer 2: OAK search (always run to provide alternatives)
        try:
            search_results = list(
                self.adapter.basic_search(chemical_name)
            )[:max_results]

            for i, curie in enumerate(search_results):
                if not curie.startswith("CHEBI:"):
                    continue

                label = self.adapter.label(curie)
                if not label:
                    continue

                confidence = self._calculate_confidence(chemical_name, label, i)
                is_protonated = self._is_protonated_form(label)
                alternative_forms = self._get_alternative_forms(label)

                results.append(
                    ChemicalEntityEvidence(
                        id=f"ev_chebi_{curie.replace(':', '_')}",
                        entity_id=curie,
                        entity_label=label,
                        entity_source="CHEBI",
                        confidence=confidence,
                        evidence_type=EvidenceType.chebi_match,
                        match_description=f"CHEBI search match for '{chemical_name}'",
                        is_protonated_form=is_protonated,
                        alternative_forms=alternative_forms if alternative_forms else None,
                    )
                )
        except Exception as e:
            logger.warning(f"CHEBI search failed for '{chemical_name}': {e}")

        # Sort by confidence
        results.sort(key=lambda x: x.confidence or 0, reverse=True)

        return results[:max_results]

    def is_role(self, chebi_id: str) -> bool:
        """Return True if a CHEBI class is a *role* rather than a material entity.

        A role is any class subsumed by CHEBI:50906 ('role'), e.g. metabolite
        (CHEBI:25212) or coenzyme (CHEBI:23354). Such a class cannot bear a
        concentration and must be modelled with ``has role`` in the EQ axiom.
        Non-CHEBI identifiers (e.g. PRO proteins) are never roles.

        Args:
            chebi_id: A CURIE (only ``CHEBI:*`` can be a role).

        Returns:
            True if the class is a role.
        """
        if not chebi_id.startswith("CHEBI:"):
            return False
        ancestors = set(self.adapter.ancestors(chebi_id, predicates=[IS_A]))
        return CHEBI_ROLE_ROOT in ancestors

    def resolve_by_id(self, chebi_id: str) -> ChemicalEntityEvidence | None:
        """Get evidence for a known CHEBI ID.

        Args:
            chebi_id: CHEBI identifier.

        Returns:
            ChemicalEntityEvidence or None if not found.
        """
        label = self.adapter.label(chebi_id)
        if not label:
            return None

        return ChemicalEntityEvidence(
            id=f"ev_chebi_{chebi_id.replace(':', '_')}",
            entity_id=chebi_id,
            entity_label=label,
            entity_source="CHEBI",
            confidence=1.0,
            evidence_type=EvidenceType.chebi_match,
            match_description="Direct CHEBI ID lookup",
            is_protonated_form=self._is_protonated_form(label),
        )

    def _calculate_confidence(
        self,
        query: str,
        label: str,
        rank: int,
    ) -> float:
        """Calculate match confidence.

        Args:
            query: Original search query.
            label: Matched label.
            rank: Position in search results.

        Returns:
            Confidence score between 0 and 1.
        """
        query_lower = query.lower().strip()
        label_lower = label.lower().strip()

        # Exact match
        if query_lower == label_lower:
            return 0.98

        # Query is contained in label or vice versa
        if query_lower in label_lower or label_lower in query_lower:
            base = 0.85
        else:
            base = 0.6

        # Reduce confidence based on rank
        rank_penalty = rank * 0.05
        return max(0.3, base - rank_penalty)

    def _is_protonated_form(self, label: str) -> bool:
        """Check if label indicates a protonated/ionized form."""
        patterns = [
            r"\(\d+[+-]\)",  # (2+), (1-), etc.
            r"ion$",
            r"cation$",
            r"anion$",
        ]
        for pattern in patterns:
            if re.search(pattern, label):
                return True
        return False

    def _get_alternative_forms(
        self,
        label: str,
    ) -> list[str]:
        """Get alternative CHEBI forms (e.g., atom vs ion).

        Checks if the label matches a curated mapping that prefers
        a different form (e.g. ion label → atom CHEBI ID).
        """
        alternatives = []

        # Check curated mappings for the label as an alias
        curated = self.selection_filter.lookup_curated(label)
        if curated is not None:
            alternatives.append(curated.chebi_id)

        return alternatives
