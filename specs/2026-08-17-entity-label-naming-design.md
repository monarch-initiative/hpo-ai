# Entity-label-based naming — design & decision

**Status:** proposed (awaiting decision)
**Date:** 2026-08-17

## Problem

The pattern-driven pipeline builds a term's label by dropping the *extracted
chemical span* (the chemical words lifted from the current label) into the
pattern template — `Elevated circulating {chemical} concentration`. The
hypothesis was that we should instead name from the *resolved entity's
systematic label* (CHEBI/PRO) and then normalise it (mirroring
`update-chemical-labels.ru`), because that is what HPO's own build does and it
would let the `.ru` renames actually fire (`alpha-2-HS-glycoprotein → fetuin-A`).

This spec tests that hypothesis against live data before building anything.

## Evidence

### Live CSF e2e (deterministic tier, branch HP:0025454)

143 associated, 2 unmapped (opaque clinical, need the LLM tier), 109 with an EQ,
1 role filler. Two measurements matter here:

- **Entity-label naming is a no-op on CSF metabolites.** For every entity-resolved
  chemical, the CHEBI *systematic* label is identical to the extracted span:
  `phenylalanine`, `tyrosine`, `glucose`, `glycine`, `dopamine`, `homovanillic
  acid`, `neopterin`, … all match exactly. Naming from the entity label would
  produce byte-identical labels. There is nothing to gain here, and swapping to
  systematic CHEBI names elsewhere risks *introducing* noise into spans that are
  already clean.

- **The real EQ-coverage bottleneck is resolver recall.** 34 of 143 terms
  (**24%**) fall back to a bare-string filler (no logical axiom) because the
  resolver's `basic_search` misses the chemical: `epinephrine` (CHEBI's primary
  label is *adrenaline*), `glutamate` (*L-glutamate*), `urate` (charge forms),
  `tetrahydrobiopterin`, `N-acetylaspartic acid`, `pyridoxal-5'-phosphate`, … all
  exist in CHEBI but are not found by label-only exact search. These are
  synonym / stereo / charge-variant misses, not naming problems.

- **The role work is correct on live data.** HP:0025454 ("metabolite",
  CHEBI:25212, a role) produced the satisfiable role EQ
  `'chemical entity' (CHEBI:24431) and has_role (RO:0000087) some metabolite`.

### Metabolism-refactor corpus (blood/protein)

The extracted spans there are *already human names* (`fetuin A`, not
`alpha-2-HS-glycoprotein`); curators normalised those further (`fetuin A →
fetuin-A`). The systematic-name renames in the `.ru` only fire when the input
actually is the systematic name — which the corpus inputs are not. Applying the
`.ru` to that corpus was net-negative (documented in
`docs/corpus-failure-modes.md`).

## Options

**A — Global entity-label naming.** Always name from the resolved systematic
label, then normalise. *Rejected:* the CSF data shows it is a no-op where the
span is already clean (CHEBI metabolites), and a risk where it is not; it also
inherits the `.ru`'s unresolved policy conflicts (`phenylalanine →
L-phenylalanine`, enzyme edge cases) which now fire live.

**B — Narrow entity-label naming.** Use the entity label *only* when the current
label carries a systematic/awkward name (chiefly PRO proteins) and the
normalised entity label is demonstrably cleaner, behind a quality gate. Marginal
value on the data we have; defer until a concrete case demands it.

**C — Don't build it; fix resolver recall instead (recommended).** Keep
extracted-span naming (it is already correct on 109/109 CSF entity terms). Invest
the effort in the bottleneck the e2e actually exposed: **resolver recall** —
search CHEBI synonyms and handle charge/stereo variants so the 24% string
fallbacks resolve and gain an EQ. Pair with the LLM clinical tier for the opaque
terms.

## Recommendation

**C.** The e2e talked us out of the design change: entity-label naming does not
move live labels, while ~1 in 4 terms silently loses its logical axiom to a
resolver miss. The ordered levers are:

1. **Resolver recall** — synonym-inclusive / variant-aware CHEBI (and PRO) search.
   Biggest EQ-coverage win; turns ~24% string fallbacks into axiomatised terms.
2. **LLM clinical tier** — resolves the opaque portmanteau terms (2 on CSF, 44 on
   the corpus) that the deterministic tier cannot.
3. **Normalisation policy** — decide whether `phenylalanine → L-phenylalanine`
   and the enzyme `concentration → activity` rule should fire by default; they
   now do (wired into `run_curate`) and diverge from some current HPO labels.

Entity-label naming stays on the shelf as option B, revisited only if a concrete
protein-branch case shows the extracted span is wrong where the entity label is
right.

## Update (2026-08-17): recall fix landed

Option C is implemented in two high-precision layers, re-measured on the CSF branch:

- **Synonym-inclusive, synonym-aware CHEBI search** (`CHEBIResolver`): 109 → 126
  EQ (+17), recovering common names that are CHEBI synonyms (`epinephrine`,
  `glutamate`, `urate`, `tetrahydrobiopterin`, `DOPA`, `fumarate`, …).
- **Curated mappings** for name-structure misses (`conf/chebi_selection_rules.yaml`,
  9 verified entries with rationale): 126 → 138 EQ (+12), recovering
  `5-HIAA`, `dihydrothymine`, `dihydrouracil`, `argininosuccinic acid`,
  `saccharopine`, `metanephrine`, `pyridoxal-5'-phosphate`, and the HPO
  spelling variants.

Net: **109 → 138 EQ (76% → 96.5%), 0 regressions.** Partial/fuzzy search was
rejected — it ranked wrong compounds first (`pyridoxal → pyridoxamine`,
`metanephrine → normetanephrine`), and a wrong axiom is worse than none. The 5
residual string terms are genuine curator/PRO decisions, deliberately not
guessed: `apolipoprotein B` (a PRO protein, not CHEBI), `dihydrobiopterin`
(4-isomer ambiguity), `L-2-hydroxyglutaric acid`, `aspartylglucosamine`,
`N-carbamyl-beta-aminoisobutyric acid`.

## Decision needed

Confirm we shelve entity-label naming (A/B) and prioritise resolver recall (C),
or steer otherwise. If C, the next spec is the resolver-recall design (synonym
search, thresholds, variant handling).
