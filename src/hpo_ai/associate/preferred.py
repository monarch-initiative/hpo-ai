"""Determine the preferred clinical term for a chemical-level phenotype.

Many blood/CSF phenotypes have an established single clinical term (increased
blood glucose -> "Hyperglycemia") that HPO prefers as the primary label over the
descriptive pattern form. We find it two ways, cheapest first:

1. deterministically, if the term already carries a clinical-morphology exact
   synonym matching the association's direction + fluid (HPO has already curated
   it, so this is high-precision and free);
2. otherwise, via a small cached LLM oracle keyed on (direction, chemical,
   fluid) -- see :class:`PreferredClinicalTermResolver`.

Obscure concepts (increased CSF ribitol) have neither, so they keep the
descriptive label -- which is exactly the issue #11702 convention.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

logger = logging.getLogger(__name__)

# location UBERON id -> (fluid label, clinical suffixes, direction is prefix-encoded)
_FLUID_BY_LOCATION: dict[str, tuple[str, tuple[str, ...]]] = {
    "UBERON:0000178": ("blood", ("aemia", "emia")),
    "UBERON:0001359": ("cerebrospinal fluid", ("rrhachia", "rachia")),
    "UBERON:0001088": ("urine", ("uria",)),
}
_PREFIX_BY_DIRECTION = {"increased": "hyper", "decreased": "hypo"}

# Fluids where it is worth asking the oracle to *find* a clinical term when the
# term has no clinical-morphology synonym. CSF is excluded here only to avoid
# wasted NONE calls (single-word CSF terms are vanishingly rare); whether a found
# or existing term is *used as the primary label* is decided by its commonness,
# not its fluid.
FIND_FLUIDS = frozenset({"blood", "urine"})


def fluid_label(location_id: str | None) -> str | None:
    """Return the human fluid label for a location id, or None.

    >>> fluid_label("UBERON:0000178")
    'blood'
    >>> fluid_label("UBERON:9999999") is None
    True
    """
    entry = _FLUID_BY_LOCATION.get(location_id or "")
    return entry[0] if entry else None


def clinical_synonym(
    synonyms: list[str], direction: str, location_id: str | None
) -> str | None:
    """Return an existing clinical-morphology synonym matching direction + fluid.

    Only the regular ``hyper``/``hypo`` + ``…emia``/``…rrhachia`` forms (blood,
    CSF) are matched -- these encode direction unambiguously. Urine forms
    (``…uria``) usually do not carry a hypo/hyper prefix and are left to the LLM
    oracle.

    >>> clinical_synonym(["Hyperglycemia", "High blood sugar"], "increased", "UBERON:0000178")
    'Hyperglycemia'
    >>> clinical_synonym(["Hyperglycemia"], "decreased", "UBERON:0000178") is None
    True
    >>> clinical_synonym(["Hypoglycorrhachia"], "decreased", "UBERON:0001359")
    'Hypoglycorrhachia'
    """
    entry = _FLUID_BY_LOCATION.get(location_id or "")
    prefix = _PREFIX_BY_DIRECTION.get(direction)
    if entry is None or prefix is None:
        return None
    _, suffixes = entry
    if "uria" in suffixes:  # urine forms do not encode direction reliably
        return None
    suffix_alt = "|".join(re.escape(s) for s in suffixes)
    pattern = re.compile(rf"^{prefix}[a-z][a-z-]*(?:{suffix_alt})$", re.IGNORECASE)
    for syn in synonyms:
        candidate = (syn or "").strip()
        if pattern.match(candidate):
            return candidate
    return None


# A preferred-term oracle takes (direction, chemical, fluid, candidate|None) and
# returns (clinical_term|None, is_common). When ``candidate`` is given it judges
# that term's commonness; otherwise it finds a term and judges it.
PreferredTermFn = Callable[[str, str, str, "str | None"], "tuple[str | None, bool]"]


class PreferredClinicalTermResolver:
    """Resolve a clinical term *and whether it is common*, cached in a store.

    Keyed on the concept ``(direction, chemical, fluid)`` so the answer is shared
    across every term with that concept and a curator edits a single row (the
    ``clinical_term`` and the ``common`` flag). Negatives are cached too.

    A **common** term is used as the primary label; an **obscure** term is kept as
    an exact synonym. The commonness decision is what separates "Hyperglycemia"
    (promote) from "Hyperlactatorachia" (synonym only).
    """

    def __init__(
        self, store, llm_fn: PreferredTermFn | None = None,
        agent_version: str = "", confidence: float = 0.8,
    ) -> None:
        """Initialise.

        Args:
            store: A :class:`~hpo_ai.provenance.store.LockedTsvStore`.
            llm_fn: Optional oracle returning ``(term|None, is_common)``.
            agent_version: Dated model id stamped onto machine rows.
            confidence: Confidence recorded for machine rows.
        """
        self.store = store
        self.llm_fn = llm_fn
        self.agent_version = agent_version
        self.confidence = confidence

    def __call__(
        self, direction: str, chemical: str, fluid: str,
        candidate: str | None = None,
    ) -> tuple[str | None, bool]:
        """Return ``(clinical_term|None, is_common)`` for a concept.

        Args:
            direction: increased/decreased/abnormal.
            chemical: chemical name.
            fluid: fluid label (blood/urine/...).
            candidate: a term already known (e.g. an existing synonym) whose
                commonness should be judged; None to also find the term.
        """
        from hpo_ai.provenance.constants import METHOD_LLM
        from hpo_ai.provenance.stores import preferred_key, preferred_term_row

        key = preferred_key(direction, chemical, fluid)
        rows = self.store.get(key)
        if rows:  # cache hit (positive term + flag, or cached negative "")
            term = (rows[0].get("clinical_term") or "").strip()
            common = (rows[0].get("common") or "").strip().lower() == "true"
            return (term or None, common)

        if self.llm_fn is None:
            # No cached decision and no LLM: keep a known candidate but treat it as
            # obscure (do not promote) -- a curator can flip the flag later.
            return (candidate, False)

        term, common = self.llm_fn(direction, chemical, fluid, candidate)
        self.store.record(key, [preferred_term_row(
            direction, chemical, fluid, term or "", common, METHOD_LLM,
            self.agent_version, self.confidence)])
        return (term, common)


def make_anthropic_preferred_term_llm(enricher) -> PreferredTermFn:
    """Build a conservative preferred-term + commonness oracle backed by Anthropic.

    Args:
        enricher: An object exposing ``.client`` (Anthropic) and ``.model``.

    Returns:
        A :data:`PreferredTermFn`.
    """

    def _ask(prompt: str) -> str:
        reply = enricher.client.messages.create(
            model=enricher.model, max_tokens=30,
            messages=[{"role": "user", "content": prompt}],
        )
        return reply.content[0].text.strip()

    def fn(
        direction: str, chemical: str, fluid: str, candidate: str | None,
    ) -> tuple[str | None, bool]:
        concept = f"an abnormally {direction} level of {chemical} in the {fluid}"
        if candidate:
            text = _ask(
                f"Is '{candidate}' a COMMON clinical term for {concept} -- i.e. one "
                "a clinician would routinely use and expect as the primary term "
                "(like Hyperglycemia or Hypokalemia), as opposed to a technically "
                "correct but rarely-used form (like Hyperlactatorachia)?\n"
                "Answer with exactly one word: COMMON or OBSCURE."
            )
            return (candidate, text.strip().upper().startswith("COMMON"))

        text = _ask(
            f"Is there a single established clinical term for {concept}?\n"
            "If yes, reply 'TERM=<term> | <COMMON|OBSCURE>' using American "
            "spelling; a term is COMMON only if clinicians routinely use it as the "
            "primary name (Hyperglycemia, Hyperkalemia). If there is no single "
            "established term, reply NONE. Be conservative."
        )
        if not text or text.upper().startswith("NONE"):
            return (None, False)
        term = text
        common = False
        if "|" in text:
            left, right = text.split("|", 1)
            term = left.replace("TERM=", "").strip()
            common = right.strip().upper().startswith("COMMON")
        return (term or None, common)

    return fn
