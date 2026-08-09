"""Apply approved curation proposals directly to an hp-edit.owl file.

The HPO editors' file ``src/ontology/hp-edit.owl`` is serialised in OWL
Functional Syntax, which is line-oriented: each ``AnnotationAssertion`` sits on
its own line.  That makes it safe to apply *targeted* edits -- rewriting a
single ``rdfs:label`` line -- instead of round-tripping the whole 33 MB file
through the OWL API (which would reformat every axiom and produce an
unreviewable diff).

Only label renames are applied, and only for packets whose review status is
approved *and* whose recorded original label still matches what is in the file.
The previous label is preserved as an ``oboInOwl:hasExactSynonym`` so existing
search/annotation behaviour is retained, mirroring standard HPO curation
practice (and issue #11702).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from hpo_ai.datamodel import EvidencePacket

logger = logging.getLogger(__name__)

_OBO = "http://purl.obolibrary.org/obo/"
_EXACT_SYN = "http://www.geneontology.org/formats/oboInOwl#hasExactSynonym"

# rdfs:label may be written with the ``rdfs:`` prefix or as a full IRI.
_LABEL_PRED = r"(?:rdfs:label|<http://www\.w3\.org/2000/01/rdf-schema#label>)"

_LABEL_RE = re.compile(
    r'^(?P<indent>\s*)AnnotationAssertion\(\s*'
    + _LABEL_PRED
    + r'\s+<(?P<iri>[^>]+)>\s+"(?P<lit>(?:[^"\\]|\\.)*)"\s*\)\s*$'
)

_SYN_RE = re.compile(
    r'^\s*AnnotationAssertion\(\s*<'
    + re.escape(_EXACT_SYN)
    + r'>\s+<(?P<iri>[^>]+)>\s+"(?P<lit>(?:[^"\\]|\\.)*)"\s*\)\s*$'
)


def _iri_for(curie_or_iri: str) -> str:
    """Return the full OBO IRI for an HP CURIE.

    >>> _iri_for("HP:0002490")
    'http://purl.obolibrary.org/obo/HP_0002490'
    >>> _iri_for("http://purl.obolibrary.org/obo/HP_0002490")
    'http://purl.obolibrary.org/obo/HP_0002490'
    """
    if curie_or_iri.startswith("http"):
        return curie_or_iri
    return _OBO + curie_or_iri.replace(":", "_")


def _fs_escape(text: str) -> str:
    r"""Escape a string for an OWL Functional Syntax literal.

    >>> _fs_escape('a "quote" and a \\')
    'a \\"quote\\" and a \\\\'
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _fs_unescape(text: str) -> str:
    r"""Reverse :func:`_fs_escape` for comparing file literals to plain strings.

    >>> _fs_unescape('a \\"quote\\"')
    'a "quote"'
    """
    return text.replace('\\"', '"').replace("\\\\", "\\")


def _status_value(val: object) -> str | None:
    """Return the string value of a review status (enum or plain string)."""
    if val is None:
        return None
    return val.value if hasattr(val, "value") else str(val)


@dataclass
class LabelChange:
    """A single applied label rename."""

    hp_id: str
    old_label: str
    new_label: str


@dataclass
class ApplyReport:
    """Summary of an :meth:`OntologyEditApplier.apply` run."""

    applied: list[LabelChange] = field(default_factory=list)
    synonyms_added: list[str] = field(default_factory=list)
    skipped_no_change: list[str] = field(default_factory=list)
    skipped_status: list[str] = field(default_factory=list)
    skipped_no_proposal: list[str] = field(default_factory=list)
    label_mismatch: list[str] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        """Whether any edit was made."""
        return bool(self.applied)


