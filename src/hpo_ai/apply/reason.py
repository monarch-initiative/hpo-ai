"""Satisfiability gate for an applied hp-edit.owl.

Role/EQ regressions (e.g. a CHEBI *role* used as a direct genus) are invisible
in ``review.tsv`` and in OAK/diff review; they surface only at reasoning time.
This module wraps ``robot reason`` so an apply run (or CI) can fail loudly when
it introduces unsatisfiable classes.

See ``issues/issue_role_based_patterns.md``.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ROBOT reason reports each unsatisfiable class on a line like:
#   ERROR unsatisfiable: http://purl.obolibrary.org/obo/HP_0001234
_UNSAT_RE = re.compile(
    r"unsatisfiable:\s*<?(?P<iri>https?://\S+?)>?\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def parse_unsatisfiable(robot_output: str) -> list[str]:
    """Extract unsatisfiable class IRIs from ROBOT reason output.

    >>> parse_unsatisfiable("ERROR unsatisfiable: http://purl.obolibrary.org/obo/HP_1")
    ['http://purl.obolibrary.org/obo/HP_1']
    >>> parse_unsatisfiable("all good") == []
    True
    """
    return _UNSAT_RE.findall(robot_output)


def check_satisfiability(
    hpo_path: str | Path,
    robot: str = "/Users/matentzn/tools/robot",
    catalog: str | Path | None = None,
    reasoner: str = "ELK",
) -> list[str]:
    """Run ``robot reason`` and return the list of unsatisfiable class IRIs.

    An empty list means the ontology is coherent. A non-empty list is the set of
    classes that could not be satisfied (a role filler used as a direct genus is
    the canonical cause here).

    Args:
        hpo_path: Path to the ontology to check.
        robot: Path to the ROBOT executable.
        catalog: Optional catalog file for import resolution.
        reasoner: Reasoner name passed to ROBOT.

    Returns:
        Unsatisfiable class IRIs (empty if satisfiable).

    Raises:
        RuntimeError: If ROBOT fails for a reason other than unsatisfiability.
    """
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "reasoned.owl"
        cmd = [robot, "reason", "--reasoner", reasoner]
        if catalog:
            cmd += ["--catalog", str(catalog)]
        cmd += ["--input", str(hpo_path), "--output", str(out)]
        result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        return []
    combined = f"{result.stdout}\n{result.stderr}"
    unsat = parse_unsatisfiable(combined)
    if not unsat:
        raise RuntimeError(
            f"robot reason failed (exit {result.returncode}) with no parseable "
            f"unsatisfiable classes:\n{combined.strip()}"
        )
    logger.warning("Ontology has %d unsatisfiable classes", len(unsat))
    return unsat
