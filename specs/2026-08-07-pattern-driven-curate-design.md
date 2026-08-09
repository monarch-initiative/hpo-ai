# Pattern-driven curation workflow — design spec

Date: 2026-08-07 (updated 2026-08-08)
Status: approved design, pre-implementation

## Problem

The current pipeline hard-codes label/definition templates (the CSF `FLUID_*`
tables in `patterns/generator.py`), assigns patterns with shallow keyword logic,
and applies only label renames. We want:

- **pattern-driven generation** — every piece of generated content (label,
  definition, synonyms, logical axiom) comes from a declared pattern, the way a
  DOSDP does;
- **smarter pattern association** that reads the label, not just keywords, with a
  deterministic tier and an agentic fallback;
- a **clear report of terms that could not be mapped** to a pattern; and
- a clean split between **producing** a patch and **applying** it.

The twist that DOSDP does not handle: the **chemical entity may be a bare
string** (no confident CHEBI/PRO match). Then we cannot emit the equivalence
(EQ) axiom, but we can still generate the label, definition, and synonyms.

## Two workflows

The pipeline is two separate commands. Everything up to *produce patch* is one
workflow; *apply* is a second.

```text
Workflow A — generate (hpo-ai curate):
  read branch -> scan term -> associate pattern -> refactor/enrich per pattern -> produce patch

Workflow B — apply (hpo-ai apply):
  take patch + hp-edit.owl -> apply -> normalise -> validate
```

- `hpo-ai curate --branch HP:0025454 --pattern-dir patterns/ --hpo hp-edit.owl [--use-llm] [--out out/]`
  reads the branch and each term's current state from `--hpo`, associates a
  pattern, materialises pattern-conformant content, and writes the patch bundle.
  **It never mutates `hp-edit.owl`.**
- `hpo-ai apply --patch out/ --hpo hp-edit.owl` applies the patch bundle to
  `hp-edit.owl` and validates. Separate invocation, separately runnable.

## Goals / non-goals

