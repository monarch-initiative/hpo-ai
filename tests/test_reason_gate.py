"""Tests for the robot-reason satisfiability gate."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from hpo_ai.apply import reason
from hpo_ai.apply.reason import check_satisfiability, parse_unsatisfiable

_SAMPLE_UNSAT = """\
ERROR There are 2 unsatisfiable classes in the ontology.
ERROR unsatisfiable: http://purl.obolibrary.org/obo/HP_0031964
ERROR unsatisfiable: http://purl.obolibrary.org/obo/HP_0025454
"""


def test_parse_unsatisfiable_extracts_iris() -> None:
    assert parse_unsatisfiable(_SAMPLE_UNSAT) == [
        "http://purl.obolibrary.org/obo/HP_0031964",
        "http://purl.obolibrary.org/obo/HP_0025454",
    ]


def test_parse_unsatisfiable_empty_when_coherent() -> None:
    assert parse_unsatisfiable("Reasoning ok, 0 unsatisfiable classes") == []


def test_check_satisfiability_returns_empty_on_success(monkeypatch) -> None:
    def fake_run(cmd, capture_output, text):  # noqa: ANN001, ANN202
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert check_satisfiability("hp-edit.owl", robot="robot") == []


def test_check_satisfiability_returns_unsat_classes(monkeypatch) -> None:
    def fake_run(cmd, capture_output, text):  # noqa: ANN001, ANN202
        return SimpleNamespace(returncode=1, stdout=_SAMPLE_UNSAT, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    unsat = check_satisfiability("hp-edit.owl", robot="robot")
    assert "http://purl.obolibrary.org/obo/HP_0031964" in unsat


def test_check_satisfiability_raises_on_other_failure(monkeypatch) -> None:
    def fake_run(cmd, capture_output, text):  # noqa: ANN001, ANN202
        return SimpleNamespace(returncode=1, stdout="", stderr="OutOfMemoryError")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        check_satisfiability("hp-edit.owl", robot="robot")


def test_reason_module_imports() -> None:
    assert hasattr(reason, "check_satisfiability")
