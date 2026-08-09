"""PRO (Protein Ontology) entity resolution using OAK."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from oaklib import get_adapter

from hpo_ai.datamodel import ChemicalEntityEvidence, EvidenceType

if TYPE_CHECKING:
    from oaklib.interfaces import SearchInterface

logger = logging.getLogger(__name__)

# Common protein abbreviations and their PRO mappings
PROTEIN_ABBREVIATIONS = {
    "IgA": ("PR:000001872", "immunoglobulin A"),
    "IgG": ("PR:000001873", "immunoglobulin G"),
    "IgM": ("PR:000001875", "immunoglobulin M"),
    "IgE": ("PR:000001871", "immunoglobulin E"),
    "IgD": ("PR:000001870", "immunoglobulin D"),
    "CRP": ("PR:000001201", "C-reactive protein"),
    "albumin": ("PR:000003918", "albumin"),
    "ferritin": ("PR:000050342", "ferritin complex"),
    "transferrin": ("PR:000017011", "transferrin"),
    "ceruloplasmin": ("PR:000004823", "ceruloplasmin"),
    "leptin": ("PR:000009758", "leptin"),
    "adiponectin": ("PR:Q15848", "adiponectin"),
    "insulin": ("PR:000009054", "insulin"),
    "glucagon": ("PR:000007285", "glucagon"),
    "hemoglobin": ("PR:000029067", "hemoglobin complex"),
    "myoglobin": ("PR:000010724", "myoglobin"),
    "troponin": ("PR:000017119", "troponin complex"),
    "creatine kinase": ("PR:000050097", "creatine kinase"),
    "alkaline phosphatase": ("PR:000003968", "alkaline phosphatase"),
    "pepsinogen": ("PR:000013508", "pepsinogen"),
    "alpha-fetoprotein": ("PR:000003809", "alpha-fetoprotein"),
    "AFP": ("PR:000003809", "alpha-fetoprotein"),
}


class PROResolver:
    """Resolve protein names to PRO identifiers."""

    def __init__(
        self,
        pro_path: str | None = None,
        adapter: SearchInterface | None = None,
    ) -> None:
        """Initialize the PRO resolver.

        Args:
            pro_path: Path to PRO or OAK selector (e.g., "sqlite:obo:pr").
            adapter: Pre-configured OAK adapter.
        """
        if adapter is not None:
            self.adapter = adapter
        elif pro_path:
            self.adapter = get_adapter(pro_path)
        else:
            # PRO can be large; use OLS as fallback
            try:
                self.adapter = get_adapter("sqlite:obo:pr")
            except Exception:
                logger.warning("PRO sqlite not available, using OLS")
                self.adapter = get_adapter("ols:pr")

    def resolve(
        self,
        protein_name: str,
        max_results: int = 5,
        prefer_human: bool = True,
    ) -> list[ChemicalEntityEvidence]:
        """Resolve a protein name to PRO entities.

        Args:
            protein_name: Name of the protein to search for.
            max_results: Maximum number of results to return.
            prefer_human: Whether to prefer human-specific proteins.

        Returns:
            List of ChemicalEntityEvidence objects, ranked by confidence.
        """
        results = []

        # Check known protein abbreviations first
        name_lower = protein_name.lower().strip()
        for abbrev, (pro_id, label) in PROTEIN_ABBREVIATIONS.items():
            if abbrev.lower() == name_lower or abbrev.lower() in name_lower:
                results.append(
                    ChemicalEntityEvidence(
                        id=f"ev_pro_{pro_id.replace(':', '_')}",
                        entity_id=pro_id,
                        entity_label=label,
                        entity_source="PRO",
                        confidence=0.95,
                        evidence_type=EvidenceType.pro_match,
                        match_description=f"Known protein: {abbrev}",
                        preferred_abbreviation=abbrev,
                    )
                )
                break

        # Search PRO if no abbreviation match
        if not results:
            try:
                # Note: basic_search doesn't support syntax parameter on SqlImplementation
                search_results = list(
                    self.adapter.basic_search(protein_name)
                )[:max_results * 2]  # Get extra to filter

                for i, curie in enumerate(search_results):
                    if not curie.startswith("PR:"):
                        continue

                    label = self.adapter.label(curie)
                    if not label:
                        continue

                    # Calculate confidence
                    confidence = self._calculate_confidence(
                        protein_name, label, i, prefer_human
                    )

                    results.append(
                        ChemicalEntityEvidence(
                            id=f"ev_pro_{curie.replace(':', '_')}",
                            entity_id=curie,
                            entity_label=label,
                            entity_source="PRO",
                            confidence=confidence,
                            evidence_type=EvidenceType.pro_match,
                            match_description=f"PRO search match for '{protein_name}'",
                        )
                    )

            except Exception as e:
                logger.warning(f"PRO search failed for '{protein_name}': {e}")

        # Sort by confidence
        results.sort(key=lambda x: x.confidence or 0, reverse=True)

        return results[:max_results]

    def resolve_by_id(self, pro_id: str) -> ChemicalEntityEvidence | None:
        """Get evidence for a known PRO ID.

        Args:
            pro_id: PRO identifier.

        Returns:
            ChemicalEntityEvidence or None if not found.
        """
        try:
            label = self.adapter.label(pro_id)
            if not label:
                return None

            return ChemicalEntityEvidence(
                id=f"ev_pro_{pro_id.replace(':', '_')}",
                entity_id=pro_id,
                entity_label=label,
                entity_source="PRO",
                confidence=1.0,
                evidence_type=EvidenceType.pro_match,
                match_description="Direct PRO ID lookup",
            )
        except Exception as e:
            logger.warning(f"PRO lookup failed for '{pro_id}': {e}")
            return None

    def _calculate_confidence(
        self,
        query: str,
        label: str,
        rank: int,
        prefer_human: bool,
    ) -> float:
        """Calculate match confidence.

        Args:
            query: Original search query.
            label: Matched label.
            rank: Position in search results.
            prefer_human: Whether to boost human-specific matches.

        Returns:
            Confidence score between 0 and 1.
        """
        query_lower = query.lower().strip()
        label_lower = label.lower().strip()

        # Base confidence from match quality
        if query_lower == label_lower:
            base = 0.95
        elif query_lower in label_lower:
            base = 0.80
        else:
            base = 0.55

        # Boost for human-specific
        if prefer_human and "(human)" in label_lower:
            base = min(1.0, base + 0.1)

        # Reduce confidence based on rank
        rank_penalty = rank * 0.03
        return max(0.3, base - rank_penalty)

    def is_protein_term(self, term_label: str) -> bool:
        """Check if a term label likely refers to a protein.

        Args:
            term_label: The term label to check.

        Returns:
            True if the term likely refers to a protein.
        """
        protein_indicators = [
            "enzyme",
            "protein",
            "kinase",
            "phosphatase",
            "transferase",
            "synthase",
            "synthetase",
            "oxidase",
            "reductase",
            "dehydrogenase",
            "hydrolase",
            "ligase",
            "lyase",
            "isomerase",
            "globulin",
            "immunoglobulin",
            "ig[a-m]",
            "albumin",
            "ferritin",
            "hemoglobin",
            "myoglobin",
            "troponin",
            "hormone",
            "cytokine",
            "receptor",
        ]

        label_lower = term_label.lower()
        for indicator in protein_indicators:
            if re.search(indicator, label_lower):
                return True

        return False
