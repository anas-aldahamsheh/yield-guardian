"""The sensor file parser: real SECOM units written in the upload format read back unchanged,
every mistake becomes a plain issue with its row and column, and no input raises."""

import io
from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from openpyxl import Workbook

from yield_guardian.contracts.runs import MAX_UNITS, SensorUnitInput, UploadIssue
from yield_guardian.live.protocols import Parsed, SensorFileParser
from yield_guardian.live.sensor_file import HEADER, MAX_ISSUES, SENSORS, SecomSensorFileParser

PARSER = SecomSensorFileParser()
GUARD = "The file could not be read."
FIXTURES = [HealthCheck.function_scoped_fixture, HealthCheck.too_slow]


def parse(data: bytes, filename: str = "units.csv") -> Parsed[SensorUnitInput]:
    parsed = PARSER.parse(data, filename)
    assert not any(i.message.startswith(GUARD) for i in parsed.issues)
    return parsed


def errors(parsed: Parsed[SensorUnitInput]) -> list[UploadIssue]:
    return [i for i in parsed.issues if i.severity == "error"]


def warnings(parsed: Parsed[SensorUnitInput]) -> list[UploadIssue]:
    return [i for i in parsed.issues if i.severity == "warning"]


def as_upload(units: list[SensorUnitInput]) -> list[SensorUnitInput]:
    """What a file of these real units should read back as: everything but the SECOM row."""
    return [u.model_copy(update={"source_unit": None}) for u in units]


def rows_of(
    units: list[SensorUnitInput], *, missing: str = "", t: str = "T", result: bool = True
) -> list[list[str]]:
    rows = [[*HEADER, *(["result"] if result else [])]]
    for u in units:
        assert u.timestamp is not None
        stamp = u.timestamp.replace(tzinfo=None).isoformat(sep=t)
        readings = [missing if v is None else repr(v) for v in u.readings]
        rows.append([u.unit_id, stamp, *readings, *([u.result or ""] if result else [])])
    return rows


def csv_bytes(rows: list[list[str]], sep: str = ",", newline: str = "\n") -> bytes:
    return "".join(sep.join(r) + newline for r in rows).encode()


def xlsx_bytes(units: list[SensorUnitInput], *, result: bool = True) -> bytes:
    """Numbers as number cells, timestamps as Excel date cells (no zone), as Excel saves them."""
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append([*HEADER, *(["result"] if result else [])])
    for u in units:
        assert u.timestamp is not None
        sheet.append(
            [
                int(u.unit_id) if u.unit_id.isdigit() else u.unit_id,
                u.timestamp.replace(tzinfo=None),
                *u.readings,
                *([u.result] if result else []),
            ]
        )
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_it_is_a_sensor_file_parser() -> None:
    checked: SensorFileParser = PARSER
    assert checked is PARSER


# Round trips of real SECOM units -----------------------------------------------------------------


def test_every_secom_unit_round_trips_through_the_upload_csv(
    all_units: list[SensorUnitInput],
) -> None:
    """The runs worker's real example file format: `YYYY-MM-DDTHH:MM:SS`, empty cell = missing."""
    parsed = parse(csv_bytes(rows_of(all_units)))
    assert parsed.issues == []
    assert parsed.items == as_upload(all_units)


def test_secom_units_round_trip_through_xlsx(all_units: list[SensorUnitInput]) -> None:
    units = all_units[700:760]
    parsed = parse(xlsx_bytes(units), "units.xlsx")
    assert parsed.issues == []
    assert parsed.items == as_upload(units)


