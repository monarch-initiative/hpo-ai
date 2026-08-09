"""Integration test for the apply runner (Workflow B) using a self-contained ofn."""

from __future__ import annotations

from pathlib import Path

import pytest

from hpo_ai.apply.runner import apply_patch_bundle, parse_axioms_ofn

ROBOT = "/Users/matentzn/tools/robot"
HP = "http://purl.obolibrary.org/obo/HP_"


def test_parse_axioms_ofn() -> None:
    out = parse_axioms_ofn(
        f"EquivalentClasses(<{HP}0002490> ObjectSomeValuesFrom(<a> <b>))\n"
    )
    assert out == {f"{HP}0002490": "ObjectSomeValuesFrom(<a> <b>)"}


@pytest.mark.integration
@pytest.mark.skipif(not Path(ROBOT).exists(), reason="requires ROBOT")
def test_apply_bundle_end_to_end(tmp_path: Path) -> None:
    # A self-contained ontology (no imports) so ROBOT needs no catalog.
    edit = tmp_path / "hp-edit.ofn"
    edit.write_text(
        "Prefix(owl:=<http://www.w3.org/2002/07/owl#>)\n"
        "Prefix(rdfs:=<http://www.w3.org/2000/01/rdf-schema#>)\n"
        "Ontology(<http://example.org/o>\n"
        f"Declaration(Class(<{HP}0002490>))\n"
        f"Declaration(Class(<http://purl.obolibrary.org/obo/CHEBI_24996>))\n"
        f"Declaration(Class(<http://purl.obolibrary.org/obo/UBERON_0001359>))\n"
        f'AnnotationAssertion(rdfs:label <{HP}0002490> "Increased CSF lactate")\n'
        ")\n"
    )
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "axioms.ofn").write_text(
        f"EquivalentClasses(<{HP}0002490> "
        f"ObjectSomeValuesFrom(<http://purl.obolibrary.org/obo/BFO_0000051> "
        f"<http://purl.obolibrary.org/obo/CHEBI_24996>))\n"
    )
    (bundle / "update.ru").write_text(
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        "PREFIX oio: <http://www.geneontology.org/formats/oboInOwl#>\n"
        f"DELETE {{ <{HP}0002490> rdfs:label ?l }}\n"
        f'INSERT {{ <{HP}0002490> rdfs:label "Elevated CSF lactate concentration" }}\n'
        f'WHERE  {{ <{HP}0002490> rdfs:label ?l . FILTER(str(?l) = "Increased CSF lactate") }} ;\n\n'
        f'INSERT DATA {{ <{HP}0002490> oio:hasExactSynonym "Increased CSF lactate" }}\n'
    )

    report = apply_patch_bundle(bundle, edit, robot=ROBOT)
    assert report.sparql_applied is True
    assert f"{HP}0002490" in report.eq.added

    text = edit.read_text()
    assert '"Elevated CSF lactate concentration"' in text
    assert "hasExactSynonym" in text and "Increased CSF lactate" in text
    assert "EquivalentClasses(" in text
    assert "CHEBI_24996" in text
