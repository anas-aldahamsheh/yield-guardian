"""Finding and verifying bundles: every file must match the size and SHA-256 in MANIFEST.json."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from yield_guardian.contracts.base import BundleName, BundleRef
from yield_guardian.contracts.methods import BundleInfo

VERSION = re.compile(r"^v(\d+)$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class BundleError(Exception):
    """A bundle is missing, malformed or does not match its manifest."""


@dataclass(frozen=True, slots=True)
class VerifiedBundle:
    path: Path
    info: BundleInfo
    manifest: dict[str, Any]

    def file(self, name: str) -> Path:
        return self.path / name


def latest_version(root: Path, name: BundleName) -> Path:
    """The highest `v<N>` folder under `<root>/<name>/`."""
    base = root / name
    versions = (
        [
            (int(m.group(1)), d)
            for d in base.iterdir()
            if d.is_dir() and (m := VERSION.match(d.name))
        ]
        if base.is_dir()
        else []
    )
    if not versions:
        raise BundleError(f"No {name} bundle under {base}.")
    return max(versions)[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_bundle(path: Path, name: BundleName) -> VerifiedBundle:
    """Check MANIFEST.json and every file it lists; raise BundleError on the first problem."""
    manifest_path = path / "MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BundleError(f"{manifest_path}: {error}") from error
    if manifest.get("name") != name:
        raise BundleError(f"{manifest_path}: name is {manifest.get('name')!r}, expected {name!r}.")
    if manifest.get("version") != path.name:
        raise BundleError(f"{manifest_path}: version does not match the folder {path.name}.")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise BundleError(f"{manifest_path}: no files listed.")
    for entry in files:
        relative = PurePosixPath(str(entry.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise BundleError(f"{manifest_path}: unsafe path {entry.get('path')!r}.")
        target = path.joinpath(*relative.parts)
        if not target.is_file():
            raise BundleError(f"{name}/{path.name}: {relative} is missing.")
        if target.stat().st_size != entry.get("bytes"):
            raise BundleError(f"{name}/{path.name}: {relative} has the wrong size.")
        expected = str(entry.get("sha256", ""))
        if not HEX64.match(expected) or _sha256(target) != expected:
            raise BundleError(f"{name}/{path.name}: {relative} does not match its SHA-256.")
    try:
        ref = BundleRef(
            name=name,
            version=manifest["version"],
            created_at=datetime.fromisoformat(manifest["created_at"]),
            git_commit=manifest["git_commit"],
        )
    except (KeyError, ValueError) as error:
        raise BundleError(f"{manifest_path}: {error}") from error
    return VerifiedBundle(
        path=path, info=BundleInfo(bundle=ref, files=len(files), verified=True), manifest=manifest
    )