@settings(max_examples=40, deadline=None, suppress_health_check=FIXTURES)
@given(
    start=st.integers(0, 1566),
    length=st.integers(1, 20),
    missing=st.sampled_from(["", "NaN", "nan"]),
    t=st.sampled_from(["T", " "]),
    sep=st.sampled_from([",", ";", "\t"]),
    newline=st.sampled_from(["\n", "\r\n"]),
    result=st.booleans(),
)
def test_csv_round_trip(
    all_units: list[SensorUnitInput],
    start: int,
    length: int,
    missing: str,
    t: str,
    sep: str,
    newline: str,
    result: bool,
) -> None:
    units = all_units[start : start + length]
    data = csv_bytes(rows_of(units, missing=missing, t=t, result=result), sep, newline)
    parsed = parse(data)
    assert parsed.issues == []
    expected = as_upload(units)
    if not result:
        expected = [u.model_copy(update={"result": None}) for u in expected]
    assert parsed.items == expected


@settings(max_examples=15, deadline=None, suppress_health_check=FIXTURES)
@given(start=st.integers(0, 1566), length=st.integers(1, 12), result=st.booleans())
def test_xlsx_round_trip(
    all_units: list[SensorUnitInput], start: int, length: int, result: bool
) -> None:
    units = all_units[start : start + length]
    parsed = parse(xlsx_bytes(units, result=result), "units.xlsx")
    assert parsed.issues == []
    expected = as_upload(units)
    if not result:
        expected = [u.model_copy(update={"result": None}) for u in expected]
    assert parsed.items == expected


# Corruption never raises and is always reported where it is ------------------------------------

NOT_A_NUMBER = st.from_regex(r"\A[A-Za-z#@!?%&*/<>]{1,12}\Z").filter(
    lambda s: s.lower() not in ("nan", "inf", "infinity")
)


@settings(max_examples=60, deadline=None, suppress_health_check=FIXTURES)
@given(
    data=st.data(),
    kind=st.sampled_from(["reading", "timestamp", "result", "unit_id", "header"]),
)
def test_a_corrupted_cell_is_an_error_at_its_row_and_column(
    all_units: list[SensorUnitInput], data: st.DataObject, kind: str
) -> None:
    rows = rows_of(all_units[300:304])
    line = data.draw(st.integers(1, 4))  # a data row (row 1 is the header)
    if kind == "reading":
        column = data.draw(st.integers(2, 591))
        rows[line][column] = data.draw(NOT_A_NUMBER)
        expected = (line + 1, HEADER[column])
    elif kind == "timestamp":
        rows[line][1] = data.draw(NOT_A_NUMBER)
        expected = (line + 1, "timestamp")
    elif kind == "result":
        rows[line][-1] = data.draw(NOT_A_NUMBER.filter(lambda s: s.lower() not in ("pass", "fail")))
        expected = (line + 1, "result")
    elif kind == "unit_id":
        rows[line][0] = "unit" + data.draw(st.sampled_from("/#?!*&%@<>")) + "1"
        expected = (line + 1, "unit_id")
    else:
        column = data.draw(st.integers(0, len(rows[0]) - 1))
        name = data.draw(NOT_A_NUMBER.filter(lambda s: s.lower() != rows[0][column].lower()))
        rows[0][column] = name
        expected = (1, name)
    parsed = parse(csv_bytes(rows))
    found = errors(parsed)
    assert found, parsed.issues
    assert (found[0].row, found[0].column) == expected
    if kind != "header":
        line_number = expected[0]
        assert len(parsed.items) == 3  # the other rows still read
        assert all(i.row == line_number for i in found)


@settings(max_examples=150, deadline=None)
@given(st.binary(max_size=4000), st.sampled_from(["f.csv", "f.xlsx", "f.txt", "f.bin"]))
def test_arbitrary_bytes_never_raise(data: bytes, filename: str) -> None:
    parsed = parse(data, filename)
    assert errors(parsed)
    assert parsed.items == [] or all(isinstance(u, SensorUnitInput) for u in parsed.items)


@settings(max_examples=150, deadline=None)
@given(st.text(max_size=3000))
def test_arbitrary_text_never_raises(text: str) -> None:
    assert errors(parse(text.encode(), "f.csv"))


