"""Run the pattern-driven pipeline over the PR-derived corpus, offline.

The corpus (``tests/corpus/corpus.tsv``) records, per HP term, the *before*
label (pipeline input) and the curator's *after* state (golden label / EQ).

To stay fast and deterministic we do NOT hit OAK: label/definition generation
uses the extracted chemical *string* (no resolver needed), and EQ generation is
exercised by injecting the golden chemical id via a stub resolver. This isolates
two independent questions:

* can we reproduce the curator's **label**? (string extraction + templating)
* given the right chemical, can we build the curator's **EQ**? (axiom template)

``run_corpus`` returns a list of :class:`CorpusResult`, one per row, each tagged
with a failure ``category`` so failure modes can be triaged and fixed one by one.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from hpo_ai.associate.deterministic import DeterministicAssociator
from hpo_ai.associate.models import Association, Unmapped
from hpo_ai.datamodel import ChemicalEntityEvidence, EvidenceType, HPTerm
from hpo_ai.generate.materialize import materialize
from hpo_ai.patterns.loader import load_patterns

_ROOT = Path(__file__).resolve().parents[1]
CORPUS = Path(__file__).parent / "corpus" / "corpus.tsv"
PATTERN_DIR = _ROOT / "patterns"


class _StubResolver:
    """Resolve any name to a fixed golden chemical id (no OAK)."""

    def __init__(self, chem_curie: str, is_role: bool) -> None:
        self._chem = chem_curie
        self._is_role = is_role

    def resolve(self, name: str, max_results: int = 5) -> list[ChemicalEntityEvidence]:
        if not self._chem:
            return []
        source = "CHEBI" if self._chem.startswith("CHEBI") else "PRO"
        return [ChemicalEntityEvidence(
            id="ev", entity_id=self._chem, entity_label=name, entity_source=source,
            confidence=1.0, evidence_type=EvidenceType.chebi_match,
        )]

    def is_role(self, chebi_id: str) -> bool:
        return self._is_role


def _norm(expr: str) -> str:
    """Collapse whitespace for structural EQ comparison."""
    return re.sub(r"\s+", " ", expr).strip()


@dataclass
class CorpusResult:
    hp_id: str
    pr: str
    before_label: str
    after_label: str
    proposed_label: str
    label_match: bool
    eq_expected: bool
    eq_match: bool
    unmapped_reason: str
    category: str


def load_rows() -> list[dict[str, str]]:
    with open(CORPUS) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _categorize(
    row: dict[str, str],
    assoc: Association | Unmapped,
    proposed_label: str,
    label_match: bool,
    eq_expected: bool,
    eq_match: bool,
) -> str:
    """Bucket a row into a failure mode (or 'pass')."""
    if isinstance(assoc, Unmapped):
        if assoc.reason.value == "no_chemical":
            return "unmapped:opaque_clinical"  # needs the agentic clinical tier
        return f"unmapped:{assoc.reason.value}"
    if label_match and (not eq_expected or eq_match):
        return "pass"
    problems = []
    if not label_match:
        problems.append(_label_failure_mode(row["after_label"], proposed_label))
    if eq_expected and not eq_match:
        problems.append("eq_structure")
    return "fail:" + "+".join(problems)


def _label_failure_mode(want: str, got: str) -> str:
    """Sub-classify a label mismatch into an actionable failure mode."""
    if not want or not got:
        return "label_text"
    if want.lower() == got.lower():
        return "label_case"
    # Enzyme phenotypes: curator says '... activity', we say '... concentration'.
    if want.endswith("activity") and got.endswith("concentration"):
        return "enzyme_activity"
    # Hyphen/space or roman/arabic numeral differences = name normalisation.
    squash = lambda s: re.sub(r"[\s\-]+", "", s.lower())  # noqa: E731
    if squash(want) == squash(got):
        return "name_hyphenation"
    # We dropped a name component the curator kept (e.g. 'serum amyloid A' -> 'amyloid A').
    if got.replace(" concentration", "") in want or _dropped_component(want, got):
        return "name_component_dropped"
    return "name_normalization"


def _dropped_component(want: str, got: str) -> bool:
    """True when our label is missing leading words present in the golden."""
    w = set(re.findall(r"[a-z0-9]+", want.lower()))
    g = set(re.findall(r"[a-z0-9]+", got.lower()))
    return bool(w - g) and not (g - w)


def run_corpus(rows: list[dict[str, str]] | None = None) -> list[CorpusResult]:
    """Run the offline pipeline over every corpus row."""
    if rows is None:
        rows = load_rows()
    patterns = load_patterns(str(PATTERN_DIR))
    results: list[CorpusResult] = []

    for row in rows:
        chem = row["after_chemical"]
        is_role = row["is_role"] == "True"
        resolver = _StubResolver(chem, is_role)
        # Route CHEBI to chebi_resolver, PRO to pro_resolver (mirrors production).
        chebi_r = resolver if chem.startswith("CHEBI") else None
        pro_r = resolver if chem.startswith(("PR", "PRO")) else None
        associator = DeterministicAssociator(
            patterns, chebi_resolver=chebi_r, pro_resolver=pro_r,
        )
        term = HPTerm(id=row["hp_id"], label=row["before_label"])
        assoc = associator.associate(term)

        proposed_label = ""
        eq_expected = bool(row["after_eq"])
        eq_match = False
        label_match = False
        unmapped_reason = ""
        if isinstance(assoc, Unmapped):
            unmapped_reason = assoc.reason.value
        else:
            # NB: the name normaliser is deliberately NOT applied here. The
            # corpus inputs are already human-normalised labels and the golden
            # partly predates the current update-chemical-labels.ru, so scoring
            # through the normaliser conflates association accuracy with a
            # production-only naming concern (see docs/corpus-failure-modes.md).
            proposal = materialize(term, assoc)
            proposed_label = proposal.proposed_label or ""
            label_match = bool(row["after_label"]) and proposed_label == row["after_label"]
            if eq_expected:
                eq_match = _norm(proposal.proposed_logical_definition or "") == _norm(row["after_eq"])

        category = _categorize(row, assoc, proposed_label, label_match, eq_expected, eq_match)
        results.append(CorpusResult(
            hp_id=row["hp_id"], pr=row["pr"], before_label=row["before_label"],
            after_label=row["after_label"], proposed_label=proposed_label,
            label_match=label_match, eq_expected=eq_expected, eq_match=eq_match,
            unmapped_reason=unmapped_reason, category=category,
        ))
    return results
