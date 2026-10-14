"""End-to-end smoke run of the pipeline on SYNTHETIC data, bundle schema validation,
the API report schema, and run-to-run determinism.

The synthetic bundle is written to a temporary folder and never published. A test at the
end validates the real bundle too, when one has been built in ``artifacts/secom/v1``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
from yg_common.io import load_npz
from yg_common.provenance import sha256_file

from yg_secom.config import PipelineConfig
from yg_secom.pipeline import run
from yg_secom.schemas import BUNDLE_FILES, BundleError, report_problems, validate_bundle

REPO = Path(__file__).resolve().parents[3]
OPENAPI = REPO / "packages" / "contracts" / "openapi.json"
REAL_BUNDLE = REPO / "artifacts" / "secom" / "v1"

SMOKE = {
    "expected_units": 400,
    "expected_features": 30,
    "min_block_failures": 5,
    "cv_folds": 3,
    "cv_min_fold_failures": 2,
    "optuna_trials": 3,
    "logreg_c_grid": [0.01, 1.0],
    "brf_n_estimators": 25,
    "bootstrap_resamples": 60,
    "stability_refits": 4,
    "stability_top_k": 5,
    "permutations": 9,
    "fdc_parallel_iterations": 10,
    "n_jobs": 1,
    "require_data_manifest": False,
    "mlflow": False,
    "notes": ["SYNTHETIC smoke run (tests/test_end_to_end.py); never published"],
}


def _run(synthetic_dir: Path, root: Path) -> tuple[dict[str, Any], Path]:
    out = root / "bundle"
    metrics = run(
        PipelineConfig().with_overrides(SMOKE),
        synthetic_dir,
        out,
        reports_dir=root / "reports",
        model_card_path=root / "model_card.md",
        manifest_path=root / "no-manifest.json",
        openapi_path=OPENAPI,
        allow_dirty=True,
    )
    return metrics, out


@pytest.fixture(scope="module")
def smoke(
    synthetic_dir: Path, tmp_path_factory: pytest.TempPathFactory
) -> tuple[dict[str, Any], Path]:
    return _run(synthetic_dir, tmp_path_factory.mktemp("smoke_a"))


@pytest.mark.slow
def test_bundle_is_complete_and_valid(smoke: tuple[dict[str, Any], Path]) -> None:
    metrics, out = smoke
    for name in BUNDLE_FILES:
        assert (out / name).is_file(), name
    validate_bundle(out, openapi_path=OPENAPI)
    assert report_problems(metrics["report"], OPENAPI) == []
    assert list(metrics["run"]["config"]["notes"]) == SMOKE["notes"]


@pytest.mark.slow
def test_timeline_follows_the_protocol(smoke: tuple[dict[str, Any], Path]) -> None:
    _, out = smoke
    tl = pq.read_table(out / "timeline.parquet").to_pandas()
    assert tl["timestamp"].is_monotonic_increasing
    train = tl[tl["block"] == "train"]
    valid = tl[tl["block"] == "validation"]
    test = tl[tl["block"] == "test"]
    assert train["risk"].isna().all()
    assert (valid["risk_source"] == "oof").all()
    assert (test["risk_source"] == "test").all()
    assert train["timestamp"].max() < valid["timestamp"].min()
    assert valid["timestamp"].max() < test["timestamp"].min()
    shap = load_npz(out / "shap.npz")
    by_unit = tl.set_index("unit_id")
    has_values = ~np.isnan(shap["base_values"])
    assert np.array_equal(has_values, by_unit.loc[shap["unit_ids"], "risk"].notna().to_numpy())
    assert set(by_unit.loc[shap["unit_ids"][has_values], "block"]) == {"validation", "test"}


@pytest.mark.slow
def test_api_keys_and_contract_fields(smoke: tuple[dict[str, Any], Path]) -> None:
    metrics, out = smoke
    report = metrics["report"]
    assert [b["block"] for b in report["blocks"]] == ["train", "validation", "test"]
    assert sum(b["units"] for b in report["blocks"]) == 400
    assert metrics["fdc_reference"]["units"] > 0
    assert 0.0 < metrics["fdc_explained_variance"] <= 1.0
    assert set(metrics["methods"]) == {"explanation", "fdc", "contributions"}
    points = json.loads((out / "operating_points.json").read_text())
    assert points["units"] == report["blocks"][2]["units"]
    assert points["failures"] == report["blocks"][2]["failures"]
    assert points["points"][0]["label"] == "5% false-alarm rate"
    health = json.loads((out / "health.json").read_text())
    assert len(health["rules"]) == 4
    assert all((s["status"] == "ok") == (s["reasons"] == []) for s in health["sensors"])


def test_report_schema_rejects_a_mismatch() -> None:
    if not OPENAPI.is_file():
        pytest.skip("packages/contracts/openapi.json not in this checkout")
    bad: dict[str, Any] = {
        "blocks": [
            {
                "block": "train",
                "start": "not a time",
                "end": "2008-07-19T00:00:00Z",
                "units": 1,
                "failures": 0,
            }
        ],
        "models": [],
        "comparisons": [],
        "tuning": None,
        "fdc": None,
        "limitations": [],
    }
    problems = report_problems(bad, OPENAPI)
    assert any("calibration" in p for p in problems)
    assert any("not an ISO date-time" in p for p in problems)
    bad["extra"] = 1
    assert any("extra" in p for p in report_problems(bad, OPENAPI))


@pytest.mark.slow
def test_rerun_reproduces_every_file(
    smoke: tuple[dict[str, Any], Path], synthetic_dir: Path, tmp_path: Path
) -> None:
    _, first = smoke
    _, second = _run(synthetic_dir, tmp_path)
    for name in BUNDLE_FILES:
        if name == "MANIFEST.json":
            continue
        assert sha256_file(first / name) == sha256_file(second / name), name


@pytest.mark.slow
def test_corrupted_bundle_is_rejected(smoke: tuple[dict[str, Any], Path], tmp_path: Path) -> None:
    _, out = smoke
    copy = tmp_path / "copy"
    copy.mkdir()
    for name in BUNDLE_FILES:
        (copy / name).write_bytes((out / name).read_bytes())
    health = json.loads((copy / "health.json").read_text())
    health["sensors"][0]["status"] = "broken"
    (copy / "health.json").write_text(json.dumps(health))
    with pytest.raises(BundleError, match=r"health\.json"):
        validate_bundle(copy)


@pytest.mark.skipif(
    not (REAL_BUNDLE / "MANIFEST.json").is_file(),
    reason="the real bundle has not been built in artifacts/secom/v1",
)
def test_real_bundle_matches_its_contract() -> None:
    validate_bundle(REAL_BUNDLE, openapi_path=OPENAPI if OPENAPI.is_file() else None)
    tl = pd.read_parquet(REAL_BUNDLE / "timeline.parquet")
    assert len(tl) == 1567