@pytest.fixture(scope="module")
def valid_files(all_units: list[SensorUnitInput]) -> dict[str, bytes]:
    """Built once: openpyxl stamps the save time into the workbook."""
    units = all_units[10:13]
    return {"f.csv": csv_bytes(rows_of(units)), "f.xlsx": xlsx_bytes(units)}


@settings(max_examples=60, deadline=None, suppress_health_check=FIXTURES)
@given(data=st.data(), filename=st.sampled_from(["f.csv", "f.xlsx"]))
def test_mutated_files_never_raise(
    valid_files: dict[str, bytes], data: st.DataObject, filename: str
) -> None:
    mutated = bytearray(valid_files[filename])
    for _ in range(data.draw(st.integers(1, 20))):
        position = data.draw(st.integers(0, len(mutated) - 1))
        action = data.draw(st.sampled_from(["flip", "insert", "delete", "truncate"]))
        byte = data.draw(st.integers(0, 255))
        if action == "flip":
            mutated[position] = byte
        elif action == "insert":
            mutated.insert(position, byte)
        elif action == "delete" and len(mutated) > 1:
            del mutated[position]
        elif action == "truncate":
            del mutated[max(1, position) :]
    parsed = parse(bytes(mutated), filename)
    assert all(isinstance(i, UploadIssue) for i in parsed.issues)


# Plain messages ---------------------------------------------------------------------------------


def one_unit(all_units: list[SensorUnitInput]) -> list[list[str]]:
    return rows_of(all_units[1043:1044])


@pytest.mark.parametrize(
    ("change", "row", "column", "message"),
    [
        (
            lambda h: h.__setitem__(0, "unit"),
            1,
            "unit",
            'Column 1 of the header is "unit"; it should be "unit_id" (the header starts with '
            "unit_id, then timestamp).",
        ),
        (
            lambda h: h.__setitem__(slice(6, 8), ["S006", "S005"]),
            1,
            "S006",
            'Column 7 of the header is "S006"; it should be "S005" (the sensors S001 to S590 '
            "come in order after unit_id and timestamp, with nothing between them).",
        ),
        (
            lambda h: h.__delitem__(slice(402, None)),
            1,
            "S400",
            'The header stops after "S400": 190 sensor columns are missing. It needs unit_id, '
            "timestamp, then all 590 sensors S001 to S590 in order, then optionally result.",
        ),
        (
            lambda h: h.append("notes"),
            1,
            "notes",
            'Column 594 of the header is "notes"; after S590 only "result" may follow.',
        ),
        (
            lambda h: h.__setitem__(592, "label"),
            1,
            "label",
            'Column 593 of the header is "label"; after S590 only "result" may follow.',
        ),
    ],
)
def test_header_mistakes(
    all_units: list[SensorUnitInput], change: object, row: int, column: str, message: str
) -> None:
    rows = one_unit(all_units)
    header = rows[0]
    change(header)  # type: ignore[operator]
    rows = [header, rows[1][: len(header)]]
    parsed = parse(csv_bytes(rows))
    assert parsed.items == []
    assert [(i.severity, i.row, i.column, i.message) for i in parsed.issues] == [
        ("error", row, column, message)
    ]


