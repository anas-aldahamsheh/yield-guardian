"""Download the raw datasets and record their provenance.

Usage (from the repository root):

    python data/download.py secom
    python data/download.py wm811k
    python data/download.py all

Raw files land in data/raw/<dataset>/ (git-ignored). Every file's SHA-256, size,
source URL and retrieval time is written to data/manifest.json, which is committed,
so anyone can check that they are training on byte-identical data.

Only the standard library is used, plus the `kaggle` command for the WM-811K fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
MANIFEST = ROOT / "manifest.json"
USER_AGENT = "yield-guardian-data/1.0 (+https://github.com/anas-aldahamsheh/yield-guardian)"

DATASETS: dict[str, dict] = {
    "secom": {
        "title": "SECOM (UCI Machine Learning Repository, dataset 179)",
        "page": "https://archive.ics.uci.edu/dataset/179/secom",
        "urls": [
            "https://archive.ics.uci.edu/static/public/179/secom.zip",
        ],
        "files_fallback": [
            "https://archive.ics.uci.edu/ml/machine-learning-databases/secom/secom.data",
            "https://archive.ics.uci.edu/ml/machine-learning-databases/secom/secom_labels.data",
            "https://archive.ics.uci.edu/ml/machine-learning-databases/secom/secom.names",
        ],
        "expected_files": ["secom.data", "secom_labels.data"],
        "citation": "McCann, M. and Johnston, A. (2008). SECOM. UCI Machine Learning Repository.",
        "licence": "Check the dataset page and record it here (expected: CC BY 4.0).",
    },
    "wm811k": {
        "title": "WM-811K wafer maps (MIR Lab, National Taiwan University)",
        "page": "http://mirlab.org/dataSet/public/",
        "urls": [
            "http://mirlab.org/dataSet/public/WM-811K.zip",
        ],
        "kaggle_dataset": "qingyi/wm811k-wafer-map",
        "expected_files": ["LSWMD.pkl"],
        "citation": (
            "Wu, M.-J., Jang, J.-S. R. and Chen, J.-L. (2015). Wafer map failure pattern "
            "recognition and similarity ranking for large-scale data sets. IEEE Transactions "
            "on Semiconductor Manufacturing, 28(1), 1-12."
        ),
        "licence": "Research dataset. Record the licence shown at the source used.",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, target: Path, attempts: int = 4) -> bool:
    """Download url to target. Returns False if every attempt failed."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                for block in iter(lambda: response.read(1 << 20), b""):
                    out.write(block)
                    done += len(block)
                    if total:
                        print(f"\r  {done / total:6.1%} of {total / 1e6:.1f} MB", end="", flush=True)
            print()
            partial.replace(target)
            return True
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            wait = 2**attempt
            print(f"  attempt {attempt} failed for {url}: {error}. Retrying in {wait}s.")
            time.sleep(wait)
    partial.unlink(missing_ok=True)
    return False


def record(name: str, source: str, files: list[Path]) -> None:
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    spec = DATASETS[name]
    manifest[name] = {
        "title": spec["title"],
        "page": spec["page"],
        "source": source,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "citation": spec["citation"],
        "licence": spec["licence"],
        "files": [
            {"path": str(f.relative_to(ROOT)).replace("\\", "/"), "bytes": f.stat().st_size, "sha256": sha256(f)}
            for f in sorted(files)
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"  recorded {len(files)} files in {MANIFEST.relative_to(ROOT.parent)}")


def unzip(archive: Path, into: Path) -> list[Path]:
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(into)
        return [into / member for member in bundle.namelist() if not member.endswith("/")]


def download_secom() -> None:
    spec = DATASETS["secom"]
    folder = RAW / "secom"
    archive = folder / "secom.zip"
    for url in spec["urls"]:
        print(f"SECOM: trying {url}")
        if fetch(url, archive) and zipfile.is_zipfile(archive):
            files = unzip(archive, folder)
            record("secom", url, [archive, *files])
            return
    print("SECOM: archive unavailable, downloading the individual files")
    files = []
    for url in spec["files_fallback"]:
        target = folder / url.rsplit("/", 1)[-1]
        if not fetch(url, target):
            sys.exit(f"SECOM: could not download {url}")
        files.append(target)
    record("secom", "individual files: " + ", ".join(spec["files_fallback"]), files)


def download_wm811k() -> None:
    spec = DATASETS["wm811k"]
    folder = RAW / "wm811k"
    archive = folder / "WM-811K.zip"
    for url in spec["urls"]:
        print(f"WM-811K: trying {url}")
        if fetch(url, archive, attempts=2) and zipfile.is_zipfile(archive):
            files = unzip(archive, folder)
            record("wm811k", url, [archive, *files])
            return
        archive.unlink(missing_ok=True)
    if shutil.which("kaggle") is None:
        sys.exit("WM-811K: the original source failed and the `kaggle` command is not installed.")
    dataset = spec["kaggle_dataset"]
    print(f"WM-811K: falling back to Kaggle dataset {dataset}")
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run(["kaggle", "datasets", "download", "-d", dataset, "-p", str(folder)], check=True)
    archives = sorted(folder.glob("*.zip"))
    if not archives:
        sys.exit("WM-811K: Kaggle returned no archive")
    files = unzip(archives[0], folder)
    record("wm811k", f"https://www.kaggle.com/datasets/{dataset}", [archives[0], *files])


def check(name: str) -> None:
    missing = [f for f in DATASETS[name]["expected_files"] if not list((RAW / name).rglob(f))]
    if missing:
        sys.exit(f"{name}: expected files not found after download: {missing}")
    print(f"{name}: ok")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset", choices=["secom", "wm811k", "all"])
    args = parser.parse_args()
    names = ["secom", "wm811k"] if args.dataset == "all" else [args.dataset]
    for name in names:
        {"secom": download_secom, "wm811k": download_wm811k}[name]()
        check(name)


if __name__ == "__main__":
    main()
