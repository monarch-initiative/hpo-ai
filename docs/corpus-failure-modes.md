# Regression corpus & failure-mode triage

This corpus pins the pattern-driven pipeline against real curator output, mined
from the five merged **metabolism refactor** PRs:

| PR | Title |
|----|-------|
| [#11616](https://github.com/obophenotype/human-phenotype-ontology/pull/11616) | Circulating organic compounds refactoring (Batch 2) |
| [#11488](https://github.com/obophenotype/human-phenotype-ontology/pull/11488) | Refactoring of Blood Ion branch |
| [#11466](https://github.com/obophenotype/human-phenotype-ontology/pull/11466) | Metabolic phenotype refactor: batch 3 |
| [#11457](https://github.com/obophenotype/human-phenotype-ontology/pull/11457) | Metabolism phenotypes refactoring (batch 2) |
| [#11380](https://github.com/obophenotype/human-phenotype-ontology/pull/11380) | 40 manually curated protein-concentration refactorings |

`scripts/extract_corpus.py` parses each PR's `hp-edit.owl` diff into
`tests/corpus/corpus.tsv` (211 term-records): the **before** label (pipeline
input) and the curator's **after** state (label, definition, exact synonyms,
`EquivalentClasses`). `tests/corpus_runner.py` replays the pipeline offline —
label/definition generation needs no resolver, and EQ generation is exercised by
injecting the curator's chemical id via a stub resolver. This isolates two
questions: *can we reproduce the curator's label?* and *given the right chemical,
can we build the curator's axiom?*

`tests/test_corpus_regression.py` locks two invariants: the pass count never
regresses, and **EQ generation is byte-exact once a term maps**.

## Headline result

**94 / 211 terms reproduced end-to-end, offline, deterministic-only** (no LLM,
no OAK). More importantly: **for every term that maps, the generated
`EquivalentClasses` axiom matches the curator's exactly (91/91 with an EQ).** The
entire remaining failure surface is in the *association* stage (labelling and
term-to-pattern mapping), never in axiom construction. The role-based EQ work
(`has role` for CHEBI:50906 fillers) is covered by `tests/test_role_patterns.py`;
these PRs predate role modelling and use direct fillers only.

## Failure modes

| Mode | Count | Disposition |
|------|-------|-------------|
| `pass` | 94 | — |
| `unmapped:opaque_clinical` | 44 | **LLM tier.** Portmanteau labels (`Hypoalbuminemia`, `Hyperamylasemia`) carry no compositional chemical span; they map only with the agentic clinical extractor (`--use-llm`), which the offline harness deliberately omits. Not a defect. |
| `unmapped:no_location` | 22 | **Design — location inference.** Protein terms whose label omits a fluid (`Elevated prostate-specific antigen level`) but which the curator placed in blood/`circulating`. Needs a policy for defaulting/ inferring location. See `issues/`. |
| `fail:name_normalization` | 19 | **Name canonicalisation.** Abbreviations (`carcinoembryonic antigen` → `CEA`) and other curator-preferred forms. Needs a name-normalisation resource. |
| `fail:name_component_dropped` | 15 | **Name canonicalisation (bug-adjacent).** A name component is lost, often because a fluid word is part of the name (`serum amyloid A` → `amyloid A`, `vitamin K-dependent protein Z` → `protein Z`). |
| `fail:name_hyphenation` | 12 | **Name canonicalisation.** Hyphen/space and roman↔arabic numeral differences (`fetuin A` → `fetuin-A`, `transcobalamin I` → `transcobalamin-1`). |
| `fail:enzyme_activity` | 3 | **Design — activity pattern.** Enzyme phenotypes are about *activity*, not concentration (`creatine kinase` → `... activity`). Needs an activity pattern family. |
| `fail:label_case` | 1 | Minor casing (`Angiotensin-converting enzyme` → lower-case). Folded into name canonicalisation. |
| `unmapped:no_pattern` | 1 | Enzyme activity (`beta-hexosaminidase activity`) — same as `enzyme_activity`. |

## Naming rules: a finding, not a lift

The `update-chemical-labels.ru` name-canonicalisation + enzyme-activity rules are
now ported into `conf/name_normalization_rules.yaml` and applied in production
(`run_curate` → `materialize`). Applying them **does not lift this corpus** — it is
slightly net-negative — for two structural reasons the corpus itself exposed:

- **The corpus inputs are already human-normalised labels**, not the *systematic*
  CHEBI/PRO names the `.ru` renames target (`alpha-2-HS-glycoprotein → fetuin-A`
  only fires when the input actually is the systematic name). Our extracted chemical
  spans rarely contain them, so the renames don't fire on the corpus. Their real
  value is on resolved entity labels in production.
- **The historical golden partly predates the current `.ru`.** Applying the enzyme
  rule faithfully turns `amylase`, `matrix metalloproteinase 2`, and the CK `BB`/`MM`
  isoforms into `... activity`, but those merged terms were curated as
  `... concentration`; and `phenylalanine → L-phenylalanine` disagrees with a term
  the curators left non-L. These are either curator inconsistencies or terms merged
  before the rule landed.

So the normaliser is **deliberately not applied in the corpus scorer** (which guards
association/EQ accuracy on realistic inputs); it is validated by dedicated tests
(`tests/test_name_normalization.py`) and shipped for production. The open lever for
actually raising label accuracy is naming from the *resolved entity's systematic
label* (then normalising) — a design change, not a rule port.

## Already fixed from this corpus

- `"Abnormality of X"` phrasing now yields `direction=abnormal` + the chemical
  span (was `unmapped:no_chemical`).
- `"Diminished"` recognised as a decreased synonym.
- Obsolete terms (`obsolete …`) are excluded — never curation inputs.

## Open work (tracked as issues)

The remaining modes collapse to three pieces of real work:

1. **Chemical/protein name canonicalisation** (46 terms: normalization +
   component-dropped + hyphenation + case) — a name-normalisation resource that
   maps a chemical/protein to the curator's preferred surface form.
2. **Location inference** (22 terms) — a policy for supplying `blood`/
   `circulating` when the label omits the fluid but context implies it.
3. **Enzyme-activity patterns** (4 terms) — an activity pattern family distinct
   from concentration.

Opaque clinical terms (44) are not open work: they are handled by the agentic
tier in production.
