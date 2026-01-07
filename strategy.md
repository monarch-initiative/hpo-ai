# HPO Chemical Phenotype Harmonisation Strategy

## Executive Summary

This document outlines a strategy for developing an AI-powered system to harmonise laboratory/chemical phenotypes in the Human Phenotype Ontology (HPO). The system will automate the curation of "concentration/level" phenotypes, ensuring consistent representation using DOSDP patterns while identifying cases requiring human review.

## Background

### Problem Statement

HPO contains thousands of "concentration/level/amount/circulating phenotypes" describing abnormalities in chemical levels (e.g., "Abnormal blood ion concentration", "Hyperkalemia"). These terms currently suffer from:

1. **Inconsistent naming**: e.g., "Abnormal blood X" vs "Abnormal circulating X"
2. **Missing or incorrect CHEBI/PRO mappings**: Terms lack proper chemical entity identifiers
3. **CHEBI ID inconsistencies**: HPO uses different CHEBI forms than GO/RHEA (e.g., `calcium atom` vs `calcium(2+)`)
4. **Pattern non-compliance**: Terms don't follow established DOSDP patterns
5. **Incomplete logical axioms**: Missing subclass relationships

### Existing Work

- **PR #10560**: Established the pipeline infrastructure with DOSDP patterns, SPARQL queries, and Jupyter notebooks
- **PR #11380**: First successful batch of 40 manually curated protein concentration refactorings
- **Issue #11342**: Finalised naming conventions for blood phenotypes
- **Issue upheno#946**: Documents CHEBI ID inconsistencies between HP and other ontologies

### Target Patterns

Terms should conform to these DOSDP patterns:
- `abnormalLevelOfChemicalEntityInBlood.yaml`
- `abnormalLevelOfChemicalEntityInUrine.yaml`
- `abnormalLevelOfChemicalEntityInLocation.yaml`
- `abnormallyIncreasedLevelOfChemicalEntityIn{Blood,Urine,Location}.yaml`
- `abnormallyDecreasedLevelOfChemicalEntityIn{Blood,Urine,Location}.yaml`

### Naming Conventions (from Issue #11342)

| Pattern | Label Template | Definition Template |
|---------|----------------|---------------------|
| Abnormal | `Abnormal circulating % concentration` | `Any deviation from the normal concentration of % in the blood circulation.` |
| Increased | `Elevated circulating % concentration` | `The concentration of % in the blood circulation is above the upper limit of normal.` |
| Decreased | `Decreased circulating % concentration` | `The concentration of % in the blood circulation is below the lower limit of normal.` |

---

## System Architecture

### Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HPO-AI Pipeline                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │   Extract    │───▶│   Enrich     │───▶│  Build Evidence      │  │
│  │  HP Terms    │    │  (CHEBI/PRO) │    │     Packets          │  │
│  └──────────────┘    └──────────────┘    └──────────────────────┘  │
│                                                   │                 │
│                                                   ▼                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │   Generate   │◀───│   Validate   │◀───│  Assign Patterns &   │  │
│  │   PR/Branch  │    │   & Score    │    │  Generate Proposals  │  │
│  └──────────────┘    └──────────────┘    └──────────────────────┘  │
│         │                   │                                       │
│         ▼                   ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Human Review Queue (when needed)                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. Term Extraction Module

Extract candidate chemical phenotypes from HPO using SPARQL queries (building on existing `list-chemical.sparql`).

#### 2. Evidence Packet System

Adapting the mondo-ai pattern, create evidence packets that collect:
- **CHEBI evidence**: Chemical entity matches with confidence scores
- **PRO evidence**: Protein entity matches for protein-based phenotypes
- **Pattern evidence**: Which DOSDP pattern the term should follow
- **Label/definition proposals**: if a pattern and a suitable CHEBI or PRO term exists, use the DOSDP patterns template specifications to generate label and synonyms. If not, just try to extract the correct chemical from the label and use that to generate the correct information. What is important: if there is a very widely used abbreviation that is preferable you can slot that into the entity definition - use an agent for that (perhaps in combination with literature search).


