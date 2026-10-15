import io
from datetime import datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openpyxl import Workbook

from yield_guardian.live.tabular import MAX_BYTES, TableError, read_table


def xlsx(rows: list[list[object]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_csv_header_rows_and_file_row_numbers() -> None:
    table = read_table(b"lot,wafer,x\r\nlot1,1,3\r\n\r\nlot1,2,\r\n", "dies.csv")
    assert table.header == ["lot", "wafer", "x"]
    assert table.header_row == 1
    assert [r.number for r in table.rows] == [2, 4]
    assert table.rows[1].cells == ["lot1", "2", None]


def test_csv_with_bom_and_semicolons() -> None:
    table = read_table("﻿a;b\n1;2\n".encode(), "t.csv")
    assert table.header == ["a", "b"]
    assert table.rows[0].cells == ["1", "2"]


def test_xlsx_keeps_numbers_and_datetimes() -> None:
    stamp = datetime(2008, 7, 19, 11, 55)
    table = read_table(xlsx([["unit_id", "timestamp", "S001"], ["u1", stamp, 3030.93]]), "u.xlsx")
    assert table.kind == "xlsx"
    assert table.rows[0].cells == ["u1", stamp, 3030.93]


@pytest.mark.parametrize(
    ("data", "name", "fragment"),
    [
        (b"", "a.csv", "empty"),
        (b"a,b\n1,2\n", "a.json", "Use .csv or .xlsx"),
        (b"a,,b\n1,2,3\n", "a.csv", "Column 2 of the header is empty"),
        (b"a,a\n1,2\n", "a.csv", 'names "a" twice'),
        (b"a,b\n1,2,3\n", "a.csv", "more values than the header"),
        (b"\xff\xfe\x00a", "a.csv", "UTF-8"),
        (b"not a zip", "a.xlsx", "not a valid .xlsx"),
    ],
)
def test_plain_errors(data: bytes, name: str, fragment: str) -> None:
    with pytest.raises(TableError) as caught:
        read_table(data, name)
    assert fragment in caught.value.message


def test_size_guard() -> None:
    with pytest.raises(TableError, match=f"limit is {MAX_BYTES // 1_048_576} MB"):
        read_table(b"a\n" + b"1\n" * (MAX_BYTES // 2 + 1), "big.csv")


@given(st.lists(st.lists(st.integers(-1000, 1000), min_size=3, max_size=3), max_size=40))
def test_csv_round_trip(values: list[list[int]]) -> None:
    text = "a,b,c\n" + "".join(",".join(map(str, row)) + "\n" for row in values)
    table = read_table(text.encode(), "r.csv")
    assert [[int(str(c)) for c in r.cells] for r in table.rows] == values