Goals: the simple LinkML pattern schema (seeded from HPO's nine DOSDP patterns),
pattern-conformant generation with the string fallback, two-tier association,
unmapped reporting, and a standard-tool apply with no meaningful diff noise.

Non-goals: reasoning/classification of the result (left to the ODK release
pipeline); inventing new CHEBI/PRO terms; a general OWL editor.

## Pattern schema (LinkML)

A pattern file is a simplified DOSDP: same shape (`vars`, `name`, `def`,
`synonyms`, `equivalentTo`), plus a `selector` (how association matches it) and
per-var `allow_string` (the twist). Templates use named `{var}` placeholders
rather than DOSDP positional `%s`. Meta-schema classes: `Pattern`, `Var`,
`SynonymTemplate`, generated to Pydantic with `gen-pydantic`.

Example (the CSF / issue #11702 case):

```yaml
id: increasedChemicalInCSF
selector: { direction: increased, location: UBERON:0001359 }
qualifier: "CSF"
vars:
  chemical: { range: CHEBI:24431, allow_string: true }
  location: { range: UBERON:0001359, fixed: true }
name:       "Elevated {qualifier} {chemical} concentration"
definition: "The concentration of {chemical} in the {location_label} is above the upper limit of normal."
synonyms:
  - { scope: exact, text: "Increased {chemical} concentration" }
  - { scope: exact, text: "Elevated {chemical} level" }
equivalentTo: "'has_part' some ('increased amount' and ('inheres_in' some ({chemical} and ('part_of' some {location}))) and ('has_modifier' some 'abnormal'))"
```

### Seeded pattern set

One file per (direction × fluid). Seeded from HPO's nine DOSDP patterns, but the
name/def templates **encode the #11702 conventions**, which the stock
`…InLocation` pattern (`"Decreased level of X in Y"`) does not. Fluid qualifier
by location: blood → `circulating`, urine → `urinary`, CSF → `CSF`.

## Pattern association (two tiers)

Association is the smart core, and it is deliberately label-aware — it parses the
term's label structure, not just the presence of keywords.

### Tier 1 — deterministic

Inputs: the term's label, definition, synonyms, and existing axioms. Steps:

1. Parse the **label** into (direction word, fluid qualifier, chemical span,
   measurement noun) using the pattern set's known vocabulary — e.g. "Increased
   CSF taurine concentration" → direction=increased, fluid=CSF, chemical="taurine".
   Location detection uses word boundaries (fixes the `taurine`→`urine` bug).
2. Corroborate with the definition and any existing EQ axiom (e.g. an existing
   `part_of UBERON:0001359` confirms CSF).
3. Match to the pattern whose `selector` fits (direction, location).
4. Resolve the chemical span via the CHEBI/PRO resolver + scorer → entity or
   string.
5. Emit `(pattern, fillers, confidence)` with the evidence used.

A term is **cleanly mapped** by Tier 1 when exactly one pattern matches and the
signals agree (label, definition, existing axiom).

### Tier 2 — agentic (only when `--use-llm`)

For the residue Tier 1 cannot confidently map — ambiguous or unusual labels,
tied patterns, direction/location not parseable — an LLM agent is given the term
(label, def, synonyms, existing axioms) and the **catalog of available patterns**
(their descriptions and selectors) and asked to choose the best pattern and
extract fillers, returning a rationale and a confidence. Its output re-enters the
same materialisation path. The agent may only *select among existing patterns and
extract fillers*; it does not invent patterns or free-text content.

### Clinical (portmanteau) terms

Opaque clinical terms like ``Hypoglycorrhachia`` encode direction, fluid, and
chemical in one word. Direction comes from the ``hypo``/``hyper`` prefix and
fluid from the suffix (``-rrhachia`` = CSF, ``-emia`` = blood, ``-uria`` =
urine) via deterministic rules; the **chemical concept** (glyco- = glucose) is
recovered by a small, focused LLM step (``associate/clinical.py``, injectable and
mock-tested). When this route fires, the term takes the **clinical route** and is
flagged ``preserve_current_label``.

For a preserved term, materialisation keeps the **current clinical label as the
primary** ``rdfs:label`` and demotes the pattern-generated label
(``Decreased CSF glucose concentration``) to an **exact synonym** — the reverse
of the normal rename, where the pattern label becomes primary and the old label
becomes the synonym. Definition and EQ are still generated in both cases.

### Preferred clinical term (e.g. "Hyperglycemia") — gated on *commonness*

A clinical term is used as the primary label only when it is **common** (a
clinician would routinely use it); an **obscure** but technically-correct term
(e.g. "Hyperlactatorachia") is kept as an exact synonym instead. Commonness — not
fluid — is the deciding signal, so a common CSF term would promote and an obscure
blood term would not.

Finding the candidate term:

1. **Deterministic (free):** an existing clinical-morphology exact synonym
   matching the association's direction + fluid (`hyper…`/`hypo…` + `…emia`,
   `…rrhachia`).
2. **Oracle find (blood/urine only):** if there is no such synonym, a tiny call
   finds one. (CSF is skipped here only to avoid wasted NONE calls.)

Judging commonness: a cheap, cached LLM call (or a curated flag) classifies the
candidate `COMMON`/`OBSCURE`. Both the term and the `common` flag live in the
locked `mappings/preferred_clinical_term.tsv`, keyed on `(direction, chemical,
fluid)`, so each concept is decided once and a curator can flip `common` on a
single row. Negatives are cached. With no LLM and no curated row, a candidate is
treated as obscure (kept as a synonym) — safe by default.

Materialisation: a **common** term becomes the primary `rdfs:label` (pattern label
+ current label demoted to exact synonyms); an **obscure** term is added as an
exact synonym while the descriptive pattern label stays primary. `review.tsv`
records `preferred_label` and `primary_label_source ∈ {current_clinical, synonym,
llm, pattern}`.

### Unmapped / ambiguous reporting (first-class output)

Any term that neither tier maps confidently is written to
`out/unmapped.tsv` with an explicit reason, and counted in the run summary.
Reasons include: no direction detected, no location detected, no matching
pattern, multiple patterns tie, chemical unresolved and `allow_string` false,
agentic tier declined / low confidence. This is a required deliverable, not a log
line — the curator must be able to see exactly which HP IDs in the branch fell
through and why.

## LLM decision caching — human-auditable, edit-preserving stores

LLM extraction is not cached as opaque prompt-hash blobs. Following MeDIC's
`LiteralMappingStore` pattern (`mappings/*.sssom.tsv` + a lock gate), each LLM
step reads/writes a **git-diffable TSV keyed on a meaningful string** that is at
once the cache, the audit trail, and the human-override surface:

- **Clinical chemical grounding** (`mappings/clinical_chemical.sssom.tsv`): an
  SSSOM literal-mappings profile, clinical term label → CHEBI/PR, with `method`,
  `agent_version` (dated model id), `confidence`, `status`, and an explicit
  `sssom:NoTermFound` row for unresolved terms (a complete audit).
- **Pattern association** (`mappings/pattern_association.tsv`): HP id → pattern id
  for **every** pick (both tiers), so the ledger is a complete audit. A curator
  locks a row (edit `pattern_id`, set `status=CONFIRMED` or `method=HUMAN`) and
  the deterministic associator **honours the override** on the next run.
- **Preferred clinical term** (`mappings/preferred_clinical_term.tsv`): concept
  `(direction, chemical, fluid)` → clinical term + a `common` flag (curatable),
  with a negative cache.

Reused verbatim from MeDIC: the **lock gate** — a row is curator-owned (and never
overwritten by a re-run) when `mapping_justification = semapv:ManualMappingCuration`,
`status ∈ {CONFIRMED, REJECTED}`, or `method = HUMAN`. The associators **read
through** these stores before calling the LLM, so a curated (or previously cached)
row short-circuits the model and honours a hand-edited CHEBI. The vendored
`schema/provenance.yaml` (from MeDIC) is the shared vocabulary. Stores load even
offline, so curated clinical mappings resolve terms with no LLM call.

## Generation (materialisation)

For a mapped term, fill the pattern templates:

- Text (name/def/synonyms) always fills — with the entity label *or* the string.
- `equivalentTo` fills **only in the entity case**. String case → no EQ. ← the
  twist.
- Diff against current state → only genuine deltas become patch operations; a
  term already conformant produces nothing.

Per decision: label, definition, and EQ all **overwrite** by default.

## Patch bundle (Workflow A output)

Written to `--out`:

- `curate.kgcl` — KGCL patch for annotation-level changes (rename / create exact
  synonym / change definition), validated with `kgcl_schema.grammar.parser`. The
  interoperable, tool-standard artifact.
- `axioms.ofn` — EQ axioms to add/replace (KGCL cannot express nested class
  expressions).
- `update.ru` — the SPARQL update compiled from the KGCL (audit + the exact thing
  apply runs, under the stop-gap).
- `review.tsv` — human-review export.
- `unmapped.tsv` — terms not cleanly mapped, with reasons.

## Apply (Workflow B) — a documented stop-gap

The apply mechanism is a **stop-gap**; the intended end state is a single
`ontology.apply_patch(kgcl)` covering all change types (see
`issues/issue_kgcl_apply_patch.md`). Diff noise from apply is acceptable **as
long as a subsequent `robot convert` re-normalises** the output — so the bar for
the eventual upstream solution is correctness and coverage, not byte-clean diffs.

Until then, `hpo-ai apply` uses the mechanisms proven clean in the feasibility
spikes:

1. **Surgical EQ edit** on the `.ofn` text (entity case only): delete the term's
   defining `EquivalentClasses(` `[Annotation(...)]` `<id> …)` line and insert the
   new one (add if absent). One axiom per line → clean single-line match. The
   only bespoke step.
2. **`robot query --update update.ru`** applies label/synonym/definition through
   ROBOT's OWLAPI model — including the **reification-aware definition update**
   (rewrites `owl:annotatedTarget`, not just the direct triple, so an
   axiom-annotated def is not duplicated). This pass also re-serialises the
   surgical EQ edit canonically.
3. **`robot convert`** final pass → canonical output; assert the diff touches
   only intended lines (benign exception: ROBOT de-duplicating pre-existing
   duplicate axioms).

Dependency: `apply` needs ROBOT + resolvable imports (to load `hp-edit.owl`).
Without imports it cannot apply; `curate` still produces the full patch bundle.

## Feasibility findings (spikes, 2026-08-07)

1. `robot convert` reproduces `hp-edit.owl` byte-for-byte — ROBOT/OWLAPI is the
   canonical serializer.
2. `robot query --update` gives a clean canonical diff for label + synonym (even
   regenerates the `# Class:` comment).
3. Definitions carry axiom annotations; a naive SPARQL def change leaves a
   duplicate via the reified `owl:annotatedTarget` — must rewrite the reification.
4. `kgcl_rdflib` / OAK `apply` are not usable as-is for in-place edits: rdflib
   serialization is non-canonical, plus a missing-`HP`-prefix `KeyError` and a
   silent no-op `rename`. These are the upstream gaps captured in the KGCL issue.
5. `horned-functional`/py-horned-owl would also reserialize non-canonically.

## Module layout

- `src/hpo_ai/patterns/schema/pattern.yaml` — LinkML meta-schema; generated model.
- `patterns/` — the seeded pattern set.
- `src/hpo_ai/patterns/loader.py` — load + validate a pattern directory.
- `src/hpo_ai/associate/deterministic.py` — Tier 1 label-aware matcher (refactor
  of `assigner.py`).
- `src/hpo_ai/associate/agentic.py` — Tier 2 LLM matcher over the pattern catalog.
- `src/hpo_ai/associate/report.py` — unmapped/ambiguous classification + `unmapped.tsv`.
- `src/hpo_ai/generate/materialize.py` — fill templates → `CurationProposal`
  (replaces the hard-coded `FLUID_*` path in `generator.py`).
- `src/hpo_ai/read/current_state.py` — standard reader (`robot query --select` /
  OAK) for a term's current label/def/synonyms/EQ.
- `src/hpo_ai/patch/kgcl.py` — build the KGCL patch.
- `src/hpo_ai/patch/sparql.py` — compile KGCL → SPARQL, incl. reification-aware
  def update.
- `src/hpo_ai/apply/eq_editor.py` — surgical EQ line edit (EQ-only).
- `src/hpo_ai/apply/runner.py` — orchestrate surgical EQ → `robot query --update`
  → `robot convert` → validate.
- `src/hpo_ai/cli.py` — `curate` and `apply` commands.
- Reused: `extraction/`, `enrichment/` (CHEBI/PRO resolvers, scorer),
  `datamodel/`, `output/tsv.py`.

## Testing (TDD)

- Pattern loader + schema validation.
- Tier 1 label parsing: direction/fluid/chemical extraction, the `taurine`→`urine`
  regression, corroboration with existing axioms, string fallback.
- Tier 2 agentic selection (mocked LLM): picks from the catalog, returns fillers +
  confidence; never invents patterns.
- Unmapped classification: each reason category produces the right `unmapped.tsv`
  row; the summary counts add up to the branch size.
- Materialisation: entity → EQ present; string → EQ absent; text identical in both.
- KGCL emission + parse round-trip; SPARQL compilation incl. the
  duplicate-definition regression (exactly one `IAO:0000115` afterward).
- Surgical EQ editor: add / replace / remove, idempotency, "defining EQ line not
  found → skip + warn".
- End-to-end on the CSF branch (HP:0025454) against the cloned `hp-edit.owl`,
  asserting via `robot convert` that only intended lines changed.

## Decisions

1. Named `{var}` templates instead of DOSDP `%s`. **Yes.**
2. One pattern file per (direction × fluid); seeded patterns encode #11702
   conventions rather than copying DOSDP text. **Yes.**
3. Label, definition, and EQ overwrite by default. **Yes.**
4. Apply is a documented **stop-gap** (KGCL patch artifact + `robot query --update`
   for label/synonym/definition with reification handling; surgical `.ofn` only
   for EQ), tracked toward a single upstream `ontology.apply_patch()` in
   `issues/issue_kgcl_apply_patch.md`. Diff noise acceptable if `robot convert`
   normalises. **Yes.**
5. Two commands: `curate` (produce patch) and `apply` (apply patch), run
   separately. **Yes.**
6. Pattern association is two-tier (deterministic + agentic) and label-aware, with
   a first-class `unmapped.tsv` for terms that do not map cleanly. **Yes.**
