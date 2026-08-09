"""A human-auditable, edit-preserving TSV store for machine decisions.

Mirrors MeDIC's ``LiteralMappingStore`` (``src/medic/grounding/store.py``): one
git-diffable TSV, rows grouped by a meaningful key, and a **lock gate** so a
re-run never overwrites a curator-owned row (see :func:`is_row_locked`).

The store *is* the cache, the audit trail, and the human-override surface in one
file — keyed on a readable string, not an opaque prompt hash — so a curator can
open it, fix a row, mark it, and have that decision stick across runs.
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

from hpo_ai.provenance.constants import is_row_locked

logger = logging.getLogger(__name__)


def normalize_key(value: str) -> str:
    """Normalise a key for grouping (case/space-insensitive).

    >>> normalize_key("  Hypo   Glycorrhachia ")
    'hypo glycorrhachia'
    """
    return re.sub(r"\s+", " ", value).strip().lower()


class LockedTsvStore:
    """A TSV store of decision rows, grouped by a key column, with a lock gate."""

    def __init__(
        self,
        path: str | Path,
        columns: list[str],
        key_column: str,
        header_comments: tuple[str, ...] = (),
        sort_key: str | None = None,
    ) -> None:
        """Initialise.

        Args:
            path: TSV file path.
            columns: Ordered column names.
            key_column: Column whose (normalised) value groups rows.
            header_comments: ``#``-prefixed lines written above the header.
            sort_key: Optional column to sort a key's rows by on save.
        """
        self.path = Path(path)
        self.columns = columns
        self.key_column = key_column
        self.header_comments = header_comments
        self.sort_key = sort_key
        self._rows: dict[str, list[dict[str, str]]] = {}

    def load(self) -> None:
        """Load rows from disk (comment lines ignored)."""
        self._rows.clear()
        if not self.path.exists():
            return
        with open(self.path, newline="") as fh:
            reader = csv.DictReader(
                (ln for ln in fh if not ln.startswith("#")), delimiter="\t"
            )
            for row in reader:
                key = normalize_key(row.get(self.key_column, ""))
                self._rows.setdefault(key, []).append(dict(row))

    def get(self, key_value: str) -> list[dict[str, str]]:
        """All rows for a key (empty list if none)."""
        return self._rows.get(normalize_key(key_value), [])

    def is_locked(self, key_value: str) -> bool:
        """Whether any row for the key is curator-owned."""
        return any(is_row_locked(r) for r in self.get(key_value))

    def record(self, key_value: str, rows: list[dict[str, str]]) -> bool:
        """Replace the machine row-set for a key, unless it is locked.

        Args:
            key_value: The key.
            rows: The new rows (each a dict over ``columns``).

        Returns:
            True if written, False if skipped because the key is locked.
        """
        if self.is_locked(key_value):
            return False
        self._rows[normalize_key(key_value)] = [
            {c: str(r.get(c, "")) for c in self.columns} for r in rows
        ]
        return True

    def all_rows(self) -> list[dict[str, str]]:
        """Every row, flattened."""
        return [r for rows in self._rows.values() for r in rows]

    def save(self) -> None:
        """Write the store to disk (comment header + sorted rows)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", newline="") as fh:
            for comment in self.header_comments:
                fh.write(f"# {comment}\n")
            writer = csv.DictWriter(fh, fieldnames=self.columns, delimiter="\t")
            writer.writeheader()
            for key in sorted(self._rows):
                rows = self._rows[key]
                if self.sort_key:
                    sk = self.sort_key
                    rows = sorted(rows, key=lambda r: r.get(sk, ""))
                for row in rows:
                    writer.writerow({c: row.get(c, "") for c in self.columns})
