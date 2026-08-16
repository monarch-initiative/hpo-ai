"""Tests for preferred clinical term detection and promotion."""

from __future__ import annotations

from pathlib import Path

from hpo_ai.associate import Association, DeterministicAssociator
from hpo_ai.associate.preferred import clinical_synonym
from hpo_ai.datamodel import ChemicalEntityEvidence, HPTerm, Synonym, SynonymScope
from hpo_ai.generate import materialize
from hpo_ai.patterns.loader import load_patterns

PATTERNS = load_patterns(Path(__file__).parent.parent / "patterns")


class FakeResolver:
    def __init__(self, mapping):
        self.mapping = mapping

    def resolve(self, name, max_results=5):
        if name in self.mapping:
            cid, conf = self.mapping[name]
            return [ChemicalEntityEvidence(id="e", entity_id=cid, entity_label=name,
                                           confidence=conf)]
        return []


def test_clinical_synonym_blood_increased() -> None:
    assert clinical_synonym(["Hyperglycemia"], "increased", "UBERON:0000178") == "Hyperglycemia"
    assert clinical_synonym(["Hyperglycemia"], "decreased", "UBERON:0000178") is None
    assert clinical_synonym(["High blood sugar"], "increased", "UBERON:0000178") is None


def _common_resolver(is_common):
    """A preferred-term resolver stub judging (or finding) a term's commonness."""
    def resolver(direction, chemical, fluid, candidate=None):
        term = candidate if candidate is not None else "Hyperuricemia"
        return (term, is_common)
    return resolver


def test_promotes_common_clinical_synonym_to_primary() -> None:
    term = HPTerm(
        id="HP:0003074",
        label="Increased blood glucose concentration",
        synonyms=[Synonym(value="Hyperglycemia", scope=SynonymScope.exact)],
    )
    assoc = DeterministicAssociator(
        PATTERNS, chebi_resolver=FakeResolver({"glucose": ("CHEBI:17234", 0.95)}),
        preferred_term_resolver=_common_resolver(True),
    ).associate(term)

    assert isinstance(assoc, Association)
    assert assoc.preferred_label == "Hyperglycemia"
    assert assoc.preferred_source == "synonym"

    proposal = materialize(term, assoc)
    assert proposal.proposed_label == "Hyperglycemia"
    assert proposal.proposed_synonyms is not None
    syns = {s.value for s in proposal.proposed_synonyms}
    assert "Elevated circulating glucose concentration" in syns
    assert "Increased blood glucose concentration" in syns


def test_obscure_clinical_synonym_kept_as_synonym_not_promoted() -> None:
    """An obscure term (judged OBSCURE) stays descriptive + keeps the term as synonym."""
    term = HPTerm(
        id="HP:0003074",
        label="Increased blood glucose concentration",
        synonyms=[Synonym(value="Hyperglucosemia", scope=SynonymScope.exact)],
    )
    assoc = DeterministicAssociator(
        PATTERNS, chebi_resolver=FakeResolver({"glucose": ("CHEBI:17234", 0.95)}),
        preferred_term_resolver=_common_resolver(False),
    ).associate(term)

    assert isinstance(assoc, Association)
    assert assoc.preferred_label is None
    assert assoc.clinical_synonym_to_add == "Hyperglucosemia"

    proposal = materialize(term, assoc)
    assert proposal.proposed_label == "Elevated circulating glucose concentration"
    assert proposal.proposed_synonyms is not None
    assert "Hyperglucosemia" in {s.value for s in proposal.proposed_synonyms}


def test_no_promotion_without_clinical_synonym() -> None:
    """A CSF term with no clinical synonym keeps the descriptive pattern label."""
    term = HPTerm(id="HP:0410071", label="Increased CSF ribitol concentration")
    assoc = DeterministicAssociator(
        PATTERNS, chebi_resolver=FakeResolver({"ribitol": ("CHEBI:15963", 0.9)})
    ).associate(term)
    assert isinstance(assoc, Association)
    assert assoc.preferred_label is None
    proposal = materialize(term, assoc)
    assert proposal.proposed_label == "Elevated CSF ribitol concentration"


def test_obscure_term_without_resolver_defaults_to_not_promoted() -> None:
    """With no commonness signal, a candidate is treated as obscure (kept as synonym)."""
    term = HPTerm(
        id="HP:0002490",
        label="Increased CSF lactate",
        synonyms=[Synonym(value="Hyperlactatorachia", scope=SynonymScope.exact)],
    )
    assoc = DeterministicAssociator(
        PATTERNS, chebi_resolver=FakeResolver({"lactate": ("CHEBI:24996", 0.95)})
    ).associate(term)
    assert isinstance(assoc, Association)
    assert assoc.preferred_label is None  # no commonness signal -> not promoted
    assert assoc.clinical_synonym_to_add == "Hyperlactatorachia"
    proposal = materialize(term, assoc)
    assert proposal.proposed_label == "Elevated CSF lactate concentration"


def test_llm_oracle_finds_and_promotes_common_term() -> None:
    """No synonym: the oracle finds a term and, if common, promotes it."""
    term = HPTerm(id="HP:0002149", label="Increased blood urate concentration")

    def oracle(direction, chemical, fluid, candidate=None):
        assert (direction, chemical, fluid, candidate) == ("increased", "urate", "blood", None)
        return ("Hyperuricemia", True)

    assoc = DeterministicAssociator(
        PATTERNS, chebi_resolver=FakeResolver({"urate": ("CHEBI:17775", 0.9)}),
        preferred_term_resolver=oracle,
    ).associate(term)
    assert isinstance(assoc, Association)
    assert assoc.preferred_label == "Hyperuricemia"
    assert assoc.preferred_source == "llm"


def test_llm_oracle_obscure_found_term_kept_as_synonym() -> None:
    """An oracle-found but obscure term is added as a synonym, not promoted."""
    term = HPTerm(id="HP:9", label="Increased blood widgetol concentration")

    def oracle(direction, chemical, fluid, candidate=None):
        return ("Hyperwidgetolemia", False)

    assoc = DeterministicAssociator(
        PATTERNS, chebi_resolver=FakeResolver({"widgetol": ("CHEBI:1", 0.9)}),
        preferred_term_resolver=oracle,
    ).associate(term)
    assert isinstance(assoc, Association)
    assert assoc.preferred_label is None
    assert assoc.clinical_synonym_to_add == "Hyperwidgetolemia"
    proposal = materialize(term, assoc)
    assert proposal.proposed_synonyms is not None
    assert "Hyperwidgetolemia" in {s.value for s in proposal.proposed_synonyms}
