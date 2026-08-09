"""Proposal generator for HPO chemical phenotype curation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from hpo_ai.datamodel import (
    ChangeType,
    ChemicalEntityEvidence,
    CurationProposal,
    Direction,
    HPTerm,
    PatternAssignment,
    PatternType,
    Synonym,
    SynonymScope,
)

if TYPE_CHECKING:
    from hpo_ai.enrichment.name_normalizer import NameNormalizer

logger = logging.getLogger(__name__)

# Label templates based on naming conventions from issue #11342
LABEL_TEMPLATES = {
    # Blood patterns
    PatternType.abnormalLevelOfChemicalEntityInBlood: "Abnormal circulating {chemical} concentration",
    PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood: "Elevated circulating {chemical} concentration",
    PatternType.abnormallyDecreasedLevelOfChemicalEntityInBlood: "Decreased circulating {chemical} concentration",
    # Urine patterns
    PatternType.abnormalLevelOfChemicalEntityInUrine: "Abnormal urinary {chemical} concentration",
    PatternType.abnormallyIncreasedLevelOfChemicalEntityInUrine: "Elevated urinary {chemical} concentration",
    PatternType.abnormallyDecreasedLevelOfChemicalEntityInUrine: "Decreased urinary {chemical} concentration",
    # Location patterns
    PatternType.abnormalLevelOfChemicalEntityInLocation: "Abnormal {chemical} concentration in {location}",
    PatternType.abnormallyIncreasedLevelOfChemicalEntityInLocation: "Elevated {chemical} concentration in {location}",
    PatternType.abnormallyDecreasedLevelOfChemicalEntityInLocation: "Decreased {chemical} concentration in {location}",
}

# Definition templates
DEFINITION_TEMPLATES = {
    # Blood patterns
    PatternType.abnormalLevelOfChemicalEntityInBlood: (
        "Any deviation from the normal concentration of {chemical} in the blood circulation."
    ),
    PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood: (
        "The concentration of {chemical} in the blood circulation is above the upper limit of normal."
    ),
    PatternType.abnormallyDecreasedLevelOfChemicalEntityInBlood: (
        "The concentration of {chemical} in the blood circulation is below the lower limit of normal."
    ),
    # Urine patterns
    PatternType.abnormalLevelOfChemicalEntityInUrine: (
        "Any deviation from the normal concentration of {chemical} in the urine."
    ),
    PatternType.abnormallyIncreasedLevelOfChemicalEntityInUrine: (
        "The concentration of {chemical} in the urine is above the upper limit of normal."
    ),
    PatternType.abnormallyDecreasedLevelOfChemicalEntityInUrine: (
        "The concentration of {chemical} in the urine is below the lower limit of normal."
    ),
    # Location patterns
    PatternType.abnormalLevelOfChemicalEntityInLocation: (
        "Any deviation from the normal concentration of {chemical} in {location}."
    ),
    PatternType.abnormallyIncreasedLevelOfChemicalEntityInLocation: (
        "The concentration of {chemical} in {location} is above the upper limit of normal."
    ),
    PatternType.abnormallyDecreasedLevelOfChemicalEntityInLocation: (
        "The concentration of {chemical} in {location} is below the lower limit of normal."
    ),
}

# Fluid-qualifier naming, for fluids that keep the location up front rather
# than using the generic "... in <location>" phrasing.  Per issue #11702, CSF
# terms follow "<Direction> CSF % concentration", mirroring the blood
# ("circulating") and urine ("urinary") conventions.  Keyed by UBERON location
# id -> (label qualifier, definition fluid name).
FLUID_QUALIFIERS = {
    "UBERON:0001359": ("CSF", "cerebrospinal fluid"),
}

# Direction (string value) -> label / definition templates for fluid qualifiers.
FLUID_LABEL_TEMPLATES = {
    "abnormal": "Abnormal {qualifier} {chemical} concentration",
    "increased": "Elevated {qualifier} {chemical} concentration",
    "decreased": "Decreased {qualifier} {chemical} concentration",
}
FLUID_DEFINITION_TEMPLATES = {
    "abnormal": "Any deviation from the normal concentration of {chemical} in the {fluid}.",
    "increased": "The concentration of {chemical} in the {fluid} is above the upper limit of normal.",
    "decreased": "The concentration of {chemical} in the {fluid} is below the lower limit of normal.",
}

# Synonym templates based on issue #11342
SYNONYM_TEMPLATES = {
    PatternType.abnormalLevelOfChemicalEntityInBlood: [
        "Abnormal {chemical} level",
        "Abnormal {chemical} concentration",
    ],
    PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood: [
        "Increased {chemical} level",
        "Elevated {chemical} level",
        "Increased {chemical} concentration",
        "Elevated {chemical} concentration",
        "Increased {chemical} level in blood",
        "Elevated {chemical} level in blood",
    ],
    PatternType.abnormallyDecreasedLevelOfChemicalEntityInBlood: [
        "Decreased {chemical} level",
        "Reduced {chemical} level",
        "Decreased {chemical} concentration",
        "Reduced {chemical} concentration",
        "Decreased {chemical} level in blood",
        "Reduced {chemical} level in blood",
    ],
}


def _generate_proposal_id() -> str:
    """Generate unique proposal ID."""
    return f"prop_{uuid4().hex[:12]}"


class ProposalGenerator:
    """Generate curation proposals for HPO chemical phenotypes."""

    def __init__(self, name_normalizer: NameNormalizer | None = None) -> None:
        """Initialize the proposal generator.

        Args:
            name_normalizer: Optional normalizer for chemical entity labels.
        """
        self._name_normalizer = name_normalizer

    def generate(
        self,
        hp_term: HPTerm,
        chemical_evidence: ChemicalEntityEvidence | None,
        pattern_assignment: PatternAssignment | None,
    ) -> CurationProposal | None:
        """Generate a curation proposal.

        Args:
            hp_term: Original HP term.
            chemical_evidence: Best chemical entity evidence.
            pattern_assignment: Assigned pattern.

        Returns:
            CurationProposal or None if no changes can be proposed.
        """
        if not pattern_assignment:
            return None

        # Skip special patterns that need manual handling
        special_patterns = [
            PatternType.abnormalAbsenceOfChemicalEntity,
            PatternType.modifier,
            PatternType.combination_phenotype,
            PatternType.process,
            PatternType.activity,
            PatternType.method_observed,
            PatternType.unknown,
        ]
        # Handle both enum and string values
        pattern_value = (
            pattern_assignment.pattern_name
            if isinstance(pattern_assignment.pattern_name, str)
            else pattern_assignment.pattern_name.value
        )
        if pattern_value in [p.value for p in special_patterns]:
            return CurationProposal(
                id=_generate_proposal_id(),
                change_type=ChangeType.no_change,
                label_diff=f"Special pattern ({pattern_value}) requires manual review",
            )

        # Get chemical name
        chemical_name = self._get_chemical_name(hp_term, chemical_evidence)
        if not chemical_name:
            return None

        # Fluids that keep the location up front (e.g. CSF, per #11702) use
        # dedicated templates instead of the generic "... in <location>" form.
        fluid = (
            FLUID_QUALIFIERS.get(pattern_assignment.location_id)
            if pattern_assignment.location_id
            else None
        )
        if fluid:
            qualifier, fluid_name = fluid
            direction = pattern_assignment.direction or Direction.abnormal
            direction_val = getattr(direction, "value", direction) or "abnormal"
            proposed_label = FLUID_LABEL_TEMPLATES[direction_val].format(
                qualifier=qualifier, chemical=chemical_name
            )
            proposed_definition = FLUID_DEFINITION_TEMPLATES[direction_val].format(
                chemical=chemical_name, fluid=fluid_name
            )
        else:
            # Generate label
            proposed_label = self._generate_label(
                pattern_assignment.pattern_name,
                chemical_name,
                pattern_assignment.location_label,
            )

            # Generate definition
            proposed_definition = self._generate_definition(
                pattern_assignment.pattern_name,
                chemical_name,
                pattern_assignment.location_label,
            )

        # Generate synonyms
        proposed_synonyms = self._generate_synonyms(
            hp_term,
            pattern_assignment.pattern_name,
            chemical_name,
        )

        # Get proposed chemical entity
        proposed_chemical = None
        if chemical_evidence and chemical_evidence.entity_id:
            proposed_chemical = chemical_evidence.entity_id

        # Generate logical definition
        proposed_logical_def = self._generate_logical_definition(
            pattern_assignment,
            proposed_chemical,
        )

        # Determine change type
        change_type = self._determine_change_type(
            hp_term,
            proposed_label,
            proposed_definition,
            proposed_chemical,
        )

        # Generate diffs
        label_diff = self._generate_label_diff(hp_term.label, proposed_label)
        definition_diff = self._generate_definition_diff(
            hp_term.definition, proposed_definition
        )

        return CurationProposal(
            id=_generate_proposal_id(),
            proposed_label=proposed_label,
            proposed_definition=proposed_definition,
            proposed_synonyms=proposed_synonyms if proposed_synonyms else None,
            proposed_chemical_entity=proposed_chemical,
            proposed_location=pattern_assignment.location_id,
            proposed_logical_definition=proposed_logical_def,
            change_type=change_type,
            label_diff=label_diff,
            definition_diff=definition_diff,
        )

    def _get_chemical_name(
        self,
        hp_term: HPTerm,
        chemical_evidence: ChemicalEntityEvidence | None,
    ) -> str | None:
        """Get the chemical name to use in templates.

        If a ``NameNormalizer`` was provided at init, the result is
        normalized before being returned.

        Args:
            hp_term: Original HP term.
            chemical_evidence: Chemical evidence if available.

        Returns:
            Chemical name or None.
        """
        name: str | None = None

        if chemical_evidence:
            # Prefer abbreviation if widely used
            if chemical_evidence.preferred_abbreviation:
                name = chemical_evidence.preferred_abbreviation
            else:
                name = chemical_evidence.entity_label
        else:
            # Try to extract from term label first
            name = self._extract_chemical_from_label(hp_term.label)
            if not name:
                # Fall back to definition extraction
                name = self._extract_chemical_from_definition(hp_term.definition)

        if name and self._name_normalizer:
            name = self._name_normalizer.normalize(name)

        return name

    def _extract_chemical_from_label(self, label: str) -> str | None:
        """Extract chemical name from explicit label patterns.

        Only matches explicit patterns like "X concentration" / "X level".
        Does NOT match suffix patterns (HyperXemia, Xuria) which produce
        stubs -- those are handled as a last resort in ``_get_chemical_name``.

        Matches against the original label using ``re.IGNORECASE`` so
        that names like "DNAJB9" or "IgA" preserve their case.

        Args:
            label: Term label.

        Returns:
            Extracted chemical name or None.
        """
        import re

        # Fluid/location qualifiers to strip (multi-word forms first).
        qualifier = (
            r"cerebrospinal fluid|cerebrospinal|circulating|blood|serum|plasma|urinary|csf"
        )
        # Explicit patterns only -- no suffix patterns here
        patterns = [
            # "Elevated circulating X concentration" / "Abnormal CSF X concentration"
            r"(?:elevated|increased|decreased|reduced|abnormal)\s+"
            rf"(?:{qualifier})?\s*"
            r"(.+?)\s+(?:concentration|level)",
        ]

        for pattern in patterns:
            match = re.search(pattern, label, re.IGNORECASE)
            if match:
                chemical = match.group(1).strip()
                # Belt-and-suspenders: strip a leading qualifier the optional
                # group may have skipped (e.g. when it matched empty).
                chemical = re.sub(
                    rf"^(?:{qualifier})\s+", "", chemical, flags=re.IGNORECASE
                )
                if len(chemical) > 2:
                    return chemical

        return None

    def _extract_chemical_from_label_suffix(self, label: str) -> str | None:
        """Extract chemical name from suffix patterns (last resort).

        Handles HyperXemia, HypoXemia, Xuria patterns which produce
        approximate stubs (e.g. "glyc" from "Hyperglycemia").

        Args:
            label: Term label.

        Returns:
            Extracted chemical name or None.
        """
        import re

        suffix_patterns = [
            r"hyper(.+?)emia$",
            r"hypo(.+?)emia$",
            r"(.+?)uria$",
        ]

        for pattern in suffix_patterns:
            match = re.search(pattern, label, re.IGNORECASE)
            if match:
                chemical = match.group(1).strip()
                if len(chemical) > 2:
                    return chemical

        return None

    def _extract_chemical_from_definition(self, definition: str | None) -> str | None:
        """Extract chemical name from term definition.

        Definitions often contain the actual chemical name verbatim,
        e.g. "An increased concentration of glucose in the blood."

        Args:
            definition: Term definition.

        Returns:
            Extracted chemical name or None.
        """
        if not definition:
            return None

        import re

        patterns = [
            # "concentration of X in the blood/urine"
            r"concentration\s+of\s+(?:an?\s+)?(.+?)\s+in\s+the\s+",
            # "level of X in the blood/urine"
            r"level\s+of\s+(?:an?\s+)?(.+?)\s+in\s+the\s+",
            # "increase in the level of X in the blood"
            r"(?:increase|decrease|abnormality)\s+in\s+the\s+level\s+of\s+(.+?)\s+in\s+the\s+",
        ]

        for pattern in patterns:
            match = re.search(pattern, definition, re.IGNORECASE)
            if match:
                chemical = match.group(1).strip()
                if len(chemical) > 2:
                    return chemical

        return None

    def _generate_label(
        self,
        pattern: PatternType,
        chemical: str,
        location: str | None,
    ) -> str:
        """Generate label from template.

        Args:
            pattern: Pattern type.
            chemical: Chemical name.
            location: Location label if needed.

        Returns:
            Generated label.
        """
        template = LABEL_TEMPLATES.get(pattern)
        if not template:
            return f"Abnormal {chemical} concentration"

        label = template.format(chemical=chemical, location=location or "the body")
        return label

    def _generate_definition(
        self,
        pattern: PatternType,
        chemical: str,
        location: str | None,
    ) -> str:
        """Generate definition from template.

        Args:
            pattern: Pattern type.
            chemical: Chemical name.
            location: Location label if needed.

        Returns:
            Generated definition.
        """
        template = DEFINITION_TEMPLATES.get(pattern)
        if not template:
            return f"An abnormality in the concentration of {chemical}."

        definition = template.format(chemical=chemical, location=location or "the body")
        return definition

    def _generate_synonyms(
        self,
        hp_term: HPTerm,
        pattern: PatternType,
        chemical: str,
    ) -> list[Synonym]:
        """Generate synonyms including original label.

        Args:
            hp_term: Original HP term.
            pattern: Pattern type.
            chemical: Chemical name.

        Returns:
            List of Synonym objects.
        """
        synonyms = []

        # Keep original label as exact synonym
        synonyms.append(
            Synonym(value=hp_term.label, scope=SynonymScope.exact)
        )

        # Add template-based synonyms
        templates = SYNONYM_TEMPLATES.get(pattern, [])
        for template in templates:
            syn_value = template.format(chemical=chemical)
            # Avoid duplicating the original label
            if syn_value.lower() != hp_term.label.lower():
                synonyms.append(
                    Synonym(value=syn_value, scope=SynonymScope.exact)
                )

        # Keep existing synonyms
        if hp_term.synonyms:
            for syn in hp_term.synonyms:
                if syn.value and syn.value.lower() not in [s.value.lower() for s in synonyms]:
                    synonyms.append(syn)

        return synonyms

    def _generate_logical_definition(
        self,
        pattern: PatternAssignment,
        chemical_id: str | None,
    ) -> str | None:
        """Generate OWL logical definition.

        Args:
            pattern: Pattern assignment.
            chemical_id: CHEBI/PRO ID.

        Returns:
            Logical definition string or None.
        """
        if not chemical_id or not pattern.location_id:
            return None

        # Generate Manchester syntax for the logical definition
        direction = pattern.direction or Direction.abnormal

        if direction == Direction.increased:
            level = "'has increased amount'"
        elif direction == Direction.decreased:
            level = "'has decreased amount'"
        else:
            level = "'has abnormal amount'"

        logical_def = (
            f"'phenotype' and "
            f"({level} some ({chemical_id} and ('part of' some {pattern.location_id})))"
        )

        return logical_def

    def _determine_change_type(
        self,
        hp_term: HPTerm,
        proposed_label: str | None,
        proposed_definition: str | None,
        proposed_chemical: str | None,
    ) -> ChangeType:
        """Determine the type of change being proposed.

        Args:
            hp_term: Original HP term.
            proposed_label: Proposed new label.
            proposed_definition: Proposed new definition.
            proposed_chemical: Proposed chemical entity.

        Returns:
            ChangeType enum value.
        """
        label_changed = bool(
            proposed_label and
            proposed_label.lower() != (hp_term.label or "").lower()
        )
        definition_changed = bool(
            proposed_definition and
            proposed_definition.lower() != (hp_term.definition or "").lower()
        )
        axiom_changed = bool(
            proposed_chemical and
            proposed_chemical != hp_term.existing_chemical_entity
        )

        changes = sum([label_changed, definition_changed, axiom_changed])

        if changes == 0:
            return ChangeType.no_change
        elif changes >= 2:
            return ChangeType.full_refactor
        elif label_changed:
            return ChangeType.label_only
        elif definition_changed:
            return ChangeType.definition_only
        else:
            return ChangeType.axiom_only

    def _generate_label_diff(
        self,
        original: str | None,
        proposed: str | None,
    ) -> str:
        """Generate a description of label changes.

        Args:
            original: Original label.
            proposed: Proposed label.

        Returns:
            Description of changes.
        """
        if not original or not proposed:
            return ""

        if original.lower() == proposed.lower():
            return "No change"

        return f"'{original}' -> '{proposed}'"

    def _generate_definition_diff(
        self,
        original: str | None,
        proposed: str | None,
    ) -> str:
        """Generate a description of definition changes.

        Args:
            original: Original definition.
            proposed: Proposed definition.

        Returns:
            Description of changes.
        """
        if not proposed:
            return ""

        if not original:
            return "Added definition"

        if original.lower() == proposed.lower():
            return "No change"

        return "Definition updated"
