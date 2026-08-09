"""TSV export for human review."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from hpo_ai.datamodel import EvidencePacket

logger = logging.getLogger(__name__)


class TSVExporter:
    """Export evidence packets to TSV format for human review."""

    # Column names matching curated_phenotypes.tsv format
    COLUMNS = [
        "finished",
        "medkorrekt",
        "hpo_id",
        "hpo_label",
        "definition",
        "MANUAL PREFERED LABEL",
        "MANUAL PREFERRED DEFINITION",
        "OFFICIAL COMMENT",
        "chemical_phenotype",
        "correct_pattern",
        "KM review",
        "defined_class",
        "defined_class_name",
        "anatomical_entity",
        "anatomical_entity_label",
        "location",
        "biological_process",
        "biological_process_label",
        "chemical_entity",
        "chemical_entity_label",
        "role",
        "role_label",
        "add_definitions",
        "add_synonym",
        "curator_comment",
        "time",
        "confidence",
        "evidence_summary",
    ]

    def __init__(self) -> None:
        """Initialize the exporter."""
        pass

    def export(
        self,
        packets: list[EvidencePacket],
        output_path: str | Path,
    ) -> None:
        """Export packets to TSV file.

        Args:
            packets: List of evidence packets.
            output_path: Path to output TSV file.
        """
        output_path = Path(output_path)

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.COLUMNS, delimiter="\t")
            writer.writeheader()

            for packet in packets:
                row = self._packet_to_row(packet)
                writer.writerow(row)

        logger.info(f"Exported {len(packets)} packets to {output_path}")

    def _packet_to_row(self, packet: EvidencePacket) -> dict:
        """Convert packet to TSV row.

        Args:
            packet: Evidence packet.

        Returns:
            Dict with column values.
        """
        term = packet.hp_term
        proposal = packet.proposal
        pattern = packet.pattern_assignment

        # Helper to get enum value (handles both enum and string)
        def get_enum_value(val):
            if val is None:
                return ""
            return val.value if hasattr(val, 'value') else str(val)

        # Determine finished status
        review_status = get_enum_value(packet.review_status)
        if review_status == "auto_approved":
            finished = "done"
        elif review_status == "skipped":
            finished = "ignore"
        else:
            finished = "to do"

        # Get best chemical evidence
        chem_id = ""
        chem_label = ""
        if packet.chemical_evidence:
            best = packet.chemical_evidence[0]
            chem_id = best.entity_id or ""
            chem_label = best.entity_label or ""

        # Get pattern name
        pattern_name = get_enum_value(pattern.pattern_name) if pattern else ""

        # Get location
        location_id = pattern.location_id if pattern else ""

        # Get proposed values
        proposed_label = ""
        proposed_def = ""
        if proposal:
            proposed_label = proposal.proposed_label or ""
            proposed_def = proposal.proposed_definition or ""

        # Generate evidence summary
        evidence_summary = self._generate_evidence_summary(packet)

        return {
            "finished": finished,
            "medkorrekt": "ignore",
            "hpo_id": term.id,
            "hpo_label": term.label,
            "definition": term.definition or "",
            "MANUAL PREFERED LABEL": proposed_label,
            "MANUAL PREFERRED DEFINITION": proposed_def,
            "OFFICIAL COMMENT": "",
            "chemical_phenotype": "Yes",
            "correct_pattern": pattern_name,
            "KM review": "",
            "defined_class": term.id,
            "defined_class_name": proposed_label or term.label,
            "anatomical_entity": "",
            "anatomical_entity_label": "",
            "location": location_id,
            "biological_process": "",
            "biological_process_label": "",
            "chemical_entity": chem_id,
            "chemical_entity_label": chem_label,
            "role": "",
            "role_label": "",
            "add_definitions": "",
            "add_synonym": "",
            "curator_comment": packet.curator_notes or "",
            "time": "",
            "confidence": f"{packet.overall_confidence:.2f}" if packet.overall_confidence else "",
            "evidence_summary": evidence_summary,
        }

    def _generate_evidence_summary(self, packet: EvidencePacket) -> str:
        """Generate a summary of evidence for human review.

        Args:
            packet: Evidence packet.

        Returns:
            Summary string.
        """
        # Helper to get enum value (handles both enum and string)
        def get_enum_value(val):
            if val is None:
                return ""
            return val.value if hasattr(val, 'value') else str(val)

        parts = []

        # Pattern info
        if packet.pattern_assignment:
            pattern_name = get_enum_value(packet.pattern_assignment.pattern_name)
            parts.append(f"Pattern: {pattern_name}")
            if packet.pattern_assignment.rationale:
                parts.append(f"Rationale: {packet.pattern_assignment.rationale}")

        # Chemical evidence
        if packet.chemical_evidence:
            best = packet.chemical_evidence[0]
            parts.append(
                f"Chemical: {best.entity_label} ({best.entity_id}) "
                f"conf={best.confidence:.2f}"
            )
            if len(packet.chemical_evidence) > 1:
                parts.append(f"({len(packet.chemical_evidence)} candidates)")

        # Proposal info
        if packet.proposal and packet.proposal.change_type:
            change_type = get_enum_value(packet.proposal.change_type)
            parts.append(f"Change type: {change_type}")
            if packet.proposal.label_diff:
                parts.append(f"Label: {packet.proposal.label_diff}")

        return " | ".join(parts)

    def export_for_review(
        self,
        packets: list[EvidencePacket],
        output_path: str | Path,
        min_confidence: float = 0.0,
        max_confidence: float = 1.0,
    ) -> None:
        """Export packets filtered by confidence for review.

        Args:
            packets: List of evidence packets.
            output_path: Path to output TSV file.
            min_confidence: Minimum confidence threshold.
            max_confidence: Maximum confidence threshold.
        """
        filtered = [
            p for p in packets
            if min_confidence <= (p.overall_confidence or 0) <= max_confidence
        ]
        self.export(filtered, output_path)
        logger.info(
            f"Exported {len(filtered)} packets with confidence "
            f"{min_confidence:.2f}-{max_confidence:.2f}"
        )
