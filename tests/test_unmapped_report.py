"""Tests for the unmapped-terms report."""

from __future__ import annotations

import csv
from pathlib import Path

from hpo_ai.associate.models import Unmapped, UnmappedReason
from hpo_ai.associate.report import summarize_reasons, write_unmapped_tsv


def test_write_unmapped_tsv(tmp_path: Path) -> None:
    rows = [
        Unmapped("HP:0000001", "Elevated something concentration",
                 UnmappedReason.no_location, "no fluid detected"),
        Unmapped("HP:0000002", "Weird term", UnmappedReason.no_chemical, "no span"),
    ]
    out = tmp_path / "unmapped.tsv"
    write_unmapped_tsv(rows, out)

    with open(out) as f:
        parsed = list(csv.DictReader(f, delimiter="\t"))
    assert len(parsed) == 2
    assert parsed[0]["hpo_id"] == "HP:0000001"
    assert parsed[0]["reason"] == "no_location"
    assert parsed[1]["reason"] == "no_chemical"


def test_summarize_reasons() -> None:
    rows = [
        Unmapped("HP:1", "a", UnmappedReason.no_location),
        Unmapped("HP:2", "b", UnmappedReason.no_location),
        Unmapped("HP:3", "c", UnmappedReason.ambiguous),
    ]
    counts = summarize_reasons(rows)
    assert counts["no_location"] == 2
    assert counts["ambiguous"] == 1
