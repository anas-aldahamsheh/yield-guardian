"""Load and validate the raw SECOM files.

Source files (UCI Machine Learning Repository, dataset 179):

- ``secom.data``: one production unit per line, 590 space-separated readings, ``NaN`` for
  a missing reading.
- ``secom_labels.data``: one line per unit, in the same order: the pass/fail result
  (``-1`` = pass, ``1`` = fail) and a quoted timestamp ``"dd/mm/yyyy HH:MM:SS"``.

Nothing is dropped or repaired here. Every structural problem stops the run with an
explicit error; every oddity that is not an error (duplicated rows, tied timestamps,
units with no readings) is reported in ``SecomData.report`` and in ``eda.json``.

Identifiers follow ``packages/contracts/ARTIFACTS.md``: row ``r`` (0-based) is unit ``r``;
column ``i`` (0-based) is sensor ``S{i+1:03d}``.

The timestamps carry no time zone in the source. They are stored as UTC *without any
conversion*, so the wall-clock values are exactly those of the source file.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import pandera.pandas as pa
from yg_common.provenance import sha256_file

FEATURES_FILE = "secom.data"
LABELS_FILE = "secom_labels.data"
NAMES_FILE = "secom.names"
DAY_FIRST = "%d/%m/%Y %H:%M:%S"
MONTH_FIRST = "%m/%d/%Y %H:%M:%S"
_LABEL_LINE = re.compile(r'^\s*(?P<label>[-+]?\d+)\s+"(?P<timestamp>[^"]*)"\s*$')


class DataValidationError(ValueError):
    """The source data do not match what the pipeline expects."""


def sensor_ids(n_features: int) -> list[str]:
    """Sensor identifiers ``S001`` ... in column order."""
    width = max(3, len(str(n_features)))
    return [f"S{i + 1:0{width}d}" for i in range(n_features)]


@dataclass(frozen=True)
class SecomData:
    """Validated SECOM data, in the file's row order (unit id = row index)."""

    features: pd.DataFrame
    labels: npt.NDArray[np.int8]
    timestamps: pd.Series
    files: dict[str, Path]
    file_sha256: dict[str, str]
    report: dict[str, Any] = field(default_factory=dict)

    @property
    def n_units(self) -> int:
        return int(self.features.shape[0])

    @property
    def n_features(self) -> int:
        return int(self.features.shape[1])

    @property
    def sensors(self) -> list[str]:
        return [str(c) for c in self.features.columns]

    @property
    def unit_ids(self) -> npt.NDArray[np.int64]:
        return np.arange(self.n_units, dtype=np.int64)


def _features_schema(columns: list[str], n_units: int) -> pa.DataFrameSchema:
    not_infinite = pa.Check(lambda s: ~np.isinf(s), error="infinite reading")
    return pa.DataFrameSchema(
        {c: pa.Column(np.float64, checks=not_infinite, nullable=True) for c in columns},
        index=pa.Index(
            np.int64,
            checks=pa.Check(
                lambda i: bool(np.array_equal(i, np.arange(len(i)))),
                error="unit ids must be 0..n-1 in file order",
            ),
            name="unit_id",
        ),
        strict=True,
        ordered=True,
        checks=pa.Check(lambda df: df.shape[0] == n_units, error=f"expected {n_units} units"),
        name="secom_features",
    )


def _labels_schema(n_units: int) -> pa.DataFrameSchema:
    return pa.DataFrameSchema(
        {
            "label_raw": pa.Column(np.int64, pa.Check.isin([-1, 1])),
            "timestamp": pa.Column(
                checks=[
                    pa.Check(
                        lambda s: pd.api.types.is_datetime64_dtype(s) and s.dt.tz is None,
                        error="timestamps must be parsed, time-zone naive datetimes",
                    ),
                ],
                nullable=False,
            ),
        },
        strict=True,
        checks=pa.Check(lambda df: df.shape[0] == n_units, error=f"expected {n_units} units"),
        name="secom_labels",
    )


def read_features(path: Path, n_features: int) -> pd.DataFrame:
    """Read ``secom.data`` strictly: only numbers and the token ``NaN`` are accepted."""
    try:
        frame = pd.read_csv(
            path,
            sep=r"\s+",
            header=None,
            dtype=np.float64,
            na_values=["NaN"],
            keep_default_na=False,
            engine="c",
        )
    except ValueError as error:
        raise DataValidationError(f"{path.name}: unreadable value ({error})") from error
    if frame.shape[1] != n_features:
        raise DataValidationError(
            f"{path.name}: expected {n_features} columns, found {frame.shape[1]}"
        )
    frame.columns = pd.Index(sensor_ids(n_features))
    frame.index = pd.RangeIndex(frame.shape[0], name="unit_id")
    frame.index = frame.index.astype(np.int64)
    return frame


