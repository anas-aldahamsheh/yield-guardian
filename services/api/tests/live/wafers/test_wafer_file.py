"""The wafer file parser: real demo wafers round-trip through CSV and XLSX, corrupted files never
raise, and every problem gets a plain message with its row and column.

Round trips use real WM-811K demo maps. Files built for the error tests are test inputs, named
"T1" and so on, and nothing computed from them is reported.
"""

import base64
import csv
import io
import random
from datetime import datetime
from typing import Any

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from openpyxl import Workbook

from yield_guardian.bundles.wafermap import WafermapBundle
from yield_guardian.contracts.runs import MAX_WAFERS
from yield_guardian.live.wafer_file import MAX_ISSUES, WaferDieFile
from yield_guardian.live.wafers import decode_map

HEADER = ["lot", "wafer", "x", "y", "result"]
parser = WaferDieFile()
SLOW = settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


def die_rows(lot: str, wafer: int, grid: np.ndarray) -> list[list[Any]]:
    """One row per die (x = column, y = row, from the top-left); no-die positions left out."""
    ys, xs = np.nonzero(grid)
    return [
        [lot, wafer, int(x), int(y), "pass" if grid[y, x] == 1 else "fail"]
        for y, x in zip(ys.tolist(), xs.tolist(), strict=True)
    ]


def csv_file(rows: list[list[Any]], header: list[str] = HEADER) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue().encode()


def xlsx_file(rows: list[list[Any]], header: list[str] = HEADER) -> bytes:
    book = Workbook(write_only=True)
    sheet = book.create_sheet()
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def demo_file(bundle: WafermapBundle, rows: list[int]) -> list[list[Any]]:
    w = bundle.wafers
    return [r for i in rows for r in die_rows(w.lot[i], w.wafer_index[i], w.grid(i))]


def errors(data: bytes, name: str = "t.csv") -> list[tuple[int | None, str | None, str]]:
    parsed = parser.parse(data, name)
    return [(i.row, i.column, i.message) for i in parsed.issues if i.severity == "error"]


# Round trips ------------------------------------------------------------------------------------


def _check_round_trip(bundle: WafermapBundle, picked: list[int], data: bytes, name: str) -> None:
    parsed = parser.parse(data, name)
    assert parsed.issues == []
    w = bundle.wafers
    assert [(p.lot, p.wafer) for p in parsed.items] == [
        (w.lot[i], w.wafer_index[i]) for i in picked
    ]
    for item, i in zip(parsed.items, picked, strict=True):
        assert np.array_equal(decode_map(item.map), w.grid(i))
        assert base64.b64decode(item.map.cells) == w.maps[i]  # byte for byte
        assert item.label is None
        assert item.source_wafer is None


@SLOW
@given(
    picked=st.lists(st.integers(0, 10_252), min_size=1, max_size=4, unique=True),
    order=st.permutations(range(5)),
    upper=st.booleans(),
    seed=st.integers(0, 2**32 - 1),
)
def test_demo_wafers_round_trip_through_csv(
    bundle: WafermapBundle, picked: list[int], order: list[int], upper: bool, seed: int
) -> None:
    rows = demo_file(bundle, picked)
    random.Random(seed).shuffle(
        rows
    )  # any row order: wafers come out in the order of their first row
    keys = list(dict.fromkeys((r[0], r[1]) for r in rows))
    w = bundle.wafers
    picked = sorted(picked, key=lambda i: keys.index((w.lot[i], w.wafer_index[i])))
    header = [HEADER[c].upper() if upper else HEADER[c] for c in order]  # any case, any order
    data = csv_file([[r[c] for c in order] for r in rows], header)
    _check_round_trip(bundle, picked, data, "dies.csv")


