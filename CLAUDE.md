# CLAUDE.md for hpo-ai

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered pipeline for harmonising chemical phenotypes in the Human Phenotype Ontology (HPO).

The project uses `uv` for dependency management and `just` as the command runner.

## IMPORTANT INSTRUCTIONS

- we use test driven development, write tests first before implementing a feature
- do not try and 'cheat' by making mock tests (unless asked)
- if functionality does not work, keep trying, do not relax the test just to get poor code in
- always run tests
- use docstrings

We make heavy use of doctests, these serve as both docs and tests. `just test` will include these,
or do `just doctest` just to write doctests

In general AVOID try/except blocks, except when these are truly called for, for example
when interfacing with external systems. For wrapping deterministic code, these are ALMOST
NEVER required, if you think you need them, it's likely a bad smell that your logic is wrong.

## Essential Commands

### Testing and Quality
- `just test` - Run all tests, type checking, and formatting checks
- `just pytest` - Run Python tests only
- `just mypy` - Run type checking
- `just format` - Run ruff linting/formatting checks
- `uv run pytest tests/test_simple.py::test_simple` - Run a specific test

### Running the CLI
- `uv run hpo-ai --help` - Run the CLI tool with options
- `uv run hpo-ai extract --help` - Extract candidate terms from HPO
- `uv run hpo-ai build-packets --help` - Build evidence packets
- `uv run hpo-ai export --help` - Export packets to TSV
- `uv run hpo-ai run-pipeline --help` - Run full pipeline

### Documentation
- `just _serve` - Run local documentation server with mkdocs

## Project Architecture

### Core Structure
- **src/hpo_ai/** - Main package
  - `cli.py` - Typer-based CLI interface
  - `schema/hpo_ai.yaml` - LinkML schema for data models
  - `datamodel/` - Generated Pydantic models from LinkML schema
  - `extraction/` - HP term extraction using OAK
  - `enrichment/` - CHEBI/PRO entity resolution and LLM enrichment
  - `packets/` - Evidence packet builder
  - `patterns/` - Pattern assignment and proposal generation
  - `scoring/` - Confidence scoring
  - `validation/` - Proposal validation
  - `output/` - TSV and ROBOT template generation
- **patterns/dosdp/** - DOSDP pattern files
- **sparql/** - SPARQL queries for term extraction
- **conf/** - Configuration files
- **tests/** - Test suite

### Technology Stack
- **Python 3.10+** with `uv` for dependency management
- **LinkML** for data modeling (linkml-runtime)
- **OAKlib** for ontology access
- **Anthropic Claude** for LLM-based enrichment
- **Typer** for CLI interface
- **pytest** for testing
- **mypy** for type checking
- **ruff** for linting and formatting
- **MkDocs Material** for documentation

### Key Configuration Files
- `pyproject.toml` - Python project configuration, dependencies, and tool settings
- `justfile` - Command runner recipes for common development tasks
- `conf/config.yaml` - Pipeline configuration (thresholds, weights, abbreviations)
- `mkdocs.yml` - Documentation configuration
- `uv.lock` - Locked dependency versions

## Pipeline Workflow

1. **Extract** - Extract candidate chemical phenotypes from HPO using OAK
2. **Build Packets** - For each term:
   - Resolve chemical entity using CHEBI/PRO (optionally with LLM)
   - Assign DOSDP pattern based on term semantics
   - Generate curation proposal with new label/definition
   - Calculate confidence score
3. **Review** - Export to TSV for human review (curated_phenotypes.tsv format)
4. **Apply** - Generate ROBOT template for approved changes

## Key Data Models

- `HPTerm` - Extracted HP term with label, definition, synonyms, existing annotations
- `ChemicalEntityEvidence` - CHEBI/PRO match with confidence score
- `PatternAssignment` - DOSDP pattern assignment with location and direction
- `CurationProposal` - Proposed label, definition, synonyms, axioms
- `EvidencePacket` - Container for all evidence supporting a curation decision

## Development Workflow

1. Dependencies are managed via `uv` - use `uv add` for new dependencies
2. All commands are run through `just` or `uv run`
3. The project uses dynamic versioning from git tags
4. Regenerate datamodels after schema changes: `uv run gen-pydantic src/hpo_ai/schema/hpo_ai.yaml > src/hpo_ai/datamodel/hpo_ai.py`
5. Documentation is auto-deployed to GitHub Pages at https://obophenotype.github.io/hpo-ai
