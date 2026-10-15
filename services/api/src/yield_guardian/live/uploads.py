"""Uploaded files (PLAN_V2 §3.1): kind detection, the validation summary, templates (header only)
and real example files in the upload format.

Sensor file: ``unit_id, timestamp, S001 … S590, result``, one row per unit. Wafer file:
``lot, wafer, x, y, result``, one row per die, ``x`` the column and ``y`` the row counted from 0
at the map's top-left, positions not listed are no die. The parsers (``SensorFileParser``,
``WaferFileParser``) read these files; this module writes them the same way, so a downloaded
example uploads back to the same input. A CSV carries its source and licence in response
headers (a comment line would not parse back); a workbook also has an "About" sheet.
"""

import asyncio
import base64
import csv
import io
import re
import unicodedata
import zipfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePath
from random import Random
from typing import Literal, Protocol

from openpyxl import Workbook, load_workbook

from yield_guardian.contracts.runs import (
    MAX_DIES,
    MAX_UNITS,
    MAX_WAFERS,
    N_SENSORS,
    SensorUnitInput,
    UploadIssue,
    UploadKind,
    UploadSummary,
    WaferInput,
)
from yield_guardian.contracts.services import NotReadyError, ServiceError
from yield_guardian.live.protocols import (
    Parsed,
    SensorEngine,
    SensorFileParser,
    WaferEngine,
    WaferFileParser,
)
from yield_guardian.live.tabular import (
    CSV_SUFFIXES,
    MAX_BYTES,
    XLSX_SUFFIXES,
    TableError,
    read_table,
)
from yield_guardian.services.runs import InputError, RunInput, count_dies

FileFormat = Literal["csv", "xlsx"]
SENSOR_HEADER = ["unit_id", "timestamp", *(f"S{i:03d}" for i in range(1, N_SENSORS + 1)), "result"]
WAFER_HEADER = ["lot", "wafer", "x", "y", "result"]
MAX_ISSUES = 200
EXAMPLE_SEED = 0
MEDIA_TYPES: dict[FileFormat, str] = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
SHEETS: dict[UploadKind, str] = {"sensors": "Units", "wafers": "Dies"}
NOUNS: dict[UploadKind, str] = {"sensors": "units", "wafers": "wafers"}
_SENSOR_COLUMN = re.compile(r"^s\d{3}$")
_DOI = re.compile(r"https://doi\.org/\S+[0-9A-Za-z]")


@dataclass(frozen=True, slots=True)
class Source:
    """A dataset's attribution: the full ATTRIBUTION.md text and its one-line citation."""

    text: str
    citation: str
    licence: str

    @property
    def doi(self) -> str | None:
        found = _DOI.search(self.citation)
        return found.group(0) if found else None


def _field(markdown: str, name: str) -> str:
    """The text of a ``- **Name:** ...`` item of an ATTRIBUTION.md, continuation lines joined."""
    lines = markdown.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"- **{name}:**"):
            parts = [line.split(":**", 1)[1].strip()]
            for more in lines[i + 1 :]:
                if not more.startswith("  ") or more.lstrip().startswith("- "):
                    break
                parts.append(more.strip())
            return re.sub(r"[<>]", "", " ".join(parts)).strip()
    return ""


def read_source(text: str) -> Source:
    """A Source from the text of an ATTRIBUTION.md; ValueError without a citation line."""
    text = text.strip()
    citation = _field(text, "Citation")
    if not citation:
        raise ValueError("the attribution has no citation line")
    return Source(text=text, citation=citation, licence=_field(text, "Licence"))


@dataclass(frozen=True, slots=True)
class Attribution:
    """Where the example files come from: data/secom/ATTRIBUTION.md and the wafer-map bundle's
    demo/ATTRIBUTION.md."""

    secom: Source | None
    wafermap: Source | None

    @classmethod
    def load(cls, secom: Path | None, wafermap_text: str | None) -> "Attribution":
        found = secom.read_text(encoding="utf-8") if secom is not None and secom.is_file() else None
        return cls(
            secom=read_source(found) if found else None,
            wafermap=read_source(wafermap_text) if wafermap_text else None,
        )

    def of(self, kind: UploadKind) -> Source | None:
        return self.secom if kind == "sensors" else self.wafermap


