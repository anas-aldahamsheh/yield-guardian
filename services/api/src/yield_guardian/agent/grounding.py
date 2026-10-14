"""What a set of evidence contains, and checks of free text against it.

The report verifier and the chat both ask the same two questions of generated text: is every
quantity a value the evidence holds, and does every identifier (unit, sensor, wafer, lot,
alarm, date) exist in the evidence? :class:`EvidenceFacts` indexes the evidence once;
:func:`check_text` answers both questions; :func:`redact_unverified` removes, before anything
reaches a user, every number that the evidence does not support.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from yield_guardian.agent.numbers import (
    Identifier,
    IdentifierKind,
    NumberMention,
    int_values_by_key,
    level_digits,
    matches,
    numeric_leaves,
    scan,
    string_leaves,
)
from yield_guardian.contracts.investigation import Evidence

REDACTED = "[unverified number removed]"
REDACTED_IDENTIFIER = "[unverified identifier removed]"

_INT_KEYS: dict[IdentifierKind, frozenset[str]] = {
    "unit": frozenset({"unit_id", "unit_ids", "jump_unit_ids"}),
    "sequence": frozenset({"sequence", "from_seq", "to_seq", "position"}),
    "wafer_index": frozenset({"wafer_index"}),
    "window": frozenset({"window_id", "flatline_windows"}),
}
_STRING_KINDS: frozenset[IdentifierKind] = frozenset({"sensor", "alarm", "wafer", "lot"})
_SUBSTRING_KINDS: frozenset[IdentifierKind] = frozenset({"date", "time"})
_LEVEL_SUFFIX = re.compile(r"_([0-9]{2,3})$")
_LEVEL_KEY = re.compile(r"(?:^|_)(?:level|confidence)$")
_LOTLIKE = re.compile(r"^[A-Za-z0-9_.]+(?:-[0-9]+)?$")


@dataclass
class EvidenceFacts:
    numbers: list[float] = field(default_factory=list)
    strings: set[str] = field(default_factory=set)
    ints: dict[IdentifierKind, set[int]] = field(default_factory=dict)
    evidence_ids: set[str] = field(default_factory=set)
    known_identifiers: set[str] = field(default_factory=set)
    """Lot names and wafer IDs found in the evidence, matched literally in text."""
    level_suffixes: set[str] = field(default_factory=set)
    """Digits that end a field name (``t2_99``, ``limit_999``): the levels the evidence names."""
    level_values: set[float] = field(default_factory=set)
    """Values of fields named like a level (``ci_level``: 0.95)."""

    @classmethod
    def build(
        cls,
        evidence: Iterable[Evidence],
        *,
        strings: Iterable[str] = (),
        units: Iterable[int] = (),
    ) -> EvidenceFacts:
        facts = cls()
        for item in evidence:
            facts.evidence_ids.add(item.evidence_id)
            for source in (item.data, item.arguments):
                facts.numbers.extend(value for _, value in numeric_leaves(source))
                facts.strings.update(string_leaves(source))
                for key, value in int_values_by_key(source):
                    for kind, keys in _INT_KEYS.items():
                        if key in keys:
                            facts.ints.setdefault(kind, set()).add(value)
            for key in ("lot", "wafer_id"):
                facts._collect_named(item.data, key)
            facts._collect_levels(item.data)
        facts.strings.update(strings)
        facts.ints.setdefault("unit", set()).update(units)
        return facts

    def _collect_levels(self, data: object) -> None:
        if isinstance(data, dict):
            for name, value in data.items():
                suffix = _LEVEL_SUFFIX.search(str(name))
                if suffix:
                    self.level_suffixes.add(suffix.group(1))
                if _LEVEL_KEY.search(str(name)) and isinstance(value, int | float):
                    self.level_values.add(float(value))
                self._collect_levels(value)
        elif isinstance(data, list):
            for value in data:
                self._collect_levels(value)

    def names_level(self, mention: NumberMention) -> bool:
        """True when the evidence names the level a percentage like "99%" refers to."""
        if level_digits(mention) in self.level_suffixes:
            return True
        if any(abs(v * 100.0 - mention.value) <= 1e-9 for v in self.level_values):
            return True
        return any(mention.text in s for s in self.strings)

    def _collect_named(self, data: object, key: str) -> None:
        if isinstance(data, dict):
            for name, value in data.items():
                if name == key and isinstance(value, str) and _LOTLIKE.match(value):
                    self.known_identifiers.add(value)
                else:
                    self._collect_named(value, key)
        elif isinstance(data, list):
            for value in data:
                self._collect_named(value, key)

    def unsupported_values(self, identifier: Identifier) -> list[str]:
        """The values of an identifier span that no evidence contains."""
        kind = identifier.kind
        if kind == "name":
            return []
        if kind == "evidence":
            return [v for v in identifier.values if v not in self.evidence_ids]
        if kind in _STRING_KINDS:
            return [v for v in identifier.values if v not in self.strings]
        if kind in _SUBSTRING_KINDS:
            return [v for v in identifier.values if not any(v in s for s in self.strings)]
        known = self.ints.get(kind, set())
        return [v for v in identifier.values if int(v) not in known]

    def supports(self, mention: NumberMention) -> bool:
        return any(matches(mention, value) for value in self.numbers)


@dataclass(frozen=True, slots=True)
class TextCheck:
    numbers: tuple[NumberMention, ...]
    unverified: tuple[NumberMention, ...]
    unsupported_identifiers: tuple[tuple[Identifier, str], ...]
    spelled: tuple[str, ...]


def check_text(text: str, facts: EvidenceFacts) -> TextCheck:
    """Check every number of free text against any value of the evidence."""
    found = scan(text, known_identifiers=facts.known_identifiers)
    unverified = tuple(n for n in found.numbers if not facts.supports(n))
    unsupported = tuple(
        (identifier, value)
        for identifier in found.identifiers
        for value in facts.unsupported_values(identifier)
    )
    return TextCheck(found.numbers, unverified, unsupported, tuple(s.text for s in found.spelled))


def redact_unverified(text: str, facts: EvidenceFacts) -> tuple[str, TextCheck]:
    """``text`` with every number and identifier the evidence does not support replaced by a
    marker, so neither reaches a reader unchecked."""
    check = check_text(text, facts)
    spans: dict[tuple[int, int], str] = {(n.start, n.end): REDACTED for n in check.unverified}
    for identifier, _ in check.unsupported_identifiers:
        spans[(identifier.start, identifier.end)] = REDACTED_IDENTIFIER
    out = text
    for (start, end), marker in sorted(spans.items(), reverse=True):
        out = out[:start] + marker + out[end:]
    return out, check