#### 3. AI-Powered Enrichment
Use LLMs (OntoGPT/Claude) to:
- Identify the chemical entity from term labels/definitions
- Map to CHEBI/PRO identifiers
- Handle ambiguous cases (L vs D forms, protonation states)
- Suggest pattern assignment
- Figure out if a widely used abbreviation is preferable to a full huge unwieldy name.

#### 4. Validation & Scoring
Score each proposed change based on:
- Confidence in CHEBI/PRO mapping (0-1)
- Pattern fit certainty
- Label change severity (minor vs major rewording)
- Potential for automated vs manual processing

#### 5. Chunk/Branch Management
Process terms in batches by:
- Anatomical location (blood, urine, CSF, etc.)
- Chemical class (ions, proteins, lipids, amino acids)
- Confidence level (high-confidence automated, low-confidence for review)

---

## Implementation Plan

### Phase 1: Project Setup

**Task 1.1: Initialize project with Monarch Copier template**
```bash
copier copy gh:monarch-initiative/monarch-project-template hpo-ai
```

**Task 1.2: Define data models (LinkML schema)**
Create `src/hpo_ai/schema/hpo_ai.yaml` defining:
- `ChemicalPhenotypeCandidate`: Extracted HP term with metadata
- `ChemicalEntityEvidence`: CHEBI/PRO match with confidence
- `PatternAssignment`: DOSDP pattern with slot values
- `CurationProposal`: Proposed label, definition, axioms
- `EvidencePacket`: Container for all evidence supporting a curation decision

**Task 1.3: Port existing infrastructure**
- Import DOSDP patterns from PR #10560
- Port SPARQL queries for term extraction
- Adapt Jupyter notebook pipeline to Python modules

### Phase 2: Evidence Collection Pipeline

**Task 2.1: Chemical Entity Resolution**

```python
class ChemicalEntityResolver:
    """Resolve HP term labels to CHEBI/PRO entities."""

    def resolve(self, hp_term: HPTerm) -> list[ChemicalEntityEvidence]:
        """
        1. Extract chemical name from label (rule-based + LLM)
        2. Search CHEBI for matches
        3. Search PRO for protein matches
        4. Handle protonation/stereochemistry variants
        5. Return ranked candidates with confidence scores
        """
```

**Task 2.2: Pattern Assignment**

```python
class PatternAssigner:
    """Assign DOSDP patterns based on term semantics."""

    PATTERNS = {
        'abnormalLevelOfChemicalEntityInBlood',
        'abnormallyIncreasedLevelOfChemicalEntityInBlood',
        'abnormallyDecreasedLevelOfChemicalEntityInBlood',
        # ... urine and location variants
    }

    def assign(self, hp_term: HPTerm, location: str,
               direction: str | None) -> PatternAssignment:
        """Determine appropriate pattern based on term semantics."""
```

**Task 2.3: Evidence Packet Builder**

```python
class EvidencePacketBuilder:
    """Build evidence packets for curation decisions."""

    def build_packet(
        self,
        hp_term: HPTerm,
        chemical_evidence: list[ChemicalEntityEvidence],
        pattern: PatternAssignment,
    ) -> EvidencePacket:
        """
        Combine all evidence into a packet with:
        - Original term data
        - Chemical entity candidates with scores
        - Pattern assignment with confidence
        - Generated label/definition proposals
        - Overall confidence score
        - Recommendation: AUTO_APPROVE | HUMAN_REVIEW | SKIP
        """
```

### Phase 3: Proposal Generation

**Task 3.1: Label/Definition Generator**

Using DOSDP templates, generate conformant labels and definitions:

```python
class ProposalGenerator:
    def generate(self, packet: EvidencePacket) -> CurationProposal:
        """
        Generate:
        - New rdfs:label following naming conventions
        - New definition following definition patterns
        - Synonyms (keep original label as exact synonym)
        - Logical axiom (equivalentClass using pattern)
        """
```

