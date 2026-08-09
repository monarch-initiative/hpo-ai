"""Tests for the surgical EquivalentClasses editor."""

from __future__ import annotations

from pathlib import Path

from hpo_ai.apply.eq_editor import EqEditor

HP = "http://purl.obolibrary.org/obo/HP_"


def _fixture(tmp_path: Path, with_eq: bool) -> Path:
    eq = (
        f"EquivalentClasses(<{HP}0002490> ObjectSomeValuesFrom(<x> <y>))\n"
        if with_eq
        else ""
    )
    text = (
        "Ontology(<http://purl.obolibrary.org/obo/hp.owl>\n\n"
        f"Declaration(Class(<{HP}0002490>))\n"
        f'AnnotationAssertion(rdfs:label <{HP}0002490> "Elevated CSF lactate concentration")\n'
        f"{eq}"
        ")\n"
    )
    p = tmp_path / "hp-edit.ofn"
    p.write_text(text)
    return p


NEW_EQ = "ObjectSomeValuesFrom(<A> ObjectIntersectionOf(<B> <C>))"


def test_adds_eq_when_absent(tmp_path: Path) -> None:
    p = _fixture(tmp_path, with_eq=False)
    report = EqEditor(p).apply({"HP:0002490": NEW_EQ})
    assert report.added == [f"{HP}0002490"]
    assert f"EquivalentClasses(<{HP}0002490> {NEW_EQ})" in p.read_text()


def test_replaces_differing_eq(tmp_path: Path) -> None:
    p = _fixture(tmp_path, with_eq=True)
    report = EqEditor(p).apply({"HP:0002490": NEW_EQ})
    assert report.replaced == [f"{HP}0002490"]
    text = p.read_text()
    assert "ObjectSomeValuesFrom(<x> <y>)" not in text
    assert NEW_EQ in text
    # exactly one EquivalentClasses line for the term
    assert text.count(f"EquivalentClasses(<{HP}0002490>") == 1


def test_unchanged_when_identical(tmp_path: Path) -> None:
    p = _fixture(tmp_path, with_eq=True)
    report = EqEditor(p).apply(
        {"HP:0002490": "ObjectSomeValuesFrom(<x> <y>)"}
    )
    assert report.unchanged == [f"{HP}0002490"]
    assert not report.changed


def test_skips_when_term_not_found(tmp_path: Path) -> None:
    p = _fixture(tmp_path, with_eq=False)
    before = p.read_text()
    report = EqEditor(p).apply({"HP:9999999": NEW_EQ})
    assert report.skipped == [f"{HP}9999999"]
    assert p.read_text() == before
