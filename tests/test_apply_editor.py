"""Tests for applying approved proposals to an hp-edit.owl functional-syntax file."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hpo_ai.apply import OntologyEditApplier
from hpo_ai.datamodel import (
    CurationProposal,
    EvidencePacket,
    HPTerm,
    ReviewStatus,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mini_hp_edit.ofn"


def _packet(
    hp_id: str,
    current_label: str,
    proposed_label: str | None,
    status: ReviewStatus = ReviewStatus.auto_approved,
) -> EvidencePacket:
    """Build a minimal packet carrying a label-rename proposal."""
    proposal = None
    if proposed_label is not None:
        proposal = CurationProposal(
            id=f"prop_{hp_id}",
            proposed_label=proposed_label,
        )
    return EvidencePacket(
        id=f"pkt_{hp_id}",
        hp_term=HPTerm(id=hp_id, label=current_label),
        proposal=proposal,
        review_status=status,
    )


@pytest.fixture
def edit_file(tmp_path: Path) -> Path:
    """A writable copy of the mini hp-edit fixture."""
    dest = tmp_path / "hp-edit.ofn"
    shutil.copy(FIXTURE, dest)
    return dest


def test_applies_label_rename(edit_file: Path) -> None:
    """An auto-approved rename updates rdfs:label in place."""
    packets = [
        _packet(
            "HP:0002490",
            "Increased CSF lactate",
            "Elevated CSF lactate concentration",
        )
    ]
    report = OntologyEditApplier(edit_file).apply(packets)

    text = edit_file.read_text()
    assert (
        'AnnotationAssertion(rdfs:label '
        '<http://purl.obolibrary.org/obo/HP_0002490> '
        '"Elevated CSF lactate concentration")'
    ) in text
    # Old label no longer used as the rdfs:label
    assert (
        'AnnotationAssertion(rdfs:label '
        '<http://purl.obolibrary.org/obo/HP_0002490> '
        '"Increased CSF lactate")'
    ) not in text
    assert len(report.applied) == 1
    assert report.applied[0].hp_id == "HP:0002490"


def test_preserves_old_label_as_exact_synonym(edit_file: Path) -> None:
    """Renaming preserves the previous label as an exact synonym."""
    packets = [
        _packet(
            "HP:0002490",
            "Increased CSF lactate",
            "Elevated CSF lactate concentration",
        )
    ]
    OntologyEditApplier(edit_file).apply(packets)

    text = edit_file.read_text()
    assert (
        'AnnotationAssertion(<http://www.geneontology.org/formats/oboInOwl#hasExactSynonym> '
        '<http://purl.obolibrary.org/obo/HP_0002490> '
        '"Increased CSF lactate")'
    ) in text


def test_skips_when_current_label_mismatches(edit_file: Path) -> None:
    """If the file's current label differs from the packet's, do not edit."""
    before = edit_file.read_text()
    packets = [
        _packet(
            "HP:0002490",
            "Some stale label that is not in the file",
            "Elevated CSF lactate concentration",
        )
    ]
    report = OntologyEditApplier(edit_file).apply(packets)

    assert edit_file.read_text() == before
    assert report.applied == []
    assert "HP:0002490" in report.label_mismatch


def test_skips_non_approved_status(edit_file: Path) -> None:
    """needs_review proposals are not applied by default."""
    before = edit_file.read_text()
    packets = [
        _packet(
            "HP:0500220",
            "Increased CSF tyrosine concentration",
            "Elevated CSF tyrosine concentration",
            status=ReviewStatus.needs_review,
        )
    ]
    report = OntologyEditApplier(edit_file).apply(packets)

    assert edit_file.read_text() == before
    assert report.applied == []
    assert "HP:0500220" in report.skipped_status


def test_skips_when_label_unchanged(edit_file: Path) -> None:
    """A proposal whose label equals the current label is a no-op."""
    before = edit_file.read_text()
    packets = [
        _packet(
            "HP:0500220",
            "Increased CSF tyrosine concentration",
            "Increased CSF tyrosine concentration",
        )
    ]
    report = OntologyEditApplier(edit_file).apply(packets)

    assert edit_file.read_text() == before
    assert report.applied == []
    assert "HP:0500220" in report.skipped_no_change


def test_no_duplicate_synonym(edit_file: Path) -> None:
    """If the old label already exists as an exact synonym, do not duplicate it."""
    # Seed HP:0500220 with an exact synonym equal to what will become the old label
    text = edit_file.read_text().replace(
        'AnnotationAssertion(rdfs:label '
        '<http://purl.obolibrary.org/obo/HP_0500220> '
        '"Increased CSF tyrosine concentration")',
        'AnnotationAssertion(<http://www.geneontology.org/formats/oboInOwl#hasExactSynonym> '
        '<http://purl.obolibrary.org/obo/HP_0500220> '
        '"Increased CSF tyrosine concentration")\n'
        'AnnotationAssertion(rdfs:label '
        '<http://purl.obolibrary.org/obo/HP_0500220> '
        '"Increased CSF tyrosine concentration")',
    )
    edit_file.write_text(text)

    packets = [
        _packet(
            "HP:0500220",
            "Increased CSF tyrosine concentration",
            "Elevated CSF tyrosine concentration",
        )
    ]
    OntologyEditApplier(edit_file).apply(packets)

    result = edit_file.read_text()
    assert (
        result.count(
            'AnnotationAssertion(<http://www.geneontology.org/formats/oboInOwl#hasExactSynonym> '
            '<http://purl.obolibrary.org/obo/HP_0500220> '
            '"Increased CSF tyrosine concentration")'
        )
        == 1
    )


def test_dry_run_does_not_write(edit_file: Path) -> None:
    """dry_run reports what would change but leaves the file untouched."""
    before = edit_file.read_text()
    packets = [
        _packet(
            "HP:0002490",
            "Increased CSF lactate",
            "Elevated CSF lactate concentration",
        )
    ]
    report = OntologyEditApplier(edit_file).apply(packets, dry_run=True)

    assert edit_file.read_text() == before
    assert len(report.applied) == 1


def test_idempotent(edit_file: Path) -> None:
    """Applying the same rename twice changes nothing the second time."""
    packets = [
        _packet(
            "HP:0002490",
            "Increased CSF lactate",
            "Elevated CSF lactate concentration",
        )
    ]
    applier = OntologyEditApplier(edit_file)
    applier.apply(packets)
    after_first = edit_file.read_text()

    # Second run: file no longer has the old label, so it's a mismatch (skip)
    report2 = applier.apply(packets)
    assert edit_file.read_text() == after_first
    assert report2.applied == []
