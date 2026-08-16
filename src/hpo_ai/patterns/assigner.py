"""Pattern assignment for HPO chemical phenotypes."""

from __future__ import annotations

import logging
import re

from hpo_ai.datamodel import Direction, HPTerm, PatternAssignment, PatternType

logger = logging.getLogger(__name__)

# Location mappings
BLOOD_TERMS = ["blood", "circulating", "serum", "plasma"]
URINE_TERMS = ["urine", "urinary", "uria"]
CSF_TERMS = ["csf", "cerebrospinal"]

# UBERON IDs for common locations
LOCATION_MAP = {
    "blood": ("UBERON:0000178", "blood"),
    "serum": ("UBERON:0001977", "blood serum"),
    "plasma": ("UBERON:0001969", "blood plasma"),
    "urine": ("UBERON:0001088", "urine"),
    "csf": ("UBERON:0001359", "cerebrospinal fluid"),
    "amniotic fluid": ("UBERON:0000173", "amniotic fluid"),
}


class PatternAssigner:
    """Assign DOSDP patterns to HPO chemical phenotype terms."""

    def __init__(self) -> None:
        """Initialize the pattern assigner."""
        # Patterns for detecting direction
        self.increased_patterns = [
            r"^hyper",
            r"^elevated",
            r"^increased",
            r"^high\b",
            r"above.*normal",
            r"overproduction",
        ]
        self.decreased_patterns = [
            r"^hypo",
            r"^decreased",
            r"^reduced",
            r"^diminished",
            r"^low\b",
            r"^deficien",
            r"below.*normal",
        ]

        # Patterns for detecting special categories
        self.modifier_keywords = [
            "episodic",
            "recurrent",
            "persistent",
            "transient",
            "fasting",
            "postprandial",
            "neonatal",
        ]
        self.combination_keywords = [
            "with",
            "and",
            "combined",
            "associated",
        ]
        self.process_keywords = [
            "metabolism",
            "metabolic",
            "homeostasis",
            "cycle",
            "pathway",
            "synthesis",
            "secretion",
        ]
        self.activity_keywords = [
            "activity",
            "deficiency",
            "enzyme",
        ]

    def assign(self, hp_term: HPTerm) -> PatternAssignment:
        """Assign a DOSDP pattern to an HP term.

        Args:
            hp_term: The HP term to analyze.

        Returns:
            PatternAssignment with the determined pattern.
        """
        label = hp_term.label.lower()
        definition = (hp_term.definition or "").lower()
        text = f"{label} {definition}"

        # Check for special categories first
        pattern_type = self._check_special_categories(label)
        if pattern_type:
            return PatternAssignment(
                pattern_name=pattern_type,
                confidence=0.8,
                rationale=f"Detected special category: {pattern_type.value}",
            )

        # Determine direction
        direction = self._determine_direction(label)

        # Determine location
        location_id, location_label = self._determine_location(text)

        # Determine pattern based on direction and location
        pattern_type = self._get_pattern_type(direction, location_id, location_label)

        confidence = self._calculate_confidence(direction, location_id)

        return PatternAssignment(
            pattern_name=pattern_type,
            direction=direction,
            location_id=location_id,
            location_label=location_label,
            confidence=confidence,
            rationale=self._generate_rationale(direction, location_label),
        )

    def _check_special_categories(self, label: str) -> PatternType | None:
        """Check if term belongs to a special category.

        Args:
            label: Term label.

        Returns:
            Special PatternType or None.
        """
        label_lower = label.lower()

        # Check for modifiers
        for keyword in self.modifier_keywords:
            if keyword in label_lower:
                return PatternType.modifier

        # Check for combination phenotypes (multiple chemicals)
        for keyword in self.combination_keywords:
            if f" {keyword} " in f" {label_lower} ":
                # Check if it's combining two phenotypes
                if re.search(r"(hyper|hypo)\w+.*(hyper|hypo)", label_lower):
                    return PatternType.combination_phenotype

        # Check for process phenotypes
        for keyword in self.process_keywords:
            if keyword in label_lower:
                return PatternType.process

        # Check for activity phenotypes
        for keyword in self.activity_keywords:
            if keyword in label_lower:
                return PatternType.activity

        # Check for enzyme names: words of 6+ chars ending in -ase
        # (e.g. dehydrogenase, kinase, lipase, phosphatase, hexokinase)
        if re.search(r"\b\w{3,}ase\b", label_lower):
            return PatternType.activity

        return None

    def _determine_direction(self, label: str) -> Direction:
        """Determine the direction of abnormality.

        Args:
            label: Term label.

        Returns:
            Direction enum value.
        """
        label_lower = label.lower()

        for pattern in self.increased_patterns:
            if re.search(pattern, label_lower):
                return Direction.increased

        for pattern in self.decreased_patterns:
            if re.search(pattern, label_lower):
                return Direction.decreased

        return Direction.abnormal

    def _determine_location(self, text: str) -> tuple[str | None, str | None]:
        """Determine the anatomical location.

        Args:
            text: Combined label and definition text.

        Returns:
            Tuple of (UBERON ID, location label).
        """
        text_lower = text.lower()

        def has_word(term: str) -> bool:
            """Match ``term`` as a whole word.

            Word boundaries stop chemical names from being read as fluids --
            e.g. 'taurine' must not match the fluid 'urine'.
            """
            return re.search(rf"\b{re.escape(term)}\b", text_lower) is not None

        # Check for specific locations (word-boundary matched)
        for location, (uberon_id, uberon_label) in LOCATION_MAP.items():
            if has_word(location):
                return uberon_id, uberon_label

        # Check for CSF-related terms (e.g. 'cerebrospinal' without 'csf')
        for term in CSF_TERMS:
            if has_word(term):
                return "UBERON:0001359", "cerebrospinal fluid"

        # Check for blood-related terms
        for term in BLOOD_TERMS:
            if has_word(term):
                return "UBERON:0000178", "blood"

        # Check for urine-related terms
        for term in URINE_TERMS:
            if has_word(term):
                return "UBERON:0001088", "urine"

        # CSF for -rrhachia / -rachia clinical terms (e.g. glycorrhachia)
        if re.search(r"rrhachia\b|rachia\b", text_lower):
            return "UBERON:0001359", "cerebrospinal fluid"

        # Default to blood for -emia terms (word-final suffix)
        if re.search(r"emia\b", text_lower):
            return "UBERON:0000178", "blood"

        # Default to urine for -uria terms (word-final suffix)
        if re.search(r"uria\b", text_lower):
            return "UBERON:0001088", "urine"

        return None, None

    def _get_pattern_type(
        self,
        direction: Direction,
        location_id: str | None,
        location_label: str | None,
    ) -> PatternType:
        """Get the appropriate pattern type.

        Args:
            direction: Direction of abnormality.
            location_id: UBERON location ID.
            location_label: Location label.

        Returns:
            PatternType enum value.
        """
        is_blood = location_label in ["blood", "blood serum", "blood plasma"]
        is_urine = location_label == "urine"

        if direction == Direction.increased:
            if is_blood:
                return PatternType.abnormallyIncreasedLevelOfChemicalEntityInBlood
            elif is_urine:
                return PatternType.abnormallyIncreasedLevelOfChemicalEntityInUrine
            else:
                return PatternType.abnormallyIncreasedLevelOfChemicalEntityInLocation
        elif direction == Direction.decreased:
            if is_blood:
                return PatternType.abnormallyDecreasedLevelOfChemicalEntityInBlood
            elif is_urine:
                return PatternType.abnormallyDecreasedLevelOfChemicalEntityInUrine
            else:
                return PatternType.abnormallyDecreasedLevelOfChemicalEntityInLocation
        else:  # abnormal
            if is_blood:
                return PatternType.abnormalLevelOfChemicalEntityInBlood
            elif is_urine:
                return PatternType.abnormalLevelOfChemicalEntityInUrine
            else:
                return PatternType.abnormalLevelOfChemicalEntityInLocation

    def _calculate_confidence(
        self,
        direction: Direction,
        location_id: str | None,
    ) -> float:
        """Calculate confidence in pattern assignment.

        Args:
            direction: Detected direction.
            location_id: Detected location.

        Returns:
            Confidence score between 0 and 1.
        """
        base = 0.7

        # Boost for specific direction
        if direction != Direction.abnormal:
            base += 0.1

        # Boost for identified location
        if location_id:
            base += 0.1

        return min(1.0, base)

    def _generate_rationale(
        self,
        direction: Direction,
        location_label: str | None,
    ) -> str:
        """Generate rationale for pattern assignment.

        Args:
            direction: Detected direction.
            location_label: Detected location.

        Returns:
            Rationale string.
        """
        parts = []

        if direction == Direction.increased:
            parts.append("Detected increased/elevated pattern")
        elif direction == Direction.decreased:
            parts.append("Detected decreased/reduced pattern")
        else:
            parts.append("Direction not specified (abnormal)")

        if location_label:
            parts.append(f"Location: {location_label}")
        else:
            parts.append("Location not clearly specified")

        return "; ".join(parts)