def test_header_letter_case_does_not_matter(all_units: list[SensorUnitInput]) -> None:
    rows = one_unit(all_units)
    rows[0] = [h.upper() if i % 2 else h.lower() for i, h in enumerate(rows[0])]
    assert parse(csv_bytes(rows)).items == as_upload(all_units[1043:1044])


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        (5, "abc", 'Row 2, column S004: "abc" is not a number.'),
        (
            5,
            "3,5",
            'Row 2, column S004: "3,5" is not a number. Use a dot as the decimal mark '
            "(3.5, not 3,5).",
        ),
        (5, "inf", 'Row 2, column S004: "inf" is not a finite number.'),
        (5, "-Infinity", 'Row 2, column S004: "-Infinity" is not a finite number.'),
        (5, "1e999", 'Row 2, column S004: "1e999" is too large to be a reading.'),
        (5, "1_000", 'Row 2, column S004: "1_000" is not a number.'),
        (
            1,
            "19/07/2008 11:55",
            None,  # SECOM's own format, read (see the next test)
        ),
        (
            1,
            "yesterday",
            'Row 2, timestamp: "yesterday" is not a date and time. Write it as '
            "2008-07-19T11:55:00 (ISO 8601, as SECOM records it).",
        ),
        (
            592,
            "-1",
            'Row 2, result: "-1" must be pass, fail or empty. SECOM\'s labels file uses -1 for '
            "pass and 1 for fail; write pass or fail.",
        ),
        (592, "ok", 'Row 2, result: "ok" must be pass, fail or empty.'),
        (
            0,
            "unit/7",
            'Row 2: unit_id "unit/7" may use only letters, digits, spaces and _ . : - '
            "(up to 64 characters).",
        ),
        (
            0,
            "x" * 65,
            f'Row 2: unit_id "{"x" * 39}…" may use only letters, digits, spaces and _ . : - '
            "(up to 64 characters).",
        ),
    ],
)
def test_cell_mistakes(
    all_units: list[SensorUnitInput], column: int, value: str, message: str | None
) -> None:
    rows = one_unit(all_units)
    rows[1][column] = f'"{value}"' if "," in value else value
    parsed = parse(csv_bytes(rows))
    if message is None:
        assert errors(parsed) == []
        return
    assert parsed.items == []
    assert [(i.severity, i.row, i.column, i.message) for i in parsed.issues] == [
        ("error", 2, HEADER[column] if column < 592 else "result", message)
    ]


def test_missing_unit_id(all_units: list[SensorUnitInput]) -> None:
    rows = one_unit(all_units)
    rows[1][0] = ""
    assert [(i.row, i.column, i.message) for i in parse(csv_bytes(rows)).issues] == [
        (2, "unit_id", "Row 2 has no unit_id.")
    ]


def test_timestamp_forms(all_units: list[SensorUnitInput]) -> None:
    unit = all_units[1043]
    assert unit.timestamp is not None
    local = unit.timestamp.replace(tzinfo=None)
    forms = [
        local.isoformat(),
        local.isoformat(sep=" "),
        f"{local:%d/%m/%Y %H:%M:%S}",
        (unit.timestamp.astimezone(timezone(timedelta(hours=3)))).isoformat(),
        local.isoformat() + "Z",
    ]
    for form in forms:
        rows = one_unit(all_units)
        rows[1][1] = form
        parsed = parse(csv_bytes(rows))
        assert parsed.issues == [], form
        assert parsed.items[0].timestamp == unit.timestamp


def test_xlsx_cell_types(all_units: list[SensorUnitInput]) -> None:
    unit = all_units[5]
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append([*HEADER, "result"])
    readings: list[object] = list(unit.readings)
    readings[0] = True
    readings[1] = datetime(2008, 1, 1)
    readings[2] = "12.5"
    sheet.append(["7", 39648.5, *readings, "PASS"])
    out = io.BytesIO()
    book.save(out)
    parsed = parse(out.getvalue(), "u.xlsx")
    assert [(i.column, i.message) for i in parsed.issues] == [
        (
            "timestamp",
            "Row 2, timestamp: 39648.5 is a number, not a date and time. Format the cell as a "
            "date, or write it as 2008-07-19T11:55:00.",
        ),
        ("S001", 'Row 2, column S001: "True" is not a number.'),
        ("S002", 'Row 2, column S002: "2008-01-01 00:00:00" is a date, not a number.'),
    ]


