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


linkml_meta = LinkMLMeta({'default_prefix': 'hpoaipat',
     'default_range': 'string',
     'description': 'A simplified, DOSDP-like pattern schema for pattern-driven '
                    'curation of chemical phenotypes. Mimics the structure of '
                    "HPO's dosdp-patterns-hpo (vars, name, def, synonyms, "
                    'equivalentTo) with named ``{var}`` placeholders, plus a '
                    '``selector`` for association and ``allow_string`` for the '
                    'case where a chemical filler is a bare string rather than a '
                    'resolved ontology entity.',
     'id': 'https://w3id.org/obophenotype/hpo-ai/pattern',
     'imports': ['linkml:types'],
     'name': 'hpo_ai_pattern',
     'prefixes': {'hpoaipat': {'prefix_prefix': 'hpoaipat',
                               'prefix_reference': 'https://w3id.org/obophenotype/hpo-ai/pattern/'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'}},
     'source_file': 'src/hpo_ai/patterns/schema/pattern.yaml',
     'title': 'HPO-AI Pattern Schema'} )

class DirectionSelector(str, Enum):
    """
    Direction of abnormality a pattern applies to.
    """
    increased = "increased"
    decreased = "decreased"
    abnormal = "abnormal"


class SynScope(str, Enum):
    """
    Scope of a synonym.
    """
    exact = "exact"
    related = "related"
    broad = "broad"
    narrow = "narrow"



class Selector(ConfiguredBaseModel):
    """
    How an HP term is matched to a pattern.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai/pattern'})

    direction: DirectionSelector = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Selector']} })
    location: Optional[str] = Field(default=None, description="""UBERON id of the fluid/anatomical location, if the pattern is location-specific.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Selector']} })


class Var(ConfiguredBaseModel):
    """
    A pattern variable and the ontology class it ranges over.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai/pattern'})

    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Var', 'Pattern']} })
    range: Optional[str] = Field(default=None, description="""CURIE of the class this variable ranges over (e.g. CHEBI:24431).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Var']} })
    allow_string: Optional[bool] = Field(default=False, description="""Whether this variable may be filled by a bare string when no entity resolves.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Var'], 'ifabsent': 'False'} })
    fixed: Optional[bool] = Field(default=False, description="""Whether this variable is fixed by the pattern (e.g. the location) rather than extracted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Var'], 'ifabsent': 'False'} })


class SynonymTemplate(ConfiguredBaseModel):
    """
    A synonym text template.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai/pattern'})

    scope: SynScope = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SynonymTemplate']} })
    text: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SynonymTemplate']} })


class Pattern(ConfiguredBaseModel):
    """
    A simplified DOSDP pattern.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/obophenotype/hpo-ai/pattern',
         'tree_root': True})

    id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Pattern']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Pattern']} })
    selector: Selector = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Pattern']} })
    qualifier: Optional[str] = Field(default=None, description="""Fluid-first qualifier used in text (e.g. CSF, circulating, urinary).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Pattern']} })
    vars: Optional[list[Var]] = Field(default=[], json_schema_extra = { "linkml_meta": {'domain_of': ['Pattern']} })
    name: str = Field(default=..., description="""Label template with named {var} placeholders.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Var', 'Pattern']} })
    definition: Optional[str] = Field(default=None, description="""Definition template with named {var} placeholders.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Pattern']} })
    synonyms: Optional[list[SynonymTemplate]] = Field(default=[], json_schema_extra = { "linkml_meta": {'domain_of': ['Pattern']} })
    equivalentTo: Optional[str] = Field(default=None, description="""OWL logical (Manchester-style) template with named {var} placeholders.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Pattern']} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
Selector.model_rebuild()
Var.model_rebuild()
SynonymTemplate.model_rebuild()
Pattern.model_rebuild()
