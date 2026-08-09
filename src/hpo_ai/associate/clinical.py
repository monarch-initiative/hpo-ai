"""Extract the chemical concept behind an opaque clinical term via an LLM.

Terms like "Hypoglycorrhachia" encode direction (hypo-), fluid (-rrhachia = CSF)
and a chemical (glyco- = glucose) as a single portmanteau word. Direction and
fluid are handled by deterministic rules; the chemical concept is recovered with
a small, focused LLM call.
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

# A clinical chemical extractor maps a label to a chemical name (or None).
ClinicalChemicalExtractor = Callable[[str], "str | None"]


def make_anthropic_chemical_extractor(enricher) -> ClinicalChemicalExtractor:
    """Build a clinical-chemical extractor backed by an Anthropic client.

    Args:
        enricher: An object exposing ``.client`` (Anthropic) and ``.model``.

    Returns:
        A callable ``label -> chemical name | None``.
    """

    def extract(label: str) -> str | None:
        prompt = (
            "An HPO clinical term encodes a chemical as a portmanteau, e.g. "
            "'Hypoglycorrhachia' -> glucose, 'Hyperlactatorrhachia' -> lactate.\n"
            f"Term: {label}\n"
            "Reply with ONLY the chemical's common name (lower case), or the word "
            "NONE if there is no single chemical."
        )
        reply = enricher.client.messages.create(
            model=enricher.model,
            max_tokens=30,
            messages=[{"role": "user", "content": prompt}],
        )
        text = reply.content[0].text.strip()
        if not text or text.upper() == "NONE":
            return None
        return text

    return extract
