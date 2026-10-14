"""Causal wording check (PLAN 7.4, rule 4): association, never causation.

The product's statistics show association with failure; nothing in the evidence establishes a
physical cause. A sentence that states a cause ("S060 caused the failure", "due to drift", "the
root cause is ...") is therefore rejected, unless the evidence it rests on is a confirmed
work-order outcome. No tool returns such outcomes yet, so in practice the rule always applies.

The list is deliberately small and explicit, so a reviewer can see exactly what is refused.
"Causal", "causation" and "association" are not on it: a limitation may say "association, not
causation". Words that name the investigation's trigger ("the trigger alarm") are not on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CAUSAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.IGNORECASE))
    for label, pattern in (
        ("cause", r"\bcaus(?:e|es|ed|ing)\b"),
        ("root cause", r"\broot[\s-]+causes?\b"),
        ("due to", r"\bdue\s+to\b"),
        ("because of", r"\bbecause\s+of\b"),
        ("owing to", r"\bowing\s+to\b"),
        ("result in", r"\bresult(?:s|ed|ing)?\s+in\b"),
        ("lead to", r"\b(?:lead(?:s|ing)?|led)\s+to\b"),
        ("responsible for", r"\bresponsible\s+for\b"),
        ("attributable to", r"\battribut(?:able|ed)\s+to\b"),
        ("drive", r"\b(?:driv(?:es|en|ing)|drove)\b"),
        ("induce", r"\binduc(?:e|es|ed|ing)\b"),
    )
)

ASSOCIATION_HINT = (
    "Use association wording instead, for example 'is associated with', 'coincides with', "
    "'contributes most to the model's risk score'."
)


@dataclass(frozen=True, slots=True)
class CausalPhrase:
    label: str
    text: str
    start: int
    end: int


def causal_phrases(text: str) -> list[CausalPhrase]:
    """Every causal phrase in ``text``, in order of appearance."""
    found = [
        CausalPhrase(label, match.group(0), match.start(), match.end())
        for label, pattern in CAUSAL_PATTERNS
        for match in pattern.finditer(text)
    ]
    found.sort(key=lambda phrase: phrase.start)
    deduplicated: list[CausalPhrase] = []
    for phrase in found:
        if deduplicated and phrase.start < deduplicated[-1].end:
            continue  # "root cause" also contains "cause"
        deduplicated.append(phrase)
    return deduplicated
