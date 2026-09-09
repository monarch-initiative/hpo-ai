# hpo-ai

AI-assisted pipeline for harmonising **chemical phenotypes** in the
[Human Phenotype Ontology](https://hpo.jax.org/) (HPO) — terms describing an
abnormal level of a chemical or protein in a body fluid, e.g. *Increased CSF
lactate*, *Hypercalcemia*, *Elevated circulating creatine kinase*.

The pipeline rewrites legacy terms to follow declared **patterns** (a simplified
form of DOSDP), emits a reviewable **KGCL patch bundle**, and can apply that
bundle to the HPO editors' file. Every decision the pipeline makes is written to
a human-editable TSV that a curator can audit and override.

## Start here

- **[Pipeline walkthrough](pipeline-walkthrough.md)** — the current architecture,
  end to end, with a real reproducible run over the CSF branch. Read this first.
- **[Regression corpus & failure modes](corpus-failure-modes.md)** — how the
  pipeline is pinned against real curator output from five merged HPO PRs.
- **[Demo](demo.md)** — name normalisation, proposal generation and scoring on
  real data from HPO PR #11457.
- **[Legacy evidence-packet pipeline](overview.md)** — the earlier
  `build-packets` design, kept for reference.

## Install

```bash
uv sync --group dev
uv run hpo-ai --help
```

Source and issue tracker: [monarch-initiative/hpo-ai](https://github.com/monarch-initiative/hpo-ai).