@dataclass(frozen=True, slots=True)
class DownloadFile:
    content: bytes
    filename: str
    media_type: str
    headers: dict[str, str]


def _ascii(text: str) -> str:
    """A header value: ASCII on one line."""
    flat = unicodedata.normalize("NFKD", " ".join(text.split()))
    return flat.encode("ascii", "ignore").decode()


# -- reading ---------------------------------------------------------------------------------


def _first_row(rows: Iterable[Sequence[object]]) -> list[str]:
    for row in rows:
        cells = ["" if c is None else str(c).strip() for c in row]
        if any(cells):
            return cells
    return []


def peek_header(data: bytes, filename: str) -> list[str]:
    """The header row only, without reading the whole file; TableError when unreadable."""
    suffix = PurePath(filename).suffix.lower()
    try:
        if suffix in CSV_SUFFIXES:
            sample = data[:65536].decode("utf-8-sig", errors="strict")
            try:
                dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(
                    sample, delimiters=",;\t"
                )
            except csv.Error:
                dialect = csv.excel
            return _first_row(csv.reader(io.StringIO(sample, newline=""), dialect))
        if suffix in XLSX_SUFFIXES:
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            try:
                return _first_row(workbook.worksheets[0].iter_rows(values_only=True))
            finally:
                workbook.close()
    except (UnicodeDecodeError, csv.Error, zipfile.BadZipFile, OSError, KeyError, IndexError):
        pass
    except Exception:  # openpyxl raises many types for damaged files  # noqa: S110
        pass
    return read_table(data, filename).header  # raises TableError with the plain reason


def detect_kind(header: Sequence[str]) -> UploadKind | None:
    names = {h.strip().lower() for h in header}
    if {"lot", "wafer", "x", "y"} <= names:
        return "wafers"
    if "unit_id" in names or any(_SENSOR_COLUMN.match(n) for n in names):
        return "sensors"
    return None


def _issue(message: str) -> UploadIssue:
    return UploadIssue(severity="error", row=None, column=None, message=message)


def summary_of(
    kind: UploadKind, parsed: Parsed[SensorUnitInput] | Parsed[WaferInput]
) -> tuple[RunInput, list[UploadIssue], bool]:
    """The parsed items as run input, the issues to show (errors first, at most MAX_ISSUES) and
    whether the file can run."""
    items = list(parsed.items)
    data = (
        RunInput(units=[i for i in items if isinstance(i, SensorUnitInput)])
        if kind == "sensors"
        else RunInput(wafers=[i for i in items if isinstance(i, WaferInput)])
    )
    issues = list(parsed.issues)
    count, limit = (
        (len(data.units), MAX_UNITS) if kind == "sensors" else (len(data.wafers), MAX_WAFERS)
    )
    many = NOUNS[kind]
    if count > limit:
        issues.append(
            _issue(f"The file has {count:,} {many}; a run takes at most {limit:,}. Split the file.")
        )
    dies = count_dies(data.wafers)
    if dies > MAX_DIES:
        issues.append(
            _issue(f"This file has {dies:,} dies; the limit is {MAX_DIES:,}. Split the file.")
        )
    if count == 0 and not any(i.severity == "error" for i in issues):
        issues.append(_issue(f"The file has no {many} to run."))
    issues.sort(key=lambda i: i.severity != "error")
    if len(issues) > MAX_ISSUES:
        left = len(issues) - (MAX_ISSUES - 1)
        issues = [
            *issues[: MAX_ISSUES - 1],
            UploadIssue(
                severity=issues[MAX_ISSUES - 1].severity,
                row=None,
                column=None,
                message=f"{left:,} more problems are not listed. Fix these and upload again.",
            ),
        ]
    runnable = count > 0 and not any(i.severity == "error" for i in issues)
    return data, issues, runnable


# -- writing ---------------------------------------------------------------------------------

Cell = str | int | float | datetime | None


def _naive(at: datetime | None) -> datetime | None:
    if at is None or at.tzinfo is None:
        return at
    return at.astimezone(UTC).replace(tzinfo=None)


def sensor_rows(units: Sequence[SensorUnitInput], *, text_times: bool) -> list[list[Cell]]:
    rows: list[list[Cell]] = []
    for unit in units:
        at = _naive(unit.timestamp)
        when: Cell = at.isoformat() if at is not None and text_times else at
        rows.append([unit.unit_id, when, *unit.readings, unit.result])
    return rows