class OntologyEditApplier:
    """Apply label-rename proposals to an OWL Functional Syntax edit file."""

    APPROVED_STATUSES = frozenset({"auto_approved", "approved"})

    def __init__(
        self,
        edit_path: str | Path,
        statuses: set[str] | None = None,
        add_original_as_synonym: bool = True,
    ) -> None:
        """Initialise the applier.

        Args:
            edit_path: Path to the ``hp-edit.owl`` functional-syntax file.
            statuses: Review statuses to apply. Defaults to approved statuses.
            add_original_as_synonym: Preserve the old label as an exact synonym.
        """
        self.edit_path = Path(edit_path)
        self.statuses = set(statuses) if statuses is not None else set(self.APPROVED_STATUSES)
        self.add_original_as_synonym = add_original_as_synonym

    def _select_targets(
        self, packets: list[EvidencePacket], report: ApplyReport
    ) -> dict[str, LabelChange]:
        """Pick packets that represent an applicable label rename."""
        targets: dict[str, LabelChange] = {}
        for packet in packets:
            hp_id = packet.hp_term.id
            status = _status_value(packet.review_status)
            if status not in self.statuses:
                report.skipped_status.append(hp_id)
                continue
            if not packet.proposal or not packet.proposal.proposed_label:
                report.skipped_no_proposal.append(hp_id)
                continue
            old = (packet.hp_term.label or "").strip()
            new = packet.proposal.proposed_label.strip()
            if not new or new == old:
                report.skipped_no_change.append(hp_id)
                continue
            targets[_iri_for(hp_id)] = LabelChange(hp_id, old, new)
        return targets

    def _existing_exact_synonyms(
        self, lines: list[str], iris: set[str]
    ) -> dict[str, set[str]]:
        """Collect existing exact-synonym values for the target IRIs."""
        found: dict[str, set[str]] = {}
        for line in lines:
            match = _SYN_RE.match(line)
            if match and match.group("iri") in iris:
                found.setdefault(match.group("iri"), set()).add(
                    _fs_unescape(match.group("lit"))
                )
        return found

    def _render_label_line(self, original_line: str, iri: str, new_label: str) -> str:
        """Rebuild a label assertion line with a new literal, preserving style."""
        indent = re.match(r"\s*", original_line).group()  # type: ignore[union-attr]
        pred = (
            "rdfs:label"
            if "rdfs:label" in original_line
            else "<http://www.w3.org/2000/01/rdf-schema#label>"
        )
        return f'{indent}AnnotationAssertion({pred} <{iri}> "{_fs_escape(new_label)}")\n'

    def _render_synonym_line(self, iri: str, value: str, reference_line: str) -> str:
        """Build an exact-synonym assertion line for the preserved old label."""
        indent = re.match(r"\s*", reference_line).group()  # type: ignore[union-attr]
        return f'{indent}AnnotationAssertion(<{_EXACT_SYN}> <{iri}> "{_fs_escape(value)}")\n'

    def apply(self, packets: list[EvidencePacket], dry_run: bool = False) -> ApplyReport:
        """Apply label renames from ``packets`` to the edit file.

        Args:
            packets: Evidence packets carrying curation proposals.
            dry_run: If true, compute the report but do not write the file.

        Returns:
            An :class:`ApplyReport` describing what was (or would be) changed.
        """
        report = ApplyReport()
        targets = self._select_targets(packets, report)
        if not targets:
            return report

        lines = self.edit_path.read_text().splitlines(keepends=True)
        existing_syn = self._existing_exact_synonyms(lines, set(targets))

        out: list[str] = []
        seen: set[str] = set()
        for line in lines:
            match = _LABEL_RE.match(line)
            change = targets.get(match.group("iri")) if match else None
            if match and change is not None:
                iri = match.group("iri")
                seen.add(iri)
                current_label = _fs_unescape(match.group("lit"))
                if current_label != change.old_label:
                    report.label_mismatch.append(change.hp_id)
                    out.append(line)
                    continue
                out.append(self._render_label_line(line, iri, change.new_label))
                report.applied.append(change)
                if (
                    self.add_original_as_synonym
                    and change.old_label not in existing_syn.get(iri, set())
                ):
                    out.append(self._render_synonym_line(iri, change.old_label, line))
                    report.synonyms_added.append(change.hp_id)
                continue
            out.append(line)

        for iri, change in targets.items():
            if iri not in seen:
                report.not_found.append(change.hp_id)

        if report.applied and not dry_run:
            self.edit_path.write_text("".join(out))
            logger.info(
                "Applied %d label rename(s) to %s", len(report.applied), self.edit_path
            )
        return report
