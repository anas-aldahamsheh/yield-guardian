"""Provenance and deterministic writers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from yg_common.estimates import UNDEFINED_BOUND_NOTE, Estimate, UndefinedEstimateError
from yg_common.io import dumps_json, load_npz, save_npz, write_json
from yg_common.provenance import (
    derive_seed,
    environment_record,
    git_commit,
    git_dirty,
    package_versions,
    sha256_bytes,
    sha256_file,
    utc_now_iso,
)


def test_sha256_known_vector(tmp_path: Path) -> None:
    target = tmp_path / "abc.txt"
    target.write_bytes(b"abc")
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert sha256_file(target) == expected
    assert sha256_bytes(b"abc") == expected


def test_sha256_large_file_matches_hashlib(tmp_path: Path) -> None:
    payload = np.random.default_rng(0).bytes(3 * (1 << 20) + 17)
    target = tmp_path / "blob.bin"
    target.write_bytes(payload)
    assert sha256_file(target) == hashlib.sha256(payload).hexdigest()


def test_derive_seed_is_stable_and_named() -> None:
    assert derive_seed(42, "optuna") == derive_seed(42, "optuna")
    assert derive_seed(42, "optuna") != derive_seed(42, "bootstrap")
    assert derive_seed(42, "optuna") != derive_seed(43, "optuna")
    assert 0 <= derive_seed(7, "x") < 2**31


def test_git_helpers_inside_and_outside_a_repository(tmp_path: Path) -> None:
    here = Path(__file__).resolve().parent
    commit = git_commit(here)
    if commit is not None:  # tests may run from an exported tarball
        assert re.fullmatch(r"[0-9a-f]{40}", commit)
        assert git_dirty(here, ["."]) in (True, False)
    assert git_commit(tmp_path) is None
    assert git_dirty(tmp_path) is None


def test_package_versions_and_environment() -> None:
    versions = package_versions(["numpy", "surely-not-installed-package"])
    assert versions["numpy"] == np.__version__
    assert versions["surely-not-installed-package"] is None
    env = environment_record(["numpy"])
    assert str(env["python"]).startswith("3.13")


def test_utc_now_iso_format() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", utc_now_iso())


def test_save_npz_is_byte_deterministic_and_round_trips(tmp_path: Path) -> None:
    arrays: dict[str, npt.ArrayLike] = {
        "values": np.arange(12, dtype=np.float32).reshape(3, 4),
        "features": np.array(["S001", "S002", "S003", "S004"]),
        "base_value": np.float64(-2.5),
    }
    first, second = tmp_path / "a.npz", tmp_path / "b.npz"
    save_npz(first, arrays)
    save_npz(second, dict(reversed(list(arrays.items()))))
    assert first.read_bytes() == second.read_bytes()
    loaded = load_npz(first)
    np.testing.assert_array_equal(loaded["values"], arrays["values"])
    assert loaded["features"].tolist() == ["S001", "S002", "S003", "S004"]
    assert float(loaded["base_value"]) == -2.5


def test_save_npz_refuses_object_arrays(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        save_npz(tmp_path / "bad.npz", {"x": np.array([{"a": 1}], dtype=object)})


def test_json_writer_rejects_nan(tmp_path: Path) -> None:
    write_json(tmp_path / "ok.json", {"a": 1.5, "b": [1, 2]})
    assert json.loads((tmp_path / "ok.json").read_text()) == {"a": 1.5, "b": [1, 2]}
    assert dumps_json({"x": 1}).endswith("\n")
    with pytest.raises(ValueError):
        dumps_json({"x": math.nan})


def test_estimate_serialisation() -> None:
    est = Estimate(0.41, 0.30, 0.52, 0.95, "stratified bootstrap, 2000 resamples", 313)
    assert est.to_dict() == {
        "value": 0.41,
        "ci_low": 0.30,
        "ci_high": 0.52,
        "ci_level": 0.95,
        "method": "stratified bootstrap, 2000 resamples",
        "n": 313,
    }
    undefined = Estimate(math.nan, math.nan, math.nan, 0.95, "m", 0)
    assert not undefined.defined
    with pytest.raises(UndefinedEstimateError):
        undefined.to_dict()
    open_bound = Estimate(0.4, math.nan, 0.6, 0.95, "m", 10).to_dict()
    assert open_bound["ci_low"] is None
    assert open_bound["note"] == UNDEFINED_BOUND_NOTE
    noted = Estimate(0.4, math.nan, math.nan, 0.95, "m", 10, note="why").to_dict()
    assert noted["note"] == "why"
    assert "note" not in est.to_dict()
    with pytest.raises(ValueError):
        Estimate(0.5, 0.6, 0.4, 0.95, "m", 1)
    with pytest.raises(ValueError):
        Estimate(0.5, 0.4, 0.6, 1.5, "m", 1)
