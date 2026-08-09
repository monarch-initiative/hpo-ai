"""Tests for KGCL patch construction."""

from __future__ import annotations

from hpo_ai.datamodel import CurationProposal, Synonym, SynonymScope
from hpo_ai.patch.kgcl import build_kgcl, validate_kgcl
from hpo_ai.read.current_state import TermState


def _proposal(label=None, definition=None, synonyms=None):
    return CurationProposal(
        id="prop_x",
        proposed_label=label,
        proposed_definition=definition,
        proposed_synonyms=synonyms,
    )


def test_label_rename_emitted_and_parses() -> None:
    state = TermState(id="HP:0002490", label="Increased CSF lactate")
    prop = _proposal(label="Elevated CSF lactate concentration")
    stmts = build_kgcl(state, prop)
    assert stmts == [
        "rename HP:0002490 from 'Increased CSF lactate' "
        "to 'Elevated CSF lactate concentration'"
    ]
    assert validate_kgcl(stmts) == []


def test_no_change_emits_nothing() -> None:
    state = TermState(id="HP:0002490", label="Elevated CSF lactate concentration")
    prop = _proposal(label="Elevated CSF lactate concentration")
    assert build_kgcl(state, prop) == []


def test_new_synonym_only_for_absent_values() -> None:
    state = TermState(
        id="HP:0002490",
        label="Elevated CSF lactate concentration",
        synonyms=["Hyperlactatorachia"],
    )
    prop = _proposal(
        label="Elevated CSF lactate concentration",
        synonyms=[
            Synonym(value="Hyperlactatorachia", scope=SynonymScope.exact),  # already present
            Synonym(value="Increased CSF lactate", scope=SynonymScope.exact),  # new
        ],
    )
    stmts = build_kgcl(state, prop)
    assert stmts == ["create exact synonym 'Increased CSF lactate' for HP:0002490"]
    assert validate_kgcl(stmts) == []


def test_change_vs_add_definition() -> None:
    with_def = TermState(id="HP:1", label="L", definition="Old definition.")
    prop = _proposal(label="L", definition="New definition.")
    assert build_kgcl(with_def, prop) == [
        "change definition of HP:1 from 'Old definition.' to 'New definition.'"
    ]

    no_def = TermState(id="HP:2", label="L")
    prop2 = _proposal(label="L", definition="A brand new definition.")
    assert build_kgcl(no_def, prop2) == [
        "add definition 'A brand new definition.' to HP:2"
    ]


def test_validate_flags_unparseable_apostrophe() -> None:
    state = TermState(id="HP:3", label="L")
    prop = _proposal(
        label="L",
        synonyms=[Synonym(value="3'-phosphoadenosine level", scope=SynonymScope.exact)],
    )
    stmts = build_kgcl(state, prop)
    # The apostrophe value cannot be represented in the single-quote-only grammar.
    assert validate_kgcl(stmts) == stmts
