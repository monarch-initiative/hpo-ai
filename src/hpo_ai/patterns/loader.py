"""Load simplified DOSDP-like patterns from a directory of YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml

from hpo_ai.datamodel.pattern import Pattern, Var


def _normalize_vars(raw: object) -> list[dict]:
    """Normalize an authored ``vars`` block into a list of Var dicts.

    Patterns may author ``vars`` as a mapping keyed by variable name
    (the ergonomic form) or as a list. Both normalize to a list of dicts
    each carrying an explicit ``name``.

    >>> _normalize_vars({"chemical": {"range": "CHEBI:24431", "allow_string": True}})
    [{'range': 'CHEBI:24431', 'allow_string': True, 'name': 'chemical'}]
    >>> _normalize_vars([{"name": "chemical", "range": "CHEBI:24431"}])
    [{'name': 'chemical', 'range': 'CHEBI:24431'}]
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        out = []
        for name, spec in raw.items():
            spec = dict(spec or {})
            spec["name"] = name
            out.append(spec)
        return out
    if isinstance(raw, list):
        return list(raw)
    raise TypeError(f"'vars' must be a mapping or list, got {type(raw).__name__}")


def load_pattern_file(path: str | Path) -> Pattern:
    """Load and validate a single pattern YAML file.

    Args:
        path: Path to a pattern ``.yaml`` file.

    Returns:
        The validated :class:`Pattern`.
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    data["vars"] = _normalize_vars(data.get("vars"))
    return Pattern(**data)


def load_patterns(pattern_dir: str | Path) -> list[Pattern]:
    """Load every ``.yaml`` pattern in a directory.

    Args:
        pattern_dir: Directory containing pattern files.

    Returns:
        Patterns sorted by id.
    """
    pattern_dir = Path(pattern_dir)
    patterns = [
        load_pattern_file(p)
        for p in sorted(pattern_dir.glob("*.yaml"))
    ]
    return sorted(patterns, key=lambda p: p.id)


def var_by_name(pattern: Pattern, name: str) -> Var | None:
    """Return the pattern variable with the given name, or None.

    >>> from hpo_ai.datamodel.pattern import Pattern, Selector, Var
    >>> p = Pattern(id="x", selector=Selector(direction="increased"), name="{chemical}",
    ...             vars=[Var(name="chemical", range="CHEBI:24431")])
    >>> var_by_name(p, "chemical").range
    'CHEBI:24431'
    >>> var_by_name(p, "missing") is None
    True
    """
    for v in pattern.vars or []:
        if v.name == name:
            return v
    return None
