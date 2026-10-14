"""Loader and manifest checks, on SYNTHETIC files in the SECOM format."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from yg_common.provenance import sha256_file

from synthetic import SyntheticSecom
from yg_secom.data import DataValidationError, load_secom, sensor_ids, verify_manifest


def test_loads_counts_labels_and_timestamps(synthetic_dir: Path, synthetic: SyntheticSecom) -> None:
    data = load_secom(synthetic_dir, expected_units=400, expected_features=30)
    assert data.features.shape == (400, 30)
    assert list(data.features.columns[:2]) == ["S001", "S002"]
    assert data.labels.tolist() == synthetic.labels.tolist()
    np.testing.assert_array_equal(np.isnan(data.features.to_numpy()), np.isnan(synthetic.features))
    assert str(data.timestamps.dt.tz) == "UTC"
    assert data.timestamps.iloc[0].strftime("%Y-%m-%d %H:%M") == "2008-07-19 11:55"
    report = data.report
    assert report["timestamp_parsing"]["line_endings"] == "CRLF"
    assert report["anomalies"]["file_order_is_chronological"]
    assert report["anomalies"]["timestamp_tie_groups"] > 0
    assert report["label_encoding"]["bundle"] == {"fail": 1, "pass": 0}


def test_count_mismatch_is_an_error(synthetic_dir: Path) -> None:
    with pytest.raises(DataValidationError):
        load_secom(synthetic_dir, expected_units=401, expected_features=30)
    with pytest.raises(DataValidationError):
        load_secom(synthetic_dir, expected_units=400, expected_features=31)


def test_malformed_label_line_is_an_error(synthetic_dir: Path, tmp_path: Path) -> None:
    target = tmp_path / "bad"
    shutil.copytree(synthetic_dir, target)
    lines = (target / "secom_labels.data").read_bytes().decode().split("\r\n")
    lines[3] = '0 "19/07/2008 12:00:00"'
    (target / "secom_labels.data").write_bytes("\r\n".join(lines).encode())
    with pytest.raises(DataValidationError):
        load_secom(target, expected_units=400, expected_features=30)


def test_unknown_token_is_an_error(synthetic_dir: Path, tmp_path: Path) -> None:
    target = tmp_path / "bad"
    shutil.copytree(synthetic_dir, target)
    text = (target / "secom.data").read_bytes().decode().replace("NaN", "NA", 1)
    (target / "secom.data").write_bytes(text.encode())
    with pytest.raises(DataValidationError):
        load_secom(target, expected_units=400, expected_features=30)


def test_manifest_digest_must_match(synthetic_dir: Path, tmp_path: Path) -> None:
    digests = {
        name: sha256_file(synthetic_dir / name) for name in ("secom.data", "secom_labels.data")
    }
    manifest = tmp_path / "manifest.json"
    entry = {"files": [{"path": f"raw/secom/{k}", "sha256": v} for k, v in digests.items()]}
    manifest.write_text(json.dumps({"secom": entry}))
    records = verify_manifest(digests, manifest)
    assert [r["manifest_path"] for r in records] == [
        "raw/secom/secom.data",
        "raw/secom/secom_labels.data",
    ]
    entry["files"][0]["sha256"] = "0" * 64
    manifest.write_text(json.dumps({"secom": entry}))
    with pytest.raises(DataValidationError):
        verify_manifest(digests, manifest)


def test_sensor_ids_follow_the_contract() -> None:
    ids = sensor_ids(590)
    assert ids[0] == "S001"
    assert ids[-1] == "S590"