def read_labels(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read ``secom_labels.data`` strictly and report how the timestamps were parsed."""
    text = path.read_bytes().decode("ascii")
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    labels: list[int] = []
    stamps: list[str] = []
    for number, line in enumerate(lines, start=1):
        match = _LABEL_LINE.match(line)
        if match is None:
            raise DataValidationError(f"{path.name} line {number}: unexpected format {line!r}")
        labels.append(int(match["label"]))
        stamps.append(match["timestamp"])
    raw = pd.Series(stamps, dtype="str")
    try:
        parsed = pd.to_datetime(raw, format=DAY_FIRST, exact=True)
    except ValueError as error:
        raise DataValidationError(
            f"{path.name}: timestamps do not all match {DAY_FIRST!r} ({error})"
        ) from error
    month_first = pd.to_datetime(raw, format=MONTH_FIRST, exact=True, errors="coerce")
    day_field = raw.str.slice(0, 2).astype(np.int64)
    parsing = {
        "format": DAY_FIRST,
        "format_note": "day/month/year, 24-hour clock; the source has no time zone",
        "lines": len(lines),
        "parsed_day_first": int(parsed.notna().sum()),
        "also_valid_month_first": int(month_first.notna().sum()),
        "day_field_above_12": int((day_field > 12).sum()),
        "line_endings": "CRLF" if "\r\n" in text else "LF",
        "example": stamps[0] if stamps else None,
    }
    frame = pd.DataFrame({"label_raw": np.asarray(labels, dtype=np.int64), "timestamp": parsed})
    frame.index = pd.RangeIndex(frame.shape[0], name="unit_id").astype(np.int64)
    return frame, parsing


def _find(data_dir: Path, name: str) -> Path:
    path = data_dir / name
    if not path.is_file():
        raise DataValidationError(f"missing source file: {path}")
    return path


def verify_manifest(
    file_sha256: dict[str, str], manifest_path: Path, dataset: str = "secom"
) -> list[dict[str, Any]]:
    """Check each file's SHA-256 against ``data/manifest.json`` (matched by file name).

    Returns one record per file with the manifest path and digest. Raises when the
    manifest, the dataset entry or a file entry is missing, or when a digest differs.
    """
    if not manifest_path.is_file():
        raise DataValidationError(f"data manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest.get(dataset)
    if not isinstance(entry, dict) or "files" not in entry:
        raise DataValidationError(f"{manifest_path.name} has no '{dataset}' entry with files")
    by_name: dict[str, dict[str, Any]] = {}
    for item in entry["files"]:
        by_name.setdefault(Path(str(item["path"])).name, item)
    records = []
    for name, digest in sorted(file_sha256.items()):
        item = by_name.get(name)
        if item is None:
            raise DataValidationError(f"{name} is not listed in {manifest_path.name}")
        if str(item["sha256"]).lower() != digest:
            raise DataValidationError(
                f"{name}: SHA-256 {digest} differs from the manifest ({item['sha256']})"
            )
        records.append({"file": name, "manifest_path": item["path"], "sha256": digest})
    return records


def _anomalies(features: pd.DataFrame, labels: pd.DataFrame) -> dict[str, Any]:
    ts = labels["timestamp"]
    all_missing_units = np.flatnonzero(features.isna().all(axis=1).to_numpy())
    dup_rows = features.duplicated(keep=False).to_numpy()
    tie_sizes = ts.value_counts()
    tie_sizes = tie_sizes[tie_sizes > 1]
    diffs = ts.diff().dt.total_seconds().to_numpy()[1:]
    return {
        "units_with_no_readings": all_missing_units.tolist(),
        "units_in_duplicated_feature_rows": np.flatnonzero(dup_rows).tolist(),
        "timestamp_tie_groups": int(tie_sizes.size),
        "units_sharing_a_timestamp": int(tie_sizes.sum()),
        "largest_tie_group": int(tie_sizes.max()) if tie_sizes.size else 1,
        "file_order_is_chronological": bool(ts.is_monotonic_increasing),
        "file_order_backward_steps": int(np.sum(diffs < 0)),
        "largest_backward_step_seconds": float(-diffs.min()) if np.any(diffs < 0) else 0.0,
    }


def load_secom(
    data_dir: Path,
    expected_units: int = 1567,
    expected_features: int = 590,
) -> SecomData:
    """Read, validate and return the SECOM data. Raises ``DataValidationError``."""
    files = {
        FEATURES_FILE: _find(data_dir, FEATURES_FILE),
        LABELS_FILE: _find(data_dir, LABELS_FILE),
    }
    names = data_dir / NAMES_FILE
    if names.is_file():
        files[NAMES_FILE] = names
    digests = {name: sha256_file(path) for name, path in files.items()}

    features = read_features(files[FEATURES_FILE], expected_features)
    labels, parsing = read_labels(files[LABELS_FILE])
    try:
        _features_schema(sensor_ids(expected_features), expected_units).validate(features)
        _labels_schema(expected_units).validate(labels)
    except (pa.errors.SchemaError, pa.errors.SchemaErrors) as error:
        raise DataValidationError(f"schema validation failed: {error}") from error
    if parsing["parsed_day_first"] != expected_units:
        raise DataValidationError("not every timestamp could be parsed")

    report = {
        "files": {name: {"sha256": digest} for name, digest in digests.items()},
        "timestamp_parsing": parsing,
        "anomalies": _anomalies(features, labels),
        "label_encoding": {"source": {"fail": 1, "pass": -1}, "bundle": {"fail": 1, "pass": 0}},
        "time_zone": "none in source; stored as UTC without conversion",
    }
    timestamps = labels["timestamp"].dt.tz_localize("UTC").rename("timestamp")
    y = (labels["label_raw"].to_numpy() == 1).astype(np.int8)
    return SecomData(
        features=features,
        labels=y,
        timestamps=timestamps,
        files=files,
        file_sha256=digests,
        report=report,
    )
