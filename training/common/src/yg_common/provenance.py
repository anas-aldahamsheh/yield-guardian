"""Provenance: SHA-256 digests, git state, package versions and named seeds."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

_CHUNK = 1 << 20


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of a byte string."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hex SHA-256 of a file, read in 1 MiB chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(args: Sequence[str], cwd: Path) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603 - fixed executable and arguments, no shell
            [git, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    return completed.stdout


def git_commit(path: str | Path) -> str | None:
    """The 40-character commit hash checked out at ``path``, or None outside a repository."""
    out = _git(["rev-parse", "HEAD"], Path(path))
    if out is None:
        return None
    commit = out.strip()
    return commit if len(commit) == 40 else None


def git_toplevel(path: str | Path) -> Path | None:
    """Root directory of the git work tree containing ``path``."""
    out = _git(["rev-parse", "--show-toplevel"], Path(path))
    return Path(out.strip()) if out else None


def git_dirty(path: str | Path, pathspecs: Iterable[str] = ()) -> bool | None:
    """Whether tracked or untracked files under ``pathspecs`` differ from the commit.

    Returns None when ``path`` is not inside a git repository. Restrict ``pathspecs`` to
    the source that produced a result, so generated reports do not count as changes.
    """
    out = _git(["status", "--porcelain", "--untracked-files=all", "--", *pathspecs], Path(path))
    if out is None:
        return None
    return bool(out.strip())


def package_versions(names: Iterable[str]) -> dict[str, str | None]:
    """Installed version of each distribution (None when it is not installed)."""
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def environment_record(packages: Iterable[str]) -> dict[str, object]:
    """Python version, platform and package versions, for run records and manifests."""
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": package_versions(packages),
    }


def utc_now_iso() -> str:
    """Current UTC time as ISO 8601 with a ``Z`` suffix, to the second."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def derive_seed(master_seed: int, name: str) -> int:
    """A stable 31-bit seed for a named purpose, derived from a master seed.

    Different purposes (tuning, bootstrap, permutations) get independent, reproducible
    streams without hand-picked offsets: the seed is the first 31 bits of
    ``SHA-256("<master_seed>:<name>")``.
    """
    digest = hashlib.sha256(f"{master_seed}:{name}".encode()).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF
