"""Reporting for terms that could not be cleanly associated with a pattern."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from hpo_ai.associate.models import Unmapped

_COLUMNS = ["hpo_id", "label", "reason", "detail"]


def write_unmapped_tsv(unmapped: list[Unmapped], path: str | Path) -> None:
    """Write unmapped terms to a TSV.

    Args:
        unmapped: Terms that did not map cleanly.
        path: Output TSV path.
    """
    path = Path(path)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS, delimiter="\t")
        writer.writeheader()
        for u in unmapped:
            reason = u.reason.value if hasattr(u.reason, "value") else u.reason
            writer.writerow(
                {"hpo_id": u.hp_id, "label": u.label, "reason": reason, "detail": u.detail}
            )


def summarize_reasons(unmapped: list[Unmapped]) -> dict[str, int]:
    """Count unmapped terms by reason.

    >>> from hpo_ai.associate.models import Unmapped, UnmappedReason
    >>> rows = [Unmapped("HP:1", "a", UnmappedReason.no_location),
    ...         Unmapped("HP:2", "b", UnmappedReason.no_location),
    ...         Unmapped("HP:3", "c", UnmappedReason.ambiguous)]
    >>> summarize_reasons(rows)["no_location"]
    2
    """
    return dict(
        Counter(
            (u.reason.value if hasattr(u.reason, "value") else u.reason) for u in unmapped
        )
    )