**Task 3.2: Change Detection**

```python
class ChangeDetector:
    def analyze(self, original: HPTerm, proposal: CurationProposal) -> ChangeReport:
        """
        Categorize changes:
        - LABEL_ONLY: Just label normalization
        - DEFINITION_ONLY: Just definition update
        - AXIOM_ONLY: Just adding/fixing logical axiom
        - FULL_REFACTOR: Multiple significant changes
        - NO_CHANGE: Term already conformant
        """
```

### Phase 4: Human Review Integration

**Task 4.1: Review Queue Management**

Cases requiring human review:
1. **Multiple CHEBI/PRO candidates** with similar confidence
2. **L vs D form ambiguity** for amino acids
3. **Protonation state decisions** (atom vs ion)
4. **Novel pattern requirements** (modifier phenotypes, combination phenotypes)
5. **Low confidence** chemical entity resolution (<0.7)
6. **Special categories**: "process", "activity", "modifier" phenotypes from TSV

**Task 4.2: Review Interface**

Generate review TSV files compatible with existing `curated_phenotypes.tsv` format:

| Column | Description |
|--------|-------------|
| `finished` | Status: `to do`, `done`, `ignore` |
| `hpo_id` | HP identifier |
| `hpo_label` | Current label |
| `correct_pattern` | Assigned DOSDP pattern |
| `chemical_entity` | Proposed CHEBI/PRO ID |
| `MANUAL PREFERRED LABEL` | For human override |
| `MANUAL PREFERRED DEFINITION` | For human override |
| `curator_comment` | Notes/questions |
| `evidence_summary` | AI-generated evidence summary |

### Phase 5: Output Generation

**Task 5.1: Branch/Chunk Generation**

```python
class BranchGenerator:
    def generate_branch(
        self,
        proposals: list[CurationProposal],
        branch_name: str,
        chunk_size: int = 50,
    ) -> Branch:
        """
        1. Create git branch
        2. Generate ROBOT template from approved proposals
        3. Apply changes to hp-edit.owl
        4. Run reasoner validation
        5. Generate diff report
        """
```

**Task 5.2: PR Generation**

Auto-generate PR descriptions with:
- Summary of changes
- Link to evidence packets
- Diff table (old label -> new label)
- Validation results

---

## Confidence Scoring & Automation Thresholds

### Confidence Score Components

| Component | Weight | Description |
|-----------|--------|-------------|
| Chemical match confidence | 0.4 | How confident is CHEBI/PRO match |
| Pattern fit | 0.2 | Does term semantics match pattern |
| Label similarity | 0.2 | How different is new label |
| Existing annotations | 0.2 | Does term already have some axioms |

### Automation Thresholds

| Overall Score | Action |
|---------------|--------|
| >= 0.9 | Auto-approve, include in batch PR |
| 0.7 - 0.9 | Auto-propose, flag for quick review |
| 0.5 - 0.7 | Human review required |
| < 0.5 | Skip or escalate to expert |

---

## Special Cases

### 1. Modifier Phenotypes
Terms like "Episodic ammonia intoxication", "Recurrent hypoglycemia" - these modify a base phenotype. Strategy:
- Identify as `modifier` pattern
- Flag for human review
- Consider if they need separate treatment

### 2. Combination Phenotypes
Terms like "Hyperinsulinemic hypoglycemia" combining multiple conditions. Strategy:
- Identify as `combination_phenotype` pattern
- Do not auto-process
- Queue for expert review

### 3. Process/Activity Phenotypes
Terms describing enzyme activities or metabolic processes. Strategy:
- Assign to `process` or `activity` pattern
- Different DOSDP patterns may be needed
- Coordinate with GO for process definitions

### 4. Immunoglobulins (IgA, IgG, IgM, IgE)
These proteins are not in CHEBI but are important. Strategy:
- Use PRO identifiers where available
- Create mapping table for common immunoglobulins
- May need custom handling

