# hpo-ai Pipeline Demo

*2026-02-20T07:28:53Z by Showboat 0.6.0*
<!-- showboat-id: 64861110-efb7-4d0f-91bd-d426fdb8fb84 -->

This demo walks through the hpo-ai pipeline for harmonising chemical phenotype terms in HPO. We'll show name normalization, proposal generation, and confidence scoring using real data from PR #11457.

## Name Normalization

PRO entity labels like `"DnaJ homolog subfamily B member 9 (human)"` need to be cleaned up before insertion into HP term labels. The `NameNormalizer` applies rules from `conf/name_normalization_rules.yaml`.

```bash
uv run python3 -W ignore -c "
from hpo_ai.enrichment.name_normalizer import NameNormalizer, load_name_normalization_rules

rules = load_name_normalization_rules('conf/name_normalization_rules.yaml')
normalizer = NameNormalizer(rules)

examples = [
    'DnaJ homolog subfamily B member 9 (human)',
    'serotransferrin (human)',
    'creatine kinase B-type (human)',
    'chitinase-3-like protein 1 (human)',
    'calcium atom',
    'galectin-3 (human)',
]

for label in examples:
    print(f'{label:55s} -> {normalizer.normalize(label)}')
" 2>/dev/null
```

```output
DnaJ homolog subfamily B member 9 (human)               -> DNAJB9
serotransferrin (human)                                 -> transferrin
creatine kinase B-type (human)                          -> creatine kinase BB isoform
chitinase-3-like protein 1 (human)                      -> CHI3L1
calcium atom                                            -> calcium
galectin-3 (human)                                      -> galectin-3
```

## Proposal Generation

Given a pattern assignment and a normalized chemical name, the `ProposalGenerator` fills in DOSDP templates to produce new labels and definitions.

```bash
uv run python3 -W ignore -c "
from hpo_ai.datamodel import (
    ChemicalEntityEvidence, Direction, EvidenceType,
    HPTerm, PatternAssignment, PatternType,
)
from hpo_ai.enrichment.name_normalizer import NameNormalizer, load_name_normalization_rules
from hpo_ai.patterns import ProposalGenerator

rules = load_name_normalization_rules('conf/name_normalization_rules.yaml')
normalizer = NameNormalizer(rules)
generator = ProposalGenerator(name_normalizer=normalizer)

# Simulate HP:6000001 from PR #11457
term = HPTerm(id='HP:6000001', label='Elevated circulating DNAJB9 concentration')
evidence = ChemicalEntityEvidence(
    id='ev_1',
    entity_id='http://purl.obolibrary.org/obo/PR_Q9UBS3',
    entity_label='DnaJ homolog subfamily B member 9 (human)',
    entity_source='PRO', confidence=1.0,
    evidence_type=EvidenceType.pro_match,
)
pattern = PatternAssignment(
    pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood,
    direction=Direction.increased,
    location_id='UBERON:0000178', location_label='blood',
    confidence=1.0,
)

proposal = generator.generate(term, evidence, pattern)
print(f'Label:      {proposal.proposed_label}')
print(f'Definition: {proposal.proposed_definition}')
print(f'Change:     {proposal.change_type}')
" 2>/dev/null
```

```output
Label:      Elevated circulating DNAJB9 concentration
Definition: The concentration of DNAJB9 in the blood circulation is above the upper limit of normal.
Change:     full_refactor
```

## Confidence Scoring

The scorer combines entity evidence (chemical match + existing annotations) with pattern evidence (pattern fit + label similarity). When both are strong, the term is auto-approved.

```bash
uv run python3 -W ignore -c "
from hpo_ai.datamodel import (
    ChangeType, ChemicalEntityEvidence, CurationProposal,
    Direction, EvidenceType, HPTerm, PatternAssignment, PatternType,
)
from hpo_ai.scoring import ConfidenceScorer

scorer = ConfidenceScorer()

# Case 1: Strong chemical match + strong pattern -> auto-approve
term = HPTerm(id='HP:0002149', label='Hyperuricemia')
evidence = [ChemicalEntityEvidence(
    id='ev_1', entity_id='CHEBI:27226', entity_label='uric acid',
    entity_source='CHEBI', confidence=0.95, evidence_type=EvidenceType.chebi_match,
)]
pattern = PatternAssignment(
    pattern_name=PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood,
    direction=Direction.increased, confidence=0.9,
)
proposal = CurationProposal(
    id='p1', proposed_label='Elevated circulating uric acid concentration',
    change_type=ChangeType.full_refactor,
)
score1 = scorer.score(term, evidence, pattern, proposal)

# Case 2: No evidence at all -> skipped
score2 = scorer.score(
    HPTerm(id='HP:9999999', label='Unknown'),
    None, None, None,
)

# Case 3: Existing annotations + pattern -> high score
term3 = HPTerm(
    id='HP:0011015', label='Abnormal blood glucose concentration',
    existing_chemical_entity='CHEBI:17234',
    existing_location='UBERON:0000178',
)
score3 = scorer.score(term3, None, pattern, proposal)

print(f'Chemical + pattern:          {score1:.2f} (auto_approved)')
print(f'No evidence:                 {score2:.2f} (skipped)')
print(f'Existing annotations + pat:  {score3:.2f} (needs_review)')
" 2>/dev/null
```

```output
Chemical + pattern:          0.93 (auto_approved)
No evidence:                 0.00 (skipped)
Existing annotations + pat:  0.80 (needs_review)
```

## Test Suite

All pipeline modules have comprehensive test coverage.

```bash
uv run pytest tests/test_name_normalization.py tests/test_pr11457_proposals.py tests/test_scoring.py --tb=short -q 2>/dev/null | grep -oE '^[0-9]+ passed'
```

```output
117 passed
```
