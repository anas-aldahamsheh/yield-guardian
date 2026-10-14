"""The real wafer-map bundle: verification (nested demo/ paths, tampering, unsafe paths), the
ONNX model's parity with the stored predictions, and startup when the bundle is missing or bad."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import pytest

from tests.science.bundle_factory import DATA
from yield_guardian.bootstrap import build_registry
from yield_guardian.bundles import wafermap as wafermap_module
from yield_guardian.bundles.manifest import BundleError, verify_bundle
from yield_guardian.bundles.wafermap import (
    PARITY_MAX_CONFIDENCE_DIFF,
    PARITY_MAX_ENERGY_DIFF,
    PARITY_MIN_AGREEMENT,
    PreprocessFile,
    WafermapBundle,
    model_input,
)
from yield_guardian.core.settings import Settings


def _settings(artifacts: Path) -> Settings:
    return Settings(
        environment="test",
        log_json=False,
        database_url=None,
        artifacts_dir=artifacts,
        secom_data_dir=DATA,
    )


@pytest.fixture
def copy(wafermap_dir: Path, tmp_path: Path) -> Path:
    target = tmp_path / "wafermap" / "v1"
    shutil.copytree(wafermap_dir, target)
    return target


def _manifest(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((path / "MANIFEST.json").read_text(encoding="utf-8"))
    return data


def _write(path: Path, manifest: dict[str, Any]) -> None:
    (path / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")


# Verification ---------------------------------------------------------------------------------


def test_the_real_bundle_verifies_with_its_nested_demo_files(wafermap_dir: Path) -> None:
    verified = verify_bundle(wafermap_dir, "wafermap")
    paths = {f["path"] for f in verified.manifest["files"]}
    assert {"demo/wafers.parquet", "demo/lots.json", "demo/ATTRIBUTION.md"} <= paths
    assert verified.info.verified
    assert verified.info.bundle.name == "wafermap"


def test_a_tampered_demo_file_is_refused(copy: Path) -> None:
    with (copy / "demo" / "lots.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(BundleError, match=r"demo/lots\.json has the wrong size"):
        verify_bundle(copy, "wafermap")


def test_a_tampered_model_is_refused(copy: Path) -> None:
    raw = bytearray((copy / "model.onnx").read_bytes())
    raw[-1] ^= 0xFF  # same size, different bytes
    (copy / "model.onnx").write_bytes(bytes(raw))
    with pytest.raises(BundleError, match=r"model\.onnx does not match its SHA-256"):
        verify_bundle(copy, "wafermap")


@pytest.mark.parametrize(
    "path", ["../outside.json", "demo/../../outside.json", "/etc/passwd", "", "demo\\lots.json"]
)
def test_unsafe_nested_paths_are_refused(copy: Path, path: str) -> None:
    manifest = _manifest(copy)
    manifest["files"][1]["path"] = path
    _write(copy, manifest)
    with pytest.raises(BundleError, match="unsafe path"):
        verify_bundle(copy, "wafermap")


def test_a_symlinked_file_is_refused(copy: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    shutil.move(copy / "demo" / "ATTRIBUTION.md", outside)
    (copy / "demo" / "ATTRIBUTION.md").symlink_to(outside)  # same bytes, outside the bundle
    with pytest.raises(BundleError, match=r"unsafe path 'demo/ATTRIBUTION\.md'"):
        verify_bundle(copy, "wafermap")


def test_a_symlinked_folder_is_refused(copy: Path, tmp_path: Path) -> None:
    shutil.move(copy / "demo", tmp_path / "demo")
    (copy / "demo").symlink_to(tmp_path / "demo", target_is_directory=True)
    with pytest.raises(BundleError, match="unsafe path 'demo/"):
        verify_bundle(copy, "wafermap")


# Model parity ---------------------------------------------------------------------------------


def test_every_demo_wafer_is_scored_and_agrees_with_the_stored_predictions(
    wafermap_bundle: WafermapBundle,
) -> None:
    parity = wafermap_bundle.parity
    n = len(wafermap_bundle.wafers)
    assert parity.wafers == n == 10253
    assert parity.top_label_agreement >= PARITY_MIN_AGREEMENT
    assert parity.max_confidence_diff <= PARITY_MAX_CONFIDENCE_DIFF
    assert parity.max_energy_diff <= PARITY_MAX_ENERGY_DIFF
    scores = wafermap_bundle.scores
    assert scores.probabilities.shape == (n, 9)
    assert np.allclose(scores.probabilities.sum(axis=1), 1.0)
    assert scores.embedding.shape == (n, 128)
    assert np.allclose(np.linalg.norm(scores.embedding, axis=1), 1.0, atol=1e-3)


def test_a_fresh_onnx_run_reproduces_the_cached_outputs(
    wafermap_bundle: WafermapBundle, wafermap_dir: Path
) -> None:
    session = ort.InferenceSession(
        str(wafermap_dir / "model.onnx"), providers=["CPUExecutionProvider"]
    )
    prep = PreprocessFile.model_validate_json((wafermap_dir / "preprocess.json").read_text())
    wafers = wafermap_bundle.wafers
    rows = [0, 1, 777, 5000, len(wafers) - 1]
    logits, embedding = session.run(
        None, {"maps": model_input([wafers.grid(i) for i in rows], prep)}
    )
    z = np.asarray(logits, dtype=np.float64) / wafermap_bundle.temperature
    probabilities = np.exp(z - z.max(axis=1, keepdims=True))
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    assert np.allclose(probabilities, wafermap_bundle.scores.probabilities[rows], atol=1e-5)
    assert np.allclose(embedding, wafermap_bundle.scores.embedding[rows], atol=1e-5)
    stored = {w.wafer_id: w for lot in wafermap_bundle.lots.values() for w in lot.wafers}
    for i in rows:
        record = stored[wafers.wafer_id[i]]
        assert abs(record.confidence - wafermap_bundle.scores.probabilities[i].max()) <= 0.05


def test_the_model_input_is_a_nearest_neighbour_one_hot_map(wafermap_dir: Path) -> None:
    # Test-only synthetic 2x3 grid, to check the resize and the channel order.
    prep = PreprocessFile.model_validate_json((wafermap_dir / "preprocess.json").read_text())
    grid = np.array([[0, 1, 2], [2, 1, 0]], dtype=np.uint8)
    x = model_input([grid], prep)
    assert x.shape == (1, 3, 64, 64)
    assert np.all(x.sum(axis=1) == 1.0)
    assert x[0, :, 0, 0].tolist() == [1.0, 0.0, 0.0]  # top-left: no die
    assert x[0, :, 0, 63].tolist() == [0.0, 0.0, 1.0]  # top-right: fail
    assert x[0, :, 63, 0].tolist() == [0.0, 0.0, 1.0]  # bottom-left: fail


def test_stored_predictions_that_disagree_are_refused(wafermap_bundle: WafermapBundle) -> None:
    # Test-only: one stored confidence shifted by 0.2 must fail the parity check.
    lots = dict(wafermap_bundle.lots)
    name = next(iter(lots))
    first = lots[name].wafers[0]
    moved = first.model_copy(update={"confidence": abs(first.confidence - 0.2)})
    lots[name] = lots[name].model_copy(update={"wafers": [moved, *lots[name].wafers[1:]]})
    with pytest.raises(BundleError, match="disagrees"):
        wafermap_module._parity(
            wafermap_bundle.wafers, wafermap_bundle.scores, lots, wafermap_bundle.labels
        )


# Startup --------------------------------------------------------------------------------------


def test_startup_loads_the_wafer_service(
    wafermap_dir: Path, wafermap_bundle: WafermapBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The session's already-loaded bundle stands in for a second 10k-wafer model run.
    monkeypatch.setattr(
        "yield_guardian.bootstrap.load_wafermap_bundle", lambda verified: wafermap_bundle
    )
    registry = build_registry(_settings(wafermap_dir.parents[1]))
    assert registry.wafer is not None
    assert "wafermap_bundle" not in registry.problems
    assert [b.bundle.name for b in registry.bundles] == ["wafermap"]


def test_a_missing_bundle_is_reported_not_raised(tmp_path: Path) -> None:
    registry = build_registry(_settings(tmp_path))
    assert registry.wafer is None
    assert "No wafermap bundle" in registry.problems["wafermap_bundle"]


def test_a_tampered_bundle_is_reported_not_raised(copy: Path) -> None:
    (copy / "labels.json").write_text('["Center"]', encoding="utf-8")
    registry = build_registry(_settings(copy.parents[1]))
    assert registry.wafer is None
    assert "labels.json" in registry.problems["wafermap_bundle"]


def test_a_verified_but_invalid_bundle_is_reported_not_raised(copy: Path) -> None:
    # Test-only: a wrong label list, re-signed in the manifest, passes verification but not loading.
    data = json.dumps(["Center", "Donut"]).encode()
    (copy / "labels.json").write_bytes(data)
    manifest = _manifest(copy)
    entry = next(f for f in manifest["files"] if f["path"] == "labels.json")
    entry.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    _write(copy, manifest)
    registry = build_registry(_settings(copy.parents[1]))
    assert registry.wafer is None
    assert "labels.json must list" in registry.problems["wafermap_bundle"]
