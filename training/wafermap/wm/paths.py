"""Repository paths and data fingerprints shared by every wafer-map script."""

from __future__ import annotations

import hashlib
import subprocess
from functools import cache
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # training/wafermap
REPO = HERE.parent.parent
RAW_PICKLE = REPO / "data" / "raw" / "wm811k" / "LSWMD.pkl"
PARQUET = REPO / "data" / "interim" / "wm811k" / "wm811k.parquet"
PROCESSED = REPO / "data" / "processed" / "wm811k"
REPORTS = HERE / "reports"
ARTIFACTS = REPO / "artifacts" / "wafermap" / "v1"
MLRUNS = REPO / "mlruns"


@cache
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit() -> str:
    """Current commit, with a '-dirty' suffix when tracked files have uncommitted changes."""
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return commit + ("-dirty" if dirty else "")
