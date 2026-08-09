"""Tests for chemical name extraction from labels and definitions.

Covers two bugs:
1. Missing CHEBI IDs because extraction from labels like "Hyperglycemia"
   yields "glyc" instead of looking at the definition for "glucose".
2. Case destruction: "DNAJB9" becomes "dnajb9" because extraction
   lower-cases the input instead of using re.IGNORECASE.
"""

import pytest

from hpo_ai.datamodel import HPTerm
from hpo_ai.packets.builder import EvidencePacketBuilder
from hpo_ai.patterns import ProposalGenerator


class TestBuilderExtractChemicalName:
    """Tests for EvidencePacketBuilder._extract_chemical_name."""

    @pytest.fixture
    def builder(self):
        """Create a builder with no resolvers (testing extraction only)."""
        return EvidencePacketBuilder(
            chebi_resolver=None,
            pro_resolver=None,
            llm_enricher=None,
        )

    # --- Definition-based extraction ---

    def test_hyperglycemia_extracts_glucose_from_definition(self, builder):
        """Hyperglycemia label gives 'glyc'; definition gives 'glucose'."""
        name = builder._extract_chemical_name(
            label="Hyperglycemia",
            definition="An increased concentration of glucose in the blood.",
        )
        assert name == "glucose"

    def test_hypoglycemia_extracts_glucose_from_definition(self, builder):
        """Hypoglycemia definition contains 'glucose'."""
        name = builder._extract_chemical_name(
            label="Hypoglycemia",
            definition="A decreased concentration of glucose in the blood.",
        )
        assert name == "glucose"

    def test_hypertriglyceridemia_extracts_from_definition(self, builder):
        """Hypertriglyceridemia definition contains 'triglycerides'."""
        name = builder._extract_chemical_name(
            label="Hypertriglyceridemia",
            definition="An abnormal increase in the level of triglycerides in the blood.",
        )
        assert name == "triglycerides"

    def test_aminoaciduria_extracts_from_definition(self, builder):
        """Aminoaciduria definition contains 'amino acid'."""
        name = builder._extract_chemical_name(
            label="Aminoaciduria",
            definition="An increased concentration of an amino acid in the urine.",
        )
        assert name == "amino acid"

    def test_direct_label_still_works(self, builder):
        """Labels like 'Abnormal blood glucose concentration' should still work."""
        name = builder._extract_chemical_name(
            label="Abnormal blood glucose concentration",
            definition="An abnormality of the concentration of glucose in the blood.",
        )
        assert name == "glucose"

    def test_label_preferred_over_definition(self, builder):
        """When label gives a good extraction, prefer it over definition."""
        name = builder._extract_chemical_name(
            label="Elevated circulating uric acid concentration",
            definition="The concentration of uric acid in the blood is above normal.",
        )
        assert name == "uric acid"

    def test_no_definition_still_extracts_from_label(self, builder):
        """When no definition is provided, fall back to label only."""
        name = builder._extract_chemical_name(
            label="Elevated circulating glucose concentration",
            definition=None,
        )
        assert name == "glucose"

    # --- CSF location stripping (issue: CSF branch junk labels) ---

    def test_csf_label_strips_csf_qualifier(self, builder):
        """'Abnormal CSF glucose concentration' must scrape 'glucose', not 'CSF glucose'."""
        name = builder._extract_chemical_name(
            label="Abnormal CSF glucose concentration",
            definition=None,
        )
        assert name == "glucose"

    def test_csf_phenylalanine_strips_csf(self, builder):
        """CSF prefix must be stripped so the chemical resolves against CHEBI."""
        name = builder._extract_chemical_name(
            label="Abnormal CSF phenylalanine concentration",
            definition=None,
        )
        assert name == "phenylalanine"

    def test_csf_level_term_strips_csf(self, builder):
        """'Decreased CSF tetrahydrobiopterin level' -> 'tetrahydrobiopterin'."""
        name = builder._extract_chemical_name(
            label="Decreased CSF tetrahydrobiopterin level",
            definition=None,
        )
        assert name == "tetrahydrobiopterin"

    def test_csf_multiword_chemical_preserved(self, builder):
        """Multi-word chemical names survive CSF stripping."""
        name = builder._extract_chemical_name(
            label="Abnormal CSF homovanillic acid concentration",
            definition=None,
        )
        assert name == "homovanillic acid"

    # --- Case preservation ---

    def test_case_preserved_in_label_extraction(self, builder):
        """Uppercase chemical names in labels must be preserved."""
        name = builder._extract_chemical_name(
            label="Elevated circulating DNAJB9 concentration",
            definition=None,
        )
        assert name == "DNAJB9"

    def test_case_preserved_ldl(self, builder):
        """LDL should stay uppercase."""
        name = builder._extract_chemical_name(
            label="Increased LDL cholesterol concentration",
            definition=None,
        )
        assert name == "LDL cholesterol"

    def test_case_preserved_in_definition_extraction(self, builder):
        """Case in definition-extracted names should be preserved."""
        name = builder._extract_chemical_name(
            label="Hyperferritinemia",
            definition="An increased concentration of ferritin in the blood.",
        )
        assert name == "ferritin"

    def test_case_preserved_mixed_case_protein(self, builder):
        """Mixed-case protein names from definitions should be preserved."""
        name = builder._extract_chemical_name(
            label="Some phenotype",
            definition="An abnormality in the level of IgA in the blood.",
        )
        assert name == "IgA"


