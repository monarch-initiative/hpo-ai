"""Confidence scoring for HPO chemical phenotype curation.

The scorer combines four raw signals into two conceptual dimensions:

- **Entity evidence** -- do we know what chemical entity this term is
  about?  Combines the best chemical-match confidence with any existing
  CHEBI/PRO/UBERON annotations already present on the term.

- **Pattern evidence** -- do we know what DOSDP template to use?
  Combines pattern-assignment confidence with label-similarity (a high
  similarity confirms the pattern choice).

When both signals are strong the overall score approaches 1.0, which is
the threshold for auto-approval.
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from hpo_ai.datamodel import (
    ChemicalEntityEvidence,
    CurationProposal,
    HPTerm,
    PatternAssignment,
    PatternType,
)

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """Calculate confidence scores for curation decisions.

    The confidence score is a weighted combination of two composite
    signals, each derived from two raw sub-scores:

    - **Entity evidence** (``entity_weight``): ``max(chemical, existing)``
    - **Pattern evidence** (``pattern_weight``): ``max(pattern, label)``

    Example
    -------
    >>> from hpo_ai.datamodel import HPTerm
    >>> scorer = ConfidenceScorer()
    >>> scorer.score(
    ...     hp_term=HPTerm(id="HP:0000001", label="test"),
    ...     chemical_evidence=None,
    ...     pattern_assignment=None,
    ...     proposal=None,
    ... )
    0.0
    """

    def __init__(
        self,
        entity_weight: float = 0.5,
        pattern_weight: float = 0.5,
    ) -> None:
        """Initialize the scorer.

        Args:
            entity_weight: Weight for entity evidence (chemical + existing).
            pattern_weight: Weight for pattern evidence (pattern + label).
        """
        total = entity_weight + pattern_weight
        self.entity_weight = entity_weight / total
        self.pattern_weight = pattern_weight / total

    def score(
        self,
        hp_term: HPTerm,
        chemical_evidence: list[ChemicalEntityEvidence] | None,
        pattern_assignment: PatternAssignment | None,
        proposal: CurationProposal | None,
    ) -> float:
        """Calculate overall confidence score.

        Args:
            hp_term: Original HP term.
            chemical_evidence: List of chemical evidence.
            pattern_assignment: Pattern assignment.
            proposal: Generated proposal.

        Returns:
            Confidence score between 0 and 1.
        """
        chemical_score = self._score_chemical(chemical_evidence)
        existing_score = self._score_existing(hp_term)
        pattern_score = self._score_pattern(pattern_assignment)
        label_score = self._score_label(hp_term, proposal)

        entity_evidence = max(chemical_score, existing_score)
        pattern_evidence = max(pattern_score, label_score)

        weighted_score = (
            entity_evidence * self.entity_weight
            + pattern_evidence * self.pattern_weight
        )

        logger.debug(
            f"Scores for {hp_term.id}: "
            f"chemical={chemical_score:.2f}, existing={existing_score:.2f}, "
            f"pattern={pattern_score:.2f}, label={label_score:.2f} | "
            f"entity={entity_evidence:.2f}, pattern_ev={pattern_evidence:.2f}, "
            f"weighted={weighted_score:.2f}"
        )

        return weighted_score

    def _score_chemical(
        self,
        chemical_evidence: list[ChemicalEntityEvidence] | None,
    ) -> float:
        """Score chemical match confidence.

        Args:
            chemical_evidence: List of chemical evidence.

        Returns:
            Score between 0 and 1.
        """
        if not chemical_evidence:
            return 0.0

        best_match = max(chemical_evidence, key=lambda x: x.confidence or 0)
        confidence = best_match.confidence or 0

        # Boost if multiple sources agree on the same entity
        if len(chemical_evidence) > 1:
            sorted_evidence = sorted(
                chemical_evidence, key=lambda x: x.confidence or 0, reverse=True
            )
            if (
                len(sorted_evidence) >= 2
                and sorted_evidence[0].entity_id == sorted_evidence[1].entity_id
            ):
                confidence = min(1.0, confidence + 0.1)

        return confidence

    def _score_pattern(
        self,
        pattern_assignment: PatternAssignment | None,
    ) -> float:
        """Score pattern fit confidence.

        Args:
            pattern_assignment: Pattern assignment.

        Returns:
            Score between 0 and 1.
        """
        if not pattern_assignment:
            return 0.0

        special_patterns = [
            PatternType.abnormalAbsenceOfChemicalEntity,
            PatternType.modifier,
            PatternType.combination_phenotype,
            PatternType.process,
            PatternType.activity,
            PatternType.method_observed,
            PatternType.unknown,
        ]

        if pattern_assignment.pattern_name in special_patterns:
            return 0.3  # These need manual review

        return pattern_assignment.confidence or 0.5

    def _score_label(
        self,
        hp_term: HPTerm,
        proposal: CurationProposal | None,
    ) -> float:
        """Score based on label similarity.

        Higher score when the proposed label is similar to the original,
        confirming the pattern assignment is likely correct.

        Args:
            hp_term: Original HP term.
            proposal: Generated proposal.

        Returns:
            Score between 0 and 1.
        """
        if not proposal or not proposal.proposed_label:
            return 0.0

        original = hp_term.label.lower()
        proposed = proposal.proposed_label.lower()

        similarity = SequenceMatcher(None, original, proposed).ratio()

        if similarity > 0.95:
            return 1.0
        elif similarity > 0.7:
            return 0.9
        elif similarity > 0.5:
            return 0.7
        else:
            return 0.5

    def _score_existing(self, hp_term: HPTerm) -> float:
        """Score based on existing annotations.

        Higher score when the term already has correct annotations,
        confirming the entity identification.

        Args:
            hp_term: Original HP term.

        Returns:
            Score between 0 and 1.
        """
        score = 0.0

        if hp_term.existing_chemical_entity:
            score += 0.4

        if hp_term.existing_location:
            score += 0.3

        if hp_term.existing_logical_definition:
            score += 0.3

        return min(1.0, score)

    def score_batch(
        self,
        packets: list,  # list[EvidencePacket]
    ) -> dict[str, float]:
        """Score a batch of evidence packets.

        Args:
            packets: List of evidence packets.

        Returns:
            Dict mapping packet IDs to scores.
        """
        scores = {}
        for packet in packets:
            score = self.score(
                hp_term=packet.hp_term,
                chemical_evidence=packet.chemical_evidence,
                pattern_assignment=packet.pattern_assignment,
                proposal=packet.proposal,
            )
            scores[packet.id] = score
        return scores
