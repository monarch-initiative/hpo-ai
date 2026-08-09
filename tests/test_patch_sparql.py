"""Tests for the KGCL->SPARQL compiler."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from hpo_ai.datamodel import CurationProposal
from hpo_ai.patch.sparql import compile_sparql, compile_term
from hpo_ai.read.current_state import TermState

ROBOT = "/Users/matentzn/tools/robot"
CLONE = Path(
    "/Users/matentzn/ws/projects/hpo-ai/github/human-phenotype-ontology/src/ontology"
)


def _prop(label=None, definition=None, synonyms=None):
    return CurationProposal(id="p", proposed_label=label,
                            proposed_definition=definition, proposed_synonyms=synonyms)


def test_label_op_structure() -> None:
    state = TermState(id="HP:0002490", label="Increased CSF lactate")
    ops = compile_term(state, _prop(label="Elevated CSF lactate concentration"))
    assert len(ops) == 1
    assert "rdfs:label" in ops[0]
    assert '"Elevated CSF lactate concentration"' in ops[0]
    assert 'FILTER(str(?l) = "Increased CSF lactate")' in ops[0]


def test_definition_op_is_reification_aware() -> None:
    state = TermState(id="HP:0002490", label="L", definition="Old def.")
    ops = compile_term(state, _prop(label="L", definition="New def."))
    op = ops[0]
    # updates BOTH the direct triple and the reified annotatedTarget
    assert "IAO:0000115" in op
    assert "owl:annotatedTarget" in op
    assert "OPTIONAL" in op


def test_add_definition_when_absent() -> None:
    state = TermState(id="HP:1", label="L")
    ops = compile_term(state, _prop(label="L", definition="A definition."))
    assert ops == ['INSERT DATA { <http://purl.obolibrary.org/obo/HP_1> '
                   'IAO:0000115 "A definition." }']


def test_empty_when_no_changes() -> None:
    state = TermState(id="HP:1", label="L", definition="D.")
    out = compile_sparql([(state, _prop(label="L", definition="D."))])
    assert "no annotation-level changes" in out


@pytest.mark.integration
@pytest.mark.skipif(
    not Path(ROBOT).exists() or not (CLONE / "hp-edit.owl").exists(),
    reason="requires ROBOT and the cloned hp-edit.owl",
)
def test_reification_no_duplicate_definition(tmp_path: Path) -> None:
    """Applying a def change to an axiom-annotated def yields exactly one def."""
    edit = tmp_path / "hp-edit.owl"
    shutil.copy(CLONE / "hp-edit.owl", edit)
    state = TermState(
        id="HP:0002490",
        label="Increased CSF lactate",
        definition="Increased concentration of lactate in the cerebrospinal fluid.",
        def_has_annotation=True,
    )
    prop = _prop(definition="The concentration of lactate in the CSF is above normal.")
    ru = tmp_path / "u.ru"
    ru.write_text(compile_sparql([(state, prop)]))
    out = tmp_path / "out.ofn"
    subprocess.run(
        [ROBOT, "query", "--catalog", str(CLONE / "catalog-v001.xml"),
         "--input", str(edit), "--update", str(ru),
         "--format", "ofn", "--output", str(out)],
        check=True, capture_output=True,
    )
    text = out.read_text()
    n = text.count("IAO_0000115> <http://purl.obolibrary.org/obo/HP_0002490>")
    assert n == 1, f"expected exactly one definition, found {n}"
