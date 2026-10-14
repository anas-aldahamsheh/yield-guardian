"""Write the SECOM bundle (``packages/contracts/ARTIFACTS.md``) and its manifest.

Every file except ``MANIFEST.json`` is byte-deterministic for a given input, code and
environment: JSON with fixed formatting, NPZ with fixed member timestamps, Parquet built
from an explicit Arrow schema. ``MANIFEST.json`` adds the creation time.

Two keys beyond the contract are written, because the contract's stated purpose needs
them (reported to the lead as a contract request):

- ``shap.npz`` ``base_values`` [units]: the expected value of the model that explained each
  row. Rows explained by rolling-origin fold models have their own expected value, so a
  single ``base_value`` cannot make every row add up to its raw score.
- ``fdc_model.npz`` ``impute_values`` [fdc_features]: the reference medians that replace
  missing readings before scaling; without them a new unit with a missing reading cannot
  be scored "with numpy only".
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from yg_common.io import save_npz, write_json
from yg_common.provenance import sha256_file, utc_now_iso

from yg_secom.fdc import FdcModel
from yg_secom.schemas import BUNDLE_FILES, TIMELINE_SCHEMA


def write_timeline(path: Path, frame: pd.DataFrame) -> None:
    """Write ``timeline.parquet`` with the exact contract schema, zstd-compressed."""
    columns = {}
    for field in TIMELINE_SCHEMA:
        values = frame[field.name]
        if field.name == "timestamp":
            columns[field.name] = pa.array(
                values.dt.tz_convert("UTC").to_numpy(dtype="datetime64[us]"),
                type=pa.timestamp("us"),
            ).cast(field.type)
        elif pa.types.is_string(field.type):
            columns[field.name] = pa.array(
                [
                    None if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)
                    for v in values
                ],
                type=pa.string(),
            )
        else:
            data = values.to_numpy()
            mask = pd.isna(values).to_numpy() if field.nullable else None
            if pa.types.is_floating(field.type):
                data = np.where(np.isnan(data.astype(np.float64)), 0.0, data).astype(np.float32)
            columns[field.name] = pa.array(data, type=field.type, mask=mask)
    table = pa.Table.from_pydict(columns, schema=TIMELINE_SCHEMA)
    pq.write_table(table, path, compression="zstd", use_dictionary=True, write_statistics=True)


def write_shap(
    path: Path,
    values: npt.NDArray[np.float32],
    base_value: float,
    base_values: npt.NDArray[np.float32],
    features: list[str],
) -> None:
    save_npz(
        path,
        {
            "values": values.astype(np.float32),
            "base_value": np.float64(base_value),
            "base_values": base_values.astype(np.float32),
            "features": np.array(features),
            "unit_ids": np.arange(values.shape[0], dtype=np.int64),
        },
    )


def write_fdc(
    directory: Path,
    model: FdcModel,
    contrib_t2: npt.NDArray[np.float64],
    contrib_spe: npt.NDArray[np.float64],
) -> None:
    features = np.array(model.features)
    save_npz(
        directory / "fdc.npz",
        {
            "contrib_t2": contrib_t2.astype(np.float32),
            "contrib_spe": contrib_spe.astype(np.float32),
            "features": features,
            "unit_ids": np.arange(contrib_t2.shape[0], dtype=np.int64),
        },
    )
    low, high = model.alphas
    save_npz(
        directory / "fdc_model.npz",
        {
            "center": model.center,
            "scale": model.scale,
            "impute_values": model.impute_values,
            "loadings": model.loadings,
            "eigenvalues": model.eigenvalues,
            "n_components": np.int64(model.n_components),
            "features": features,
            "t2_limit_99": np.float64(model.t2_limits[low]),
            "t2_limit_999": np.float64(model.t2_limits[high]),
            "spe_limit_99": np.float64(model.spe_limits[low]),
            "spe_limit_999": np.float64(model.spe_limits[high]),
            "reference_unit_ids": model.reference_unit_ids,
        },
    )


def write_model(path: Path, booster: lgb.Booster) -> None:
    path.write_text(booster.model_to_string(), encoding="utf-8")


def write_json_files(directory: Path, documents: Mapping[str, Any]) -> None:
    for name, content in documents.items():
        write_json(directory / name, content)


def write_manifest(
    directory: Path,
    *,
    version: str,
    git_commit: str,
    data: list[dict[str, str]],
    environment: dict[str, Any],
) -> dict[str, Any]:
    """Write ``MANIFEST.json`` with the SHA-256 and size of every other bundle file."""
    files = []
    for name in BUNDLE_FILES:
        if name == "MANIFEST.json":
            continue
        path = directory / name
        files.append({"path": name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    manifest = {
        "name": "secom",
        "version": version,
        "created_at": utc_now_iso(),
        "git_commit": git_commit,
        "data": data,
        "environment": {
            "python": environment["python"],
            "packages": {k: v for k, v in environment["packages"].items() if v is not None},
        },
        "files": files,
    }
    write_json(directory / "MANIFEST.json", manifest)
    return manifest
