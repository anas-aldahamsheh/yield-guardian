#!/usr/bin/env python3
"""Download, verify and unpack the model bundles listed in deploy/artifacts.lock.json.

Standard library only, so it runs in a bare Python image during `docker build`.

For every bundle in the lock file:

1. download the archive (HTTPS only, redirects included) and check its SHA-256 against the lock;
2. unpack it into a temporary folder, refusing absolute paths, `..`, links and special files;
3. read the bundle's MANIFEST.json, check that its name and version match the lock, and that
   every file it lists exists with exactly the listed size and SHA-256, and that the archive
   holds no file the manifest does not list;
4. only then move the bundle to <dest>/<name>/<version>/.

Any mismatch stops the run with a non-zero exit code and leaves no partial bundle behind. An
empty lock is valid: nothing is fetched, and the API answers 503 not_ready for model routes.

Usage:

    python3 deploy/fetch_artifacts.py --lock deploy/artifacts.lock.json --dest artifacts

The lock file:

    {"bundles": [{"name": "secom", "version": "v1",
                  "url": "https://github.com/<owner>/<repo>/releases/download/<tag>/secom-v1.tar.gz",
                  "sha256": "<64 lowercase hex>"}]}

The archive (.tar, .tar.gz, .tar.xz, .tar.bz2 or .zip) holds the bundle's files with
MANIFEST.json at its top level, or inside one wrapper folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MANIFEST = "MANIFEST.json"
CHUNK = 1 << 20
DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_TIMEOUT_S = 60
USER_AGENT = "yield-guardian-fetch-artifacts/1"


class ArtifactError(Exception):
    """A bundle failed a check. The message says which one and why."""


@dataclass(frozen=True, slots=True)
class LockEntry:
    name: str
    version: str
    url: str
    sha256: str

    @property
    def label(self) -> str:
        return f"{self.name}/{self.version}"


# Lock file


def load_lock(path: Path) -> list[LockEntry]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ArtifactError(f"cannot read lock file {path}: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("bundles"), list):
        raise ArtifactError(f'{path}: expected an object with a "bundles" list')
    entries: list[LockEntry] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(raw["bundles"]):
        where = f"{path}: bundles[{index}]"
        if not isinstance(item, dict):
            raise ArtifactError(f"{where}: expected an object")
        missing = {"name", "version", "url", "sha256"} - item.keys()
        if missing:
            raise ArtifactError(f"{where}: missing {', '.join(sorted(missing))}")
        values = {key: item[key] for key in ("name", "version", "url", "sha256")}
        if not all(isinstance(value, str) for value in values.values()):
            raise ArtifactError(f"{where}: name, version, url and sha256 must be strings")
        entry = LockEntry(**values)
        if not NAME.match(entry.name):
            raise ArtifactError(f"{where}: invalid name {entry.name!r}")
        if not VERSION.match(entry.version) or entry.version in {".", ".."}:
            raise ArtifactError(f"{where}: invalid version {entry.version!r}")
        if not SHA256.match(entry.sha256):
            raise ArtifactError(f"{where}: sha256 must be 64 lowercase hex characters")
        scheme = urllib.parse.urlsplit(entry.url).scheme
        if scheme not in {"https", "file"}:
            raise ArtifactError(f"{where}: url must be https:// (got {scheme or 'no'} scheme)")
        if (entry.name, entry.version) in seen:
            raise ArtifactError(f"{where}: {entry.label} is listed twice")
        seen.add((entry.name, entry.version))
        entries.append(entry)
    return entries


# Download


class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise ArtifactError(f"refusing a redirect to a non-HTTPS URL: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    """Write the resource at `url` to `target`, retrying transient network failures."""
    if urllib.parse.urlsplit(url).scheme == "file":
        source = Path(urllib.request.url2pathname(urllib.parse.urlsplit(url).path))
        shutil.copyfile(source, target)
        return
    opener = urllib.request.build_opener(_HttpsOnlyRedirects())
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            with (
                opener.open(request, timeout=DOWNLOAD_TIMEOUT_S) as response,
                target.open("wb") as out,
            ):
                shutil.copyfileobj(response, out, CHUNK)
            return
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == DOWNLOAD_ATTEMPTS:
                raise ArtifactError(f"download failed: HTTP {exc.code} for {url}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == DOWNLOAD_ATTEMPTS:
                raise ArtifactError(f"download failed: {exc} for {url}") from exc
        time.sleep(2 * attempt)


# Safe extraction


def safe_relative(name: str, *, allow_root: bool = False) -> PurePosixPath:
    """The archive member name as a relative path, or an error when it could escape."""
    if not name or "\\" in name or "\x00" in name:
        raise ArtifactError(f"unsafe path in archive: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or re.match(r"^[A-Za-z]:", name):
        raise ArtifactError(f"unsafe path in archive (absolute): {name!r}")
    parts = [part for part in path.parts if part not in {"", "."}]
    if any(part == ".." for part in parts) or (not parts and not allow_root):
        raise ArtifactError(f"unsafe path in archive: {name!r}")
    return PurePosixPath(*parts)


def _check_unique(names: list[PurePosixPath]) -> None:
    seen: set[PurePosixPath] = set()
    for name in names:
        if name in seen:
            raise ArtifactError(f"archive lists {name} twice")
        seen.add(name)


def extract_tar(archive: Path, dest: Path) -> None:
    with tarfile.open(archive, mode="r:*") as tar:
        members = tar.getmembers()
        files: list[PurePosixPath] = []
        for member in members:
            rel = safe_relative(member.name, allow_root=member.isdir())
            if member.isdir():
                continue
            if not member.isreg():
                raise ArtifactError(f"archive member is not a regular file: {member.name!r}")
            files.append(rel)
        _check_unique(files)
        for member in members:
            rel = safe_relative(member.name, allow_root=member.isdir())
            target = dest.joinpath(*rel.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise ArtifactError(f"cannot read archive member {member.name!r}")
            with source, target.open("xb") as out:
                shutil.copyfileobj(source, out, CHUNK)


def extract_zip(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        files: list[PurePosixPath] = []
        for info in infos:
            rel = safe_relative(info.filename, allow_root=info.is_dir())
            kind = stat.S_IFMT(info.external_attr >> 16)
            if info.is_dir():
                continue
            if kind and kind != stat.S_IFREG:
                raise ArtifactError(f"archive member is not a regular file: {info.filename!r}")
            files.append(rel)
        _check_unique(files)
        for info in infos:
            rel = safe_relative(info.filename, allow_root=info.is_dir())
            target = dest.joinpath(*rel.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, target.open("xb") as out:
                shutil.copyfileobj(source, out, CHUNK)


def extract(archive: Path, dest: Path) -> None:
    if zipfile.is_zipfile(archive):
        extract_zip(archive, dest)
    elif tarfile.is_tarfile(archive):
        extract_tar(archive, dest)
    else:
        raise ArtifactError("archive is neither a tar nor a zip file")


def bundle_root(extracted: Path) -> Path:
    """The folder holding MANIFEST.json: the archive root, or one wrapper folder down."""
    current = extracted
    for _ in range(3):
        if (current / MANIFEST).is_file():
            return current
        entries = list(current.iterdir())
        if len(entries) != 1 or not entries[0].is_dir():
            break
        current = entries[0]
    raise ArtifactError(f"no {MANIFEST} at the top of the archive")


# Manifest verification


def verify_bundle(root: Path, name: str, version: str) -> int:
    """Check the bundle in `root` against its MANIFEST.json. Returns the number of files."""
    manifest_path = root / MANIFEST
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ArtifactError(f"{MANIFEST} is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ArtifactError(f"{MANIFEST} is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ArtifactError(f"{MANIFEST} must be an object")
    if manifest.get("name") != name or manifest.get("version") != version:
        raise ArtifactError(
            f"{MANIFEST} names {manifest.get('name')!r}/{manifest.get('version')!r}, "
            f"the lock expects {name!r}/{version!r}"
        )
    listed = manifest.get("files")
    if not isinstance(listed, list) or not listed:
        raise ArtifactError(f'{MANIFEST} has no "files" list')

    expected: set[PurePosixPath] = set()
    for index, item in enumerate(listed):
        where = f"{MANIFEST} files[{index}]"
        if not isinstance(item, dict):
            raise ArtifactError(f"{where}: expected an object")
        path, size, digest = item.get("path"), item.get("bytes"), item.get("sha256")
        if not isinstance(path, str):
            raise ArtifactError(f"{where}: path must be a string")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ArtifactError(f"{where}: bytes must be a non-negative integer")
        if not isinstance(digest, str) or not SHA256.match(digest):
            raise ArtifactError(f"{where}: sha256 must be 64 lowercase hex characters")
        rel = safe_relative(path)
        if rel == PurePosixPath(MANIFEST):
            raise ArtifactError(f"{where}: {MANIFEST} cannot list itself")
        if rel in expected:
            raise ArtifactError(f"{where}: {rel} is listed twice")
        expected.add(rel)
        file = root.joinpath(*rel.parts)
        if file.is_symlink() or not file.is_file():
            raise ArtifactError(f"{rel}: listed in {MANIFEST} but missing")
        actual_size = file.stat().st_size
        if actual_size != size:
            raise ArtifactError(f"{rel}: {actual_size} bytes, {MANIFEST} says {size}")
        actual = sha256_of(file)
        if actual != digest:
            raise ArtifactError(f"{rel}: sha256 {actual}, {MANIFEST} says {digest}")

    present: set[PurePosixPath] = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        for entry in [*dirnames, *filenames]:
            if (base / entry).is_symlink():
                raise ArtifactError(f"{(base / entry).relative_to(root)}: links are not allowed")
        for filename in filenames:
            present.add(PurePosixPath((base / filename).relative_to(root).as_posix()))
    unlisted = sorted(str(p) for p in present - expected - {PurePosixPath(MANIFEST)})
    if unlisted:
        raise ArtifactError(f"files not listed in {MANIFEST}: {', '.join(unlisted)}")
    return len(expected)


# Orchestration


def make_readable(root: Path) -> None:
    """Folders 0755 and files 0644, so a non-root process can read the bundle."""
    root.chmod(0o755)
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            (Path(dirpath) / name).chmod(0o755)
        for name in filenames:
            (Path(dirpath) / name).chmod(0o644)


def fetch_bundle(entry: LockEntry, dest: Path, log: Any = print) -> Path:
    """Fetch one bundle into dest/<name>/<version>/ and return that folder."""
    final = dest / entry.name / entry.version
    if final.exists():
        try:
            count = verify_bundle(final, entry.name, entry.version)
        except ArtifactError as exc:
            raise ArtifactError(
                f"{entry.label}: existing {final} fails verification: {exc}"
            ) from exc
        log(f"{entry.label}: already present and verified ({count} files)")
        return final

    final.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{entry.name}-", dir=final.parent) as tmp:
        work = Path(tmp)
        archive = work / "bundle.archive"
        log(f"{entry.label}: downloading {entry.url}")
        try:
            download(entry.url, archive)
            actual = sha256_of(archive)
            if actual != entry.sha256:
                raise ArtifactError(f"archive sha256 {actual}, the lock says {entry.sha256}")
            unpacked = work / "unpacked"
            unpacked.mkdir()
            extract(archive, unpacked)
            root = bundle_root(unpacked)
            count = verify_bundle(root, entry.name, entry.version)
        except ArtifactError as exc:
            raise ArtifactError(f"{entry.label}: {exc}") from exc
        except (OSError, tarfile.TarError, zipfile.BadZipFile, EOFError) as exc:
            raise ArtifactError(f"{entry.label}: cannot unpack the archive: {exc}") from exc
        make_readable(root)
        os.replace(root, final)
    log(f"{entry.label}: verified {count} files into {final}")
    return final


def fetch_all(lock: Path, dest: Path, log: Any = print) -> list[Path]:
    entries = load_lock(lock)
    dest.mkdir(parents=True, exist_ok=True)
    if not entries:
        log(f"{lock}: no bundles listed; the API will answer 503 not_ready for model routes")
        return []
    return [fetch_bundle(entry, dest, log) for entry in entries]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    here = Path(__file__).resolve().parent
    parser.add_argument("--lock", type=Path, default=here / "artifacts.lock.json")
    parser.add_argument("--dest", type=Path, default=here.parent / "artifacts")
    args = parser.parse_args(argv)
    try:
        fetch_all(args.lock, args.dest)
    except ArtifactError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