def test_warnings_do_not_block(all_units: list[SensorUnitInput]) -> None:
    units = all_units[40:46]
    rows = rows_of(units)
    rows[3][0] = rows[1][0]  # a repeated unit_id
    rows[4][1] = ""  # no timestamp
    rows[5], rows[6] = rows[6], rows[5]  # back in time
    rows[2][2:592] = [""] * 590  # no readings
    parsed = parse(csv_bytes(rows))
    assert errors(parsed) == []
    assert len(parsed.items) == 6
    assert [(i.row, i.column) for i in warnings(parsed)] == [
        (3, None),
        (4, "unit_id"),
        (5, "timestamp"),
        (7, "timestamp"),
    ]
    messages = [i.message for i in warnings(parsed)]
    assert messages[0] == "Row 3 has no sensor readings (every cell from S001 to S590 is empty)."
    assert messages[1] == (
        f'Row 4 repeats unit_id "{units[0].unit_id}" from row 2. The run numbers units by row, '
        "so both are kept."
    )
    assert messages[2] == (
        "1 of 6 units have no timestamp (the first is in row 5). Drift and sensor health need a "
        "timestamp on every unit."
    )
    assert messages[3].startswith("Row 7's timestamp (")
    assert messages[3].endswith(
        "1 row goes back in time. The run keeps the file's order, so drift and sensor health "
        "will be skipped: sort the file by timestamp to get them."
    )


@pytest.mark.parametrize(
    ("data", "filename", "message"),
    [
        (b"", "u.csv", "The file is empty."),
        (b"a,b\n", "u.json", '".json" files are not read here. Use .csv or .xlsx.'),
        (
            ",".join(HEADER).encode() + b"\n",
            "u.csv",
            "The file has a header but no units below it.",
        ),
    ],
)
def test_file_level_mistakes(data: bytes, filename: str, message: str) -> None:
    parsed = parse(data, filename)
    assert [(i.severity, i.message) for i in parsed.issues] == [("error", message)]


def test_at_most_five_thousand_units() -> None:
    row = "u1,2008-07-19T11:55:00" + "," * 590 + "\n"
    data = (",".join(HEADER) + "\n" + row * (MAX_UNITS + 1)).encode()
    parsed = parse(data)
    assert parsed.items == []
    assert [(i.row, i.message) for i in parsed.issues] == [
        (
            MAX_UNITS + 2,
            "The file has 5,001 units; a run takes at most 5,000. Split it into smaller files.",
        )
    ]
    assert len(parse((",".join(HEADER) + "\n" + row * MAX_UNITS).encode()).items) == MAX_UNITS


def test_issues_are_capped_with_a_count_of_the_rest(all_units: list[SensorUnitInput]) -> None:
    rows = rows_of(all_units[:50])
    for row in rows[1:]:
        row[2:592] = ["x"] * 590
    parsed = parse(csv_bytes(rows))
    assert len(parsed.issues) == MAX_ISSUES + 1
    first = parsed.issues[:6]
    assert [i.column for i in first] == [*SENSORS[:5], "S006"]
    assert (
        first[5].message == "Row 2 has 585 more readings that are not a number (from column S006)."
    )
    last = parsed.issues[-1]
    assert (last.severity, last.row, last.column) == ("error", None, None)
    assert last.message == (
        "100 more problems (100 of them errors) are not listed. Fix the ones above and upload "
        "the file again to see the rest."
    )


def test_semicolons_bom_and_quoted_cells(all_units: list[SensorUnitInput]) -> None:
    rows = one_unit(all_units)
    rows[1] = [f'"{c}"' for c in rows[1]]
    data = "﻿".encode() + csv_bytes(rows, ";")
    assert parse(data).items == as_upload(all_units[1043:1044])


def test_timestamps_are_utc_and_the_items_are_contracts(all_units: list[SensorUnitInput]) -> None:
    parsed = parse(csv_bytes(rows_of(all_units[:3])))
    assert all(u.timestamp is not None and u.timestamp.tzinfo == UTC for u in parsed.items)
    assert all(u.source_unit is None for u in parsed.items)
