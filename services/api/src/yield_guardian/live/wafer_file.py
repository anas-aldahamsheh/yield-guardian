"""Read an uploaded wafer file (CSV or XLSX): one row per die, `lot, wafer, x, y, result`.

`x` is the column and `y` the row, both counted from 0 at the map's top-left; each wafer's grid
is (max y + 1) rows by (max x + 1) columns, a listed die is 1 (pass) or 2 (fail), and every
position not listed is 0 (no die). That is the WM-811K map layout, so a real map written out
die by die reads back as the same grid (PLAN_V2 §3.1).

Every problem becomes an `UploadIssue` with the file's own row number and the column as the
header writes it; the parser never raises. Errors block the run, warnings do not.
"""

import base64
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import numpy as np

from yield_guardian.contracts.runs import MAX_WAFERS, UploadIssue, WaferInput
from yield_guardian.contracts.wafer import WaferMap
from yield_guardian.live.protocols import Parsed
from yield_guardian.live.tabular import Cell, Row, Table, TableError, read_table

COLUMNS = ("lot", "wafer", "x", "y", "result")
MAX_SIDE = 512  # WaferMap allows 512 x 512
MAX_WAFER_NUMBER = 10_000
MAX_LOT_LENGTH = 64
LOT_PATTERN = re.compile(r"^[A-Za-z0-9_.:\- ]+$")
INTEGER_PATTERN = re.compile(r"^[+-]?\d{1,12}(\.0*)?$")
MAX_ISSUES = 100  # issues listed one by one; the rest are counted in one closing issue
PASS, FAIL = 1, 2
RESULT_WORDS = {"pass": PASS, "fail": FAIL}
RESULT_CODES = {1: PASS, 2: FAIL}

Severity = Literal["error", "warning"]
WaferKey = tuple[str, int]


@dataclass(slots=True)
class _Wafer:
    first_row: int
    dies: dict[tuple[int, int], tuple[int, int]]  # (x, y) -> (value, row)


class _Issues:
    def __init__(self) -> None:
        self.items: list[UploadIssue] = []
        self.dropped = 0
        self.dropped_errors = 0

    def add(
        self, severity: Severity, message: str, row: int | None = None, column: str | None = None
    ) -> None:
        if len(self.items) >= MAX_ISSUES:
            self.dropped += 1
            self.dropped_errors += severity == "error"
            return
        self.items.append(UploadIssue(severity=severity, row=row, column=column, message=message))

    def done(self) -> list[UploadIssue]:
        if self.dropped:
            return [
                *self.items,
                UploadIssue(
                    severity="error" if self.dropped_errors else "warning",
                    row=None,
                    column=None,
                    message=f"{self.dropped:,} more problems are not listed. Fix the ones "
                    "above and upload the file again.",
                ),
            ]
        return self.items


def _shown(cell: Cell) -> str:
    text = str(cell)
    return f'"{text[:40]}…"' if len(text) > 40 else f'"{text}"'


def _integer(cell: Cell) -> int | None:
    """A whole number written as an integer, an integral float (XLSX) or digits; else None."""
    if isinstance(cell, bool):
        return None
    if isinstance(cell, int):
        return cell
    if isinstance(cell, float):
        return int(cell) if math.isfinite(cell) and cell.is_integer() else None
    if isinstance(cell, str) and INTEGER_PATTERN.match(text := cell.strip()):
        return int(text.split(".")[0])
    return None


