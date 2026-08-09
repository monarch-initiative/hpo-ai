"""Validation for HPO curation proposals."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from hpo_ai.datamodel import CurationProposal, EvidencePacket, HPTerm

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating a proposal."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ProposalValidator:
    """Validate curation proposals before applying them."""

    def __init__(self) -> None:
        """Initialize the validator."""
        pass

    def validate(self, packet: EvidencePacket) -> ValidationResult:
        """Validate an evidence packet and its proposal.

        Args:
            packet: Evidence packet to validate.

        Returns:
            ValidationResult with any errors or warnings.
        """
        errors = []
        warnings = []

        # Check HP term
        term_errors = self._validate_hp_term(packet.hp_term)
        errors.extend(term_errors)

        # Check proposal
        if packet.proposal:
            proposal_errors, proposal_warnings = self._validate_proposal(
                packet.hp_term, packet.proposal
            )
            errors.extend(proposal_errors)
            warnings.extend(proposal_warnings)

        # Check chemical evidence
        if packet.chemical_evidence:
            chem_warnings = self._validate_chemical_evidence(packet.chemical_evidence)
            warnings.extend(chem_warnings)

        # Check pattern assignment
        if packet.pattern_assignment:
            pattern_warnings = self._validate_pattern(packet.pattern_assignment)
            warnings.extend(pattern_warnings)

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _validate_hp_term(self, term: HPTerm) -> list[str]:
        """Validate HP term data.

        Args:
            term: HP term to validate.

        Returns:
            List of error messages.
        """
        errors = []

        if not term.id:
            errors.append("HP term missing ID")

        if not term.label:
            errors.append("HP term missing label")

        if term.id and not term.id.startswith("HP:"):
            errors.append(f"Invalid HP ID format: {term.id}")

        return errors

    def _validate_proposal(
        self,
        term: HPTerm,
        proposal: CurationProposal,
    ) -> tuple[list[str], list[str]]:
        """Validate a curation proposal.

        Args:
            term: Original HP term.
            proposal: Proposal to validate.

        Returns:
            Tuple of (errors, warnings).
        """
        errors = []
        warnings = []

        # Check proposed label
        if proposal.proposed_label:
            label_errors, label_warnings = self._validate_label(
                proposal.proposed_label, term.label
            )
            errors.extend(label_errors)
            warnings.extend(label_warnings)

        # Check proposed definition
        if proposal.proposed_definition:
            def_errors, def_warnings = self._validate_definition(
                proposal.proposed_definition
            )
            errors.extend(def_errors)
            warnings.extend(def_warnings)

        # Check proposed chemical entity
        if proposal.proposed_chemical_entity:
            chem_errors = self._validate_chemical_id(proposal.proposed_chemical_entity)
            errors.extend(chem_errors)

        # Check proposed location
        if proposal.proposed_location:
            loc_errors = self._validate_location_id(proposal.proposed_location)
            errors.extend(loc_errors)

        return errors, warnings

    def _validate_label(
        self,
        proposed: str,
        original: str,
    ) -> tuple[list[str], list[str]]:
        """Validate proposed label.

        Args:
            proposed: Proposed label.
            original: Original label.

        Returns:
            Tuple of (errors, warnings).
        """
        errors = []
        warnings = []

        # Check length
        if len(proposed) > 200:
            warnings.append(f"Label is very long ({len(proposed)} chars)")

        # Check for common issues
        if proposed.endswith(" "):
            errors.append("Label has trailing whitespace")

        if "  " in proposed:
            errors.append("Label has double spaces")

        # Check case consistency
        if proposed[0].islower():
            warnings.append("Label starts with lowercase letter")

        # Warn if very different from original
        if original:
            from difflib import SequenceMatcher
            similarity = SequenceMatcher(None, original.lower(), proposed.lower()).ratio()
            if similarity < 0.3:
                warnings.append(
                    f"Proposed label is very different from original "
                    f"(similarity: {similarity:.1%})"
                )

        return errors, warnings

    def _validate_definition(
        self,
        definition: str,
    ) -> tuple[list[str], list[str]]:
        """Validate proposed definition.

        Args:
            definition: Proposed definition.

        Returns:
            Tuple of (errors, warnings).
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check basic format
        if not definition.endswith("."):
            warnings.append("Definition should end with a period")

        if definition[0].islower():
            warnings.append("Definition should start with uppercase letter")

        # Check length
        if len(definition) < 20:
            warnings.append("Definition is very short")

        return errors, warnings

    def _validate_chemical_id(self, chemical_id: str) -> list[str]:
        """Validate chemical entity ID.

        Args:
            chemical_id: CHEBI or PRO ID.

        Returns:
            List of errors.
        """
        errors = []

        if not chemical_id.startswith(("CHEBI:", "PR:")):
            errors.append(f"Invalid chemical ID prefix: {chemical_id}")

        return errors

    def _validate_location_id(self, location_id: str) -> list[str]:
        """Validate location ID.

        Args:
            location_id: UBERON ID.

        Returns:
            List of errors.
        """
        errors = []

        if not location_id.startswith("UBERON:"):
            errors.append(f"Invalid location ID prefix: {location_id}")

        return errors

    def _validate_chemical_evidence(
        self,
        evidence: list,  # list[ChemicalEntityEvidence]
    ) -> list[str]:
        """Validate chemical evidence.

        Args:
            evidence: List of chemical evidence.

        Returns:
            List of warnings.
        """
        warnings: list[str] = []

        if not evidence:
            return warnings

        # Check if top matches disagree
        if len(evidence) >= 2:
            top_ids = [e.entity_id for e in evidence[:2] if e.entity_id]
            if len(top_ids) == 2 and top_ids[0] != top_ids[1]:
                warnings.append(
                    f"Top chemical matches disagree: {top_ids[0]} vs {top_ids[1]}"
                )

        # Check for low confidence
        best = evidence[0]
        if best.confidence and best.confidence < 0.7:
            warnings.append(f"Low confidence chemical match: {best.confidence:.2f}")

        return warnings

    def _validate_pattern(
        self,
        pattern,  # PatternAssignment
    ) -> list[str]:
        """Validate pattern assignment.

        Args:
            pattern: Pattern assignment.

        Returns:
            List of warnings.
        """
        warnings = []

        if pattern.confidence and pattern.confidence < 0.7:
            warnings.append(f"Low confidence pattern: {pattern.confidence:.2f}")

        if pattern.requires_new_pattern:
            warnings.append("New DOSDP pattern may be required")

        return warnings

    def validate_batch(
        self,
        packets: list,  # list[EvidencePacket]
    ) -> dict[str, ValidationResult]:
        """Validate a batch of packets.

        Args:
            packets: List of evidence packets.

        Returns:
            Dict mapping packet IDs to validation results.
        """
        results = {}
        for packet in packets:
            results[packet.id] = self.validate(packet)
        return results
