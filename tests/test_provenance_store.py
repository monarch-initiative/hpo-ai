"""Tests for the locked, human-editable TSV stores (medic pattern reuse)."""

from __future__ import annotations

from pathlib import Path

from hpo_ai.provenance import (
    clinical_grounding_store,
    machine_grounding_rows,
    read_grounding,
)
from hpo_ai.provenance.constants import JUSTIFICATION_MANUAL, STATUS_CONFIRMED
from hpo_ai.provenance.store import LockedTsvStore


def _clinical_row(label, chemical, chebi, manual=False, confirmed=False):
    from hpo_ai.datamodel import ChemicalEntityEvidence
    entity = ChemicalEntityEvidence(id="ev", entity_id=chebi, entity_label=chemical,
                                    confidence=0.9) if chebi else None
    row = machine_grounding_rows("HP:1", label, chemical, entity, "model-x")[0]
    if manual:
        row["mapping_justification"] = JUSTIFICATION_MANUAL
    if confirmed:
        row["status"] = STATUS_CONFIRMED
    return row


def test_record_and_read_roundtrip(tmp_path: Path) -> None:
    store = clinical_grounding_store(tmp_path / "clinical.sssom.tsv")
    store.record("Hypoglycorrhachia", [_clinical_row("Hypoglycorrhachia", "glucose", "CHEBI:17234")])
    store.save()

    reloaded = clinical_grounding_store(tmp_path / "clinical.sssom.tsv")
    name, entity = read_grounding(reloaded, "Hypoglycorrhachia")
    assert name == "glucose"
    assert entity.entity_id == "CHEBI:17234"


def test_manual_row_survives_rerun(tmp_path: Path) -> None:
    """A curator's manual row is never overwritten by a machine re-run."""
    path = tmp_path / "clinical.sssom.tsv"
    store = clinical_grounding_store(path)
    # curator hand-edits: glucose, marked manual
    store.record("Hypoglycorrhachia",
                 [_clinical_row("Hypoglycorrhachia", "glucose", "CHEBI:17234", manual=True)])
    store.save()

    # a re-run tries to write a different (wrong) machine value
    rerun = clinical_grounding_store(path)
    wrote = rerun.record("Hypoglycorrhachia",
                         [_clinical_row("Hypoglycorrhachia", "galactose", "CHEBI:28061")])
    assert wrote is False  # locked
    rerun.save()

    final = clinical_grounding_store(path)
    name, entity = read_grounding(final, "Hypoglycorrhachia")
    assert name == "glucose"                # human value preserved
    assert entity.entity_id == "CHEBI:17234"


def test_confirmed_status_locks(tmp_path: Path) -> None:
    path = tmp_path / "c.sssom.tsv"
    store = clinical_grounding_store(path)
    store.record("X", [_clinical_row("X", "glucose", "CHEBI:17234", confirmed=True)])
    assert store.is_locked("X") is True
    assert store.record("X", [_clinical_row("X", "wrong", "CHEBI:1")]) is False


def test_machine_row_is_refreshed(tmp_path: Path) -> None:
    path = tmp_path / "m.sssom.tsv"
    store = clinical_grounding_store(path)
    store.record("X", [_clinical_row("X", "glucose", "CHEBI:17234")])  # MACHINE
    wrote = store.record("X", [_clinical_row("X", "lactate", "CHEBI:24996")])
    assert wrote is True  # unlocked machine row overwritten
    name, _ = read_grounding(store, "X")
    assert name == "lactate"


def test_noterm_row_reads_as_unresolved(tmp_path: Path) -> None:
    path = tmp_path / "n.sssom.tsv"
    store = clinical_grounding_store(path)
    store.record("Mysteryitis", machine_grounding_rows("HP:9", "Mysteryitis", "mysteryol", None, "m"))
    name, entity = read_grounding(store, "Mysteryitis")
    assert name == "mysteryol"
    assert entity is None


def test_key_is_case_and_space_insensitive(tmp_path: Path) -> None:
    store = LockedTsvStore(tmp_path / "k.tsv", ["k", "v"], key_column="k")
    store.record("Foo  Bar", [{"k": "Foo  Bar", "v": "1"}])
    assert store.get("foo bar")[0]["v"] == "1"
