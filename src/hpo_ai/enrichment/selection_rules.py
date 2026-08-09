"""CHEBI selection rules for deterministic chemical entity resolution.

This module provides a two-layer system for picking the correct CHEBI/PRO term:

1. **Curated mappings**: Known chemicals with a definitive correct CHEBI/PRO ID.
2. **Abbreviations**: Common clinical abbreviations mapped to entity IDs.

Rules are loaded from a YAML file (``conf/chebi_selection_rules.yaml``), replacing
the previously hardcoded dicts in ``chebi.py`` and the unused ``config.yaml`` entries.

A separate markdown selection guide (``conf/chebi_selection_guide.md``) provides
prose instructions for the LLM enricher when disambiguation is needed.

Example:
    >>> from pathlib import Path
    >>> rules = CHEBISelectionRules(
    ...     curated_mappings=[
    ...         CuratedMapping(
    ...             chemical_name="calcium",
    ...             chebi_id="CHEBI:22984",
    ...             chebi_label="calcium atom",
    ...         )
    ...     ],
    ...     abbreviations={
    ...         "LDL": AbbreviationMapping(
    ...             entity_id="CHEBI:47774",
    ...             entity_label="low-density lipoprotein cholesterol",
    ...         )
    ...     },
    ... )
    >>> sf = CHEBISelectionFilter(rules)
    >>> sf.resolve("calcium")
    ('CHEBI:22984', 'calcium atom', 'curated')
    >>> sf.resolve("LDL")
    ('CHEBI:47774', 'low-density lipoprotein cholesterol', 'abbreviation')
    >>> sf.resolve("unknownium") is None
    True
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CuratedMapping(BaseModel):
    """A curated mapping from a chemical name to a specific CHEBI ID.

    Used for known chemicals where there is one definitive correct answer.
    Aliases allow matching variant names (e.g. "Ca2+" → calcium atom).
    """

    chemical_name: str = Field(description="Canonical chemical name")
    chebi_id: str = Field(description="CHEBI identifier (e.g. CHEBI:22984)")
    chebi_label: str = Field(description="CHEBI label for this entity")
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative names that should resolve to this mapping",
    )
    rationale: str | None = Field(
        default=None,
        description="Why this CHEBI term was chosen over alternatives",
    )


class AbbreviationMapping(BaseModel):
    """A mapping from a clinical abbreviation to an entity ID.

    Supports both CHEBI and PRO identifiers.
    """

    entity_id: str = Field(description="CHEBI or PRO identifier")
    entity_label: str = Field(description="Full label for this entity")


class CHEBISelectionRules(BaseModel):
    """Container for all CHEBI selection rules.

    Loaded from ``conf/chebi_selection_rules.yaml``.
    """

    curated_mappings: list[CuratedMapping] = Field(default_factory=list)
    abbreviations: dict[str, AbbreviationMapping] = Field(default_factory=dict)


def load_chebi_selection_rules(path: Path) -> CHEBISelectionRules:
    """Load CHEBI selection rules from a YAML file.

    Args:
        path: Path to the YAML rules file.

    Returns:
        Parsed CHEBISelectionRules.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Rules file not found: {path}")

    raw = yaml.safe_load(path.read_text())
    if raw is None:
        return CHEBISelectionRules()

    return CHEBISelectionRules(**raw)


def load_selection_guide(path: Path) -> str:
    """Load the CHEBI selection guide markdown.

    Args:
        path: Path to the markdown guide file.

    Returns:
        Guide content as a string.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Selection guide not found: {path}")
    return path.read_text()


class CHEBISelectionFilter:
    """Lookup engine for CHEBI selection rules.

    Provides fast deterministic lookups for abbreviations and curated
    mappings before falling through to OAK search.

    Example:
        >>> rules = CHEBISelectionRules(
        ...     abbreviations={
        ...         "LDL": AbbreviationMapping(
        ...             entity_id="CHEBI:47774",
        ...             entity_label="low-density lipoprotein cholesterol",
        ...         ),
        ...     },
        ... )
        >>> sf = CHEBISelectionFilter(rules)
        >>> sf.lookup_abbreviation("LDL").entity_id
        'CHEBI:47774'
        >>> sf.lookup_abbreviation("unknown") is None
        True
    """

    def __init__(self, rules: CHEBISelectionRules) -> None:
        """Initialize the filter with parsed rules.

        Args:
            rules: Parsed CHEBISelectionRules from YAML.
        """
        self.rules = rules
        # Build case-insensitive abbreviation index
        self._abbrev_index: dict[str, AbbreviationMapping] = {
            k.upper(): v for k, v in rules.abbreviations.items()
        }
        # Build case-insensitive curated mapping indices
        self._name_index: dict[str, CuratedMapping] = {}
        self._alias_index: dict[str, CuratedMapping] = {}
        for mapping in rules.curated_mappings:
            self._name_index[mapping.chemical_name.lower()] = mapping
            for alias in mapping.aliases:
                self._alias_index[alias.lower()] = mapping

    def lookup_abbreviation(self, name: str) -> AbbreviationMapping | None:
        """Look up a clinical abbreviation.

        Args:
            name: Potential abbreviation (e.g. "LDL", "CK").

        Returns:
            AbbreviationMapping if found, None otherwise.
        """
        return self._abbrev_index.get(name.upper().strip())

    def lookup_curated(self, name: str) -> CuratedMapping | None:
        """Look up a curated chemical mapping by name or alias.

        Args:
            name: Chemical name or alias (e.g. "calcium", "Ca2+").

        Returns:
            CuratedMapping if found, None otherwise.
        """
        key = name.lower().strip()
        result = self._name_index.get(key)
        if result is not None:
            return result
        return self._alias_index.get(key)

    def resolve(
        self, name: str
    ) -> tuple[str, str, str] | None:
        """Resolve a chemical name using rules (abbreviation, then curated).

        Resolution order:
        1. Abbreviation lookup
        2. Curated mapping lookup (exact name, then aliases)

        Args:
            name: Chemical name or abbreviation.

        Returns:
            Tuple of (entity_id, entity_label, match_type) or None.
            match_type is "abbreviation" or "curated".
        """
        # 1. Abbreviation
        abbrev = self.lookup_abbreviation(name)
        if abbrev is not None:
            return abbrev.entity_id, abbrev.entity_label, "abbreviation"

        # 2. Curated mapping
        curated = self.lookup_curated(name)
        if curated is not None:
            return curated.chebi_id, curated.chebi_label, "curated"

        return None
