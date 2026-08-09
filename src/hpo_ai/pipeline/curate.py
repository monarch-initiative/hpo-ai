"""Workflow A: read branch -> associate -> materialise -> produce patch bundle."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

from hpo_ai.associate.agentic import AgenticAssociator
from hpo_ai.associate.deterministic import DeterministicAssociator
from hpo_ai.associate.models import Association, Unmapped
from hpo_ai.associate.report import summarize_reasons, write_unmapped_tsv
from hpo_ai.datamodel import HPTerm
from hpo_ai.datamodel.pattern import Pattern
from hpo_ai.generate import materialize
from hpo_ai.patch.kgcl import build_kgcl, validate_kgcl
from hpo_ai.patch.sparql import compile_sparql
from hpo_ai.provenance.constants import METHOD_LLM, METHOD_RULE
from hpo_ai.provenance.stores import pattern_row
from hpo_ai.read.current_state import term_state_from_hpterm

logger = logging.getLogger(__name__)

_OBO = "http://purl.obolibrary.org/obo/"

_REVIEW_COLUMNS = [
    "hpo_id", "current_label", "proposed_label", "preferred_label",
    "primary_label_source", "proposed_definition", "change_type", "confidence",
    "tier", "pattern", "chemical", "is_entity", "eq_present",
]


@dataclass
class CurateResult:
    """Summary of a curate run."""

    associated: int
    unmapped: int
    kgcl_statements: int
    eq_axioms: int
    unmapped_by_reason: dict[str, int] = field(default_factory=dict)
    invalid_kgcl: list[str] = field(default_factory=list)
    out_dir: Path | None = None


def _iri(curie: str) -> str:
    prefix, local = curie.split(":", 1)
    return f"{_OBO}{prefix}_{local}"


def run_curate(
    terms: list[HPTerm],
    patterns: list[Pattern],
    out_dir: str | Path,
    chebi_resolver=None,
    pro_resolver=None,
    agentic_selector=None,
    clinical_chemical_extractor=None,
    clinical_store=None,
    pattern_store=None,
    preferred_term_resolver=None,
    preferred_term_store=None,
    agent_version: str = "",
) -> CurateResult:
    """Run Workflow A and write the patch bundle.

    Args:
        terms: Extracted HP terms (the branch).
        patterns: Loaded patterns.
        out_dir: Output directory for the bundle.
        chebi_resolver: CHEBI resolver (``.resolve``).
        pro_resolver: PRO resolver.
        agentic_selector: Optional Tier-2 selector callable (enables agentic tier).

    Returns:
        A :class:`CurateResult`.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    det = DeterministicAssociator(
        patterns, chebi_resolver, pro_resolver,
        clinical_chemical_extractor=clinical_chemical_extractor,
        clinical_store=clinical_store,
        clinical_agent_version=agent_version,
        preferred_term_resolver=preferred_term_resolver,
        pattern_store=pattern_store,
    )
    agentic = (
        AgenticAssociator(agentic_selector, chebi_resolver, pro_resolver,
                          pattern_store=pattern_store, agent_version=agent_version)
        if agentic_selector is not None
        else None
    )

    associations: list[Association] = []
    unmapped: list[Unmapped] = []
    for term in terms:
        result = det.associate(term)
        if isinstance(result, Unmapped) and agentic is not None:
            result = agentic.associate(term, patterns)
        if isinstance(result, Unmapped):
            unmapped.append(result)
        else:
            associations.append(result)

    by_id = {t.id: t for t in terms}
    kgcl_lines: list[str] = []
    sparql_items = []
    eq_lines: list[str] = []
    review_rows: list[dict] = []

    for assoc in associations:
        term = by_id[assoc.hp_id]
        state = term_state_from_hpterm(term)
        proposal = materialize(term, assoc)

        kgcl_lines.extend(build_kgcl(state, proposal))
        sparql_items.append((state, proposal))

        # Record the pattern pick in the auditable store (lock gate preserves
        # curator edits). Every association, both tiers.
        if pattern_store is not None:
            method = METHOD_LLM if assoc.tier == "agentic" else METHOD_RULE
            version = agent_version if assoc.tier == "agentic" else ""
            pattern_store.record(assoc.hp_id, [pattern_row(
                assoc.hp_id, term.label or "", assoc.pattern.id,
                assoc.fillers.chemical_string, method, version, assoc.confidence)])

        eq_present = False
        if proposal.proposed_logical_definition:
            eq_lines.append(
                f"EquivalentClasses(<{_iri(assoc.hp_id)}> "
                f"{proposal.proposed_logical_definition})"
            )
            eq_present = True

        review_rows.append({
            "hpo_id": assoc.hp_id,
            "current_label": term.label,
            "proposed_label": proposal.proposed_label or "",
            "preferred_label": assoc.preferred_label or "",
            "primary_label_source": assoc.preferred_source or "pattern",
            "proposed_definition": proposal.proposed_definition or "",
            "change_type": _val(proposal.change_type),
            "confidence": f"{assoc.confidence:.2f}",
            "tier": assoc.tier,
            "pattern": assoc.pattern.id,
            "chemical": assoc.fillers.chemical_string,
            "is_entity": str(assoc.fillers.is_entity),
            "eq_present": str(eq_present),
        })

    # Write bundle
    (out_dir / "curate.kgcl").write_text("\n".join(kgcl_lines) + ("\n" if kgcl_lines else ""))
    (out_dir / "axioms.ofn").write_text("\n".join(eq_lines) + ("\n" if eq_lines else ""))
    (out_dir / "update.ru").write_text(compile_sparql(sparql_items))
    write_unmapped_tsv(unmapped, out_dir / "unmapped.tsv")
    _write_review(review_rows, out_dir / "review.tsv")

    # Persist the auditable/editable decision stores (curator edits preserved).
    if clinical_store is not None:
        clinical_store.save()
    if pattern_store is not None:
        pattern_store.save()
    if preferred_term_store is not None:
        preferred_term_store.save()

    invalid = validate_kgcl(kgcl_lines)
    if invalid:
        logger.warning("%d KGCL statement(s) not parseable (applied via SPARQL): %s",
                       len(invalid), invalid[:3])

    return CurateResult(
        associated=len(associations),
        unmapped=len(unmapped),
        kgcl_statements=len(kgcl_lines),
        eq_axioms=len(eq_lines),
        unmapped_by_reason=summarize_reasons(unmapped),
        invalid_kgcl=invalid,
        out_dir=out_dir,
    )


def _val(x) -> str:
    if x is None:
        return ""
    return x.value if hasattr(x, "value") else str(x)


def _write_review(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_REVIEW_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