class WaferDieFile:
    """Implements :class:`~yield_guardian.live.protocols.WaferFileParser`."""

    def parse(self, data: bytes, filename: str) -> Parsed[WaferInput]:
        issues = _Issues()
        try:
            table = read_table(data, filename)
        except TableError as error:
            issues.add("error", error.message, error.row, error.column)
            return Parsed(items=[], issues=issues.done())
        except Exception:  # read_table reports every failure it knows; untrusted bytes never raise
            issues.add("error", "The file cannot be read as a table. Save the sheet as CSV.")
            return Parsed(items=[], issues=issues.done())
        columns = self._columns(table, issues)
        if columns is None:
            return Parsed(items=[], issues=issues.done())
        wafers = self._rows(table, columns, issues)
        if not wafers:
            issues.add(
                "error",
                "The file lists no wafer that could be read: it needs one row per die under the "
                "header (lot, wafer, x, y, result).",
            )
            return Parsed(items=[], issues=issues.done())
        if len(wafers) > MAX_WAFERS:
            issues.add(
                "error",
                f"The file has {len(wafers):,} wafers; a run takes at most {MAX_WAFERS}. "
                "Split it into several files.",
            )
            return Parsed(items=[], issues=issues.done())
        items = [
            wafer
            for key, record in wafers.items()
            if (wafer := self._wafer(key, record, columns, issues)) is not None
        ]
        return Parsed(items=items, issues=issues.done())

    # Header -----------------------------------------------------------------------------------

    @staticmethod
    def _columns(table: Table, issues: _Issues) -> dict[str, tuple[int, str]] | None:
        """Each expected column's position and name as written; None when one is missing."""
        found: dict[str, tuple[int, str]] = {}
        for position, name in enumerate(table.header):
            key = name.strip().lower()
            if key in COLUMNS:
                if key in found:
                    issues.add(
                        "error",
                        f'The header names the column "{key}" twice ("{found[key][1]}" and '
                        f'"{name}").',
                        table.header_row,
                        name,
                    )
                    return None
                found[key] = (position, name)
            else:
                issues.add(
                    "warning",
                    f'The column "{name}" is not used; it is ignored.',
                    table.header_row,
                    name,
                )
        missing = [c for c in COLUMNS if c not in found]
        if missing:
            names = ", ".join(f'"{c}"' for c in missing)
            issues.add(
                "error",
                f"The header has no {names} column{'s' if len(missing) > 1 else ''}. A wafer "
                "file needs the columns lot, wafer, x, y, result (one row per die).",
                table.header_row,
                None,
            )
            return None
        return found

    # Rows -------------------------------------------------------------------------------------

    def _rows(
        self, table: Table, columns: dict[str, tuple[int, str]], issues: _Issues
    ) -> dict[WaferKey, _Wafer]:
        wafers: dict[WaferKey, _Wafer] = {}
        codes_row: int | None = None
        for row in table.rows:
            lot = self._lot(row, columns["lot"], issues)
            wafer = self._number(
                row, columns["wafer"], issues, low=1, high=MAX_WAFER_NUMBER, what="a wafer number"
            )
            x = self._number(row, columns["x"], issues, low=0, high=None, what="a column (x)")
            y = self._number(row, columns["y"], issues, low=0, high=None, what="a row (y)")
            result = self._result(row, columns["result"], issues)
            if result is not None and result[1] and codes_row is None:
                codes_row = row.number
            if lot is None or wafer is None:
                continue
            record = wafers.setdefault((lot, wafer), _Wafer(first_row=row.number, dies={}))
            if x is None or y is None or result is None:
                continue
            first = record.dies.get((x, y))
            if first is not None:
                issues.add(
                    "error",
                    f"Row {row.number} repeats the die at x {x}, y {y} of lot {lot}, wafer "
                    f"{wafer} (first on row {first[1]}). List each die once.",
                    row.number,
                    None,
                )
                continue
            record.dies[(x, y)] = (result[0], row.number)
        if codes_row is not None:
            name = columns["result"][1]
            issues.add(
                "warning",
                f'The column "{name}" uses the WM-811K codes 1 and 2; they are read as pass (1) '
                "and fail (2).",
                codes_row,
                name,
            )
        return wafers

    @staticmethod
    def _value(row: Row, column: tuple[int, str], issues: _Issues, what: str) -> Cell:
        cell = row.cells[column[0]]
        if cell is None:
            issues.add(
                "error",
                f'Row {row.number}: the "{column[1]}" cell is empty; it needs {what}.',
                row.number,
                column[1],
            )
        return cell

    def _lot(self, row: Row, column: tuple[int, str], issues: _Issues) -> str | None:
        cell = self._value(row, column, issues, "the lot name")
        if cell is None:
            return None
        text: str | None
        if isinstance(cell, bool | datetime):
            text = None
        elif isinstance(cell, int | float):
            number = _integer(cell)  # a lot named by a number in a spreadsheet
            text = None if number is None else str(number)
        else:
            text = cell.strip()
        if text is None or len(text) > MAX_LOT_LENGTH or not LOT_PATTERN.match(text):
            issues.add(
                "error",
                f"Row {row.number}: the lot {_shown(cell)} is not a name of 1 to "
                f"{MAX_LOT_LENGTH} letters, digits, spaces or the signs _ . : -",
                row.number,
                column[1],
            )
            return None
        return text

    def _number(
        self,
        row: Row,
        column: tuple[int, str],
        issues: _Issues,
        *,
        low: int,
        high: int | None,
        what: str,
    ) -> int | None:
        cell = self._value(row, column, issues, what)
        if cell is None:
            return None
        number = _integer(cell)
        if number is None or number < low or (high is not None and number > high):
            limits = f"from {low} to {high:,}" if high is not None else f"of {low} or more"
            issues.add(
                "error",
                f"Row {row.number}: {_shown(cell)} is not {what}; it must be a whole number "
                f"{limits}.",
                row.number,
                column[1],
            )
            return None
        return number

    def _result(
        self, row: Row, column: tuple[int, str], issues: _Issues
    ) -> tuple[int, bool] | None:
        """(1 pass or 2 fail, whether a WM-811K code was used)."""
        cell = self._value(row, column, issues, "pass or fail")
        if cell is None:
            return None
        if isinstance(cell, str) and cell.strip().lower() in RESULT_WORDS:
            return RESULT_WORDS[cell.strip().lower()], False
        code = _integer(cell)
        if code in RESULT_CODES:
            return RESULT_CODES[code], True
        if code == 0:
            issues.add(
                "error",
                f"Row {row.number}: 0 means no die in WM-811K. Leave positions without a die "
                "out of the file; list only dies, as pass or fail.",
                row.number,
                column[1],
            )
            return None
        issues.add(
            "error",
            f"Row {row.number}: the result {_shown(cell)} is not pass or fail.",
            row.number,
            column[1],
        )
        return None

    # Wafers -----------------------------------------------------------------------------------

    @staticmethod
    def _wafer(
        key: WaferKey, record: _Wafer, columns: dict[str, tuple[int, str]], issues: _Issues
    ) -> WaferInput | None:
        lot, number = key
        if not record.dies:
            issues.add(
                "error",
                f"Lot {lot}, wafer {number} has no die that could be read: every row of it has "
                "a problem listed here.",
                record.first_row,
                None,
            )
            return None
        for axis, side, name in ((0, "x", "columns"), (1, "y", "rows")):
            far = max(record.dies, key=lambda p: p[axis])
            if far[axis] >= MAX_SIDE:
                issues.add(
                    "error",
                    f"Lot {lot}, wafer {number} is larger than {MAX_SIDE} x {MAX_SIDE}: {side} "
                    f"goes up to {far[axis]:,} (row {record.dies[far][1]}), and a map has at "
                    f"most {MAX_SIDE} {name}, numbered 0 to {MAX_SIDE - 1}.",
                    record.dies[far][1],
                    columns[side][1],
                )
                return None
        width = max(x for x, _ in record.dies) + 1
        height = max(y for _, y in record.dies) + 1
        grid = np.zeros((height, width), dtype=np.uint8)
        for (x, y), (value, _) in record.dies.items():
            grid[y, x] = value
        return WaferInput(
            lot=lot,
            wafer=number,
            map=WaferMap(
                height=height,
                width=width,
                cells=base64.b64encode(grid.tobytes()).decode("ascii"),
            ),
        )
