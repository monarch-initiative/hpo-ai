"""Surgical EquivalentClasses editing of an OWL Functional Syntax edit file.

This is the *only* bespoke apply step (see ``issues/issue_kgcl_apply_patch.md``).
KGCL cannot express a nested genus-differentia class expression, so logical
axioms are added/replaced by a targeted single-line edit. ``robot convert`` is
expected to run afterward and re-canonicalise the inserted axiom.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_OBO = "http://purl.obolibrary.org/obo/"


def _iri(curie_or_iri: str) -> str:
    if curie_or_iri.startswith("http"):
        return curie_or_iri
    prefix, local = curie_or_iri.split(":", 1)
    return f"{_OBO}{prefix}_{local}"


@dataclass
class EqReport:
    """Outcome of an :meth:`EqEditor.apply` run."""

    added: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.replaced)


class EqEditor:
    """Add or replace ``EquivalentClasses`` axioms for specific terms."""

    def __init__(self, edit_path: str | Path) -> None:
        """Initialise.

        Args:
            edit_path: Path to the ``hp-edit.owl`` functional-syntax file.
        """
        self.edit_path = Path(edit_path)

    def apply(self, eq_by_id: dict[str, str], dry_run: bool = False) -> EqReport:
        """Add or replace EquivalentClasses axioms.

        Args:
            eq_by_id: Map of HP id/IRI to the new class-expression (the RHS of
                ``EquivalentClasses(<id> <expr>)``).
            dry_run: Compute the report without writing.

        Returns:
            An :class:`EqReport`.
        """
        report = EqReport()
        if not eq_by_id:
            return report

        targets = {_iri(k): v.strip() for k, v in eq_by_id.items()}
        lines = self.edit_path.read_text().splitlines(keepends=True)

        # Regex per target: the defining EquivalentClasses line and the label line.
        eq_res = {
            iri: re.compile(
                r"^EquivalentClasses\((?:Annotation\(.*?\)\s*)*<"
                + re.escape(iri)
                + r">\s+(?P<expr>.*)\)\s*$"
            )
            for iri in targets
        }
        label_res = {
            iri: re.compile(
                r"^AnnotationAssertion\(\s*(?:rdfs:label|<http://www\.w3\.org/2000/01/rdf-schema#label>)"
                r"\s+<" + re.escape(iri) + r">"
            )
            for iri in targets
        }

        out: list[str] = []
        replaced: set[str] = set()
        label_index: dict[str, int] = {}
        for line in lines:
            matched_iri = None
            matched = None
            if line.startswith("EquivalentClasses("):
                for iri in targets:
                    m = eq_res[iri].match(line)
                    if m:
                        matched_iri = iri
                        matched = m
                        break
            if matched_iri is not None and matched is not None:
                new_expr = targets[matched_iri]
                current = matched.group("expr").strip()
                if current == new_expr:
                    report.unchanged.append(matched_iri)
                    out.append(line)
                else:
                    # Overwrite by default (per policy), but flag the one case that
                    # silently reintroduces an unsatisfiable class: replacing a
                    # curator's role-based EQ ('has role' RO_0000087) with a direct
                    # filler. The reason gate is the backstop; this makes it visible.
                    if "RO_0000087" in current and "RO_0000087" not in new_expr:
                        logger.warning(
                            "Replacing role-based EQ for %s with a direct-filler form; "
                            "this may reintroduce an unsatisfiable class (run the reason gate)",
                            matched_iri,
                        )
                    out.append(f"EquivalentClasses(<{matched_iri}> {new_expr})\n")
                    report.replaced.append(matched_iri)
                replaced.add(matched_iri)
                continue
            # Track a label line index as an insertion anchor
            for iri in targets:
                if label_res[iri].match(line):
                    label_index[iri] = len(out)
            out.append(line)

        # Insert EQ for targets that had none, after their label line.
        to_insert = [
            iri for iri in targets
            if iri not in replaced and iri not in report.unchanged
        ]
        # Insert from the bottom up so earlier indices stay valid.
        for iri in sorted(to_insert, key=lambda i: label_index.get(i, -1), reverse=True):
            anchor = label_index.get(iri)
            if anchor is None:
                report.skipped.append(iri)
                logger.warning("No label/declaration found for %s; skipping EQ", iri)
                continue
            new_line = f"EquivalentClasses(<{iri}> {targets[iri]})\n"
            out.insert(anchor + 1, new_line)
            report.added.append(iri)

        if report.changed and not dry_run:
            self.edit_path.write_text("".join(out))
        return report
