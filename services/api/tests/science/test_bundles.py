"""Bundle verification and loading: a bundle is used only if every file matches its manifest."""

import json
import shutil
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from tests.science.bundle_factory import DATA, write_manifest
from yield_guardian.bundles.manifest import BundleError, latest_version, verify_bundle
from yield_guardian.bundles.secom import SecomBundle, feature_sensor, load_secom_bundle


def test_a_complete_bundle_verifies(bundle_dir: Path) -> None:
    verified = verify_bundle(bundle_dir, "secom")
    assert verified.info.verified
    assert verified.info.bundle.version == "v1"
    assert verified.info.files == len(verified.manifest["files"])


def test_the_highest_version_is_chosen(tmp_path: Path) -> None:
    for name in ("v1", "v10", "v2", "notes"):
        (tmp_path / "secom" / name).mkdir(parents=True)
    assert latest_version(tmp_path, "secom").name == "v10"
    with pytest.raises(BundleError):
        latest_version(tmp_path, "wafermap")


@pytest.fixture
def copy(bundle_dir: Path, tmp_path: Path) -> Path:
    target = tmp_path / "secom" / "v1"
    shutil.copytree(bundle_dir, target)
    return target


def test_a_changed_file_is_refused(copy: Path) -> None:
    with (copy / "groups.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(BundleError, match=r"groups\.json"):
        verify_bundle(copy, "secom")


def test_a_missing_file_is_refused(copy: Path) -> None:
    (copy / "shap.npz").unlink()
    with pytest.raises(BundleError, match=r"shap\.npz is missing"):
        verify_bundle(copy, "secom")


def test_the_wrong_name_or_version_is_refused(copy: Path) -> None:
    with pytest.raises(BundleError, match="expected 'wafermap'"):
        verify_bundle(copy, "wafermap")
    renamed = copy.parent / "v2"
    copy.rename(renamed)
    with pytest.raises(BundleError, match="version"):
        verify_bundle(renamed, "secom")


def test_unsafe_manifest_paths_are_refused(copy: Path) -> None:
    manifest = json.loads((copy / "MANIFEST.json").read_text())
    manifest["files"][0]["path"] = "../outside.json"
    (copy / "MANIFEST.json").write_text(json.dumps(manifest))
    with pytest.raises(BundleError, match="unsafe path"):
        verify_bundle(copy, "secom")


def test_a_timeline_that_disagrees_with_the_source_files_is_refused(copy: Path) -> None:
    table = pq.read_table(copy / "timeline.parquet")
    labels = table.column("label").to_pylist()
    labels[0] = 1 - labels[0]
    table = table.set_column(table.schema.get_field_index("label"), "label", [labels])
    pq.write_table(table.cast(pq.read_schema(copy / "timeline.parquet")), copy / "timeline.parquet")
    write_manifest(copy, "v1")
    with pytest.raises(BundleError, match=r"disagrees with secom_labels\.data"):
        load_secom_bundle(verify_bundle(copy, "secom"), DATA)


def test_the_loaded_timeline_is_in_time_order(secom_bundle: SecomBundle) -> None:
    timeline = secom_bundle.timeline
    assert len(timeline) == 1567
    pairs = list(zip(timeline.timestamp, timeline.unit_id.tolist(), strict=True))
    assert pairs == sorted(pairs)
    assert (timeline.unit_id[timeline.sequence_of] == range(1567)).all()


def test_feature_names_map_to_sensors() -> None:
    assert feature_sensor("S060") == ("S060", False)
    assert feature_sensor("S060_missing") == ("S060", True)
    for bad in ("S000", "S591", "X060", "S60"):
        with pytest.raises(ValueError, match="sensor"):
            feature_sensor(bad)
