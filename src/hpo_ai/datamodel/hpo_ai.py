from __future__ import annotations

import re
import sys
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Literal,
    Optional,
    Union
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer
)


metamodel_version = "None"
version = "None"


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias = True,
        validate_by_name = True,
        validate_assignment = True,
        validate_default = True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        use_enum_values = True,
        strict = False,
    )

    @model_serializer(mode='wrap', when_used='unless-none')
    def treat_empty_lists_as_none(
            self, handler: SerializerFunctionWrapHandler,
            info: SerializationInfo) -> dict[str, Any]:
        if info.exclude_none:
            _instance = self.model_copy()
            for field, field_info in type(_instance).model_fields.items():
                if getattr(_instance, field) == [] and not(
                        field_info.is_required()):
                    setattr(_instance, field, None)
        else:
            _instance = self
        return handler(_instance, info)



class LinkMLMeta(RootModel):
    root: dict[str, Any] = {}
    model_config = ConfigDict(frozen=True)

    def __getattr__(self, key:str):
        return getattr(self.root, key)

    def __getitem__(self, key:str):
        return self.root[key]

    def __setitem__(self, key:str, value):
        self.root[key] = value

    def __contains__(self, key:str) -> bool:
        return key in self.root


linkml_meta = LinkMLMeta({'default_prefix': 'hpoai',
     'default_range': 'string',
     'description': 'Data models for AI-assisted curation of chemical phenotypes '
                    'in the Human Phenotype Ontology (HPO).',
     'id': 'https://w3id.org/obophenotype/hpo-ai',
     'imports': ['linkml:types'],
     'name': 'hpo_ai',
     'prefixes': {'CHEBI': {'prefix_prefix': 'CHEBI',
                            'prefix_reference': 'http://purl.obolibrary.org/obo/CHEBI_'},
                  'GO': {'prefix_prefix': 'GO',
                         'prefix_reference': 'http://purl.obolibrary.org/obo/GO_'},
                  'HP': {'prefix_prefix': 'HP',
                         'prefix_reference': 'http://purl.obolibrary.org/obo/HP_'},
                  'IAO': {'prefix_prefix': 'IAO',
                          'prefix_reference': 'http://purl.obolibrary.org/obo/IAO_'},
                  'PR': {'prefix_prefix': 'PR',
                         'prefix_reference': 'http://purl.obolibrary.org/obo/PR_'},
                  'UBERON': {'prefix_prefix': 'UBERON',
                             'prefix_reference': 'http://purl.obolibrary.org/obo/UBERON_'},
                  'hpoai': {'prefix_prefix': 'hpoai',
                            'prefix_reference': 'https://w3id.org/obophenotype/hpo-ai/'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'},
                  'oio': {'prefix_prefix': 'oio',
                          'prefix_reference': 'http://www.geneontology.org/formats/oboInOwl#'},
                  'rdfs': {'prefix_prefix': 'rdfs',
                           'prefix_reference': 'http://www.w3.org/2000/01/rdf-schema#'},
                  'skos': {'prefix_prefix': 'skos',
                           'prefix_reference': 'http://www.w3.org/2004/02/skos/core#'}},
     'source_file': '/Users/matentzn/ws/hpo-ai/src/hpo_ai/schema/hpo_ai.yaml',
     'title': 'HPO-AI Data Model'} )

class PatternType(str, Enum):
    """
    DOSDP pattern types for chemical phenotypes.
    """
    abnormalLevelOfChemicalEntityInBlood = "abnormalLevelOfChemicalEntityInBlood"
    """
    Abnormal level of a chemical in blood
    """
    abnormalLevelOfChemicalEntityInUrine = "abnormalLevelOfChemicalEntityInUrine"
    """
    Abnormal level of a chemical in urine
    """
    abnormalLevelOfChemicalEntityInLocation = "abnormalLevelOfChemicalEntityInLocation"
    """
    Abnormal level of a chemical in a specific location
    """
    abnormallyIncreasedLevelOfChemicalEntityInBlood = "abnormallyIncreasedLevelOfChemicalEntityInBlood"
    """
    Increased level of a chemical in blood
    """
    abnormallyIncreasedLevelOfChemicalEntityInUrine = "abnormallyIncreasedLevelOfChemicalEntityInUrine"
    """
    Increased level of a chemical in urine
    """
    abnormallyIncreasedLevelOfChemicalEntityInLocation = "abnormallyIncreasedLevelOfChemicalEntityInLocation"
    """
    Increased level of a chemical in a specific location
    """
    abnormallyDecreasedLevelOfChemicalEntityInBlood = "abnormallyDecreasedLevelOfChemicalEntityInBlood"
    """
    Decreased level of a chemical in blood
    """
    abnormallyDecreasedLevelOfChemicalEntityInUrine = "abnormallyDecreasedLevelOfChemicalEntityInUrine"
    """
    Decreased level of a chemical in urine
    """
    abnormallyDecreasedLevelOfChemicalEntityInLocation = "abnormallyDecreasedLevelOfChemicalEntityInLocation"
    """
    Decreased level of a chemical in a specific location
    """
    abnormalAbsenceOfChemicalEntity = "abnormalAbsenceOfChemicalEntity"
    """
    Abnormal absence of a chemical entity
    """
    modifier = "modifier"
    """
    Modifier phenotype (e.g., episodic, recurrent)
    """
    combination_phenotype = "combination_phenotype"
    """
    Combination of multiple phenotypes
    """
    process = "process"
    """
    Process or metabolic pathway phenotype
    """
    activity = "activity"
    """
    Enzyme activity phenotype
    """
    method_observed = "method_observed"
    """
    Method-specific observation
    """
    unknown = "unknown"
    """
    Pattern could not be determined
    """


class Direction(str, Enum):
    """
    Direction of the abnormality.
    """
    increased = "increased"
    """
    Level is above normal
    """
    decreased = "decreased"
    """
    Level is below normal
    """
    abnormal = "abnormal"
    """
    Level deviates from normal (direction unspecified)
    """


class EvidenceType(str, Enum):
    """
    Type of evidence supporting a curation decision.
    """
    chebi_match = "chebi_match"
    """
    Direct match to CHEBI term
    """
    pro_match = "pro_match"
    """
    Direct match to PRO (Protein Ontology) term
    """
    llm_extraction = "llm_extraction"
    """
    Chemical entity extracted by LLM
    """
    pattern_inference = "pattern_inference"
    """
    Pattern inferred from term structure
    """
    literature_support = "literature_support"
    """
    Evidence from literature search
    """
    existing_axiom = "existing_axiom"
    """
    Evidence from existing ontology axiom
    """


class ReviewStatus(str, Enum):
    """
    Status of the curation proposal.
    """
    pending = "pending"
    """
    Not yet reviewed
    """
    auto_approved = "auto_approved"
    """
    Automatically approved (high confidence)
    """
    needs_review = "needs_review"
    """
    Requires human review
    """
    approved = "approved"
    """
    Approved by curator
    """
    rejected = "rejected"
    """
    Rejected by curator
    """
    skipped = "skipped"
    """
    Skipped (e.g., not a chemical phenotype)
    """


class ChangeType(str, Enum):
    """
    Type of change proposed.
    """
    label_only = "label_only"
    """
    Only the label is changing
    """
    definition_only = "definition_only"
    """
    Only the definition is changing
    """
    axiom_only = "axiom_only"
    """
    Only adding/fixing logical axiom
    """
    full_refactor = "full_refactor"
    """
    Multiple significant changes
    """
    no_change = "no_change"
    """
    Term already conformant
    """


class SynonymScope(str, Enum):
    """
    Scope of synonym.
    """
    exact = "exact"
    """
    Exact synonym
    """
    narrow = "narrow"
    """
    Narrower meaning
    """
    broad = "broad"
    """
    Broader meaning
    """
    related = "related"
    """
    Related term
    """



class HPTerm(ConfiguredBaseModel):
    """
    An extracted HP term that is a candidate for chemical phenotype curation.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai'})

    id: str = Field(default=..., description="""HP term identifier (e.g., HP:0001943)""", json_schema_extra = { "linkml_meta": {'domain_of': ['HPTerm',
                       'ChemicalEntityEvidence',
                       'CurationProposal',
                       'EvidencePacket',
                       'CurationBatch']} })
    label: str = Field(default=..., description="""Current rdfs:label of the term""", json_schema_extra = { "linkml_meta": {'domain_of': ['HPTerm']} })
    definition: Optional[str] = Field(default=None, description="""Current definition (IAO:0000115)""", json_schema_extra = { "linkml_meta": {'domain_of': ['HPTerm']} })
    synonyms: Optional[list[Synonym]] = Field(default=[], description="""Current synonyms""", json_schema_extra = { "linkml_meta": {'domain_of': ['HPTerm']} })
    parents: Optional[list[str]] = Field(default=[], description="""Direct parent HP term IDs""", json_schema_extra = { "linkml_meta": {'domain_of': ['HPTerm']} })
    existing_chemical_entity: Optional[str] = Field(default=None, description="""Existing CHEBI/PRO annotation if present""", json_schema_extra = { "linkml_meta": {'domain_of': ['HPTerm']} })
    existing_location: Optional[str] = Field(default=None, description="""Existing anatomical location (UBERON) if present""", json_schema_extra = { "linkml_meta": {'domain_of': ['HPTerm']} })
    existing_logical_definition: Optional[str] = Field(default=None, description="""Existing logical definition if present""", json_schema_extra = { "linkml_meta": {'domain_of': ['HPTerm']} })


class Synonym(ConfiguredBaseModel):
    """
    A synonym with scope information.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai'})

    value: str = Field(default=..., description="""The synonym text""", json_schema_extra = { "linkml_meta": {'domain_of': ['Synonym']} })
    scope: Optional[SynonymScope] = Field(default=None, description="""Scope of the synonym""", json_schema_extra = { "linkml_meta": {'domain_of': ['Synonym']} })


class ChemicalEntityEvidence(ConfiguredBaseModel):
    """
    Evidence for a CHEBI or PRO entity match.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai'})

    id: str = Field(default=..., description="""Unique evidence ID""", json_schema_extra = { "linkml_meta": {'domain_of': ['HPTerm',
                       'ChemicalEntityEvidence',
                       'CurationProposal',
                       'EvidencePacket',
                       'CurationBatch']} })
    entity_id: str = Field(default=..., description="""CHEBI or PRO identifier""", json_schema_extra = { "linkml_meta": {'domain_of': ['ChemicalEntityEvidence']} })
    entity_label: str = Field(default=..., description="""Label of the chemical/protein entity""", json_schema_extra = { "linkml_meta": {'domain_of': ['ChemicalEntityEvidence']} })
    entity_source: Optional[str] = Field(default=None, description="""Source ontology (CHEBI or PRO)""", json_schema_extra = { "linkml_meta": {'domain_of': ['ChemicalEntityEvidence']} })
    confidence: Optional[float] = Field(default=None, description="""Confidence score for this match""", ge=0.0, le=1.0, json_schema_extra = { "linkml_meta": {'domain_of': ['ChemicalEntityEvidence', 'PatternAssignment']} })
    evidence_type: Optional[EvidenceType] = Field(default=None, description="""How this match was determined""", json_schema_extra = { "linkml_meta": {'domain_of': ['ChemicalEntityEvidence']} })
    match_description: Optional[str] = Field(default=None, description="""Explanation of why this entity was matched""", json_schema_extra = { "linkml_meta": {'domain_of': ['ChemicalEntityEvidence']} })
    preferred_abbreviation: Optional[str] = Field(default=None, description="""Widely used abbreviation if applicable (e.g., LDL, HDL, CK)""", json_schema_extra = { "linkml_meta": {'domain_of': ['ChemicalEntityEvidence']} })
    is_protonated_form: Optional[bool] = Field(default=None, description="""Whether this is an ionized/protonated form""", json_schema_extra = { "linkml_meta": {'domain_of': ['ChemicalEntityEvidence']} })
    is_stereoisomer: Optional[bool] = Field(default=None, description="""Whether this is a specific stereoisomer (L/D form)""", json_schema_extra = { "linkml_meta": {'domain_of': ['ChemicalEntityEvidence']} })
    alternative_forms: Optional[list[str]] = Field(default=[], description="""Alternative CHEBI IDs (e.g., atom vs ion)""", json_schema_extra = { "linkml_meta": {'domain_of': ['ChemicalEntityEvidence']} })


class PatternAssignment(ConfiguredBaseModel):
    """
    Assignment of a DOSDP pattern to an HP term.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai'})

    pattern_name: PatternType = Field(default=..., description="""Name of the DOSDP pattern""", json_schema_extra = { "linkml_meta": {'domain_of': ['PatternAssignment']} })
    direction: Optional[Direction] = Field(default=None, description="""Direction of abnormality""", json_schema_extra = { "linkml_meta": {'domain_of': ['PatternAssignment']} })
    location_id: Optional[str] = Field(default=None, description="""Anatomical location (UBERON ID)""", json_schema_extra = { "linkml_meta": {'domain_of': ['PatternAssignment']} })
    location_label: Optional[str] = Field(default=None, description="""Label of anatomical location""", json_schema_extra = { "linkml_meta": {'domain_of': ['PatternAssignment']} })
    confidence: Optional[float] = Field(default=None, description="""Confidence in pattern assignment""", ge=0.0, le=1.0, json_schema_extra = { "linkml_meta": {'domain_of': ['ChemicalEntityEvidence', 'PatternAssignment']} })
    rationale: Optional[str] = Field(default=None, description="""Explanation for pattern choice""", json_schema_extra = { "linkml_meta": {'domain_of': ['PatternAssignment']} })
    requires_new_pattern: Optional[bool] = Field(default=None, description="""Whether a new DOSDP pattern is needed""", json_schema_extra = { "linkml_meta": {'domain_of': ['PatternAssignment']} })


class CurationProposal(ConfiguredBaseModel):
    """
    A proposed change to an HP term.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai'})

    id: str = Field(default=..., description="""Unique proposal ID""", json_schema_extra = { "linkml_meta": {'domain_of': ['HPTerm',
                       'ChemicalEntityEvidence',
                       'CurationProposal',
                       'EvidencePacket',
                       'CurationBatch']} })
    proposed_label: Optional[str] = Field(default=None, description="""New proposed label""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationProposal']} })
    proposed_definition: Optional[str] = Field(default=None, description="""New proposed definition""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationProposal']} })
    proposed_synonyms: Optional[list[Synonym]] = Field(default=[], description="""Proposed synonyms (including original label as exact synonym)""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationProposal']} })
    proposed_chemical_entity: Optional[str] = Field(default=None, description="""Proposed CHEBI/PRO ID""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationProposal']} })
    proposed_location: Optional[str] = Field(default=None, description="""Proposed anatomical location""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationProposal']} })
    proposed_logical_definition: Optional[str] = Field(default=None, description="""Proposed OWL logical definition""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationProposal']} })
    change_type: Optional[ChangeType] = Field(default=None, description="""Type of change being proposed""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationProposal']} })
    label_diff: Optional[str] = Field(default=None, description="""Description of label change""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationProposal']} })
    definition_diff: Optional[str] = Field(default=None, description="""Description of definition change""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationProposal']} })


class EvidencePacket(ConfiguredBaseModel):
    """
    Container for all evidence supporting a curation decision for an HP term.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai'})

    id: str = Field(default=..., description="""Unique packet ID (e.g., pkt_abc123)""", json_schema_extra = { "linkml_meta": {'domain_of': ['HPTerm',
                       'ChemicalEntityEvidence',
                       'CurationProposal',
                       'EvidencePacket',
                       'CurationBatch']} })
    hp_term: HPTerm = Field(default=..., description="""The HP term being curated""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidencePacket']} })
    chemical_evidence: Optional[list[ChemicalEntityEvidence]] = Field(default=[], description="""Evidence for chemical entity matches""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidencePacket']} })
    pattern_assignment: Optional[PatternAssignment] = Field(default=None, description="""Assigned DOSDP pattern""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidencePacket']} })
    proposal: Optional[CurationProposal] = Field(default=None, description="""Generated curation proposal""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidencePacket']} })
    overall_confidence: Optional[float] = Field(default=None, description="""Overall confidence score""", ge=0.0, le=1.0, json_schema_extra = { "linkml_meta": {'domain_of': ['EvidencePacket']} })
    review_status: Optional[ReviewStatus] = Field(default=None, description="""Current review status""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidencePacket']} })
    curator_notes: Optional[str] = Field(default=None, description="""Notes from curator review""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidencePacket']} })
    created_at: Optional[datetime ] = Field(default=None, description="""When this packet was created""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidencePacket', 'CurationBatch']} })
    updated_at: Optional[datetime ] = Field(default=None, description="""When this packet was last updated""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidencePacket']} })


class CurationBatch(ConfiguredBaseModel):
    """
    A batch of evidence packets for processing together.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai'})

    id: str = Field(default=..., description="""Unique batch ID""", json_schema_extra = { "linkml_meta": {'domain_of': ['HPTerm',
                       'ChemicalEntityEvidence',
                       'CurationProposal',
                       'EvidencePacket',
                       'CurationBatch']} })
    name: Optional[str] = Field(default=None, description="""Human-readable batch name""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationBatch']} })
    description: Optional[str] = Field(default=None, description="""Description of what this batch contains""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationBatch']} })
    packets: Optional[list[EvidencePacket]] = Field(default=[], description="""Evidence packets in this batch""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationBatch']} })
    filter_criteria: Optional[str] = Field(default=None, description="""How terms were selected for this batch""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationBatch']} })
    created_at: Optional[datetime ] = Field(default=None, description="""When this batch was created""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidencePacket', 'CurationBatch']} })
    stats: Optional[BatchStats] = Field(default=None, description="""Statistics about this batch""", json_schema_extra = { "linkml_meta": {'domain_of': ['CurationBatch']} })


class BatchStats(ConfiguredBaseModel):
    """
    Statistics about a curation batch.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai'})

    total_terms: Optional[int] = Field(default=None, description="""Total number of terms in batch""", json_schema_extra = { "linkml_meta": {'domain_of': ['BatchStats']} })
    auto_approved: Optional[int] = Field(default=None, description="""Terms auto-approved""", json_schema_extra = { "linkml_meta": {'domain_of': ['BatchStats']} })
    needs_review: Optional[int] = Field(default=None, description="""Terms needing human review""", json_schema_extra = { "linkml_meta": {'domain_of': ['BatchStats']} })
    high_confidence: Optional[int] = Field(default=None, description="""Terms with confidence >= 0.9""", json_schema_extra = { "linkml_meta": {'domain_of': ['BatchStats']} })
    medium_confidence: Optional[int] = Field(default=None, description="""Terms with confidence 0.7-0.9""", json_schema_extra = { "linkml_meta": {'domain_of': ['BatchStats']} })
    low_confidence: Optional[int] = Field(default=None, description="""Terms with confidence < 0.7""", json_schema_extra = { "linkml_meta": {'domain_of': ['BatchStats']} })


class PipelineConfig(ConfiguredBaseModel):
    """
    Configuration for the HPO-AI pipeline.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai'})

    auto_approve_threshold: Optional[float] = Field(default=None, description="""Minimum confidence for auto-approval (default 0.9)""", json_schema_extra = { "linkml_meta": {'domain_of': ['PipelineConfig']} })
    review_threshold: Optional[float] = Field(default=None, description="""Minimum confidence to include in review queue (default 0.5)""", json_schema_extra = { "linkml_meta": {'domain_of': ['PipelineConfig']} })
    chebi_weight: Optional[float] = Field(default=None, description="""Weight for CHEBI match confidence""", json_schema_extra = { "linkml_meta": {'domain_of': ['PipelineConfig']} })
    pattern_weight: Optional[float] = Field(default=None, description="""Weight for pattern fit confidence""", json_schema_extra = { "linkml_meta": {'domain_of': ['PipelineConfig']} })
    label_similarity_weight: Optional[float] = Field(default=None, description="""Weight for label similarity""", json_schema_extra = { "linkml_meta": {'domain_of': ['PipelineConfig']} })
    preferred_chebi_forms: Optional[list[str]] = Field(default=[], description="""List of preferred CHEBI ID conventions""", json_schema_extra = { "linkml_meta": {'domain_of': ['PipelineConfig']} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
HPTerm.model_rebuild()
Synonym.model_rebuild()
ChemicalEntityEvidence.model_rebuild()
PatternAssignment.model_rebuild()
CurationProposal.model_rebuild()
EvidencePacket.model_rebuild()
CurationBatch.model_rebuild()
BatchStats.model_rebuild()
PipelineConfig.model_rebuild()