@settings(
    deadline=None, max_examples=12, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(picked=st.lists(st.integers(0, 10_252), min_size=1, max_size=2, unique=True))
def test_demo_wafers_round_trip_through_xlsx(bundle: WafermapBundle, picked: list[int]) -> None:
    _check_round_trip(bundle, picked, xlsx_file(demo_file(bundle, picked)), "dies.xlsx")


def test_a_whole_real_lot_round_trips_in_both_formats(bundle: WafermapBundle) -> None:
    lot = sorted(bundle.lots)[0]
    picked = [i for i, name in enumerate(bundle.wafers.lot) if name == lot]
    rows = demo_file(bundle, picked)
    _check_round_trip(bundle, picked, csv_file(rows), "lot.csv")
    _check_round_trip(bundle, picked, xlsx_file(rows), "lot.xlsx")


# Corruption -------------------------------------------------------------------------------------


@SLOW
@given(
    picked=st.integers(0, 10_252),
    edits=st.lists(
        st.tuples(
            st.integers(0, 10**9),
            st.sampled_from(["flip", "drop", "insert", "cut"]),
            st.binary(min_size=1, max_size=4),
        ),
        min_size=1,
        max_size=6,
    ),
    xlsx=st.booleans(),
)
def test_random_corruption_never_raises(
    bundle: WafermapBundle, picked: int, edits: list[tuple[int, str, bytes]], xlsx: bool
) -> None:
    rows = demo_file(bundle, [picked])[:400]
    data = bytearray(xlsx_file(rows) if xlsx else csv_file(rows))
    for at, kind, junk in edits:
        at %= len(data) + 1
        if kind == "flip" and at < len(data):
            data[at] ^= junk[0] or 0xFF
        elif kind == "drop":
            del data[at : at + len(junk)]
        elif kind == "insert":
            data[at:at] = junk
        else:
            del data[at:]
        if not data:
            data = bytearray(b"\x00")
    parsed = parser.parse(bytes(data), "dies.xlsx" if xlsx else "dies.csv")
    assert parsed.items or any(i.severity == "error" for i in parsed.issues)
    for issue in parsed.issues:
        assert issue.message


@given(data=st.binary(max_size=2000), name=st.sampled_from(["a.csv", "a.xlsx", "a.txt", "a.bin"]))
def test_arbitrary_bytes_never_raise(data: bytes, name: str) -> None:
    parsed = parser.parse(data, name)
    assert parsed.items or any(i.severity == "error" for i in parsed.issues)


BAD_VALUES: dict[int, list[Any]] = {
    0: ["lot#1", "", "x" * 65, "Ünïcode"],
    1: ["abc", "0", "-2", "3.5", "10001", ""],
    2: ["-1", "a", "2.5", "1e3", ""],
    3: ["-4", "y", "0.1", ""],
    4: ["ok", "0", "3", "passed", ""],
}


@SLOW
@given(
    picked=st.integers(0, 10_252),
    where=st.integers(0, 10**6),
    column=st.integers(0, 4),
    choice=st.integers(0, 10),
)
def test_a_bad_cell_is_an_error_at_its_row_and_column(
    bundle: WafermapBundle, picked: int, where: int, column: int, choice: int
) -> None:
    rows = demo_file(bundle, [picked])
    target = where % len(rows)
    values = BAD_VALUES[column]
    rows[target][column] = values[choice % len(values)]
    found = errors(csv_file(rows))
    assert (target + 2, HEADER[column], found[0][2]) == found[0]  # the header is row 1
    assert f"Row {target + 2}" in found[0][2]


# Plain messages ---------------------------------------------------------------------------------


def test_missing_columns_are_named() -> None:
    (error,) = errors(b"lot,wafer,x\nT1,1,0\n")
    assert error[0] == 1
    assert '"y", "result" columns' in error[2]
    assert "lot, wafer, x, y, result" in error[2]


def test_a_column_named_twice_in_another_case() -> None:
    (error,) = errors(b"lot,LOT,wafer,x,y,result\nT1,T1,1,0,0,pass\n")
    assert "twice" in error[2]
    assert error[1] == "LOT"


def test_extra_columns_are_a_warning() -> None:
    parsed = parser.parse(
        b"Lot,Wafer,X,Y,Result,note\nT1,1,0,0,PASS,hello\nT1,1,1,0,Fail,\n", "t.csv"
    )
    assert [(i.severity, i.row, i.column) for i in parsed.issues] == [("warning", 1, "note")]
    assert 'The column "note" is not used' in parsed.issues[0].message
    (wafer,) = parsed.items
    assert decode_map(wafer.map).tolist() == [[1, 2]]


@pytest.mark.parametrize(
    ("cell", "column", "fragment"),
    [
        ("lot#1", "lot", 'the lot "lot#1" is not a name of 1 to 64 letters'),
        ("0", "wafer", '"0" is not a wafer number; it must be a whole number from 1 to 10,000'),
        ("3.5", "wafer", '"3.5" is not a wafer number'),
        ("-1", "x", '"-1" is not a column (x); it must be a whole number of 0 or more'),
        ("abc", "y", '"abc" is not a row (y)'),
        ("ok", "result", 'the result "ok" is not pass or fail'),
        ("0", "result", "0 means no die in WM-811K"),
        ("", "x", 'the "x" cell is empty; it needs a column (x)'),
    ],
)
def test_bad_values_have_plain_messages(cell: str, column: str, fragment: str) -> None:
    rows = [["T1", 1, 0, 0, "pass"], ["T1", 1, 1, 0, "pass"]]
    rows[1][HEADER.index(column)] = cell
    found = errors(csv_file(rows))
    assert found[0][:2] == (3, column)
    assert fragment in found[0][2]


def test_wm811k_codes_are_read_with_a_warning() -> None:
    parsed = parser.parse(
        csv_file([["T1", 1, 0, 0, 1], ["T1", 1, 1, 0, 2], ["T1", 1, 2, 0, "pass"]]), "t.csv"
    )
    assert [(i.severity, i.row, i.column) for i in parsed.issues] == [("warning", 2, "result")]
    assert "WM-811K codes 1 and 2" in parsed.issues[0].message
    assert decode_map(parsed.items[0].map).tolist() == [[1, 2, 1]]


def test_a_repeated_die_is_an_error() -> None:
    (error,) = errors(
        csv_file([["T1", 1, 4, 2, "pass"], ["T1", 1, 0, 0, "pass"], ["T1", 1, 4, 2, "fail"]])
    )
    assert error[0] == 4
    assert "repeats the die at x 4, y 2 of lot T1, wafer 1 (first on row 2)" in error[2]


def test_a_wafer_larger_than_512_is_an_error() -> None:
    (error,) = errors(csv_file([["T1", 1, 0, 0, "pass"], ["T1", 1, 512, 3, "fail"]]))
    assert error[:2] == (3, "x")
    assert "larger than 512 x 512: x goes up to 512 (row 3)" in error[2]
    (error,) = errors(csv_file([["T1", 1, 0, 10**9, "pass"]]))
    assert error[:2] == (2, "y")


def test_more_than_500_wafers_is_an_error() -> None:
    rows = [["T1", n, 0, 0, "pass"] for n in range(1, MAX_WAFERS + 2)]
    parsed = parser.parse(csv_file(rows), "t.csv")
    assert parsed.items == []
    assert [i.message for i in parsed.issues] == [
        "The file has 501 wafers; a run takes at most 500. Split it into several files."
    ]
    assert len(parser.parse(csv_file(rows[:-1]), "t.csv").items) == MAX_WAFERS


def test_a_wafer_with_no_readable_die_is_an_error() -> None:
    found = errors(csv_file([["T1", 1, "a", 0, "pass"], ["T2", 1, 0, 0, "pass"]]))
    assert found[0][:2] == (2, "x")
    assert found[1][0] == 2
    assert "Lot T1, wafer 1 has no die that could be read" in found[1][2]


def test_xlsx_cells_keep_their_types() -> None:
    rows: list[list[Any]] = [
        [12, 1.0, 0, 0, "pass"],  # a lot named by a number; a whole float
        ["T1", True, 1, 0, "pass"],
        ["T1", 1, datetime(2026, 1, 1), 0, "fail"],
        ["T1", 1, 2.5, 0, "fail"],
        ["T1", 1, 3, 0, 2.0],
    ]
    parsed = parser.parse(xlsx_file(rows), "t.xlsx")
    found = [(i.row, i.column) for i in parsed.issues if i.severity == "error"]
    assert found == [(3, "wafer"), (4, "x"), (5, "x")]
    assert [(w.lot, w.wafer) for w in parsed.items] == [("12", 1), ("T1", 1)]


def test_a_header_without_dies_is_an_error() -> None:
    (error,) = errors(b"lot,wafer,x,y,result\n")
    assert "lists no wafer that could be read" in error[2]
    found = errors(b"lot,wafer,x,y,result\n#,1,0,0,pass\n")
    assert [e[:2] for e in found] == [(2, "lot"), (None, None)]


def test_table_errors_pass_through() -> None:
    assert errors(b"", "t.csv") == [(None, None, "The file is empty.")]
    assert "Use .csv or .xlsx" in errors(b"a", "t.json")[0][2]


def test_issues_are_capped_with_a_count_of_the_rest() -> None:
    rows = [["T1", 1, n, "?", "pass"] for n in range(300)]
    parsed = parser.parse(csv_file(rows), "t.csv")
    assert len(parsed.issues) == MAX_ISSUES + 1
    last = parsed.issues[-1]
    assert last.severity == "error"
    assert last.message.startswith("201 more problems are not listed")
