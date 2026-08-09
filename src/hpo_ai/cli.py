"""CLI interface for hpo-ai.

This module provides the command-line interface for the HPO-AI pipeline,
which automates the curation of chemical phenotypes in HPO.

Example usage:
    # Extract candidates
    hpo-ai extract --output candidates.json

    # Enrich with CHEBI/PRO mappings
    hpo-ai enrich candidates.json --output enriched.json

    # Build evidence packets
    hpo-ai build-packets enriched.json --output packets.json

    # Export for review
    hpo-ai export packets.json --output review.tsv

    # Generate ROBOT template
    hpo-ai generate-robot packets.json --output template.tsv
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer
from typing_extensions import Annotated


def _get_enum_value(val):
    """Get enum value, handling both enum and string types.

    This is needed because Pydantic's use_enum_values=True serializes
    enums to their string values.
    """
    if val is None:
        return None
    return val.value if hasattr(val, 'value') else val


app = typer.Typer(
    help="hpo-ai: AI-powered pipeline for harmonising chemical phenotypes in HPO",
    no_args_is_help=True,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@app.command()
def extract(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output JSON file for extracted terms"),
    ] = Path("candidates.json"),
    hpo_path: Annotated[
        str | None,
        typer.Option("--hpo", help="Path to HPO or OAK selector (default: sqlite:obo:hp)"),
    ] = None,
    root_id: Annotated[
        str,
        typer.Option("--root", help="Root HP term ID to extract from"),
    ] = "HP:0001939",
    from_tsv: Annotated[
        Path | None,
        typer.Option("--from-tsv", help="Extract terms listed in TSV file"),
    ] = None,
    id_column: Annotated[
        str,
        typer.Option("--id-column", help="Column name with HP IDs in TSV"),
    ] = "hpo_id",
) -> None:
    """Extract candidate chemical phenotypes from HPO.

    Extracts HP terms that are candidates for chemical phenotype curation,
    either from a root term's descendants or from a TSV file.
    """
    from hpo_ai.extraction import HPOExtractor

    extractor = HPOExtractor(hpo_path=hpo_path)

    if from_tsv:
        typer.echo(f"Extracting terms from TSV: {from_tsv}")
        terms = extractor.extract_from_tsv(str(from_tsv), id_column=id_column)
    else:
        typer.echo(f"Extracting chemical phenotypes from {root_id}")
        terms = extractor.extract_chemical_phenotypes(root_ids=[root_id])

    typer.echo(f"Extracted {len(terms)} candidate terms")

    # Serialize to JSON
    output_data = [t.model_dump(mode="json", exclude_none=True) for t in terms]

    with open(output, "w") as f:
        json.dump(output_data, f, indent=2)

    typer.echo(f"Saved to {output}")


@app.command()
def build_packets(
    input_file: Annotated[
        Path,
        typer.Argument(help="Input JSON file with extracted terms"),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output JSON file for evidence packets"),
    ] = Path("packets.json"),
    use_llm: Annotated[
        bool,
        typer.Option("--use-llm/--no-llm", help="Use LLM for entity extraction"),
    ] = False,
    chebi_path: Annotated[
        str | None,
        typer.Option("--chebi", help="Path to CHEBI or OAK selector"),
    ] = None,
    auto_threshold: Annotated[
        float,
        typer.Option("--auto-threshold", help="Threshold for auto-approval"),
    ] = 0.9,
    review_threshold: Annotated[
        float,
        typer.Option("--review-threshold", help="Minimum threshold for review"),
    ] = 0.5,
    chebi_rules: Annotated[
        Path | None,
        typer.Option("--chebi-rules", help="Path to CHEBI selection rules YAML"),
    ] = None,
    selection_guide: Annotated[
        Path | None,
        typer.Option("--selection-guide", help="Path to CHEBI selection guide markdown"),
    ] = None,
    normalization_rules: Annotated[
        Path | None,
        typer.Option("--normalization-rules", help="Path to name normalization rules YAML"),
    ] = None,
) -> None:
    """Build evidence packets for extracted terms.

    Creates evidence packets containing chemical evidence, pattern assignments,
    and curation proposals for each extracted HP term.
    """
    from hpo_ai.datamodel import HPTerm
    from hpo_ai.enrichment import (
        CHEBIResolver,
        LLMEnricher,
        NameNormalizer,
        PROResolver,
        load_name_normalization_rules,
    )
    from hpo_ai.packets import EvidencePacketBuilder

    # Load terms
    with open(input_file) as f:
        terms_data = json.load(f)

    terms = [HPTerm(**t) for t in terms_data]
    typer.echo(f"Loaded {len(terms)} terms from {input_file}")

    # Initialize resolvers
    chebi_resolver = None
    pro_resolver = None
    llm_enricher = None

    try:
        typer.echo("Initializing CHEBI resolver...")
        chebi_resolver = CHEBIResolver(
            chebi_path=chebi_path,
            rules_path=chebi_rules,
        )
    except Exception as e:
        typer.echo(f"Warning: Could not initialize CHEBI resolver: {e}", err=True)

    try:
        typer.echo("Initializing PRO resolver...")
        pro_resolver = PROResolver()
    except Exception as e:
        typer.echo(f"Warning: Could not initialize PRO resolver: {e}", err=True)

    if use_llm:
        try:
            typer.echo("Initializing LLM enricher...")
            llm_enricher = LLMEnricher(
                selection_guide_path=selection_guide,
            )
        except Exception as e:
            typer.echo(f"Warning: Could not initialize LLM enricher: {e}", err=True)

    # Initialize name normalizer
    name_normalizer = None
    if normalization_rules:
        typer.echo("Loading name normalization rules...")
        rules = load_name_normalization_rules(normalization_rules)
        name_normalizer = NameNormalizer(rules)

    # Build packets
    builder = EvidencePacketBuilder(
        chebi_resolver=chebi_resolver,
        pro_resolver=pro_resolver,
        llm_enricher=llm_enricher,
        name_normalizer=name_normalizer,
        auto_approve_threshold=auto_threshold,
        review_threshold=review_threshold,
    )

    packets = []
    with typer.progressbar(terms, label="Building packets") as progress:
        for term in progress:
            packet = builder.build_packet(term, use_llm=use_llm)
            packets.append(packet)

    # Serialize to JSON
    output_data = [p.model_dump(mode="json", exclude_none=True) for p in packets]

    with open(output, "w") as f:
        json.dump(output_data, f, indent=2)

    # Summary
    auto_approved = sum(1 for p in packets if _get_enum_value(p.review_status) == "auto_approved")
    needs_review = sum(1 for p in packets if _get_enum_value(p.review_status) == "needs_review")
    skipped = sum(1 for p in packets if _get_enum_value(p.review_status) == "skipped")

    typer.echo(f"\nBuilt {len(packets)} evidence packets:")
    typer.echo(f"  Auto-approved: {auto_approved}")
    typer.echo(f"  Needs review:  {needs_review}")
    typer.echo(f"  Skipped:       {skipped}")
    typer.echo(f"\nSaved to {output}")


@app.command()
def export(
    input_file: Annotated[
        Path,
        typer.Argument(help="Input JSON file with evidence packets"),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output TSV file"),
    ] = Path("review.tsv"),
    min_confidence: Annotated[
        float,
        typer.Option("--min-confidence", help="Minimum confidence threshold"),
    ] = 0.0,
    max_confidence: Annotated[
        float,
        typer.Option("--max-confidence", help="Maximum confidence threshold"),
    ] = 1.0,
) -> None:
    """Export evidence packets to TSV for human review.

    Exports packets in a format compatible with the existing
    curated_phenotypes.tsv workflow.
    """
    from hpo_ai.datamodel import EvidencePacket
    from hpo_ai.output import TSVExporter

    # Load packets
    with open(input_file) as f:
        packets_data = json.load(f)

    packets = [EvidencePacket(**p) for p in packets_data]
    typer.echo(f"Loaded {len(packets)} packets from {input_file}")

    # Export
    exporter = TSVExporter()
    exporter.export_for_review(
        packets,
        output,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
    )

    typer.echo(f"Exported to {output}")


@app.command()
def generate_robot(
    input_file: Annotated[
        Path,
        typer.Argument(help="Input JSON file with evidence packets"),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output ROBOT template TSV"),
    ] = Path("robot_template.tsv"),
    only_approved: Annotated[
        bool,
        typer.Option("--only-approved/--all", help="Only include approved packets"),
    ] = True,
) -> None:
    """Generate ROBOT template from evidence packets.

    Creates a ROBOT template that can be used to apply the proposed
    changes to hp-edit.owl.
    """
    from hpo_ai.datamodel import EvidencePacket
    from hpo_ai.output import ROBOTTemplateGenerator

    # Load packets
    with open(input_file) as f:
        packets_data = json.load(f)

    packets = [EvidencePacket(**p) for p in packets_data]
    typer.echo(f"Loaded {len(packets)} packets from {input_file}")

    # Generate template
    generator = ROBOTTemplateGenerator()
    generator.generate(packets, output, only_approved=only_approved)

    typer.echo(f"Generated ROBOT template at {output}")


@app.command()
def curate(
    branch: Annotated[
        str, typer.Option("--branch", help="Root HP term id to curate (branch)")
    ] = "HP:0025454",
    pattern_dir: Annotated[
        Path, typer.Option("--pattern-dir", help="Directory of pattern YAML files")
    ] = Path("patterns"),
    hpo: Annotated[
        str | None,
        typer.Option("--hpo", help="OAK selector to extract from (default sqlite:obo:hp)"),
    ] = None,
    out: Annotated[
        Path, typer.Option("--out", "-o", help="Output bundle directory")
    ] = Path("out"),
    mappings_dir: Annotated[
        Path,
        typer.Option("--mappings-dir", help="Directory of auditable decision stores (TSV)"),
    ] = Path("mappings"),
    use_llm: Annotated[
        bool,
        typer.Option("--use-llm/--no-llm", help="Enable the agentic (Tier 2) associator"),
    ] = False,
) -> None:
    """Workflow A: produce a KGCL patch bundle for an HP branch (no mutation).

    Reads the branch, associates each term with a pattern (deterministic, with an
    optional agentic tier), materialises label/definition/synonyms/EQ, and writes
    ``curate.kgcl``, ``axioms.ofn``, ``update.ru``, ``review.tsv`` and
    ``unmapped.tsv`` to the output directory.
    """
    from hpo_ai.enrichment import CHEBIResolver, PROResolver
    from hpo_ai.extraction import HPOExtractor
    from hpo_ai.patterns.loader import load_patterns
    from hpo_ai.pipeline import run_curate

    typer.echo(f"Extracting branch {branch} ...")
    extractor = HPOExtractor(hpo_path=hpo)
    terms = extractor.extract_chemical_phenotypes(root_ids=[branch])
    typer.echo(f"  {len(terms)} terms")

    patterns = load_patterns(pattern_dir)
    typer.echo(f"Loaded {len(patterns)} patterns from {pattern_dir}")

    chebi = None
    pro = None
    try:
        chebi = CHEBIResolver()
    except Exception as e:  # noqa: BLE001 - external resolver init
        typer.echo(f"Warning: CHEBI resolver unavailable: {e}", err=True)
    try:
        pro = PROResolver()
    except Exception as e:  # noqa: BLE001 - external resolver init
        typer.echo(f"Warning: PRO resolver unavailable: {e}", err=True)

    agentic_selector = None
    clinical_extractor = None
    preferred_llm = None
    agent_version = ""
    if use_llm:
        from hpo_ai.associate.agentic import make_anthropic_selector
        from hpo_ai.associate.clinical import make_anthropic_chemical_extractor
        from hpo_ai.associate.preferred import make_anthropic_preferred_term_llm
        from hpo_ai.enrichment import LLMEnricher

        try:
            enricher = LLMEnricher()
            agent_version = getattr(enricher, "model", "")
            agentic_selector = make_anthropic_selector(enricher)
            clinical_extractor = make_anthropic_chemical_extractor(enricher)
            preferred_llm = make_anthropic_preferred_term_llm(enricher)
        except Exception as e:  # noqa: BLE001 - external LLM init
            typer.echo(f"Warning: LLM tiers unavailable: {e}", err=True)

    # Auditable, edit-preserving decision stores (loaded even offline so curated
    # mappings/terms resolve without an LLM call).
    from hpo_ai.associate.preferred import PreferredClinicalTermResolver
    from hpo_ai.provenance import (
        clinical_grounding_store,
        pattern_association_store,
        preferred_term_store,
    )

    clinical_store = clinical_grounding_store(mappings_dir / "clinical_chemical.sssom.tsv")
    pattern_store = pattern_association_store(mappings_dir / "pattern_association.tsv")
    preferred_store = preferred_term_store(mappings_dir / "preferred_clinical_term.tsv")
    preferred_resolver = PreferredClinicalTermResolver(
        preferred_store, llm_fn=preferred_llm, agent_version=agent_version
    )

    result = run_curate(
        terms, patterns, out,
        chebi_resolver=chebi, pro_resolver=pro,
        agentic_selector=agentic_selector,
        clinical_chemical_extractor=clinical_extractor,
        clinical_store=clinical_store,
        pattern_store=pattern_store,
        preferred_term_resolver=preferred_resolver,
        preferred_term_store=preferred_store,
        agent_version=agent_version,
    )

    typer.echo(f"\nAssociated: {result.associated}")
    typer.echo(f"Unmapped:   {result.unmapped}")
    for reason, n in sorted(result.unmapped_by_reason.items()):
        typer.echo(f"    {reason}: {n}")
    typer.echo(f"KGCL statements: {result.kgcl_statements}")
    typer.echo(f"EQ axioms:       {result.eq_axioms}")
    if result.invalid_kgcl:
        typer.echo(
            f"  ({len(result.invalid_kgcl)} KGCL line(s) not parseable; applied via SPARQL)"
        )
    typer.echo(f"\nBundle written to {out}/")


@app.command()
def apply(
    patch: Annotated[
        Path, typer.Option("--patch", help="Patch bundle directory produced by curate")
    ],
    hpo: Annotated[
        Path, typer.Option("--hpo", help="Path to hp-edit.owl to modify in place")
    ],
    robot: Annotated[
        str, typer.Option("--robot", help="Path to the ROBOT executable")
    ] = "/Users/matentzn/tools/robot",
    catalog: Annotated[
        Path | None,
        typer.Option("--catalog", help="Catalog file for import resolution"),
    ] = None,
) -> None:
    """Workflow B: apply a curate patch bundle to hp-edit.owl (stop-gap).

    Applies EquivalentClasses axioms with a surgical edit, then label/synonym/
    definition changes via ``robot query --update``. See
    ``issues/issue_kgcl_apply_patch.md`` for the intended upstream replacement.
    """
    from hpo_ai.apply.runner import apply_patch_bundle

    report = apply_patch_bundle(patch, hpo, robot=robot, catalog=catalog)
    typer.echo(f"EQ added:    {len(report.eq.added)}")
    typer.echo(f"EQ replaced: {len(report.eq.replaced)}")
    typer.echo(f"EQ unchanged:{len(report.eq.unchanged)}")
    typer.echo(f"EQ skipped:  {len(report.eq.skipped)}")
    typer.echo(f"SPARQL applied: {report.sparql_applied}")
    typer.echo(f"Wrote {report.output}")


@app.command()
def validate(
    input_file: Annotated[
        Path,
        typer.Argument(help="Input JSON file with evidence packets"),
    ],
) -> None:
    """Validate evidence packets.

    Checks packets for errors and warnings before applying changes.
    """
    from hpo_ai.datamodel import EvidencePacket
    from hpo_ai.validation import ProposalValidator

    # Load packets
    with open(input_file) as f:
        packets_data = json.load(f)

    packets = [EvidencePacket(**p) for p in packets_data]
    typer.echo(f"Loaded {len(packets)} packets from {input_file}")

    # Validate
    validator = ProposalValidator()
    results = validator.validate_batch(packets)

    # Summary
    valid_count = sum(1 for r in results.values() if r.is_valid)
    error_count = sum(len(r.errors) for r in results.values())
    warning_count = sum(len(r.warnings) for r in results.values())

    typer.echo("\nValidation results:")
    typer.echo(f"  Valid packets:   {valid_count}/{len(packets)}")
    typer.echo(f"  Total errors:    {error_count}")
    typer.echo(f"  Total warnings:  {warning_count}")

    # Show errors
    if error_count > 0:
        typer.echo("\nErrors:")
        for packet_id, result in results.items():
            if result.errors:
                for error in result.errors:
                    typer.echo(f"  {packet_id}: {error}")


@app.command()
def stats(
    input_file: Annotated[
        Path,
        typer.Argument(help="Input JSON file with evidence packets"),
    ],
) -> None:
    """Show statistics about evidence packets."""
    from collections import Counter

    from hpo_ai.datamodel import EvidencePacket

    # Load packets
    with open(input_file) as f:
        packets_data = json.load(f)

    packets = [EvidencePacket(**p) for p in packets_data]

    # Calculate stats
    status_counts = Counter(_get_enum_value(p.review_status) for p in packets if p.review_status)
    pattern_counts = Counter(
        _get_enum_value(p.pattern_assignment.pattern_name)
        for p in packets
        if p.pattern_assignment
    )
    change_counts = Counter(
        _get_enum_value(p.proposal.change_type)
        for p in packets
        if p.proposal and p.proposal.change_type
    )

    confidence_buckets = {
        "high (>=0.9)": sum(1 for p in packets if (p.overall_confidence or 0) >= 0.9),
        "medium (0.7-0.9)": sum(
            1 for p in packets if 0.7 <= (p.overall_confidence or 0) < 0.9
        ),
        "low (<0.7)": sum(1 for p in packets if (p.overall_confidence or 0) < 0.7),
    }

    typer.echo(f"\nStatistics for {len(packets)} packets:\n")

    typer.echo("Review Status:")
    for status, count in status_counts.most_common():
        typer.echo(f"  {status}: {count}")

    typer.echo("\nPatterns:")
    for pattern, count in pattern_counts.most_common(10):
        typer.echo(f"  {pattern}: {count}")

    typer.echo("\nChange Types:")
    for change, count in change_counts.most_common():
        typer.echo(f"  {change}: {count}")

    typer.echo("\nConfidence Buckets:")
    for bucket, count in confidence_buckets.items():
        typer.echo(f"  {bucket}: {count}")


@app.command()
def run_pipeline(
    input_tsv: Annotated[
        Path | None,
        typer.Option("--input", "-i", help="Input TSV file with HP IDs"),
    ] = None,
    root_id: Annotated[
        str,
        typer.Option("--root", help="Root HP term ID to extract from"),
    ] = "HP:0001939",
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Output directory"),
    ] = Path("output"),
    use_llm: Annotated[
        bool,
        typer.Option("--use-llm/--no-llm", help="Use LLM for entity extraction"),
    ] = False,
    auto_threshold: Annotated[
        float,
        typer.Option("--auto-threshold", help="Threshold for auto-approval"),
    ] = 0.9,
    chebi_rules: Annotated[
        Path | None,
        typer.Option("--chebi-rules", help="Path to CHEBI selection rules YAML"),
    ] = None,
    selection_guide: Annotated[
        Path | None,
        typer.Option("--selection-guide", help="Path to CHEBI selection guide markdown"),
    ] = None,
    normalization_rules: Annotated[
        Path | None,
        typer.Option("--normalization-rules", help="Path to name normalization rules YAML"),
    ] = None,
) -> None:
    """Run the full HPO-AI pipeline.

    Extracts terms, builds evidence packets, and exports results.
    """
    from hpo_ai.enrichment import (
        CHEBIResolver,
        LLMEnricher,
        NameNormalizer,
        load_name_normalization_rules,
    )
    from hpo_ai.extraction import HPOExtractor
    from hpo_ai.output import ROBOTTemplateGenerator, TSVExporter
    from hpo_ai.packets import EvidencePacketBuilder

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Extract terms
    typer.echo("Step 1: Extracting terms...")
    extractor = HPOExtractor()

    if input_tsv:
        terms = extractor.extract_from_tsv(str(input_tsv))
    else:
        terms = extractor.extract_chemical_phenotypes(root_ids=[root_id])

    typer.echo(f"  Extracted {len(terms)} terms")

    # Save extracted terms
    terms_path = output_dir / "candidates.json"
    with open(terms_path, "w") as f:
        json.dump([t.model_dump(mode="json", exclude_none=True) for t in terms], f, indent=2)

    # Step 2: Build evidence packets
    typer.echo("\nStep 2: Building evidence packets...")

    chebi_resolver = None
    llm_enricher = None

    try:
        chebi_resolver = CHEBIResolver(rules_path=chebi_rules)
    except Exception as e:
        typer.echo(f"  Warning: CHEBI resolver not available: {e}", err=True)

    if use_llm:
        try:
            llm_enricher = LLMEnricher(selection_guide_path=selection_guide)
        except Exception as e:
            typer.echo(f"  Warning: LLM enricher not available: {e}", err=True)

    # Initialize name normalizer
    name_normalizer = None
    if normalization_rules:
        typer.echo("  Loading name normalization rules...")
        rules = load_name_normalization_rules(normalization_rules)
        name_normalizer = NameNormalizer(rules)

    builder = EvidencePacketBuilder(
        chebi_resolver=chebi_resolver,
        llm_enricher=llm_enricher,
        name_normalizer=name_normalizer,
        auto_approve_threshold=auto_threshold,
    )

    packets = builder.build_batch(terms, use_llm=use_llm)
    typer.echo(f"  Built {len(packets)} evidence packets")

    # Save packets
    packets_path = output_dir / "packets.json"
    with open(packets_path, "w") as f:
        json.dump([p.model_dump(mode="json", exclude_none=True) for p in packets], f, indent=2)

    # Step 3: Export results
    typer.echo("\nStep 3: Exporting results...")

    exporter = TSVExporter()

    # Export all for review
    review_path = output_dir / "review.tsv"
    exporter.export(packets, review_path)
    typer.echo(f"  Review TSV: {review_path}")

    # Export auto-approved
    auto_path = output_dir / "auto_approved.tsv"
    exporter.export_for_review(packets, auto_path, min_confidence=auto_threshold)
    typer.echo(f"  Auto-approved TSV: {auto_path}")

    # Export needs review
    needs_review_path = output_dir / "needs_review.tsv"
    exporter.export_for_review(packets, needs_review_path, min_confidence=0.5, max_confidence=auto_threshold)
    typer.echo(f"  Needs review TSV: {needs_review_path}")

    # Generate ROBOT template
    robot_path = output_dir / "robot_template.tsv"
    generator = ROBOTTemplateGenerator()
    generator.generate(packets, robot_path, only_approved=True)
    typer.echo(f"  ROBOT template: {robot_path}")

    # Summary
    auto_approved = sum(1 for p in packets if _get_enum_value(p.review_status) == "auto_approved")
    needs_review = sum(1 for p in packets if _get_enum_value(p.review_status) == "needs_review")

    typer.echo("\nPipeline complete!")
    typer.echo(f"  Total terms:    {len(packets)}")
    typer.echo(f"  Auto-approved:  {auto_approved}")
    typer.echo(f"  Needs review:   {needs_review}")
    typer.echo(f"\nOutput directory: {output_dir}")


def main():
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
