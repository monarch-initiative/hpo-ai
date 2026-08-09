# hpo-ai

AI-assisted pipeline for **harmonising chemical phenotypes in the Human Phenotype Ontology (HPO)**.

> **Status: prototype / work in progress.** The pipeline described below is implemented and
> tested, but most of the source tree is still uncommitted local work (only a minimal
> scaffold is in git history). A redesign of the architecture is under active consideration —
> see [Project status & direction](#project-status--direction). Treat this README as a
> snapshot of the current state, not a stable spec.

---

## What it does

HPO contains hundreds of "chemical phenotype" terms — terms describing abnormal levels of a
chemical or protein entity in a body fluid (e.g. *Abnormal blood glucose concentration*,
*Hypercalcemia*, *Elevated circulating creatine kinase*). Many predate HPO's adoption of
[DOSDP](https://github.com/INCATools/dead_simple_owl_design_patterns) design patterns and are
inconsistent:

- **Arbitrary wording** — "glucose *level*" vs "calcium *concentration*" for identical semantics.
- **Missing logical definitions** — no OWL axiom linking the term to CHEBI/UBERON.
- **Wrong or missing CHEBI/PRO annotations** — ion form used where HPO conventionally uses the atom form.
- **Inconsistent abbreviation** — some labels use "CK", others spell out "creatine kinase".

`hpo-ai` automates the evidence-gathering, pattern-matching, and proposal-generation steps so a
human curator only has to review a pre-populated spreadsheet, then apply approved changes via a
ROBOT template.

For the full problem statement and design rationale see [`strategy.md`](strategy.md); for a
worked, stage-by-stage walkthrough see [`docs/overview.md`](docs/overview.md).

---

## Pipeline

```
Input (HP IDs / root term)
        │
        ▼
  1. extract          → candidates.json      (HPTerm objects, via OAK)
        │
        ▼
  2. build-packets    → packets.json         (EvidencePacket per term)
        │  ├─ resolve chemical entity (CHEBI/PRO; rules → OAK search → optional LLM)
        │  ├─ assign DOSDP pattern (direction + location heuristics)
        │  ├─ generate curation proposal (label / definition / axiom from template)
        │  └─ score & triage → auto_approved | needs_review | skipped
        ▼
  3. export           → review.tsv           (curated_phenotypes.tsv format)
        │                                      human curator reviews
        ▼
  4. generate-robot   → robot_template.tsv   (apply approved changes to hp-edit.owl)
```

Each stage is a standalone CLI command; `run-pipeline` chains them end to end.

### Confidence scoring

Overall confidence combines two equally-weighted dimensions, each the `max()` of two raw signals:

| Dimension | Signals | Question |
|---|---|---|
| Entity evidence (50%) | chemical match, existing annotations | Do we know *what chemical* this term is about? |
| Pattern evidence (50%) | pattern fit, label similarity | Do we know *which DOSDP template* to use? |

| Score | Status | Action |
|---|---|---|
| ≥ 0.9 | `auto_approved` | apply directly |
| 0.5 – 0.9 | `needs_review` | curator checks |
| < 0.5 | `skipped` | insufficient evidence |

---

## Installation & commands

The project uses [`uv`](https://docs.astral.sh/uv/) for dependencies and
[`just`](https://just.systems/) as the command runner.

```bash
uv sync --group dev        # install (or: just install)
just test                  # pytest + mypy + ruff
just pytest                # tests only
just _serve                # local docs server (mkdocs)
```

### CLI

```bash
uv run hpo-ai --help
```

| Command | Purpose |
|---|---|
| `extract` | Extract candidate chemical phenotypes from HPO (from a root term or a TSV of HP IDs) |
| `build-packets` | Resolve entities, assign patterns, generate proposals, score → evidence packets |
| `export` | Write packets to a review TSV (`curated_phenotypes.tsv` format) |
| `generate-robot` | Generate a ROBOT template from approved packets |
| `validate` | Check packets for errors/warnings before applying |
| `stats` | Summarise packets (status, patterns, change types, confidence buckets) |
| `run-pipeline` | Run extract → build-packets → export → ROBOT end to end |

Example full run:

```bash
uv run hpo-ai run-pipeline \
  --input example_output/sample_input.tsv \
  --output-dir output/ \
  --chebi-rules conf/chebi_selection_rules.yaml \
  --selection-guide conf/chebi_selection_guide.md \
  --normalization-rules conf/name_normalization_rules.yaml
```

Chemical resolution and the LLM enricher (`--use-llm`, Claude API) are **optional** layers; the
deterministic rule/search path runs without any API key.

---

## Repository layout

```
src/hpo_ai/
  cli.py                 # Typer CLI (the commands above)
  schema/hpo_ai.yaml     # LinkML schema — source of truth for the data model
  datamodel/             # Pydantic models generated from the schema
  extraction/            # HP term extraction via OAK
  enrichment/            # CHEBI + PRO resolution, LLM enricher, name normalization, selection rules
  patterns/              # DOSDP pattern assignment + proposal generation
  scoring/               # confidence scoring
  validation/            # proposal validation
  packets/               # EvidencePacketBuilder — orchestrates the above per term
  output/                # TSV export + ROBOT template generation

patterns/dosdp/          # DOSDP pattern YAMLs (abnormal / increased / decreased × blood / urine)
sparql/                  # SPARQL queries for term extraction
conf/                    # config.yaml, CHEBI selection rules + guide, name-normalization rules
docs/                    # MkDocs Material site (overview.md has the detailed walkthrough)
example_output/          # sample input + example pipeline outputs
tests/                   # pytest suite (~120 tests) incl. real-batch regression fixtures
```

### Data model (LinkML → Pydantic)

Defined in `src/hpo_ai/schema/hpo_ai.yaml`, regenerate models with
`uv run gen-pydantic src/hpo_ai/schema/hpo_ai.yaml > src/hpo_ai/datamodel/hpo_ai.py`.

- `HPTerm` — extracted term with label, definition, synonyms, existing annotations
- `ChemicalEntityEvidence` — a CHEBI/PRO match with confidence
- `PatternAssignment` — DOSDP pattern + location + direction
- `CurationProposal` — proposed label, definition, synonyms, logical axiom, change type
- `EvidencePacket` — container tying it all together with an overall score and review status
- `CurationBatch` / `BatchStats` / `PipelineConfig` — batch and config models

### Configuration

- `conf/config.yaml` — thresholds, scoring weights, ontology sources, preferred CHEBI forms, abbreviations
- `conf/chebi_selection_rules.yaml` — abbreviation lookups + curated name→CHEBI/PRO mappings (deterministic layer)
- `conf/chebi_selection_guide.md` — prose disambiguation rules injected into the LLM prompt (LLM layer)
- `conf/name_normalization_rules.yaml` — strip PRO species suffixes / verbose names (e.g. `DnaJ homolog … (human)` → `DNAJB9`)

Key domain convention: per [upheno#946](https://github.com/obophenotype/upheno/issues/946),
HPO uses **atom** forms of elements (e.g. `calcium atom`, not `calcium(2+)`).

---

## Tech stack

[OAK](https://incatools.github.io/ontology-access-kit/) (ontology access) ·
[LinkML](https://linkml.io/) + [Pydantic](https://docs.pydantic.dev/) (data model) ·
[DOSDP](https://github.com/INCATools/dead_simple_owl_design_patterns) patterns ·
[ROBOT](http://robot.obolibrary.org/) (OWL editing) ·
[Claude API](https://docs.anthropic.com/) (optional enrichment) ·
[Typer](https://typer.tiangolo.com/) (CLI) · Python 3.10+.

---

## Project status & direction

- The pipeline described above **works and is tested**, but is a prototype. Most of `src/`,
  `tests/`, `conf/`, `patterns/`, and `sparql/` is **uncommitted** local work on top of a minimal
  git scaffold.
- [`redesign.md`](redesign.md) sketches a possible architectural pivot: invert the design so
  **Claude is the orchestrator** and the Python modules become thin, deterministic, LLM-free
  helpers driven from `workflows/*.md`, rather than the current model where an LLM is called as a
  step *inside* the Python pipeline. This has **not** been implemented.
- [`todo.md`](todo.md) tracks specific curation-quality issues raised in review (e.g. G6PD should
  use "activity" not "concentration"; abbreviation-usage consistency).
- Related HPO work referenced by the strategy: PR #10560 (pipeline infra), PR #11380 (first
  protein-concentration batch), issue #11342 (naming conventions), upheno#946 (CHEBI alignment).

Expect the design to be reworked and a new spec to supersede parts of this document.

---

## License

Apache-2.0. See [`LICENSE`](LICENSE).
Docs are published at https://obophenotype.github.io/hpo-ai.
