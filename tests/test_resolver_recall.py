"""Resolver-recall tests: synonym-inclusive, synonym-aware CHEBI resolution.

Common metabolite names are often CHEBI *synonyms*, not the primary label
(``epinephrine`` -> "(R)-adrenaline"). Label-only search misses them and the
term loses its EQ (see issues/issue_resolver_recall.md). These tests use a fake
adapter so they stay fast and offline.
"""

from __future__ import annotations

from hpo_ai.enrichment.chebi import CHEBIResolver


class _FakeChebi:
    """Adapter with label + alias search, honouring exact matches only."""

    _LABELS = {
        "CHEBI:28918": "(R)-adrenaline",
        "CHEBI:17234": "glucose",
        "CHEBI:17775": "7,9-dihydro-1H-purine-2,6,8(3H)-trione",
    }
    _ALIASES = {
        "CHEBI:28918": ["epinephrine", "adrenaline", "epinephrinum"],
        "CHEBI:17234": ["D-glucose"],
        "CHEBI:17775": ["urate", "uric acid anion"],
    }

    def basic_search(self, query, config=None):  # noqa: ANN001, ANN201
        q = query.lower().strip()
        hits = []
        for curie, label in self._LABELS.items():
            if q == label.lower() or q in {a.lower() for a in self._ALIASES[curie]}:
                hits.append(curie)
        return hits

    def label(self, curie):  # noqa: ANN001, ANN201
        return self._LABELS.get(curie)

    def entity_aliases(self, curie):  # noqa: ANN001, ANN201
        return self._ALIASES.get(curie, [])


def _resolver() -> CHEBIResolver:
    return CHEBIResolver(adapter=_FakeChebi())


def test_synonym_match_resolves_above_threshold() -> None:
    """'epinephrine' (a synonym of (R)-adrenaline) resolves with high confidence."""
    results = _resolver().resolve("epinephrine")
    assert results, "expected a synonym match"
    top = results[0]
    assert top.entity_id == "CHEBI:28918"
    assert (top.confidence or 0) >= 0.7  # must clear the entity threshold


def test_urate_synonym_resolves() -> None:
    """'urate' resolves though the primary CHEBI label is systematic."""
    results = _resolver().resolve("urate")
    assert results
    assert results[0].entity_id == "CHEBI:17775"
    assert (results[0].confidence or 0) >= 0.7


def test_exact_label_still_wins() -> None:
    """An exact label match keeps top confidence."""
    results = _resolver().resolve("glucose")
    assert results[0].entity_id == "CHEBI:17234"
    assert (results[0].confidence or 0) >= 0.95


def test_confidence_synonym_vs_label() -> None:
    """Exact synonym match ranks below exact label but above the threshold."""
    r = _resolver()
    label_conf = r._calculate_confidence("glucose", "glucose", 0)
    syn_conf = r._calculate_confidence(
        "epinephrine", "(R)-adrenaline", 0, ["epinephrine"]
    )
    miss_conf = r._calculate_confidence("epinephrine", "(R)-adrenaline", 0, [])
    assert label_conf > syn_conf >= 0.7 > miss_conf


# ---------------------------------------------------------------------------
# Curated mappings for name-structure misses (seeded in the production conf)
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from hpo_ai.enrichment.chebi import DEFAULT_RULES_PATH  # noqa: E402
from hpo_ai.enrichment.selection_rules import (  # noqa: E402
    CHEBISelectionFilter,
    load_chebi_selection_rules,
)


@pytest.fixture(scope="module")
def curated_filter() -> CHEBISelectionFilter:
    return CHEBISelectionFilter(load_chebi_selection_rules(DEFAULT_RULES_PATH))


@pytest.mark.parametrize(
    "name, chebi_id",
    [
        ("5-hydroxyindoleacetic acid", "CHEBI:27823"),
        ("5-hydroxyindolacetic acid", "CHEBI:27823"),  # HPO misspelling -> same
        ("dihydrothymine", "CHEBI:27468"),
        ("dihydrouracil", "CHEBI:15901"),
        ("argininosuccinic acid", "CHEBI:15682"),
        ("saccharopine", "CHEBI:16927"),
        ("metanephrine", "CHEBI:89633"),
        ("N-carbamyl-beta-alanine", "CHEBI:18261"),
        ("pyridoxal-5'-phosphate", "CHEBI:18405"),
        ("branched-chain amino acid", "CHEBI:22918"),
    ],
)
def test_curated_mapping_resolves(
    curated_filter: CHEBISelectionFilter, name: str, chebi_id: str
) -> None:
    """Each seeded curated mapping resolves the HPO name to the verified id."""
    match = curated_filter.resolve(name)
    assert match is not None, f"{name!r} did not resolve via curated mappings"
    assert match[0] == chebi_id
