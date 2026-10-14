"""A SECOM bundle in the ARTIFACTS.md v1 layout, for tests of the loader and the services.

Unit IDs, timestamps, final-test labels and sensor readings are the real SECOM files. Every model
output in this bundle (risk, T², SPE, SHAP, contributions, groups, health, metrics) is a synthetic
test input for the API code only; nothing computed from it is reported anywhere.
"""

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from yield_guardian.bundles.secom import SourceData, sensor_id

REPO = Path(__file__).resolve().parents[4]
DATA = REPO / "data" / "secom"
FIXTURES = REPO / "packages" / "contracts" / "fixtures"

WARM_UP = 100
REFERENCE = 200
EWMA_RUN = range(900, 906)
LIMITS = (11.0, 16.0, 18.0, 25.0)
SHAP_SENSORS = [sensor_id(c) for c in range(0, 60, 2)]
FDC_SENSORS = [sensor_id(c) for c in range(100, 120)]
GROUPS = [["S001", "S003"], ["S005", "S007", "S009"], ["S011"]]

TIMELINE_SCHEMA = pa.schema(
    [
        ("unit_id", pa.int32()),
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("label", pa.int8()),
        ("block", pa.string()),
        ("risk", pa.float32()),
        ("risk_source", pa.string()),
        ("risk_band", pa.string()),
        ("t2", pa.float32()),
        ("spe", pa.float32()),
        ("t2_limit_99", pa.float32()),
        ("t2_limit_999", pa.float32()),
        ("spe_limit_99", pa.float32()),
        ("spe_limit_999", pa.float32()),
        ("fdc_alarm", pa.string()),
        ("fdc_period", pa.string()),
        ("ewma_alarm", pa.bool_()),
        ("cusum_alarm", pa.bool_()),
    ]
)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def write_manifest(directory: Path, version: str) -> None:
    files = []
    for path in sorted(p for p in directory.iterdir() if p.name != "MANIFEST.json"):
        data = path.read_bytes()
        files.append(
            {"path": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        )
    _write_json(
        directory / "MANIFEST.json",
        {
            "name": "secom",
            "version": version,
            "created_at": "2026-10-14T12:00:00+00:00",
            "git_commit": "0" * 40,
            "data": [{"path": "data/secom/secom.data", "sha256": "0" * 64}],
            "environment": {"python": "3.13", "packages": {}},
            "files": files,
        },
    )


def build_secom_bundle(root: Path, *, version: str = "v1", seed: int = 7) -> Path:
    """Write the bundle to root/secom/<version>/ and return that folder."""
    source = SourceData.load(DATA)
    n = len(source.timestamps)
    rng = np.random.default_rng(seed)
    order = sorted(range(n), key=lambda u: (source.timestamps[u], u))
    directory = root / "secom" / version
    directory.mkdir(parents=True)

    risk = rng.beta(1.2, 12.0, n)
    t2 = rng.chisquare(5, n)
    spe = rng.chisquare(10, n)
    rows: dict[str, list[Any]] = {name: [] for name in TIMELINE_SCHEMA.names}
    for seq, unit in enumerate(order):
        block = "train" if seq < 0.6 * n else "validation" if seq < 0.8 * n else "test"
        warm = seq < WARM_UP
        r = None if warm else float(risk[seq])
        band = None if r is None else "high" if r >= 0.25 else "elevated" if r >= 0.15 else "low"
        level = (
            "alarm"
            if t2[seq] > LIMITS[1] or spe[seq] > LIMITS[3]
            else "warning"
            if t2[seq] > LIMITS[0] or spe[seq] > LIMITS[2]
            else "none"
        )
        values = {
            "unit_id": unit,
            "timestamp": source.timestamps[unit],
            "label": int(source.failed[unit]),
            "block": block,
            "risk": r,
            "risk_source": None if warm else "oof" if block == "train" else block,
            "risk_band": band,
            "t2": float(t2[seq]),
            "spe": float(spe[seq]),
            "t2_limit_99": LIMITS[0],
            "t2_limit_999": LIMITS[1],
            "spe_limit_99": LIMITS[2],
            "spe_limit_999": LIMITS[3],
            "fdc_alarm": level,
            "fdc_period": "reference" if seq < REFERENCE else "monitoring",
            "ewma_alarm": seq in EWMA_RUN,
            "cusum_alarm": seq == 950,
        }
        for name, value in values.items():
            rows[name].append(value)
    pq.write_table(
        pa.Table.from_pydict(rows, schema=TIMELINE_SCHEMA),
        directory / "timeline.parquet",
        compression="zstd",
    )

    features = [*SHAP_SENSORS, "S060_missing"]
    shap = rng.normal(0.0, 0.3, (n, len(features))).astype(np.float32)
    for unit in order[:WARM_UP]:
        shap[unit] = np.nan
    np.savez(
        directory / "shap.npz",
        values=shap,
        base_value=np.float64(-2.8),
        base_values=np.full(n, -2.8, dtype=np.float32),
        features=np.array(features),
        unit_ids=np.arange(n),
    )
    np.savez(
        directory / "fdc.npz",
        contrib_t2=rng.normal(0.2, 0.5, (n, len(FDC_SENSORS))).astype(np.float32),
        contrib_spe=rng.chisquare(1, (n, len(FDC_SENSORS))).astype(np.float32),
        features=np.array(FDC_SENSORS),
        unit_ids=np.arange(n),
    )
    p = len(FDC_SENSORS)
    np.savez(
        directory / "fdc_model.npz",
        center=np.zeros(p),
        scale=np.ones(p),
        loadings=np.eye(p)[:, :3],
        eigenvalues=np.linspace(3.0, 0.1, p),
        n_components=np.int64(3),
        features=np.array(FDC_SENSORS),
        impute_values=np.linspace(1.0, 2.0, p),
        t2_limit_99=np.float64(LIMITS[0]),
        t2_limit_999=np.float64(LIMITS[1]),
        spe_limit_99=np.float64(LIMITS[2]),
        spe_limit_999=np.float64(LIMITS[3]),
        reference_unit_ids=np.array(order[:REFERENCE]),
    )

    groups_fixture = _fixture("get_sensor_groups.json")
    _write_json(
        directory / "groups.json",
        {
            "method": groups_fixture["method"],
            "groups": [
                {
                    "group_id": f"G{i + 1:02d}",
                    "sensors": sensors,
                    "representative": sensors[0],
                    "importance": round(0.3 - 0.1 * i, 3),
                    "stability": [0.95, 0.6, 0.8][i],
                    "p_value": [0.004, 0.2, 0.01][i],
                    "q_value": [0.012, 0.3, 0.015][i],
                    "significant": i != 1,
                    "univariate": [
                        {
                            "sensor": s,
                            "mann_whitney_p": None if s == "S011" else 0.01,
                            "q_value": None if s == "S011" else 0.02,
                            "direction": "not_tested" if s == "S011" else "higher_in_failures",
                        }
                        for s in sensors
                    ],
                }
                for i, sensors in enumerate(GROUPS)
            ],
        },
    )

    start = source.timestamps[order[0]]
    windows: list[dict[str, Any]] = []
    for w in range(14):
        lo, hi = start + timedelta(weeks=w), start + timedelta(weeks=w + 1)
        units = [u for u in order if lo <= source.timestamps[u] < hi]
        if units:
            windows.append(
                {
                    "window_id": len(windows),
                    "start": lo.isoformat(),
                    "end": hi.isoformat(),
                    "unit_ids": units,
                }
            )
    jump_units = [order[10], order[1500]]
    _write_json(
        directory / "health.json",
        {
            "rules": [
                "dead: constant or never measured",
                "watch: a jump beyond the test threshold",
            ],
            "windows": windows,
            "sensors": [
                {
                    "sensor": sensor_id(c),
                    "status": "watch" if c == 0 else "ok",
                    "reasons": ["jump beyond the test threshold"] if c == 0 else [],
                    "missing_rate": 0.01,
                    "missing_by_window": [0.01] * len(windows),
                    "flatline_windows": [],
                    "stuck_value": None,
                    "jump_unit_ids": jump_units if c == 0 else [],
                    "out_of_reference_rate": 0.02,
                    "missing_vs_failure": {"odds_ratio": 1.1, "p_value": 0.5, "q_value": 0.9},
                }
                for c in range(590)
            ],
        },
    )
    _write_json(directory / "operating_points.json", _fixture("get_operating_points.json"))
    report = _fixture("get_secom_metrics.json")
    report.pop("bundle")
    _write_json(
        directory / "metrics.json",
        {
            "report": report,
            "fdc_reference": {
                "start": source.timestamps[order[0]].isoformat(),
                "end": source.timestamps[order[REFERENCE - 1]].isoformat(),
                "units": REFERENCE,
                "stationarity": "test input",
            },
            "fdc_explained_variance": 0.42,
            "methods": {
                "explanation": "test input",
                "fdc": "test input",
                "contributions": "test input",
            },
            "split": {},
            "run": {},
        },
    )
    _write_json(directory / "calibrator.json", {"method": "platt", "a": -1.0, "b": 0.0})
    _write_json(
        directory / "preprocess.json",
        {"model_features": features, "dropped": [], "missingness_indicators": ["S060"]},
    )
    _write_json(directory / "eda.json", {})
    (directory / "model.txt").write_text("test input\n", encoding="utf-8")
    (directory / "model_card.md").write_text("# Test bundle\n", encoding="utf-8")
    write_manifest(directory, version)
    return directory