def wafer_rows(wafers: Sequence[WaferInput]) -> list[list[Cell]]:
    rows: list[list[Cell]] = []
    for wafer in wafers:
        cells = base64.b64decode(wafer.map.cells)
        width = wafer.map.width
        for position, value in enumerate(cells):
            if value in (1, 2):
                y, x = divmod(position, width)
                rows.append([wafer.lot, wafer.wafer, x, y, "pass" if value == 1 else "fail"])
    return rows


def write_csv(header: Sequence[str], rows: Iterable[Sequence[Cell]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if c is None else repr(c) if isinstance(c, float) else c for c in row])
    return buffer.getvalue().encode("utf-8")


def write_xlsx(
    sheet: str, header: Sequence[str], rows: Iterable[Sequence[Cell]], about: Sequence[str]
) -> bytes:
    workbook = Workbook(write_only=True)
    data = workbook.create_sheet(sheet)
    data.append(list(header))
    for row in rows:
        data.append(list(row))
    if about:
        notes = workbook.create_sheet("About")
        for line in about:
            notes.append([line])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def template(kind: UploadKind, fmt: FileFormat) -> DownloadFile:
    header = SENSOR_HEADER if kind == "sensors" else WAFER_HEADER
    content = write_csv(header, []) if fmt == "csv" else write_xlsx(SHEETS[kind], header, [], [])
    return DownloadFile(
        content=content,
        filename=f"yield-guardian-{kind}-template.{fmt}",
        media_type=MEDIA_TYPES[fmt],
        headers={},
    )


class UnreadableFileError(ServiceError):
    """The file cannot be read as a table at all (not CSV or XLSX, damaged, not UTF-8)."""

    code = "validation_error"
    status = 422
    title = "File not readable"


class FileTooLargeError(ServiceError):
    code = "bad_request"
    status = 413
    title = "File too large"


def too_large(size: int) -> FileTooLargeError:
    return FileTooLargeError(
        f"The file is {size / 1_048_576:.1f} MB; the limit is {MAX_BYTES // 1_048_576} MB. "
        "Split it into smaller files."
    )


class UploadStore(Protocol):
    """Where uploads are kept for 24 h (``services.runs.DbRunStore``)."""

    async def create_upload(
        self,
        *,
        kind: UploadKind,
        filename: str,
        data: RunInput,
        summary: Callable[[str, datetime], UploadSummary],
    ) -> UploadSummary: ...

    async def get_upload(self, upload_id: str) -> tuple[UploadSummary, RunInput]: ...


def clean_filename(name: str | None) -> str:
    """The file's own name, without any folder, printable, at most 255 characters."""
    base = PurePath((name or "").replace("\\", "/")).name.strip()
    base = "".join(c for c in base if c.isprintable())
    return base[-255:] or "upload"


def example_about(rule: str, source: Source | None) -> list[str]:
    lines = ["Real data in the Yield Guardian upload format.", rule]
    if source is not None:
        lines += [f"Source: {source.citation}", f"Licence: {source.licence}", ""]
        lines += source.text.splitlines()
    return lines


def example_headers(rule: str, source: Source | None) -> dict[str, str]:
    headers = {"X-Example-Rule": _ascii(rule)}
    if source is not None:
        headers["X-Data-Attribution"] = _ascii(source.citation)
        if source.doi:
            headers["Link"] = f'<{source.doi}>; rel="cite-as"'
    return headers


