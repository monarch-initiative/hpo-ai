"""Extract candidate chemical phenotypes from HPO using OAK."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from oaklib import get_adapter
from oaklib.datamodels.vocabulary import IS_A

from hpo_ai.datamodel import HPTerm, Synonym, SynonymScope

if TYPE_CHECKING:
    from oaklib.interfaces import OboGraphInterface

logger = logging.getLogger(__name__)

# Keywords that indicate a chemical/concentration phenotype
CHEMICAL_KEYWORDS = [
    "concentration",
    "level",
    "circulating",
    "blood",
    "serum",
    "plasma",
    "urine",
    "urinary",
    "csf",
    "cerebrospinal",
    "-emia",
    "-uria",
    "hyper",
    "hypo",
    "increased",
    "decreased",
    "elevated",
    "reduced",
    "abnormal",
]

# Root terms for chemical phenotypes in HPO
CHEMICAL_PHENOTYPE_ROOTS = [
    "HP:0001939",  # Abnormality of metabolism/homeostasis
    "HP:0032180",  # Abnormal circulating metabolite concentration
    "HP:0003111",  # Abnormal blood ion concentration
    "HP:0003112",  # Abnormal circulating amino acid concentration
]


class HPOExtractor:
    """Extract candidate chemical phenotypes from HPO."""

    def __init__(
        self,
        hpo_path: str | None = None,
        adapter: OboGraphInterface | None = None,
    ) -> None:
        """Initialize the extractor.

        Args:
            hpo_path: Path to HPO OWL/OBO file, or OAK selector (e.g., "sqlite:obo:hp").
            adapter: Pre-configured OAK adapter (takes precedence over hpo_path).
        """
        if adapter is not None:
            self.adapter = adapter
        elif hpo_path:
            self.adapter = get_adapter(hpo_path)
        else:
            # Default to using the OBO sqlite version
            self.adapter = get_adapter("sqlite:obo:hp")

    def extract_all_descendants(
        self,
        root_id: str = "HP:0001939",
    ) -> list[HPTerm]:
        """Extract all descendants of a root term.

        Args:
            root_id: Root HP term ID to start from.

        Returns:
            List of HPTerm objects.
        """
        terms = []
        descendants = list(self.adapter.descendants(root_id, predicates=[IS_A]))

        for hp_id in descendants:
            term = self._extract_term(hp_id)
            if term:
                terms.append(term)

        logger.info(f"Extracted {len(terms)} terms from {root_id}")
        return terms

    def extract_chemical_phenotypes(
        self,
        root_ids: list[str] | None = None,
        filter_keywords: bool = True,
    ) -> list[HPTerm]:
        """Extract chemical phenotype candidates.

        Args:
            root_ids: Root term IDs to search under. Defaults to CHEMICAL_PHENOTYPE_ROOTS.
            filter_keywords: Whether to filter by chemical keywords.

        Returns:
            List of HPTerm objects that are chemical phenotype candidates.
        """
        if root_ids is None:
            root_ids = CHEMICAL_PHENOTYPE_ROOTS

        all_terms = []
        seen_ids = set()

        for root_id in root_ids:
            terms = self.extract_all_descendants(root_id)
            for term in terms:
                if term.id not in seen_ids:
                    seen_ids.add(term.id)
                    if not filter_keywords or self._is_chemical_phenotype(term):
                        all_terms.append(term)

        logger.info(f"Found {len(all_terms)} chemical phenotype candidates")
        return all_terms

    def extract_term(self, hp_id: str) -> HPTerm | None:
        """Extract a single HP term by ID.

        Args:
            hp_id: HP term identifier.

        Returns:
            HPTerm object or None if not found.
        """
        return self._extract_term(hp_id)

    def _extract_term(self, hp_id: str) -> HPTerm | None:
        """Internal method to extract a term."""
        label = self.adapter.label(hp_id)
        if not label:
            return None

        definition = self.adapter.definition(hp_id)

        # Get synonyms
        synonyms = []
        for syn in self.adapter.entity_aliases(hp_id):
            if syn != label:
                synonyms.append(
                    Synonym(
                        value=syn,
                        scope=SynonymScope.exact,
                    )
                )

        # Get parents
        parents = list(self.adapter.hierarchical_parents(hp_id))

        # Get existing logical definition components
        existing_chemical = None
        existing_location = None
        existing_logical_def = None

        # Try to extract from logical definitions if available
        try:
            for ldef in self.adapter.logical_definitions(hp_id):
                existing_logical_def = str(ldef)
                for genus in ldef.genusIds or []:
                    if genus.startswith("CHEBI:") or genus.startswith("PR:"):
                        existing_chemical = genus
                for restriction in ldef.restrictions or []:
                    filler = restriction.fillerId
                    if filler and filler.startswith("UBERON:"):
                        existing_location = filler
        except Exception:
            # Logical definitions may not be available
            pass

        return HPTerm(
            id=hp_id,
            label=label,
            definition=definition,
            synonyms=synonyms if synonyms else None,
            parents=parents if parents else None,
            existing_chemical_entity=existing_chemical,
            existing_location=existing_location,
            existing_logical_definition=existing_logical_def,
        )

    def _is_chemical_phenotype(self, term: HPTerm) -> bool:
        """Check if a term appears to be a chemical phenotype.

        Args:
            term: HPTerm to check.

        Returns:
            True if term appears to be a chemical phenotype.
        """
        text = (term.label or "").lower()
        if term.definition:
            text += " " + term.definition.lower()

        for keyword in CHEMICAL_KEYWORDS:
            if keyword in text:
                return True

        # Check for common patterns
        patterns = [
            r"hyper\w+emia",
            r"hypo\w+emia",
            r"\w+uria",
            r"(increased|decreased|elevated|reduced|abnormal).*(level|concentration)",
        ]

        for pattern in patterns:
            if re.search(pattern, text):
                return True

        return False

    def extract_from_tsv(
        self,
        tsv_path: str,
        id_column: str = "hpo_id",
    ) -> list[HPTerm]:
        """Extract terms listed in a TSV file.

        Args:
            tsv_path: Path to TSV file with HP IDs.
            id_column: Column name containing HP IDs.

        Returns:
            List of HPTerm objects.
        """
        import csv

        terms = []

        with open(tsv_path) as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                hp_id = row.get(id_column)
                if hp_id:
                    term = self._extract_term(hp_id)
                    if term:
                        terms.append(term)

        logger.info(f"Extracted {len(terms)} terms from {tsv_path}")
        return terms
