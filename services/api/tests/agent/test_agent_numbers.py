"""The number scanner and the matching rules every generated number goes through."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from yield_guardian.agent.numbers import (
    NumberMention,
    int_values_by_key,
    magnitude_matches,
    matches,
    numeric_leaves,
    parse_number,
    scan,
    string_leaves,
)

MINUS = "\u2212"
TIMES = "\u00d7"


def one(written: str) -> NumberMention:
    mention = parse_number(written)
    assert mention is not None, written
    return mention


def texts(text: str) -> list[str]:
    return [n.text for n in scan(text).numbers]


# -- reading numbers ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "value", "percent", "decimals"),
    [
        ("42", 42.0, False, 0),
        ("-0.42", -0.42, False, 2),
        (f"{MINUS}0.42", -0.42, False, 2),
        ("+3", 3.0, False, 0),
        ("1,567", 1567.0, False, 0),
        (".05", 0.05, False, 2),
        ("12.5%", 12.5, True, 1),
        ("12.5 %", 12.5, True, 1),
        ("12.5 percent", 12.5, True, 1),
        ("2.3e-4", 0.00023, False, 5),
        ("1e-3", 0.001, False, 3),
        ("2.3E+2", 230.0, False, -1),
        (f"2.3 {TIMES} 10^-4", 0.00023, False, 5),
        (f"2.3{TIMES}10⁻⁴", 0.00023, False, 5),
    ],
)
def test_parse_number_reads_every_written_form(
    written: str, value: float, percent: bool, decimals: int
) -> None:
    mention = one(written)
    assert mention.value == pytest.approx(value)
    assert mention.percent is percent
    assert mention.decimals == decimals


@pytest.mark.parametrize("written", ["", "abc", "1 2", "0.3-0.5", "S060", "12.5% and 3"])
def test_parse_number_rejects_anything_but_one_number(written: str) -> None:
    assert parse_number(written) is None


def test_scan_finds_quantities_with_their_spans() -> None:
    text = "Risk 0.184 rose by 12.5% over 1,567 units."
    found = scan(text).numbers
    assert [n.text for n in found] == ["0.184", "12.5%", "1,567"]
    for n in found:
        assert text[n.start : n.end] == n.text


def test_a_dash_between_numbers_is_a_range_not_a_sign() -> None:
    found = scan("a share of 0.3-0.5 of the score").numbers
    assert [(n.text, n.value) for n in found] == [("0.3", 0.3), ("0.5", 0.5)]


def test_a_dash_after_a_space_is_a_sign() -> None:
    assert [n.value for n in scan("SHAP of -0.42 for S060").numbers] == [-0.42]


@pytest.mark.parametrize(
    ("text", "comparator"),
    [
        ("p < 0.001", "<"),
        ("p ≤ 0.001", "<="),
        ("q >= 0.05", ">="),
        ("less than 0.001", "<"),
        ("below 5%", "<"),
        ("at most 3", "<="),
        ("more than 20", ">"),
        ("exceeds 32.9", ">"),
        ("at least 10", ">="),
        ("equal to 7", None),
    ],
)
def test_comparators_before_a_number(text: str, comparator: str | None) -> None:
    (mention,) = scan(text).numbers
    assert mention.comparator == comparator


# -- identifiers ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind", "values"),
    [
        ("sensor S060 drifts", "sensor", ("S060",)),
        ("see E3", "evidence", ("E3",)),
        ("alarm AL-1043-t2 opened", "alarm", ("AL-1043-t2",)),
        ("wafer lot47542-12 shows", "wafer", ("lot47542-12",)),
        ("lot lot47542 has", "lot", ("lot47542",)),
        ("unit 1043.", "unit", ("1043",)),
        ("units 1043, 1050 and 1077 failed", "unit", ("1043", "1050", "1077")),
        ("sequence 1200 to 1240", "sequence", ("1200", "1240")),
        ("window 3 of the health report", "window", ("3",)),
        ("on 2008-09-24 at", "date", ("2008-09-24",)),
        ("at 15:05 on", "time", ("15:05",)),
    ],
)
def test_identifiers_are_found_and_normalised(
    text: str, kind: str, values: tuple[str, ...]
) -> None:
    found = [i for i in scan(text).identifiers if i.kind == kind]
    assert [i.values for i in found] == [values]
    assert scan(text).numbers == () or all(
        not (i.start <= n.start < i.end) for n in scan(text).numbers for i in found
    )


def test_identifier_digits_are_not_quantities() -> None:
    found = scan("Unit 1062 has S060 at E2 with T2 and V4 models; risk 0.184.")
    assert [n.text for n in found.numbers] == ["0.184"]
    kinds = {i.kind for i in found.identifiers}
    assert {"unit", "sensor", "evidence", "name"} <= kinds


def test_a_singular_keyword_takes_no_list() -> None:
    found = scan("unit 1043, 7 sensors")
    assert [i.values for i in found.identifiers if i.kind == "unit"] == [("1043",)]
    assert [n.text for n in found.numbers] == ["7"]


def test_known_identifiers_from_evidence_are_matched_literally() -> None:
    found = scan("Lot Q12_A.3 and wafer Q12_A.3-7", known_identifiers={"Q12_A.3", "Q12_A.3-7"})
    pairs = [(i.kind, i.text) for i in found.identifiers]
    assert ("lot", "Q12_A.3") in pairs
    assert ("wafer", "Q12_A.3-7") in pairs
    assert found.numbers == ()


def test_spelled_numbers_are_reported_except_one_and_two_sided() -> None:
    found = scan("Three sensors and twice the rate; one unit; a two-sided test; two-tailed.")
    assert [s.text for s in found.spelled] == ["Three", "twice"]


# -- matching -------------------------------------------------------------------------------


def test_percent_against_a_fraction_matches() -> None:
    assert matches(one("5%"), 0.05)


def test_percent_never_matches_the_same_digits() -> None:
    assert not matches(one("5%"), 5.0)


def test_a_fraction_never_matches_a_percentage_value() -> None:
    assert not matches(one("0.05"), 5.0)


def test_rounding_tolerance_follows_written_decimals() -> None:
    assert matches(one("0.12"), 0.1234)
    assert matches(one("0.055"), 0.0551)
    assert not matches(one("0.05"), 0.0551)
    assert matches(one("12%"), 0.1234)
    assert not matches(one("12.0%"), 0.1234)


def test_scientific_notation_tolerance() -> None:
    assert matches(one("1e-3"), 0.0014)
    assert not matches(one("1e-3"), 0.0016)
    assert matches(one("2.3e-4"), 0.000234)
    assert not matches(one("2.3e-4"), 0.000236)


def test_signs_must_agree() -> None:
    assert not matches(one("-0.42"), 0.42)
    assert not matches(one("0.42"), -0.42)
    assert matches(one("-0.42"), -0.42)
    assert magnitude_matches(one("0.42"), -0.42, percent=False)
    assert not magnitude_matches(one("0.43"), -0.42, percent=False)


def test_comparators_accept_the_inequality() -> None:
    (lt,) = scan("p < 0.001").numbers
    assert matches(lt, 0.0004)
    assert not matches(lt, 0.002)
    (ge,) = scan("at least 10").numbers
    assert matches(ge, 12)
    assert not matches(ge, 9)


def test_percent_override_from_a_reference_unit() -> None:
    assert matches(one("25.4"), 0.254, percent=True)
    assert not matches(one("25.4"), 0.254, percent=False)


def test_non_finite_evidence_never_matches() -> None:
    assert not matches(one("1"), float("nan"))
    assert not matches(one("1"), float("inf"))


@given(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False), st.integers(0, 6))
def test_a_number_rounded_for_display_always_matches_its_value(value: float, digits: int) -> None:
    written = f"{value:.{digits}f}"
    mention = one(written)
    assert matches(mention, value)


@given(st.floats(min_value=0, max_value=1, allow_nan=False), st.integers(0, 4))
def test_a_percentage_rounded_for_display_matches_its_fraction(value: float, digits: int) -> None:
    mention = one(f"{value * 100:.{digits}f}%")
    assert matches(mention, value)


# -- JSON helpers ---------------------------------------------------------------------------


def test_numeric_leaves_give_json_pointers_and_skip_booleans() -> None:
    data = {"a": 1, "b": [0.5, True, {"c/d": 2}], "e~": 3, "f": "x"}
    assert list(numeric_leaves(data)) == [("/a", 1.0), ("/b/0", 0.5), ("/b/2/c~1d", 2.0), ("/e~0", 3.0)]  # fmt: skip


def test_string_leaves_include_keys_and_values() -> None:
    assert set(string_leaves({"sensor": "S060", "list": ["a", 1]})) == {"sensor", "S060", "list", "a"}  # fmt: skip


def test_int_values_by_key_follow_list_items() -> None:
    data = {"unit_id": 5, "jump_unit_ids": [7, 9], "x": 1.5, "flag": True, "seq": 4.0}
    assert sorted(int_values_by_key(data)) == [("jump_unit_ids", 7), ("jump_unit_ids", 9), ("seq", 4), ("unit_id", 5)]  # fmt: skip


def test_scan_of_text_without_numbers() -> None:
    assert texts("No quantities here.") == []
