"""Evidence packet builder for HPO chemical phenotype curation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from hpo_ai.datamodel import (
    ChemicalEntityEvidence,
    CurationProposal,
    EvidencePacket,
    HPTerm,
    PatternAssignment,
    ReviewStatus,
)
from hpo_ai.enrichment import CHEBIResolver, LLMEnricher, NameNormalizer, PROResolver
from hpo_ai.patterns import PatternAssigner
from hpo_ai.scoring import ConfidenceScorer

logger = logging.getLogger(__name__)


def _generate_packet_id() -> str:
    """Generate unique packet ID."""
    return f"pkt_{uuid4().hex[:12]}"


class EvidencePacketBuilder:
    """Build evidence packets for HP term curation.

    An evidence packet collects all evidence needed to make a curation
    decision for an HP term, including:
    - Chemical entity matches (CHEBI/PRO)
    - Pattern assignment
    - Proposed changes
    - Confidence scores
    """

    def __init__(
        self,
        chebi_resolver: CHEBIResolver | None = None,
        pro_resolver: PROResolver | None = None,
        llm_enricher: LLMEnricher | None = None,
        pattern_assigner: PatternAssigner | None = None,
        scorer: ConfidenceScorer | None = None,
        name_normalizer: NameNormalizer | None = None,
        auto_approve_threshold: float = 0.9,
        review_threshold: float = 0.5,
    ) -> None:
        """Initialize the packet builder.

        Args:
            chebi_resolver: CHEBI resolver instance.
            pro_resolver: PRO resolver instance.
            llm_enricher: LLM enricher instance.
            pattern_assigner: Pattern assigner instance.
            scorer: Confidence scorer instance.
            name_normalizer: Optional normalizer for chemical entity labels.
            auto_approve_threshold: Threshold for auto-approval.
            review_threshold: Minimum threshold for review queue.
        """
        self.chebi_resolver = chebi_resolver
        self.pro_resolver = pro_resolver
        self.llm_enricher = llm_enricher
        self.pattern_assigner = pattern_assigner or PatternAssigner()
        self.scorer = scorer or ConfidenceScorer()
        self.name_normalizer = name_normalizer
        self.auto_approve_threshold = auto_approve_threshold
        self.review_threshold = review_threshold

    def build_packet(
        self,
        hp_term: HPTerm,
        use_llm: bool = True,
    ) -> EvidencePacket:
        """Build an evidence packet for an HP term.

        Args:
            hp_term: The HP term to build a packet for.
            use_llm: Whether to use LLM for entity extraction.

        Returns:
            Complete EvidencePacket with all evidence and proposals.
        """
        logger.info(f"Building evidence packet for {hp_term.id}: {hp_term.label}")

        # Collect chemical entity evidence
        chemical_evidence = self._collect_chemical_evidence(hp_term, use_llm)

        # Assign pattern
        pattern_assignment = self.pattern_assigner.assign(hp_term)

        # Generate proposal
        proposal = self._generate_proposal(hp_term, chemical_evidence, pattern_assignment)

        # Calculate overall confidence
        overall_confidence = self.scorer.score(
            hp_term=hp_term,
            chemical_evidence=chemical_evidence,
            pattern_assignment=pattern_assignment,
            proposal=proposal,
        )

        # Determine review status
        review_status = self._determine_review_status(overall_confidence)

        return EvidencePacket(
            id=_generate_packet_id(),
            hp_term=hp_term,
            chemical_evidence=chemical_evidence if chemical_evidence else None,
            pattern_assignment=pattern_assignment,
            proposal=proposal,
            overall_confidence=overall_confidence,
            review_status=review_status,
            created_at=datetime.now(timezone.utc),
        )

    def _collect_chemical_evidence(
        self,
        hp_term: HPTerm,
        use_llm: bool,
    ) -> list[ChemicalEntityEvidence]:
        """Collect chemical entity evidence from multiple sources.

        Args:
            hp_term: The HP term to analyze.
            use_llm: Whether to use LLM for extraction.

        Returns:
            List of ChemicalEntityEvidence from all sources.
        """
        evidence = []

        # If term already has a chemical entity, validate it
        if hp_term.existing_chemical_entity:
            existing_id = hp_term.existing_chemical_entity
            if existing_id.startswith("CHEBI:") and self.chebi_resolver:
                ev = self.chebi_resolver.resolve_by_id(existing_id)
                if ev:
                    ev.confidence = 1.0  # Existing annotation is trusted
                    evidence.append(ev)
            elif existing_id.startswith("PR:") and self.pro_resolver:
                ev = self.pro_resolver.resolve_by_id(existing_id)
                if ev:
                    ev.confidence = 1.0
                    evidence.append(ev)

        # Extract chemical name from term (rule-based)
        chemical_name = self._extract_chemical_name(
            hp_term.label, hp_term.definition
        )

        if chemical_name:
            # Search CHEBI
            if self.chebi_resolver:
                chebi_matches = self.chebi_resolver.resolve(chemical_name)
                evidence.extend(chebi_matches)

            # Search PRO if it looks like a protein
            if self.pro_resolver:
                if self.pro_resolver.is_protein_term(hp_term.label):
                    pro_matches = self.pro_resolver.resolve(chemical_name)
                    evidence.extend(pro_matches)

        # Use LLM for additional extraction
        if use_llm and self.llm_enricher:
            llm_evidence = self.llm_enricher.extract_chemical_entity(hp_term)
            if llm_evidence and llm_evidence.entity_label:
                # Resolve the LLM-extracted name
                if llm_evidence.entity_source == "CHEBI" and self.chebi_resolver:
                    matches = self.chebi_resolver.resolve(llm_evidence.entity_label)
                    for match in matches:
                        match.evidence_type = llm_evidence.evidence_type
                        match.preferred_abbreviation = llm_evidence.preferred_abbreviation
                    evidence.extend(matches)
                elif llm_evidence.entity_source == "PRO" and self.pro_resolver:
                    matches = self.pro_resolver.resolve(llm_evidence.entity_label)
                    for match in matches:
                        match.evidence_type = llm_evidence.evidence_type
                    evidence.extend(matches)

        # Deduplicate by entity_id
        seen_ids = set()
        unique_evidence = []
        for ev in sorted(evidence, key=lambda x: x.confidence or 0, reverse=True):
            if ev.entity_id and ev.entity_id not in seen_ids:
                seen_ids.add(ev.entity_id)
                unique_evidence.append(ev)
            elif not ev.entity_id:
                unique_evidence.append(ev)

        return unique_evidence

    def _extract_chemical_name(
        self,
        label: str,
        definition: str | None = None,
    ) -> str | None:
        """Extract chemical name from term label and/or definition.

        Tries label-based patterns first (these work well for explicit labels
        like "Abnormal blood glucose concentration").  When the label only
        yields a stub (e.g. "glyc" from "Hyperglycemia"), falls back to
        definition-based extraction where the real chemical name usually
        appears verbatim.

        Original case is preserved so that names like "DNAJB9" or "IgA"
        are not lowercased.

        Args:
            label: Term label.
            definition: Term definition (optional but recommended).

        Returns:
            Extracted chemical name or None.
        """
        import re

        # --- Label patterns (match against original, case-insensitive) ---
        # Fluid/location qualifiers that sit between the direction word and the
        # chemical name and must NOT become part of the chemical (multi-word
        # forms first so they win the alternation).
        _qualifier = (
            r"cerebrospinal fluid|cerebrospinal|circulating|blood|serum|plasma|urinary|csf"
        )
        label_patterns = [
            # "Elevated circulating X concentration" / "Abnormal CSF X concentration"
            r"(?:elevated|increased|decreased|reduced|abnormal)\s+"
            rf"(?:{_qualifier})?\s*"
            r"(.+?)\s+(?:concentration|level)",
            # "Abnormal X level"
            r"abnormal\s+(.+?)\s+level",
            # "Increased X"
            r"(?:increased|elevated|decreased|reduced)\s+"
            r"(?:circulating\s+)?(.+?)(?:\s+level|\s+concentration)?$",
        ]

        for pattern in label_patterns:
            match = re.search(pattern, label, re.IGNORECASE)
            if match:
                chemical = match.group(1).strip()
                # Clean up common prefixes/suffixes (case-insensitive)
                chemical = re.sub(
                    rf"^(?:{_qualifier})\s+", "", chemical, flags=re.IGNORECASE
                )
                chemical = re.sub(
                    r"\s+(?:in\s+blood|in\s+urine)$", "", chemical, flags=re.IGNORECASE
                )
                if len(chemical) > 2:
                    return chemical

        # --- Definition patterns (more reliable for Hyper/Hypo-Xemia) ---
        if definition:
            def_patterns = [
                # "concentration of X in the blood/urine"
                r"concentration\s+of\s+(?:an?\s+)?(.+?)\s+in\s+the\s+",
                # "level of X in the blood/urine"
                r"level\s+of\s+(?:an?\s+)?(.+?)\s+in\s+the\s+",
                # "increase in the level of X in the blood"
                r"(?:increase|decrease|abnormality)\s+in\s+the\s+level\s+of\s+(.+?)\s+in\s+the\s+",
            ]

            for pattern in def_patterns:
                match = re.search(pattern, definition, re.IGNORECASE)
                if match:
                    chemical = match.group(1).strip()
                    if len(chemical) > 2:
                        return chemical

        # --- Fallback: HyperXemia / HypoXemia / Xuria from label ---
        # These are last resort since they yield stubs like "glyc"
        suffix_patterns = [
            r"hyper(.+?)emia",
            r"hypo(.+?)emia",
            r"(.+?)uria$",
        ]

        for pattern in suffix_patterns:
            match = re.search(pattern, label, re.IGNORECASE)
            if match:
                chemical = match.group(1).strip()
                if len(chemical) > 2:
                    return chemical

        return None

    def _generate_proposal(
        self,
        hp_term: HPTerm,
        chemical_evidence: list[ChemicalEntityEvidence],
        pattern_assignment: PatternAssignment | None,
    ) -> CurationProposal | None:
        """Generate a curation proposal.

        Args:
            hp_term: Original HP term.
            chemical_evidence: Collected chemical evidence.
            pattern_assignment: Assigned pattern.

        Returns:
            CurationProposal or None if no changes needed.
        """
        from hpo_ai.patterns import ProposalGenerator

        generator = ProposalGenerator(name_normalizer=self.name_normalizer)

        # Get best chemical evidence
        best_chemical = None
        if chemical_evidence:
            best_chemical = max(chemical_evidence, key=lambda x: x.confidence or 0)

        return generator.generate(
            hp_term=hp_term,
            chemical_evidence=best_chemical,
            pattern_assignment=pattern_assignment,
        )

    def _determine_review_status(self, confidence: float) -> ReviewStatus:
        """Determine review status based on confidence.

        Args:
            confidence: Overall confidence score.

        Returns:
            ReviewStatus enum value.
        """
        if confidence >= self.auto_approve_threshold:
            return ReviewStatus.auto_approved
        elif confidence >= self.review_threshold:
            return ReviewStatus.needs_review
        else:
            return ReviewStatus.skipped

    def build_batch(
        self,
        terms: list[HPTerm],
        use_llm: bool = True,
    ) -> list[EvidencePacket]:
        """Build evidence packets for a batch of terms.

        Args:
            terms: List of HP terms.
            use_llm: Whether to use LLM for extraction.

        Returns:
            List of evidence packets.
        """
        packets = []
        for term in terms:
            packet = self.build_packet(term, use_llm=use_llm)
            packets.append(packet)
            logger.info(
                f"Built packet for {term.id}: confidence={packet.overall_confidence:.2f}, "
                f"status={packet.review_status}"
            )
        return packets
