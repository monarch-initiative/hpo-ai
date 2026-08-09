"""Workflow B: apply a curate patch bundle to hp-edit.owl (the stop-gap path).

Order of operations:
1. surgical EquivalentClasses edits from ``axioms.ofn`` (the only bespoke step);
2. ``robot query --update update.ru`` for label/synonym/definition changes,
   which also re-serialises (canonicalises) the EQ edits from step 1.

See ``issues/issue_kgcl_apply_patch.md`` for the intended upstream replacement.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hpo_ai.apply.eq_editor import EqEditor, EqReport

logger = logging.getLogger(__name__)

_EQ_LINE_RE = re.compile(r"^EquivalentClasses\(<(?P<iri>[^>]+)>\s+(?P<expr>.*)\)\s*$")


@dataclass
class ApplyReport:
    """Outcome of applying a patch bundle."""

    eq: EqReport
    sparql_applied: bool
    output: Path


def parse_axioms_ofn(text: str) -> dict[str, str]:
    """Parse an ``axioms.ofn`` bundle file into ``{iri: class_expression}``.

    >>> parse_axioms_ofn("EquivalentClasses(<http://x/HP_1> ObjectSomeValuesFrom(<a> <b>))")
    {'http://x/HP_1': 'ObjectSomeValuesFrom(<a> <b>)'}
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _EQ_LINE_RE.match(line)
        if m:
            out[m.group("iri")] = m.group("expr").strip()
    return out


def apply_patch_bundle(
    bundle_dir: str | Path,
    hpo_path: str | Path,
    robot: str = "/Users/matentzn/tools/robot",
    catalog: str | Path | None = None,
) -> ApplyReport:
    """Apply a curate bundle to an hp-edit.owl in place.

    Args:
        bundle_dir: Directory holding ``axioms.ofn`` and ``update.ru``.
        hpo_path: Path to the hp-edit.owl to modify.
        robot: Path to the ROBOT executable.
        catalog: Optional catalog file for import resolution.

    Returns:
        An :class:`ApplyReport`.
    """
    bundle_dir = Path(bundle_dir)
    hpo_path = Path(hpo_path)

    # Step 1: surgical EQ edits
    eq_by_id = parse_axioms_ofn((bundle_dir / "axioms.ofn").read_text()) \
        if (bundle_dir / "axioms.ofn").exists() else {}
    eq_report = EqEditor(hpo_path).apply(eq_by_id)

    # Step 2: robot query --update (applies annotations, canonicalises EQ)
    update_ru = bundle_dir / "update.ru"
    sparql_applied = False
    if update_ru.exists() and "no annotation-level changes" not in update_ru.read_text():
        cmd = [robot, "query"]
        if catalog:
            cmd += ["--catalog", str(catalog)]
        cmd += ["--input", str(hpo_path), "--update", str(update_ru),
                "--format", "ofn", "--output", str(hpo_path)]
        subprocess.run(cmd, check=True, capture_output=True)
        sparql_applied = True
    elif eq_report.changed and catalog is not None:
        # Canonicalise the EQ-only edit via convert.
        cmd = [robot, "convert", "--catalog", str(catalog),
               "--input", str(hpo_path), "--format", "ofn", "--output", str(hpo_path)]
        subprocess.run(cmd, check=True, capture_output=True)

    logger.info("Applied bundle: EQ added=%d replaced=%d; sparql=%s",
                len(eq_report.added), len(eq_report.replaced), sparql_applied)
    return ApplyReport(eq=eq_report, sparql_applied=sparql_applied, output=hpo_path)
