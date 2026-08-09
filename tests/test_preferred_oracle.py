"""Tests for the cached preferred-clinical-term + commonness oracle."""

from __future__ import annotations

from pathlib import Path

from hpo_ai.associate.preferred import PreferredClinicalTermResolver
from hpo_ai.provenance import preferred_term_row, preferred_term_store
from hpo_ai.provenance.constants import JUSTIFICATION_MANUAL, METHOD_HUMAN


def test_oracle_caches_positive(tmp_path: Path) -> None:
    store = preferred_term_store(tmp_path / "pref.tsv")
    calls = {"n": 0}

    def llm(direction, chemical, fluid, candidate):
        calls["n"] += 1
        return ("Hyperuricemia", True)

    resolver = PreferredClinicalTermResolver(store, llm_fn=llm, agent_version="m")
    assert resolver("increased", "urate", "blood") == ("Hyperuricemia", True)
    assert resolver("increased", "urate", "blood") == ("Hyperuricemia", True)  # cache
    assert calls["n"] == 1


def test_oracle_negative_is_cached(tmp_path: Path) -> None:
    store = preferred_term_store(tmp_path / "pref.tsv")
    calls = {"n": 0}

    def llm(direction, chemical, fluid, candidate):
        calls["n"] += 1
        return (None, False)

    resolver = PreferredClinicalTermResolver(store, llm_fn=llm)
    assert resolver("increased", "ribitol", "blood") == (None, False)
    assert resolver("increased", "ribitol", "blood") == (None, False)
    assert calls["n"] == 1  # negative answer cached, LLM asked once


def test_commonness_is_cached_and_curatable(tmp_path: Path) -> None:
    path = tmp_path / "pref.tsv"
    store = preferred_term_store(path)
    # curator marks an obscure term common=false, locked
    row = preferred_term_row("increased", "lactate", "cerebrospinal fluid",
                             "Hyperlactatorachia", False, METHOD_HUMAN, "", 1.0)
    row["mapping_justification"] = JUSTIFICATION_MANUAL
    store.record("increased|lactate|cerebrospinal fluid", [row])
    store.save()

    def llm(direction, chemical, fluid, candidate):
        raise AssertionError("LLM should not be called for a cached concept")

    resolver = PreferredClinicalTermResolver(preferred_term_store(path), llm_fn=llm)
    term, common = resolver("increased", "lactate", "cerebrospinal fluid",
                            "Hyperlactatorachia")
    assert term == "Hyperlactatorachia"
    assert common is False  # curator says obscure -> keep as synonym


def test_offline_no_llm_treats_candidate_as_obscure(tmp_path: Path) -> None:
    """With no LLM and no cached row, a known candidate is kept but not promoted."""
    store = preferred_term_store(tmp_path / "pref.tsv")
    resolver = PreferredClinicalTermResolver(store, llm_fn=None)
    assert resolver("increased", "glucose", "blood", "Hyperglycemia") == ("Hyperglycemia", False)
    assert resolver("increased", "glucose", "blood") == (None, False)
