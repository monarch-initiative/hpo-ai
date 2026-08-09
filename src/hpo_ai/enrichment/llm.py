"""LLM-based enrichment for chemical entity resolution."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from hpo_ai.datamodel import ChemicalEntityEvidence, EvidenceType, HPTerm
from hpo_ai.enrichment.selection_rules import load_selection_guide

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Default location for the selection guide
DEFAULT_GUIDE_PATH = Path(__file__).parents[2].parent / "conf" / "chebi_selection_guide.md"

# System prompt for chemical entity extraction
EXTRACTION_SYSTEM_PROMPT = """You are an expert biomedical ontologist specializing in chemical and protein entities.

Your task is to extract the chemical or protein entity from a phenotype term label and definition.

For each term, provide:
1. The primary chemical/protein name (normalized, not an abbreviation unless it's the standard name)
2. A common abbreviation if one exists and is widely used (e.g., LDL, HDL, CK, ACTH)
3. Whether this is likely a CHEBI chemical or a PRO protein
4. Any notes about the entity (e.g., "prefer atom form over ion", "L-form amino acid")

Return your response as JSON with this structure:
{
    "chemical_name": "the normalized chemical or protein name",
    "abbreviation": "common abbreviation or null",
    "entity_type": "CHEBI" or "PRO",
    "confidence": 0.0 to 1.0,
    "notes": "any relevant notes",
    "reasoning": "brief explanation of your reasoning"
}

If you cannot determine the chemical entity, return:
{
    "chemical_name": null,
    "error": "explanation of why extraction failed"
}
"""

# Prompt for determining preferred label
ABBREVIATION_PROMPT = """You are an expert in biomedical nomenclature.

Given the following chemical/protein entity, determine if there is a widely-used abbreviation
that would be more appropriate than the full name in a clinical/phenotype context.

Entity: {entity_name}
Context: This will be used in a phenotype term label like "Elevated circulating {name} concentration"

Consider:
- Is there a universally recognized abbreviation in clinical use?
- Would the abbreviation be immediately understood by clinicians?
- Is the full name unwieldy (>3 words or >30 characters)?

Return JSON:
{{
    "use_abbreviation": true/false,
    "abbreviation": "the abbreviation" or null,
    "reasoning": "brief explanation"
}}
"""


class LLMEnricher:
    """LLM-based enrichment for chemical entity resolution.

    When a selection guide is provided (``conf/chebi_selection_guide.md``),
    its contents are appended to the system prompt so the LLM follows
    domain-specific disambiguation rules.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        selection_guide_path: Path | None = None,
    ) -> None:
        """Initialize the LLM enricher.

        Args:
            api_key: Anthropic API key. If not provided, uses ANTHROPIC_API_KEY env var.
            model: Model to use for enrichment.
            selection_guide_path: Path to CHEBI selection guide markdown.
                Defaults to ``conf/chebi_selection_guide.md``.
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self._client = None

        # Load selection guide and build augmented system prompt
        guide_path = selection_guide_path or DEFAULT_GUIDE_PATH
        self.selection_guide: str | None = None
        if guide_path.exists():
            self.selection_guide = load_selection_guide(guide_path)
            logger.info("Loaded CHEBI selection guide from %s", guide_path)

        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build the system prompt, appending the selection guide if available."""
        prompt = EXTRACTION_SYSTEM_PROMPT
        if self.selection_guide:
            prompt += (
                "\n\n--- CHEBI SELECTION GUIDE ---\n\n"
                + self.selection_guide
            )
        return prompt

    @property
    def client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY environment variable not set. "
                    "Please set it or pass api_key to LLMEnricher."
                )
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def extract_chemical_entity(
        self,
        term: HPTerm,
    ) -> ChemicalEntityEvidence | None:
        """Extract chemical entity from an HP term using LLM.

        Args:
            term: HPTerm to analyze.

        Returns:
            ChemicalEntityEvidence or None if extraction failed.
        """
        user_prompt = f"""Extract the chemical or protein entity from this phenotype term:

Label: {term.label}
Definition: {term.definition or "No definition available"}
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            # Parse the response
            content = response.content[0].text

            # Extract JSON from response (handle markdown code blocks)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())

            if result.get("chemical_name") is None:
                logger.warning(
                    f"LLM could not extract entity from '{term.label}': "
                    f"{result.get('error', 'Unknown error')}"
                )
                return None

            return ChemicalEntityEvidence(
                id=f"ev_llm_{term.id.replace(':', '_')}",
                entity_id="",  # To be resolved by CHEBI/PRO lookup
                entity_label=result["chemical_name"],
                entity_source=result.get("entity_type", "CHEBI"),
                confidence=result.get("confidence", 0.7),
                evidence_type=EvidenceType.llm_extraction,
                match_description=result.get("reasoning", "LLM extraction"),
                preferred_abbreviation=result.get("abbreviation"),
            )

        except Exception as e:
            logger.error(f"LLM extraction failed for '{term.label}': {e}")
            return None

    def determine_preferred_name(
        self,
        entity_name: str,
    ) -> tuple[str, str | None]:
        """Determine if an abbreviation should be used.

        Args:
            entity_name: Full entity name.

        Returns:
            Tuple of (preferred_name, abbreviation_if_used).
        """
        prompt = ABBREVIATION_PROMPT.format(entity_name=entity_name, name="{name}")

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())

            if result.get("use_abbreviation") and result.get("abbreviation"):
                return result["abbreviation"], result["abbreviation"]
            return entity_name, None

        except Exception as e:
            logger.warning(f"Abbreviation check failed for '{entity_name}': {e}")
            return entity_name, None

    def batch_extract(
        self,
        terms: list[HPTerm],
        batch_size: int = 10,
    ) -> list[ChemicalEntityEvidence | None]:
        """Extract chemical entities from multiple terms.

        Args:
            terms: List of HPTerms to analyze.
            batch_size: Number of terms to process at once (for future batching).

        Returns:
            List of ChemicalEntityEvidence or None for each term.
        """
        results = []
        for term in terms:
            result = self.extract_chemical_entity(term)
            results.append(result)
        return results