class UploadService:
    """POST /uploads (parse, validate, keep for 24 h), the templates and the real example files;
    also the UploadSource a run reads its upload from."""

    def __init__(
        self,
        store: UploadStore,
        *,
        sensor_file: SensorFileParser | None = None,
        wafer_file: WaferFileParser | None = None,
        sensors: SensorEngine | None = None,
        wafers: WaferEngine | None = None,
        attribution: Attribution | None = None,
    ) -> None:
        self.store = store
        self.sensor_file = sensor_file
        self.wafer_file = wafer_file
        self.sensors = sensors
        self.wafers = wafers
        self.attribution = attribution or Attribution(secom=None, wafermap=None)
        self._examples: dict[tuple[UploadKind, FileFormat], DownloadFile] = {}
        self._lock = asyncio.Lock()

    async def upload(
        self, data: bytes, filename: str | None, kind: UploadKind | None = None
    ) -> UploadSummary:
        """Parse and validate a file and keep it for 24 h. Only an unreadable file is refused
        (422); what is wrong inside it comes back as issues, with runnable false."""
        name = clean_filename(filename)
        if len(data) > MAX_BYTES:
            raise too_large(len(data))
        try:
            header = await asyncio.to_thread(peek_header, data, name)
        except TableError as error:
            raise UnreadableFileError(error.message) from error
        found = kind or detect_kind(header)
        if found is None:
            raise UnreadableFileError(
                "The first row is not a sensor header (unit_id, timestamp, S001 … S590, result) "
                "or a wafer header (lot, wafer, x, y, result). Start from a template."
            )
        parsed: Parsed[SensorUnitInput] | Parsed[WaferInput]
        try:
            if found == "sensors":
                if self.sensor_file is None:
                    raise NotReadyError(
                        "Sensor files cannot be read here: the SECOM bundle is not loaded."
                    )
                parsed = await asyncio.to_thread(self.sensor_file.parse, data, name)
            else:
                if self.wafer_file is None:
                    raise NotReadyError(
                        "Wafer files cannot be read here: the wafer-map bundle is not loaded."
                    )
                parsed = await asyncio.to_thread(self.wafer_file.parse, data, name)
        except TableError as error:
            raise UnreadableFileError(error.message) from error
        items, issues, runnable = summary_of(found, parsed)
        missing = sum(r is None for u in items.units for r in u.readings)

        def summary(upload_id: str, expires_at: datetime) -> UploadSummary:
            return UploadSummary(
                upload_id=upload_id,
                kind=found,
                filename=name,
                units=len(items.units),
                wafers=len(items.wafers),
                lots=len({w.lot for w in items.wafers}),
                missing_readings=missing,
                issues=issues,
                runnable=runnable,
                expires_at=expires_at,
            )

        return await self.store.create_upload(
            kind=found, filename=name, data=items, summary=summary
        )

    async def runnable_upload(self, upload_id: str) -> tuple[str, RunInput]:
        summary, data = await self.store.get_upload(upload_id)
        if not summary.runnable:
            errors = sum(i.severity == "error" for i in summary.issues)
            raise InputError(
                f"The file {summary.filename} has {errors:,} problem{'s' if errors != 1 else ''} "
                "to fix before it can run. Fix them and upload it again."
            )
        return summary.filename, data

    async def example(self, kind: UploadKind, fmt: FileFormat) -> DownloadFile:
        """Real data in the upload format: a window of real SECOM units the risk model never saw,
        or every die of one real WM-811K demo lot, picked by the engine's own rule with a fixed
        seed, so the file is the same on every request."""
        async with self._lock:
            cached = self._examples.get((kind, fmt))
            if cached is None:
                cached = await asyncio.to_thread(self._build_example, kind, fmt)
                self._examples[(kind, fmt)] = cached
        return cached

    def _build_example(self, kind: UploadKind, fmt: FileFormat) -> DownloadFile:
        rng = Random(EXAMPLE_SEED)  # noqa: S311 - a fixed pick of real data, not a secret
        header: list[str]
        rows: list[list[Cell]]
        if kind == "sensors":
            if self.sensors is None:
                raise NotReadyError("The SECOM model bundle is not loaded on this server.")
            units = self.sensors.sample(rng)
            header, rule = SENSOR_HEADER, units.rule
            rows = sensor_rows(units.items, text_times=fmt == "csv")
        else:
            if self.wafers is None:
                raise NotReadyError("The wafer-map model bundle is not loaded on this server.")
            lot = self.wafers.sample(rng)
            header, rule = WAFER_HEADER, lot.rule
            rows = wafer_rows(lot.items)
        source = self.attribution.of(kind)
        content = (
            write_csv(header, rows)
            if fmt == "csv"
            else write_xlsx(SHEETS[kind], header, rows, example_about(rule, source))
        )
        return DownloadFile(
            content=content,
            filename=f"yield-guardian-{kind}-example.{fmt}",
            media_type=MEDIA_TYPES[fmt],
            headers=example_headers(rule, source),
        )
