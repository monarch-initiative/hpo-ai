"""Name normalization for chemical / protein entity labels.

Replicates the SPARQL-based label rewriting rules from the HPO build
(``src/sparql/update-chemical-labels.ru``) so that PRO entity labels
like ``"DnaJ homolog subfamily B member 9 (human)"`` become
``"DNAJB9"`` before template insertion.

Rules are loaded from a YAML configuration file so they can be updated
without changing code.

Example
-------
>>> from hpo_ai.enrichment.name_normalizer import (
...     NameNormalizer,
...     load_name_normalization_rules,
... )
>>> rules = load_name_normalization_rules(
...     "conf/name_normalization_rules.yaml"
... )
>>> normalizer = NameNormalizer(rules)
>>> normalizer.normalize("DnaJ homolog subfamily B member 9 (human)")
'DNAJB9'
>>> normalizer.normalize("calcium atom")
'calcium'
>>> normalizer.normalize("galectin-3")
'galectin-3'
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel

# Enzyme-activity rule (ported from update-chemical-labels.ru): an enzyme is
# measured as *activity*, not concentration. Trigger on a word ending in "-ase"
# or a known protease that does not follow the "-ase" convention...
_ENZYME_RE = re.compile(
    r"\w+ase\b|\b(?:thrombin|plasmin|trypsin|chymotrypsin|pepsin|renin|kallikrein)\b",
    re.IGNORECASE,
)
# ...but exclude zymogens/inhibitors that match the pattern yet are not enzymes,
# and "-base" words (nucleobase, Schiff base) that match "\w+ase" spuriously.
_ENZYME_EXCLUDE_RE = re.compile(
    r"\b(?:alpha-1-antitrypsin|antitrypsin|plasminogen|trypsinogen"
    r"|chymotrypsinogen|pepsinogen)\b|base\b",
    re.IGNORECASE,
)


def is_enzyme_activity(name: str) -> bool:
    """Return True if a chemical name denotes an enzyme measured as activity.

    Mirrors the enzyme rule in ``update-chemical-labels.ru``: an ``-ase`` word
    (or a known protease) implies the phenotype is about catalytic *activity*
    rather than concentration, excluding zymogens/inhibitors and ``-base`` words.

    >>> is_enzyme_activity("creatine kinase")
    True
    >>> is_enzyme_activity("beta-hexosaminidase")
    True
    >>> is_enzyme_activity("thrombin")
    True
    >>> is_enzyme_activity("trypsinogen")
    False
    >>> is_enzyme_activity("nucleobase")
    False
    >>> is_enzyme_activity("fetuin-A")
    False
    """
    return bool(_ENZYME_RE.search(name)) and not _ENZYME_EXCLUDE_RE.search(name)


class GenericCleanup(BaseModel):
    """A regex-based cleanup rule.

    Attributes:
        pattern: Regex pattern to match (e.g. ``" atom$"``).
        replacement: Replacement string (usually ``""``).
    """

    pattern: str
    replacement: str


class SpecificRename(BaseModel):
    """A literal substring replacement.

    Attributes:
        old: Substring to find.
        new: Replacement string.
    """

    old: str
    new: str


class NameNormalizationRules(BaseModel):
    """Container for all normalization rules.

    Attributes:
        generic_cleanups: Regex-based cleanups applied first.
        specific_renames: Literal substring replacements applied second.
    """

    generic_cleanups: list[GenericCleanup]
    specific_renames: list[SpecificRename]


def load_name_normalization_rules(path: str | Path) -> NameNormalizationRules:
    """Load normalization rules from a YAML file.

    Args:
        path: Path to the YAML rules file.

    Returns:
        Parsed ``NameNormalizationRules``.

    Example
    -------
    >>> rules = load_name_normalization_rules(
    ...     "conf/name_normalization_rules.yaml"
    ... )
    >>> len(rules.generic_cleanups)
    19
    >>> len(rules.specific_renames)
    15
    """
    with open(path) as fh:
        data = yaml.safe_load(fh)
    return NameNormalizationRules(**data)


class NameNormalizer:
    """Apply sequential name normalization rules to entity labels.

    Generic cleanups (regex) run first, then specific renames (literal
    substring replacement), mirroring the order in the HPO SPARQL update.

    Args:
        rules: The normalization rules to apply.

    Example
    -------
    >>> from hpo_ai.enrichment.name_normalizer import (
    ...     NameNormalizer,
    ...     load_name_normalization_rules,
    ... )
    >>> rules = load_name_normalization_rules(
    ...     "conf/name_normalization_rules.yaml"
    ... )
    >>> n = NameNormalizer(rules)
    >>> n.normalize("serotransferrin (human)")
    'transferrin'
    >>> n.normalize("creatine kinase B-type (human)")
    'creatine kinase BB isoform'
    """

    def __init__(self, rules: NameNormalizationRules) -> None:
        """Initialize with normalization rules."""
        self._rules = rules

    def normalize(self, label: str) -> str:
        """Normalize an entity label by applying all rules in order.

        Args:
            label: The raw entity label.

        Returns:
            The normalized label.

        Example
        -------
        >>> from hpo_ai.enrichment.name_normalizer import (
        ...     NameNormalizer,
        ...     load_name_normalization_rules,
        ... )
        >>> rules = load_name_normalization_rules(
        ...     "conf/name_normalization_rules.yaml"
        ... )
        >>> n = NameNormalizer(rules)
        >>> n.normalize("72 kDa type IV collagenase (human)")
        'matrix metalloproteinase 2'
        """
        result = label

        # Phase 1: generic regex cleanups
        for cleanup in self._rules.generic_cleanups:
            result = re.sub(cleanup.pattern, cleanup.replacement, result)

        # Phase 2: specific literal renames
        for rename in self._rules.specific_renames:
            result = result.replace(rename.old, rename.new)

        return result
