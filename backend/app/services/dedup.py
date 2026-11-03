"""Near-duplicate question removal: normalise the text, then compare with a similarity ratio."""

import re
from difflib import SequenceMatcher

from app.questions import Question

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace: "What's X?" == "whats x"."""
    return _NON_ALNUM.sub(" ", text.lower().replace("'", "")).strip()


def similarity(a: str, b: str) -> float:
    """0.0 (nothing shared) to 1.0 (identical) on already-normalised strings."""
    return SequenceMatcher(None, a, b).ratio()


def dedupe(
    candidates: list[Question], existing_prompts: list[str], threshold: float
) -> tuple[list[Question], int]:
    """Keep candidates that are not near-duplicates of existing prompts or of each other.

    Returns (kept questions, number removed).
    """
    seen = [normalize(prompt) for prompt in existing_prompts]
    kept: list[Question] = []
    for question in candidates:
        text = normalize(question.prompt)
        if any(similarity(text, other) >= threshold for other in seen):
            continue
        kept.append(question)
        seen.append(text)
    return kept, len(candidates) - len(kept)
