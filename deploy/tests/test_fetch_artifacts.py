"""Tests for deploy/fetch_artifacts.py, on synthetic archives built in a temporary folder.

The bundle contents here are placeholder bytes made up for these tests, not model data.
Run with: python3 -m pytest deploy/tests
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "fetch_artifacts.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fetch_artifacts", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_artifacts"] = module
    spec.loader.exec_module(module)
    return module


fa = _load()

FILES = {"model.txt": b"synthetic test bytes\n", "nested/table.json": b'{"synthetic": true}\n'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_for(files: dict[str, bytes], name: str = "secom", version: str = "v1") -> bytes:
    return json.dumps(
        {
            "name": name,
            "version": version,
            "files": [
                {"path": path, "bytes": len(data), "sha256": sha(data)}
                for path, data in files.items()
            ],
        }
    ).encode()


def make_tar(path: Path, members: dict[str, bytes], prefix: str = "") -> Path:
    with tarfile.open(path, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(prefix + name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def make_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def bundle_members(files: dict[str, bytes] = FILES) -> dict[str, bytes]:
    return {"MANIFEST.json": manifest_for(files), **files}


def write_lock(tmp: Path, archive: Path, digest: str | None = None, **extra: str) -> Path:
    entry = {
        "name": "secom",
        "version": "v1",
        "url": archive.as_uri(),
        "sha256": digest or sha(archive.read_bytes()),
        **extra,
    }
    lock = tmp / "artifacts.lock.json"
    lock.write_text(json.dumps({"bundles": [entry]}))
    return lock


def quiet(_message: str) -> None:
    return None


@pytest.fixture
def dest(tmp_path: Path) -> Path:
    return tmp_path / "artifacts"


# Good archives


@pytest.mark.parametrize(
    "build",
    [
        lambda p: make_tar(p / "b.tar.gz", bundle_members()),
        lambda p: make_tar(p / "b.tar.gz", bundle_members(), prefix="secom-v1/"),
        lambda p: make_tar(p / "b.tar.gz", bundle_members(), prefix="./"),
        lambda p: make_zip(p / "b.zip", bundle_members()),
    ],
    ids=["tar", "tar-wrapper-folder", "tar-dot-prefix", "zip"],
)
def test_good_archive_is_verified_and_extracted(
    tmp_path: Path, dest: Path, build: Callable[[Path], Path]
) -> None:
    lock = write_lock(tmp_path, build(tmp_path))
    [bundle] = fa.fetch_all(lock, dest, log=quiet)
    assert bundle == dest / "secom" / "v1"
    for name, data in FILES.items():
        assert (bundle / name).read_bytes() == data
    assert (bundle / "MANIFEST.json").is_file()
    # No temporary folders are left next to the bundle.
    assert sorted(p.name for p in (dest / "secom").iterdir()) == ["v1"]


def test_second_run_verifies_the_existing_bundle(tmp_path: Path, dest: Path) -> None:
    lock = write_lock(tmp_path, make_tar(tmp_path / "b.tar.gz", bundle_members()))
    fa.fetch_all(lock, dest, log=quiet)
    fa.fetch_all(lock, dest, log=quiet)
    (dest / "secom" / "v1" / "model.txt").write_bytes(b"tampered")
    with pytest.raises(fa.ArtifactError, match="fails verification"):
        fa.fetch_all(lock, dest, log=quiet)


def test_empty_lock_is_valid(tmp_path: Path, dest: Path) -> None:
    lock = tmp_path / "artifacts.lock.json"
    lock.write_text('{"bundles": []}')
    assert fa.fetch_all(lock, dest, log=quiet) == []
    assert dest.is_dir()


def test_repository_lock_file_parses() -> None:
    fa.load_lock(MODULE_PATH.parent / "artifacts.lock.json")


def test_main_returns_non_zero_on_failure(tmp_path: Path, dest: Path) -> None:
    lock = write_lock(tmp_path, make_tar(tmp_path / "b.tar.gz", bundle_members()), "0" * 64)
    assert fa.main(["--lock", str(lock), "--dest", str(dest)]) == 1


# Wrong checksum


def test_wrong_archive_checksum_fails_closed(tmp_path: Path, dest: Path) -> None:
    lock = write_lock(tmp_path, make_tar(tmp_path / "b.tar.gz", bundle_members()), "0" * 64)
    with pytest.raises(fa.ArtifactError, match="archive sha256"):
        fa.fetch_all(lock, dest, log=quiet)
    assert not (dest / "secom" / "v1").exists()
    assert list((dest / "secom").iterdir()) == []


# Unsafe archive paths


@pytest.mark.parametrize(
    "member",
    ["../evil.txt", "/abs/evil.txt", "a/../../evil.txt", "C:/evil.txt", "a\\..\\evil.txt"],
)
def test_path_traversal_in_tar_is_refused(tmp_path: Path, dest: Path, member: str) -> None:
    members = {**bundle_members(), member: b"x"}
    lock = write_lock(tmp_path, make_tar(tmp_path / "b.tar.gz", members))
    with pytest.raises(fa.ArtifactError, match="unsafe path"):
        fa.fetch_all(lock, dest, log=quiet)
    assert not (tmp_path / "evil.txt").exists()
    assert not (dest / "secom" / "v1").exists()


@pytest.mark.parametrize("member", ["../evil.txt", "/abs/evil.txt"])
def test_path_traversal_in_zip_is_refused(tmp_path: Path, dest: Path, member: str) -> None:
    members = {**bundle_members(), member: b"x"}
    lock = write_lock(tmp_path, make_zip(tmp_path / "b.zip", members))
    with pytest.raises(fa.ArtifactError, match="unsafe path"):
        fa.fetch_all(lock, dest, log=quiet)
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_links_and_special_files_in_tar_are_refused(
    tmp_path: Path, dest: Path, kind: bytes
) -> None:
    archive = tmp_path / "b.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in bundle_members().items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("link")
        link.type = kind
        link.linkname = "/etc/passwd"
        tar.addfile(link)
    lock = write_lock(tmp_path, archive)
    with pytest.raises(fa.ArtifactError, match="not a regular file"):
        fa.fetch_all(lock, dest, log=quiet)


def test_duplicate_member_is_refused(tmp_path: Path, dest: Path) -> None:
    archive = tmp_path / "b.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in [*bundle_members().items(), ("model.txt", b"second copy")]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    lock = write_lock(tmp_path, archive)
    with pytest.raises(fa.ArtifactError, match="twice"):
        fa.fetch_all(lock, dest, log=quiet)


# Manifest mismatches


def test_manifest_hash_mismatch_fails_closed(tmp_path: Path, dest: Path) -> None:
    members = {**bundle_members(), "model.txt": b"synthetic test bytes, altered\n"}
    lock = write_lock(tmp_path, make_tar(tmp_path / "b.tar.gz", members))
    with pytest.raises(fa.ArtifactError, match=r"model\.txt"):
        fa.fetch_all(lock, dest, log=quiet)
    assert not (dest / "secom" / "v1").exists()


def test_manifest_size_mismatch_fails_closed(tmp_path: Path, dest: Path) -> None:
    files = dict(FILES)
    manifest = json.loads(manifest_for(files))
    manifest["files"][0]["bytes"] += 1
    members = {"MANIFEST.json": json.dumps(manifest).encode(), **files}
    lock = write_lock(tmp_path, make_tar(tmp_path / "b.tar.gz", members))
    with pytest.raises(fa.ArtifactError, match="bytes"):
        fa.fetch_all(lock, dest, log=quiet)


def test_file_listed_but_missing_fails_closed(tmp_path: Path, dest: Path) -> None:
    members = bundle_members()
    del members["nested/table.json"]
    lock = write_lock(tmp_path, make_tar(tmp_path / "b.tar.gz", members))
    with pytest.raises(fa.ArtifactError, match="missing"):
        fa.fetch_all(lock, dest, log=quiet)


def test_unlisted_file_fails_closed(tmp_path: Path, dest: Path) -> None:
    members = {**bundle_members(), "extra.bin": b"not in the manifest"}
    lock = write_lock(tmp_path, make_tar(tmp_path / "b.tar.gz", members))
    with pytest.raises(fa.ArtifactError, match="not listed"):
        fa.fetch_all(lock, dest, log=quiet)


def test_manifest_for_another_bundle_fails_closed(tmp_path: Path, dest: Path) -> None:
    members = {"MANIFEST.json": manifest_for(FILES, name="wafermap"), **FILES}
    lock = write_lock(tmp_path, make_tar(tmp_path / "b.tar.gz", members))
    with pytest.raises(fa.ArtifactError, match="lock expects"):
        fa.fetch_all(lock, dest, log=quiet)


def test_missing_manifest_fails_closed(tmp_path: Path, dest: Path) -> None:
    lock = write_lock(tmp_path, make_tar(tmp_path / "b.tar.gz", dict(FILES)))
    with pytest.raises(fa.ArtifactError, match=r"MANIFEST\.json"):
        fa.fetch_all(lock, dest, log=quiet)


def test_manifest_path_traversal_is_refused(tmp_path: Path, dest: Path) -> None:
    manifest = json.loads(manifest_for(FILES))
    manifest["files"][0]["path"] = "../../outside.txt"
    members = {"MANIFEST.json": json.dumps(manifest).encode(), **FILES}
    lock = write_lock(tmp_path, make_tar(tmp_path / "b.tar.gz", members))
    with pytest.raises(fa.ArtifactError, match="unsafe path"):
        fa.fetch_all(lock, dest, log=quiet)


# Lock file validation


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"url": "http://example.com/b.tar.gz"}, "https"),
        ({"sha256": "ABC"}, "sha256"),
        ({"name": "../secom"}, "invalid name"),
        ({"version": ".."}, "invalid version"),
    ],
)
def test_invalid_lock_entries_are_refused(
    tmp_path: Path, dest: Path, change: dict[str, str], message: str
) -> None:
    archive = make_tar(tmp_path / "b.tar.gz", bundle_members())
    lock = write_lock(tmp_path, archive, **change)
    with pytest.raises(fa.ArtifactError, match=message):
        fa.fetch_all(lock, dest, log=quiet)


def test_duplicate_lock_entries_are_refused(tmp_path: Path) -> None:
    entry = {"name": "secom", "version": "v1", "url": "https://x/b.tgz", "sha256": "0" * 64}
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"bundles": [entry, entry]}))
    with pytest.raises(fa.ArtifactError, match="twice"):
        fa.load_lock(lock)


def test_non_https_redirect_is_refused() -> None:
    import urllib.request

    handler = fa._HttpsOnlyRedirects()
    request = urllib.request.Request("https://example.com/a")
    with pytest.raises(fa.ArtifactError, match="non-HTTPS"):
        handler.redirect_request(request, None, 302, "Found", {}, "http://example.com/b")


def test_symlink_in_zip_is_refused(tmp_path: Path, dest: Path) -> None:
    archive = make_zip(tmp_path / "b.zip", bundle_members())
    with zipfile.ZipFile(archive, "a") as zf:
        info = zipfile.ZipInfo("link")
        info.external_attr = (0o120777 << 16) | 0
        zf.writestr(info, "/etc/passwd")
    lock = write_lock(tmp_path, archive)
    with pytest.raises(fa.ArtifactError, match="not a regular file"):
        fa.fetch_all(lock, dest, log=quiet)