### 5. CHEBI Protonation State Alignment
Per upheno#946, HPO uses atoms while GO uses ions. Strategy:
- Document the HPO convention explicitly
- Create mapping table of preferred CHEBI IDs
- Flag cases where alignment with GO is desired

---

## CLI Interface

```bash
# Extract candidates
hpo-ai extract --branch chemical-phenotypes --output candidates.tsv

# Enrich with CHEBI/PRO mappings
hpo-ai enrich candidates.tsv --output enriched.tsv

# Build evidence packets
hpo-ai build-packets enriched.tsv --output packets.json

# Generate proposals
hpo-ai propose packets.json --output proposals.tsv

# Filter by confidence for human review
hpo-ai filter proposals.tsv --min-confidence 0.7 --output auto-approve.tsv
hpo-ai filter proposals.tsv --max-confidence 0.7 --output needs-review.tsv

# Generate branch with approved changes
hpo-ai generate-branch auto-approve.tsv --branch-name "chemical-phenotypes-batch-1"

# Generate PR
hpo-ai create-pr --branch "chemical-phenotypes-batch-1" --title "Harmonise chemical phenotypes (batch 1)"
```

---

## Project Structure

```
hpo-ai/
├── pyproject.toml
├── src/
│   └── hpo_ai/
│       ├── __init__.py
│       ├── cli.py                    # Click CLI
│       ├── config.py                 # Configuration
│       ├── schema/
│       │   └── hpo_ai.yaml          # LinkML schema
│       ├── datamodel/
│       │   └── hpo_ai.py            # Generated dataclasses
│       ├── extraction/
│       │   ├── __init__.py
│       │   └── extractor.py         # SPARQL-based extraction
│       ├── enrichment/
│       │   ├── __init__.py
│       │   ├── chebi.py             # CHEBI lookup
│       │   ├── pro.py               # PRO lookup
│       │   └── llm.py               # LLM-based resolution
│       ├── packets/
│       │   ├── __init__.py
│       │   └── builder.py           # Evidence packet builder
│       ├── patterns/
│       │   ├── __init__.py
│       │   ├── assigner.py          # Pattern assignment
│       │   └── generator.py         # Proposal generation
│       ├── validation/
│       │   ├── __init__.py
│       │   └── validator.py         # Validate proposals
│       ├── scoring/
│       │   ├── __init__.py
│       │   └── scorer.py            # Confidence scoring
│       └── output/
│           ├── __init__.py
│           ├── robot.py             # ROBOT template generation
│           ├── branch.py            # Git branch management
│           └── pr.py                # PR generation
├── conf/
│   ├── config.yaml                  # Default configuration
│   └── chebi_mappings.yaml          # Preferred CHEBI IDs
├── patterns/
│   └── dosdp/                       # DOSDP pattern files
├── sparql/
│   └── list-chemical.sparql         # Extraction queries
├── tests/
│   └── ...
└── notebooks/
    └── exploration.ipynb            # Analysis notebooks
```

---

## Success Metrics

1. **Coverage**: % of chemical phenotypes with CHEBI/PRO mappings
2. **Automation rate**: % of terms processed without human intervention
3. **Accuracy**: % of auto-approved changes accepted in PR review
4. **Consistency**: All processed terms conform to naming conventions
5. **Time savings**: Reduction in manual curation time per term

---

## Next Steps

1. **Initialize project** using Monarch copier template
2. **Define LinkML schema** for data models
3. **Implement extraction module** using existing SPARQL
4. **Build CHEBI/PRO resolution** with OAK integration
5. **Implement evidence packet system** adapted from mondo-ai
6. **Create scoring system** with tunable thresholds
7. **Test on protein concentration branch** (already partially done)
8. **Iterate** based on curator feedback

---

## References

- PR #10560: Pipeline infrastructure
- PR #11380: First successful refactoring batch
- Issue #11342: Naming conventions
- Issue upheno#946: CHEBI alignment issues
- mondo-ai: Evidence packet pattern reference
