#!/usr/bin/env python3
"""Extract a regression corpus from merged 'metabolism refactor' PRs.

For each PR we take the unified diff of ``src/ontology/hp-edit.owl`` and, per
HP term, capture the *before* label (the pipeline input) and the *after* state
the curators produced (label, definition, exact synonyms, EquivalentClasses).
The after-state is the golden oracle our pipeline is measured against.

Output: ``tests/corpus/pr<N>.tsv`` per PR and a combined ``tests/corpus/corpus.tsv``.
Run: ``uv run python scripts/extract_corpus.py``
"""

from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

REPO = "obophenotype/human-phenotype-ontology"
PRS = [11616, 11488, 11466, 11457, 11380]
EDIT_FILE = "src/ontology/hp-edit.owl"
_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = _ROOT / "tests" / "corpus"
CLONE_EDIT = _ROOT / "github" / "human-phenotype-ontology" / "src" / "ontology" / "hp-edit.owl"

_HP = r"http://purl\.obolibrary\.org/obo/HP_\d+"
LABEL_RE = re.compile(rf'AnnotationAssertion\(rdfs:label <({_HP})> "((?:[^"\\]|\\.)*)"')
DEF_RE = re.compile(rf'IAO_0000115> <({_HP})> "((?:[^"\\]|\\.)*)"')
SYN_RE = re.compile(rf'has(?:Exact|Related|Broad|Narrow)Synonym> <({_HP})> "((?:[^"\\]|\\.)*)"')
EQ_RE = re.compile(rf"EquivalentClasses\(<({_HP})> (.*)\)\s*$")
# CHEBI ids are numeric; PRO protein ids are UniProt-style (PR_P07288).
CHEM_RE = re.compile(r"(?:CHEBI_\d+|PRO?_[A-Za-z0-9]+)")
ROLE_MARK = "RO_0000087"  # has_role


def load_clone_labels() -> dict[str, str]:
    """Map ``HP:xxxxxxx -> current label`` from the local clone's hp-edit.owl."""
    labels: dict[str, str] = {}
    if not CLONE_EDIT.exists():
        return labels
    for line in CLONE_EDIT.read_text().splitlines():
        m = LABEL_RE.search(line)
        if m:
            labels[_iri_to_curie(m.group(1))] = m.group(2)
    return labels


def _iri_to_curie(iri: str) -> str:
    return iri.rsplit("/", 1)[-1].replace("_", ":", 1)


def _diff(pr: int) -> str:
    return subprocess.run(
        ["gh", "pr", "diff", str(pr), "--repo", REPO],
        capture_output=True, text=True, check=True,
    ).stdout


def _hp_edit_lines(diff: str) -> list[str]:
    """Yield diff body lines that belong to the hp-edit.owl file section."""
    out: list[str] = []
    in_file = False
    for line in diff.splitlines():
        if line.startswith("diff --git") or line.startswith("+++ ") or line.startswith("--- "):
            if line.startswith("diff --git"):
                in_file = EDIT_FILE in line
            continue
        if line.startswith("@@"):
            continue
        if in_file:
            out.append(line)
    return out


def _first_chem(eq: str) -> tuple[str, bool]:
    """Return (chemical curie, is_role) from an EQ expression."""
    is_role = ROLE_MARK in eq
    if is_role:
        # role filler: the chemical is the has_role target, i.e. the id that is
        # NOT CHEBI:24431 ('chemical entity' genus).
        for m in CHEM_RE.finditer(eq):
            if m.group(0) != "CHEBI_24431":
                return _iri_to_curie(f"obo/{m.group(0)}"), True
        return "", True
    m = CHEM_RE.search(eq)
    return (_iri_to_curie(f"obo/{m.group(0)}"), False) if m else ("", False)


def extract_pr(pr: int) -> dict[str, dict]:
    """Parse one PR into ``{hp_id: record}``."""
    records: dict[str, dict] = {}

    def rec(iri: str) -> dict:
        cid = _iri_to_curie(iri)
        return records.setdefault(cid, {
            "pr": pr, "hp_id": cid, "before_label": "", "after_label": "",
            "after_definition": "", "after_synonyms": [], "after_eq": "",
            "after_chemical": "", "is_role": False,
        })

    for line in _hp_edit_lines(_diff(pr)):
        if not line or line[0] not in "+-":
            continue
        added = line[0] == "+"
        body = line[1:]

        m = LABEL_RE.search(body)
        if m:
            rec(m.group(1))["after_label" if added else "before_label"] = m.group(2)
            continue
        if not added:
            continue  # for def/syn/eq we only care about the after-state
        m = DEF_RE.search(body)
        if m:
            rec(m.group(1))["after_definition"] = m.group(2)
            continue
        m = SYN_RE.search(body)
        if m:
            rec(m.group(1))["after_synonyms"].append(m.group(2))
            continue
        m = EQ_RE.search(body)
        if m:
            r = rec(m.group(1))
            r["after_eq"] = m.group(2).strip()
            r["after_chemical"], r["is_role"] = _first_chem(m.group(2))
    return records


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    clone_labels = load_clone_labels()
    cols = ["pr", "hp_id", "before_label", "after_label", "after_definition",
            "after_synonyms", "after_eq", "after_chemical", "is_role", "label_changed"]
    combined: list[dict] = []
    for pr in PRS:
        recs = extract_pr(pr)
        rows = []
        for r in recs.values():
            row = dict(r)
            row["after_synonyms"] = " | ".join(r["after_synonyms"])
            row["is_role"] = str(r["is_role"])
            label_changed = bool(r["before_label"] and r["after_label"]
                                 and r["before_label"] != r["after_label"])
            # When the PR left the label untouched (no -/+ label line), the
            # before and after label both equal the current clone label. This
            # lets EQ-only terms carry their label as pipeline input.
            if not r["before_label"] and not r["after_label"]:
                current = clone_labels.get(r["hp_id"], "")
                row["before_label"] = current
                row["after_label"] = current
            row["label_changed"] = str(label_changed)
            # Obsolete terms are never curation inputs; drop them.
            if row["before_label"].lower().startswith("obsolete"):
                continue
            # A row is testable only if we have an input label AND a golden signal.
            if row["before_label"] and (row["after_label"] or row["after_eq"]
                                        or row["after_definition"]):
                rows.append(row)
        rows.sort(key=lambda x: x["hp_id"])
        with open(OUT_DIR / f"pr{pr}.tsv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t")
            w.writeheader()
            w.writerows(rows)
        combined.extend(rows)
        n_eq = sum(1 for r in rows if r["after_eq"])
        n_role = sum(1 for r in rows if r["is_role"] == "True")
        n_relabel = sum(1 for r in rows if r["before_label"] and r["after_label"]
                        and r["before_label"] != r["after_label"])
        print(f"PR {pr}: {len(rows)} terms | {n_eq} with EQ | {n_role} role | "
              f"{n_relabel} relabelled")

    combined.sort(key=lambda x: (x["pr"], x["hp_id"]))
    with open(OUT_DIR / "corpus.tsv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t")
        w.writeheader()
        w.writerows(combined)
    print(f"TOTAL: {len(combined)} term-records -> {OUT_DIR / 'corpus.tsv'}")


if __name__ == "__main__":
    main()
