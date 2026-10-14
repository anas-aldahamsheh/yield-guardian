"""Find every number in generated text, and decide by code whether evidence supports it.

Ground rule 4 of the plan: language models never produce numbers that reach a user unchecked.
This module is the deterministic half of that rule. It reads text the way an engineer would:

* quantities: ``42``, ``-0.42`` (ASCII hyphen or Unicode minus), ``+3``, ``1,567``, ``.05``,
  ``12.5%`` (also ``12.5 percent``), ``2.3e-4`` and 2.3 times ten to the power -4 written with
  a multiplication sign and a caret or superscript digits, optionally
  after a comparator (``<``, ``≤``, ``>``, ``≥``, "less than", "below", "at least" ...);
* identifiers, which are not quantities but must still exist in the evidence: sensor IDs
  (``S060``), evidence IDs (``E3``), alarm IDs (``AL-1043-t2``), wafer IDs (``lot47542-12``), lot
  names, unit and sequence numbers after the words "unit", "units", "sequence" (``units 1043
  and 1050``), wafer indexes after "wafer", health windows after "window", dates and times;
* digits glued to a letter on their left (``T2``, ``V4``) belong to a name and are skipped;
* spelled-out numbers ("three sensors") cannot be checked, so they are reported separately and
  the writer is asked to use digits. "One" is not reported (too common in other senses), and
  neither are "two-sided" and "two-tailed".

A written number matches an evidence value when the value, rounded to the precision the text
shows, equals it: ``0.12`` matches 0.1234 (tolerance half a unit in the last written digit),
``12%`` matches 0.1234 (a percentage is compared with the evidence times 100), ``2.3e-4``
matches 0.000234. ``5%`` never matches 5, and ``0.05`` never matches 5. After a comparator the
inequality may hold instead: ``p < 0.001`` matches a p-value of 0.0004.

A number may also come from evidence text rather than a numeric field (an operating point
labelled ``"5% false-alarm rate"``): it is supported when the same number, with the same percent
sign, appears literally in that text (:func:`appears_in_text`). A percentage that names a level
("the 99% control limit", "a 95% confidence interval") is a name, not a quantity
(:func:`names_a_level`): it is checked like an identifier, against the levels the evidence
names (a key such as ``t2_99``, a ``ci_level`` of 0.95, or the literal text).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

Comparator = Literal["<", "<=", ">", ">="]
IdentifierKind = Literal[
    "unit", "sequence", "sensor", "evidence", "alarm", "wafer", "lot", "wafer_index", "window",
    "date", "time", "name",
]  # fmt: skip

_MINUS = "-\u2212\u2013\u2012"  # hyphen-minus, minus sign, en dash, figure dash
_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
_SIGN_CONTEXT = set(" \t\n([{=:;,/≈~<>≤≥") | {""}

_NUMBER = re.compile(
    r"""
    (?P<sign>[-+\u2212\u2013\u2012](?=\.?[0-9]))?
    (?P<mantissa>(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?|\.[0-9]+)
    (?P<exponent>
        [eE][-+\u2212]?[0-9]+
      | \s?[\u00d7x\u00b7]\s?10(?:\^\s?[-+\u2212]?[0-9]+|[⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)
    )?
    (?P<percent>\s?%|\s(?:percent|per\scent)\b)?
    """,
    re.VERBOSE,
)
_COMPARATOR_SYMBOL = re.compile(r"(?P<cmp><=|>=|≤|≥|<|>)\s*$")
_COMPARATOR_WORDS: tuple[tuple[re.Pattern[str], Comparator], ...] = (
    (re.compile(r"\b(?:less|fewer|lower)\s+than\s*$", re.IGNORECASE), "<"),
    (re.compile(r"\b(?:below|under)\s*$", re.IGNORECASE), "<"),
    (re.compile(r"\bat\s+most\s*$", re.IGNORECASE), "<="),
    (re.compile(r"\b(?:more|greater|higher)\s+than\s*$", re.IGNORECASE), ">"),
    (re.compile(r"\b(?:above|over|exceeds|exceeding)\s*$", re.IGNORECASE), ">"),
    (re.compile(r"\bat\s+least\s*$", re.IGNORECASE), ">="),
)

_SPELLED = re.compile(
    r"\b(?:two(?!-(?:sided|tailed))|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty"
    r"|fifty|sixty|seventy|eighty|ninety|hundreds?|thousands?|millions?|billions?|dozens?"
    r"|twice|thrice)\b",
    re.IGNORECASE,
)

_ONE = r"#?[0-9]+(?![0-9]|\.[0-9])"
_RANGE_TAIL = rf"(?:\s*(?:to|through|-|\u2013)\s*{_ONE})?"
# A plural keyword may introduce a list ("units 1043, 1050 and 1077"); any keyword may introduce
# a range ("sequence 1200 to 1240"). A singular keyword takes no list, so "unit 1043 and 2
# sensors" keeps the 2 as a quantity.
_LIST_TAIL = rf"(?:(?:\s*,\s*{_ONE})*\s*,?\s*(?:and|or)\s*{_ONE}|{_RANGE_TAIL})"


def _keyword(singular: str, plural: str, prefix: str = "") -> re.Pattern[str]:
    return re.compile(
        rf"\b(?:{plural}\s*{prefix}{_ONE}{_LIST_TAIL}|{singular}\s*{prefix}{_ONE}{_RANGE_TAIL})",
        re.IGNORECASE,
    )


_IDENTIFIER_PATTERNS: tuple[tuple[IdentifierKind, re.Pattern[str]], ...] = (
    ("alarm", re.compile(r"\bAL-[0-9]+-(?:risk|t2|spe|ewma|cusum)\b")),
    (
        "date",
        re.compile(
            r"\b[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]+)?)?"
            r"(?:Z|[+-][0-9]{2}:?[0-9]{2})?)?(?![0-9])"
        ),
    ),
    ("time", re.compile(r"(?<![0-9.:])[0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?(?![0-9:])")),
    ("wafer", re.compile(r"\blot[A-Za-z0-9_.]*-[0-9]+\b")),
    ("lot", re.compile(r"\blot[A-Za-z0-9_.]*[0-9][A-Za-z0-9_.]*\b")),
    ("sensor", re.compile(r"\bS[0-9]{3}\b")),
    ("evidence", re.compile(r"\bE[0-9]+\b")),
    ("unit", _keyword("unit", "units", r"(?:no\.?\s*|id\s*)?")),
    ("sequence", _keyword("(?:sequence|position)", "(?:sequences|positions)")),
    ("wafer_index", _keyword("wafer", "wafers", r"(?:index\s*)?")),
    ("window", _keyword("window", "windows")),
    # Digits glued to a letter on their left are part of a name (T2, V4, x86, S60).
    ("name", re.compile(r"(?<=[A-Za-z_])[0-9][0-9.]*")),
)  # fmt: skip
_DIGITS = re.compile(r"[0-9]+")


@dataclass(frozen=True, slots=True)
class NumberMention:
    """A quantity as written in the text."""

    text: str
    """Exactly as written, comparator excluded (``-0.42``, ``12.5%``, ``1,567``)."""
    value: float
    """The written value (12.5 for ``12.5%``)."""
    percent: bool
    decimals: int
    """Decimal places shown, counted after applying any exponent (``2.3e-4`` shows 5)."""
    comparator: Comparator | None
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Identifier:
    kind: IdentifierKind
    text: str
    values: tuple[str, ...]
    """Normalised identifiers in the span (``units 1043 and 1050`` gives two)."""
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SpelledNumber:
    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class TextNumbers:
    numbers: tuple[NumberMention, ...]
    identifiers: tuple[Identifier, ...]
    spelled: tuple[SpelledNumber, ...]


def _decimals(mantissa: str) -> int:
    _, _, fraction = mantissa.partition(".")
    return len(fraction)


def _exponent_value(raw: str) -> int:
    text = raw.translate(_SUPERSCRIPT).replace("\u2212", "-")
    if "e" in text.lower():
        return int(text.lower().split("e", 1)[1])
    digits = re.sub(r"^\s?[\u00d7x\u00b7]\s?10\^?\s?", "", text)
    return int(digits)


_SYMBOLS: dict[str, Comparator] = {"<": "<", "≤": "<=", "<=": "<=", ">": ">", "≥": ">=", ">=": ">="}


def _comparator(prefix: str) -> Comparator | None:
    symbol = _COMPARATOR_SYMBOL.search(prefix)
    if symbol:
        return _SYMBOLS[symbol.group("cmp")]
    for pattern, comparator in _COMPARATOR_WORDS:
        if pattern.search(prefix):
            return comparator
    return None


def _mention(match: re.Match[str], text: str) -> NumberMention:
    start = match.start()
    sign = match.group("sign")
    if sign and text[start - 1 : start] not in _SIGN_CONTEXT and start > 0:
        # A dash after a digit or letter joins a range or a compound word ("0.3-0.5").
        sign = None
        start += 1
    mantissa = match.group("mantissa")
    exponent_raw = match.group("exponent")
    exponent = _exponent_value(exponent_raw) if exponent_raw else 0
    magnitude = float(mantissa.replace(",", "")) * (10.0**exponent)
    negative = sign is not None and sign in _MINUS
    end = match.end()
    written = text[start:end]
    return NumberMention(
        text=written,
        value=-magnitude if negative else magnitude,
        percent=match.group("percent") is not None,
        decimals=_decimals(mantissa) - exponent,
        comparator=_comparator(text[max(0, start - 20) : start]),
        start=start,
        end=end,
    )


def _identifier_values(kind: IdentifierKind, span: str) -> tuple[str, ...]:
    if kind in ("unit", "sequence", "wafer_index", "window"):
        return tuple(str(int(d)) for d in _DIGITS.findall(span))
    return (span,)


def find_identifiers(text: str, known: Iterable[str] = ()) -> list[Identifier]:
    """Identifier spans, longest pattern first; ``known`` adds literal identifiers (for example
    lot names taken from the evidence) that the patterns do not cover."""
    taken = [False] * len(text)
    found: list[Identifier] = []

    def claim(kind: IdentifierKind, start: int, end: int) -> None:
        if any(taken[start:end]):
            return
        for i in range(start, end):
            taken[i] = True
        span = text[start:end]
        found.append(Identifier(kind, span, _identifier_values(kind, span), start, end))

    for literal in sorted({k for k in known if k}, key=len, reverse=True):
        for match in re.finditer(rf"(?<![A-Za-z0-9_.]){re.escape(literal)}(?![A-Za-z0-9_])", text):
            claim("lot" if "-" not in literal else "wafer", match.start(), match.end())
    for kind, pattern in _IDENTIFIER_PATTERNS:
        for match in pattern.finditer(text):
            claim(kind, match.start(), match.end())
    return sorted(found, key=lambda i: i.start)


def scan(text: str, *, known_identifiers: Iterable[str] = ()) -> TextNumbers:
    """Every quantity, identifier and spelled-out number in ``text``."""
    identifiers = find_identifiers(text, known_identifiers)
    masked = list(text)
    for identifier in identifiers:
        for i in range(identifier.start, identifier.end):
            masked[i] = " "
    masked_text = "".join(masked)
    numbers = []
    for match in _NUMBER.finditer(masked_text):
        mention = _mention(match, masked_text)
        numbers.append(
            NumberMention(
                text=text[mention.start : mention.end],
                value=mention.value,
                percent=mention.percent,
                decimals=mention.decimals,
                comparator=_comparator(text[max(0, mention.start - 20) : mention.start]),
                start=mention.start,
                end=mention.end,
            )
        )
    spelled = [SpelledNumber(m.group(0), m.start(), m.end()) for m in _SPELLED.finditer(text)]
    return TextNumbers(tuple(numbers), tuple(identifiers), tuple(spelled))


def parse_number(written: str) -> NumberMention | None:
    """Parse a number written on its own (``NumberRef.as_written``); None if it is not exactly
    one number."""
    text = written.strip()
    match = _NUMBER.fullmatch(text)
    if match is None:
        return None
    return _mention(match, text)


def _tolerance(mention: NumberMention, target: float) -> float:
    half_unit = 0.5 * 10.0 ** (-mention.decimals)
    return half_unit * (1 + 1e-9) + 1e-12 * max(1.0, abs(target))


def matches(mention: NumberMention, evidence_value: float, *, percent: bool | None = None) -> bool:
    """True when ``evidence_value`` supports the written number (see the module docstring).
    ``percent`` overrides the mention's own percent flag (a reference may declare unit "%")."""
    if not math.isfinite(evidence_value):
        return False
    is_percent = mention.percent if percent is None else percent
    target = evidence_value * 100.0 if is_percent else evidence_value
    if abs(target - mention.value) <= _tolerance(mention, target):
        return True
    match mention.comparator:
        case "<":
            return target < mention.value
        case "<=":
            return target <= mention.value
        case ">":
            return target > mention.value
        case ">=":
            return target >= mention.value
        case _:
            return False


def written_value_matches(written: NumberMention, value: float, *, percent: bool) -> bool:
    """True when a ``numbers[]`` entry's ``value`` agrees with its ``as_written`` to the written
    precision: ``+0.80`` with 0.802666, ``10.2%`` with 10.21 or (a percentage given as the
    fraction the evidence holds) 0.1021. The sign must agree; a comparator in ``as_written``
    does not widen the match."""
    plain = replace(written, comparator=None)
    return matches(plain, value, percent=False) or (percent and matches(plain, value, percent=True))


_LEVEL_FOLLOW = re.compile(
    r"\s*(?:(?:upper|lower)\s+)?(?:control\s+|confidence\s+)?"
    r"(?:limits?|confidence|CI|intervals?|quantiles?|percentiles?|levels?|bands?|UCL|LCL)\b",
    re.IGNORECASE,
)


def names_a_level(text: str, mention: NumberMention) -> bool:
    """True when a percentage in ``text`` names a level rather than a quantity: "the 99% limit",
    "99.9% control limits", "a 95% CI". "99% of units" is a quantity."""
    return (
        mention.percent
        and mention.comparator is None
        and _LEVEL_FOLLOW.match(text, mention.end) is not None
    )


def level_digits(mention: NumberMention) -> str:
    """The digits a field name uses for a level: 99% gives "99", 99.9% gives "999"."""
    return f"{mention.value:g}".replace(".", "")


def appears_in_text(mention: NumberMention, text: str) -> bool:
    """True when ``text`` (a string in the evidence) contains the same number literally, with
    the same percent sign: ``5%`` in ``"5% false-alarm rate"``, not ``5`` or ``0.05``."""
    return any(
        found.percent == mention.percent
        and abs(found.value - mention.value) <= 1e-12 * max(1.0, abs(mention.value))
        for found in scan(text).numbers
    )


def magnitude_matches(mention: NumberMention, evidence_value: float, *, percent: bool) -> bool:
    """True when only the sign differs ("lowered the score by 0.42" for a SHAP of -0.42)."""
    flipped = NumberMention(
        mention.text, -mention.value, percent, mention.decimals, None, mention.start, mention.end
    )
    return matches(flipped, evidence_value, percent=percent)


def numeric_leaves(data: Any, path: str = "") -> Iterator[tuple[str, float]]:
    """Every number in a JSON value with its JSON Pointer (booleans are not numbers)."""
    if isinstance(data, bool):
        return
    if isinstance(data, int | float):
        yield path, float(data)
    elif isinstance(data, Mapping):
        for key, value in data.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            yield from numeric_leaves(value, f"{path}/{escaped}")
    elif isinstance(data, Sequence) and not isinstance(data, str | bytes):
        for index, value in enumerate(data):
            yield from numeric_leaves(value, f"{path}/{index}")


def string_leaves(data: Any) -> Iterator[str]:
    if isinstance(data, str):
        yield data
    elif isinstance(data, Mapping):
        for key, value in data.items():
            yield str(key)
            yield from string_leaves(value)
    elif isinstance(data, Sequence) and not isinstance(data, bytes):
        for value in data:
            yield from string_leaves(value)


def int_values_by_key(data: Any, key: str | None = None) -> Iterator[tuple[str, int]]:
    """(key, integer) for every integer in a JSON value, including list items under a key."""
    if isinstance(data, bool):
        return
    if isinstance(data, int) and key is not None:
        yield key, data
    elif isinstance(data, float) and data.is_integer() and key is not None:
        yield key, int(data)
    elif isinstance(data, Mapping):
        for name, value in data.items():
            yield from int_values_by_key(value, str(name))
    elif isinstance(data, Sequence) and not isinstance(data, str | bytes):
        for value in data:
            yield from int_values_by_key(value, key)
