"""ROBOT template generation for applying changes."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from hpo_ai.datamodel import EvidencePacket, ReviewStatus

logger = logging.getLogger(__name__)


class ROBOTTemplateGenerator:
    """Generate ROBOT templates for applying curation changes."""

    def __init__(self) -> None:
        """Initialize the generator."""
        pass

    def generate(
        self,
        packets: list[EvidencePacket],
        output_path: str | Path,
        only_approved: bool = True,
    ) -> None:
        """Generate ROBOT template from approved packets.

        Args:
            packets: List of evidence packets.
            output_path: Path to output TSV file.
            only_approved: Only include approved packets.
        """
        output_path = Path(output_path)

        # Filter packets
        if only_approved:
            packets = [
                p for p in packets
                if p.review_status in [ReviewStatus.auto_approved, ReviewStatus.approved]
            ]

        if not packets:
            logger.warning("No approved packets to export")
            return

        # ROBOT template columns
        columns = [
            "ID",
            "LABEL",
            "A oboInOwl:hasExactSynonym SPLIT=|",
            "A IAO:0000115",  # definition
            "SC 'has role' some %",  # chemical entity
            "SC 'part of' some %",  # location
        ]

        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")

            # Write header row
            writer.writerow(["ID", "LABEL", "SYNONYM", "DEFINITION", "CHEMICAL", "LOCATION"])

            # Write template row (ROBOT header)
            writer.writerow(columns)

            # Write data rows
            for packet in packets:
                row = self._packet_to_row(packet)
                if row:
                    writer.writerow(row)

        logger.info(f"Generated ROBOT template with {len(packets)} terms at {output_path}")

    def _packet_to_row(self, packet: EvidencePacket) -> list[str] | None:
        """Convert packet to ROBOT template row.

        Args:
            packet: Evidence packet.

        Returns:
            List of values for template row, or None if invalid.
        """
        if not packet.proposal:
            return None

        term = packet.hp_term
        proposal = packet.proposal

        # ID
        hp_id = term.id

        # Label
        label = proposal.proposed_label or term.label

        # Synonyms (pipe-separated)
        synonyms = ""
        if proposal.proposed_synonyms:
            syn_values = [s.value for s in proposal.proposed_synonyms if s.value]
            synonyms = "|".join(syn_values)

        # Definition
        definition = proposal.proposed_definition or term.definition or ""

        # Chemical entity
        chemical = proposal.proposed_chemical_entity or ""

        # Location
        location = proposal.proposed_location or ""

        return [hp_id, label, synonyms, definition, chemical, location]

    def generate_update_template(
        self,
        packets: list[EvidencePacket],
        output_path: str | Path,
    ) -> None:
        """Generate ROBOT template for updating existing terms.

        This template only updates labels and definitions, preserving
        existing axioms.

        Args:
            packets: List of evidence packets.
            output_path: Path to output TSV file.
        """
        output_path = Path(output_path)

        # Filter for approved packets
        approved = [
            p for p in packets
            if p.review_status in [ReviewStatus.auto_approved, ReviewStatus.approved]
        ]

        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")

            # Write ROBOT template header
            writer.writerow([
                "ID",
                "LABEL",
                "A oboInOwl:hasExactSynonym SPLIT=|",
                "A IAO:0000115",
            ])

            for packet in approved:
                if not packet.proposal:
                    continue

                term = packet.hp_term
                proposal = packet.proposal

                # Collect synonyms
                synonyms = []
                if proposal.proposed_synonyms:
                    synonyms = [s.value for s in proposal.proposed_synonyms if s.value]

                writer.writerow([
                    term.id,
                    proposal.proposed_label or term.label,
                    "|".join(synonyms),
                    proposal.proposed_definition or term.definition or "",
                ])

        logger.info(f"Generated update template with {len(approved)} terms")
