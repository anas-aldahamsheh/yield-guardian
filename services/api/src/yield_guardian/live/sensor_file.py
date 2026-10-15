"""Read an uploaded sensor file (CSV or XLSX) into SECOM-layout units, with plain-language issues.

The format (PLAN_V2 §3.1): one row per unit, the header

    unit_id, timestamp, S001, S002, ..., S590[, result]

with the 590 SECOM sensors by name and in order (letter case is not significant), and `result`
optional. Cells:

- `unit_id`: the unit's name as the file has it: letters, digits, spaces and `_ . : -`, up to
  64 characters. Names should be unique (a repeat is a warning: the run numbers units by row).
- `timestamp`: ISO 8601 without a zone, `YYYY-MM-DDTHH:MM:SS` as SECOM records it; a space in
  place of the `T`, SECOM's raw `dd/mm/yyyy HH:MM:SS`, and Excel date cells are read too. A
  time without a zone is UTC, as in SECOM; one with a zone is converted to UTC. An empty cell is
  allowed (a warning: drift and sensor health need every timestamp), as are timestamps that go
  back in time (a warning: the run keeps the file's order and skips drift).
- `S001` to `S590`: numbers; an empty cell, `NaN` or `nan` is a missing reading. Infinity, text
  or a decimal comma is an error.
- `result`: `pass` or `fail` in any letter case, or empty.

Errors block the run and warnings do not. Every issue names the 1-based file row (the header is
row 1 in a plain CSV) and the column. At most `MAX_UNITS` units are read. Whatever the bytes,
`parse` returns: a file it cannot read becomes an error issue, never an exception.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from pydantic import ValidationError

from yield_guardian.contracts.runs import MAX_UNITS, N_SENSORS, SensorUnitInput, UploadIssue
from yield_guardian.live.protocols import Parsed
from yield_guardian.live.tabular import Cell, Row, TableError, read_table

log = structlog.get_logger(__name__)

SENSORS = [f"S{i:03d}" for i in range(1, N_SENSORS + 1)]
HEADER = ["unit_id", "timestamp", *SENSORS]
RESULT = "result"
MAX_ISSUES = 200
MAX_CELL_ISSUES_PER_ROW = 5
SHOWN = 40  # characters of a bad value quoted back

UNIT_LABEL = re.compile(r"^[A-Za-z0-9_.:\- ]{1,64}$")
NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
DECIMAL_COMMA = re.compile(r"^[+-]?\d+,\d+$")
SECOM_TIME = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M")
ISO_EXAMPLE = "2008-07-19T11:55:00"


@dataclass
class _Issues:
    """Issues in file order, capped at MAX_ISSUES; what the cap leaves out is counted."""

    listed: list[UploadIssue] = field(default_factory=list)
    left_out: int = 0
    left_out_errors: int = 0

    def add(self, severity: str, row: int | None, column: str | None, message: str) -> None:
        if len(self.listed) < MAX_ISSUES:
            self.listed.append(
                UploadIssue.model_validate(
                    {"severity": severity, "row": row, "column": column, "message": message}
                )
            )
            return
        self.left_out += 1
        self.left_out_errors += severity == "error"

    def done(self, summary: Sequence[UploadIssue] = ()) -> list[UploadIssue]:
        out = [*self.listed, *summary]
        if self.left_out:
            out.append(
                UploadIssue(
                    severity="error" if self.left_out_errors else "warning",
                    row=None,
                    column=None,
                    message=(
                        f"{self.left_out:,} more problem{'s' if self.left_out != 1 else ''} "
                        f"({self.left_out_errors:,} of them errors) are not listed. Fix the "
                        "ones above and upload the file again to see the rest."
                    ),
                )
            )
        return out


def _shown(value: Cell) -> str:
    text = str(value).strip()
    return text if len(text) <= SHOWN else text[: SHOWN - 1] + "…"


def _error(
    message: str, row: int | None = None, column: str | None = None
) -> Parsed[SensorUnitInput]:
    return Parsed(
        items=[], issues=[UploadIssue(severity="error", row=row, column=column, message=message)]
    )


class SecomSensorFileParser:
    """`SensorFileParser` for the SECOM upload format (see the module docstring)."""

    def parse(self, data: bytes, filename: str) -> Parsed[SensorUnitInput]:
        try:
            return self._parse(data, filename)
        except Exception:  # the last guard: an upload never takes the request down
            log.exception("sensor_file_unreadable", filename=filename, size=len(data))
            return _error(
                "The file could not be read. Save it again as CSV (UTF-8) or .xlsx, with the "
                "header unit_id, timestamp, S001 to S590 and optionally result."
            )

    def _parse(self, data: bytes, filename: str) -> Parsed[SensorUnitInput]:
        try:
            table = read_table(data, filename)
        except TableError as error:
            return _error(error.message, error.row, error.column)
        problem = _header_problem(table.header)
        if problem is not None:
            message, column = problem
            return _error(message, table.header_row, column)
        if not table.rows:
            return _error("The file has a header but no units below it.", table.header_row + 1)
        if len(table.rows) > MAX_UNITS:
            return _error(
                f"The file has {len(table.rows):,} units; a run takes at most {MAX_UNITS:,}. "
                "Split it into smaller files.",
                table.rows[MAX_UNITS].number,
            )
        has_result = len(table.header) == len(HEADER) + 1
        issues = _Issues()
        items: list[SensorUnitInput] = []
        first_row_of: dict[str, int] = {}
        undated: list[int] = []
        dated: list[tuple[int, datetime]] = []
        for row in table.rows:
            unit = _parse_row(row, has_result, issues)
            if unit is None:
                continue
            label = unit.unit_id
            if label in first_row_of:
                issues.add(
                    "warning",
                    row.number,
                    "unit_id",
                    f'Row {row.number} repeats unit_id "{label}" from row '
                    f"{first_row_of[label]}. The run numbers units by row, so both are kept.",
                )
            else:
                first_row_of[label] = row.number
            if unit.timestamp is None:
                undated.append(row.number)
            else:
                dated.append((row.number, unit.timestamp))
            items.append(unit)
        return Parsed(
            items=items, issues=issues.done(_time_warnings(undated, dated, len(table.rows)))
        )


def _header_problem(header: list[str]) -> tuple[str, str | None] | None:
    """The first wrong header column, as (message, column name in the file), or None."""
    names = [h.strip() for h in header]
    for position, expected in enumerate(HEADER, start=1):
        if position > len(names):
            last = names[-1] if names else None
            if expected in SENSORS:
                missing = len(HEADER) - position + 1
                return (
                    f'The header stops after "{last}": {missing} sensor column'
                    f"{'s are' if missing != 1 else ' is'} missing. It needs unit_id, "
                    "timestamp, then all 590 sensors S001 to S590 in order, then optionally "
                    "result.",
                    last,
                )
            return (
                f'The header needs a "{expected}" column. It must start with unit_id and '
                "timestamp, followed by S001 to S590 in order.",
                last,
            )
        name = names[position - 1]
        if name.lower() != expected.lower():
            if expected in SENSORS:
                where = (
                    "the sensors S001 to S590 come in order after unit_id and timestamp, "
                    "with nothing between them"
                )
            else:
                where = "the header starts with unit_id, then timestamp"
            return (
                f'Column {position} of the header is "{name}"; it should be "{expected}" '
                f"({where}).",
                name,
            )
    extra = names[len(HEADER) :]
    if len(extra) > 1 or (extra and extra[0].lower() != RESULT):
        position = len(HEADER) + 1 + (1 if extra[0].lower() == RESULT else 0)
        name = names[position - 1]
        return (
            f'Column {position} of the header is "{name}"; after S590 only "result" may follow.',
            name,
        )
    return None


def _parse_row(row: Row, has_result: bool, issues: _Issues) -> SensorUnitInput | None:
    """One unit, or None when the row has an error (each error is added to `issues`)."""
    r = row.number
    cells = row.cells
    ok = True
    label = _unit_label(cells[0], r, issues)
    ok &= label is not None
    stamp, stamp_ok = _timestamp(cells[1], r, issues)
    ok &= stamp_ok
    readings: list[float | None] = []
    bad: list[str] = []
    for sensor, cell in zip(SENSORS, cells[2 : 2 + N_SENSORS], strict=True):
        value, problem = _reading(cell)
        if problem is None:
            readings.append(value)
            continue
        bad.append(sensor)
        if len(bad) <= MAX_CELL_ISSUES_PER_ROW:
            issues.add("error", r, sensor, f"Row {r}, column {sensor}: {problem}")
    if len(bad) > MAX_CELL_ISSUES_PER_ROW:
        more = len(bad) - MAX_CELL_ISSUES_PER_ROW
        issues.add(
            "error",
            r,
            bad[MAX_CELL_ISSUES_PER_ROW],
            f"Row {r} has {more} more reading{'s' if more != 1 else ''} that "
            f"{'are' if more != 1 else 'is'} not a number (from column "
            f"{bad[MAX_CELL_ISSUES_PER_ROW]}).",
        )
    ok &= not bad
    result, result_ok = _result(cells[2 + N_SENSORS] if has_result else None, r, issues)
    ok &= result_ok
    if not ok or label is None:
        return None
    if all(v is None for v in readings):
        issues.add(
            "warning",
            r,
            None,
            f"Row {r} has no sensor readings (every cell from S001 to S590 is empty).",
        )
    try:
        return SensorUnitInput(unit_id=label, timestamp=stamp, readings=readings, result=result)
    except ValidationError as error:  # every field was checked above; kept as a guard
        issues.add("error", r, None, f"Row {r} cannot be read: {error.errors()[0]['msg']}.")
        return None


def _unit_label(cell: Cell, r: int, issues: _Issues) -> str | None:
    if cell is None:
        issues.add("error", r, "unit_id", f"Row {r} has no unit_id.")
        return None
    if isinstance(cell, bool):
        text = ""
    elif isinstance(cell, datetime):
        text = cell.isoformat(sep=" ")
    elif isinstance(cell, float) and cell.is_integer():
        text = str(int(cell))
    else:
        text = str(cell).strip()
    if not UNIT_LABEL.match(text):
        issues.add(
            "error",
            r,
            "unit_id",
            f'Row {r}: unit_id "{_shown(cell)}" may use only letters, digits, spaces and '
            "_ . : - (up to 64 characters).",
        )
        return None
    return text


def _timestamp(cell: Cell, r: int, issues: _Issues) -> tuple[datetime | None, bool]:
    """(timestamp in UTC or None, whether the cell is acceptable)."""
    if cell is None:
        return None, True
    if isinstance(cell, datetime):
        return _as_utc(cell), True
    if isinstance(cell, bool | int | float):
        issues.add(
            "error",
            r,
            "timestamp",
            f"Row {r}, timestamp: {_shown(cell)} is a number, not a date and time. Format the "
            f"cell as a date, or write it as {ISO_EXAMPLE}.",
        )
        return None, False
    text = str(cell).strip()
    stamp = _read_time(text)
    if stamp is None:
        issues.add(
            "error",
            r,
            "timestamp",
            f'Row {r}, timestamp: "{_shown(cell)}" is not a date and time. Write it as '
            f"{ISO_EXAMPLE} (ISO 8601, as SECOM records it).",
        )
        return None, False
    return stamp, True


def _read_time(text: str) -> datetime | None:
    try:
        return _as_utc(datetime.fromisoformat(text))
    except ValueError:
        pass
    for pattern in SECOM_TIME:
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _as_utc(stamp: datetime) -> datetime:
    return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)


def _reading(cell: Cell) -> tuple[float | None, str | None]:
    """(reading or None for missing, problem or None)."""
    if cell is None:
        return None, None
    if isinstance(cell, bool):
        return None, f'"{cell}" is not a number.'
    if isinstance(cell, int | float):
        number = float(cell)
        if math.isnan(number):
            return None, None
        if math.isinf(number):
            return None, f'"{_shown(cell)}" is not a finite number.'
        return number, None
    if isinstance(cell, datetime):
        return None, f'"{_shown(cell)}" is a date, not a number.'
    text = str(cell).strip()
    value: float | None
    try:  # the fast path; float() also reads "1_0", "inf" and "nan", sorted out below
        value = float(text)
    except ValueError:
        value = None
    if value is not None and "_" not in text:
        if math.isfinite(value):
            return value, None
        if text.lower() == "nan":
            return None, None
        if NUMBER.match(text):  # an exponent too large for a double
            return None, f'"{_shown(text)}" is too large to be a reading.'
        if math.isinf(value):
            return None, f'"{_shown(text)}" is not a finite number.'
    if DECIMAL_COMMA.match(text):
        return None, (
            f'"{_shown(text)}" is not a number. Use a dot as the decimal mark '
            f"({text.replace(',', '.')}, not {text})."
        )
    return None, f'"{_shown(text)}" is not a number.'


def _result(cell: Cell, r: int, issues: _Issues) -> tuple[str | None, bool]:
    if cell is None:
        return None, True
    text = "" if isinstance(cell, bool) else str(cell).strip().lower()
    if text in ("pass", "fail"):
        return text, True
    hint = ""
    if text in ("-1", "1", "1.0", "-1.0"):
        hint = " SECOM's labels file uses -1 for pass and 1 for fail; write pass or fail."
    issues.add(
        "error",
        r,
        RESULT,
        f'Row {r}, result: "{_shown(cell)}" must be pass, fail or empty.{hint}',
    )
    return None, False


def _time_warnings(
    undated: list[int], dated: list[tuple[int, datetime]], units: int
) -> list[UploadIssue]:
    out: list[UploadIssue] = []
    if undated:
        out.append(
            UploadIssue(
                severity="warning",
                row=undated[0],
                column="timestamp",
                message=(
                    f"{len(undated):,} of {units:,} units have no timestamp (the first is in "
                    f"row {undated[0]}). Drift and sensor health need a timestamp on every unit."
                ),
            )
        )
    back = [(dated[i - 1], dated[i]) for i in range(1, len(dated)) if dated[i][1] < dated[i - 1][1]]
    if back:
        (previous_row, previous), (row, stamp) = back[0]
        out.append(
            UploadIssue(
                severity="warning",
                row=row,
                column="timestamp",
                message=(
                    f"Row {row}'s timestamp ({stamp:%Y-%m-%d %H:%M:%S}) is earlier than row "
                    f"{previous_row}'s ({previous:%Y-%m-%d %H:%M:%S}); {len(back):,} "
                    f"row{'s go' if len(back) != 1 else ' goes'} back in time. The run keeps "
                    "the file's order, so drift and sensor health will be skipped: sort the "
                    "file by timestamp to get them."
                ),
            )
        )
    return out