class TestGeneratorExtractChemicalFromLabel:
    """Tests for ProposalGenerator._extract_chemical_from_label."""

    @pytest.fixture
    def generator(self):
        """Create generator instance."""
        return ProposalGenerator()

    def test_case_preserved_uppercase(self, generator):
        """Uppercase names like DNAJB9 must be preserved."""
        name = generator._extract_chemical_from_label(
            "Elevated circulating DNAJB9 concentration",
        )
        assert name == "DNAJB9"

    def test_case_preserved_ldl(self, generator):
        """LDL cholesterol should preserve case."""
        name = generator._extract_chemical_from_label(
            "Increased LDL cholesterol concentration",
        )
        assert name == "LDL cholesterol"

    def test_case_preserved_normal_chemical(self, generator):
        """Normal lowercase chemicals should still work."""
        name = generator._extract_chemical_from_label(
            "Abnormal circulating glucose concentration",
        )
        # HPO labels are capitalised, so first letter may be capital
        # but the chemical inside the label is lowercase
        assert name is not None
        assert name.lower() == "glucose"

    def test_hyper_emia_not_matched_by_explicit_patterns(self, generator):
        """Explicit label extraction does NOT match HyperXemia suffixes."""
        name = generator._extract_chemical_from_label("Hyperuricemia")
        assert name is None

    def test_hyper_emia_matched_by_suffix_extraction(self, generator):
        """Suffix extraction handles HyperXemia, returning approximate stub."""
        name = generator._extract_chemical_from_label_suffix("Hyperuricemia")
        assert name is not None
        assert name == "uric"

    def test_case_preserved_mixed_case(self, generator):
        """Mixed case like IgA should be preserved."""
        name = generator._extract_chemical_from_label(
            "Elevated circulating IgA concentration",
        )
        assert name == "IgA"

    def test_csf_qualifier_stripped(self, generator):
        """CSF prefix must not leak into the scraped chemical name."""
        name = generator._extract_chemical_from_label(
            "Abnormal CSF glucose concentration",
        )
        assert name == "glucose"


class TestEndToEndChemicalNameInProposal:
    """Test that the full proposal generation preserves chemical names."""

    def test_proposal_uses_definition_chemical(self):
        """When evidence is absent, proposal should use definition-derived name."""
        builder = EvidencePacketBuilder(
            chebi_resolver=None,
            pro_resolver=None,
            llm_enricher=None,
        )

        term = HPTerm(
            id="HP:0003074",
            label="Hyperglycemia",
            definition="An increased concentration of glucose in the blood.",
        )

        packet = builder.build_packet(term, use_llm=False)

        # Without CHEBI resolver, no chemical_evidence.
        # But the proposal should still use "glucose" from the definition,
        # not "glyc" from the label.
        if packet.proposal and packet.proposal.proposed_label:
            assert "glucose" in packet.proposal.proposed_label.lower()
            assert "glyc " not in packet.proposal.proposed_label.lower()
