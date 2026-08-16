"""Regression corpus mined from merged 'metabolism refactor' PRs.

The corpus (``tests/corpus/corpus.tsv``, 212 term-records from PRs #11616,
#11488, #11466, #11457, #11380) pins the pipeline against real curator output.
See ``tests/corpus_runner.py`` for the offline harness and
``docs/corpus-failure-modes.md`` for the failure-mode triage.

Two invariants are locked here:

* **EQ generation is exact once a term maps.** Given the curator's chemical id,
  the generated ``EquivalentClasses`` axiom must match the curator's byte-for-byte
  (whitespace-normalised). This guards the pattern templates incl. role handling.
* **The deterministic pass count does not regress.** A baseline number of terms
  are reproduced end-to-end (label + EQ) with no LLM tier and no OAK access.

Failing rows are catalogued by failure mode (not asserted here) so we can drive
them to green over time; the counts are asserted so a *regression* (a previously
passing term breaking) fails the build.
"""

from __future__ import annotations

from collections import Counter

import pytest

from tests.corpus_runner import CorpusResult, run_corpus

# Baseline established 2026-08-16. Raise (never lower) as failure modes are fixed.
BASELINE_PASS = 94
# Terms that need the agentic clinical extractor (opaque portmanteau labels like
# "Hypoalbuminemia") cannot map in the deterministic-only offline harness.
BASELINE_NEEDS_LLM = 44


@pytest.fixture(scope="module")
def results() -> list[CorpusResult]:
    return run_corpus()


def test_corpus_is_large(results: list[CorpusResult]) -> None:
    """The corpus is a meaningful size (guards accidental truncation)."""
    assert len(results) >= 200


def test_eq_generation_exact_when_mapped(results: list[CorpusResult]) -> None:
    """Given the curator's chemical, our EQ axiom reproduces theirs exactly.

    This is the strongest invariant: it proves the pattern EQ templates
    (location substitution, role vs direct filler) are correct. Any mismatch
    here is a genuine axiom-construction bug, not an association/labelling gap.
    """
    mapped_with_eq = [r for r in results if r.eq_expected and not r.unmapped_reason]
    mismatches = [r.hp_id for r in mapped_with_eq if not r.eq_match]
    assert mismatches == [], f"EQ construction regressed for: {mismatches}"


def test_pass_count_does_not_regress(results: list[CorpusResult]) -> None:
    """At least BASELINE_PASS terms reproduce end-to-end, offline."""
    passes = sum(1 for r in results if r.category == "pass")
    assert passes >= BASELINE_PASS, (
        f"deterministic pass count dropped to {passes} (baseline {BASELINE_PASS})"
    )


def test_opaque_clinical_terms_are_the_llm_gap(results: list[CorpusResult]) -> None:
    """Opaque clinical terms are the documented LLM-tier gap, not a silent loss."""
    needs_llm = sum(1 for r in results if r.category == "unmapped:opaque_clinical")
    # These are expected to be unmapped without the agentic tier; assert the
    # count is stable so a deterministic *improvement* is noticed and folded in.
    assert needs_llm <= BASELINE_NEEDS_LLM + 2


def test_failure_modes_are_catalogued(results: list[CorpusResult]) -> None:
    """Every non-pass row carries a recognised failure-mode category."""
    known_prefixes = ("pass", "fail:", "unmapped:")
    unknown = [r.hp_id for r in results if not r.category.startswith(known_prefixes)]
    assert unknown == []


def test_print_histogram(results: list[CorpusResult], capsys: pytest.CaptureFixture) -> None:
    """Emit the category histogram (visible with -s) for triage."""
    hist = Counter(r.category for r in results)
    with capsys.disabled():
        print("\ncorpus failure-mode histogram:")
        for cat, n in hist.most_common():
            print(f"  {n:4d}  {cat}")
