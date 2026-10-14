"""Device, determinism, data access and run bookkeeping shared by every training script."""

from __future__ import annotations

import json
import os
import platform
import random
from dataclasses import dataclass
from importlib.metadata import version

import numpy as np
import pandas as pd
import torch

from wm import splits as split_module
from wm.paths import ARTIFACTS, MLRUNS, PROCESSED, git_commit, sha256
from wm.preprocess import CLASSES, INDEX, MAPS, load_maps

RUNS = ARTIFACTS.parent / "runs"


def device() -> torch.device:
    """CUDA on NVIDIA, and also on AMD: ROCm builds of PyTorch expose HIP as torch.cuda."""
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def amp_dtype(dev: torch.device) -> torch.dtype | None:
    if dev.type == "cuda" and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    return None


def seed_everything(seed: int) -> None:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    # Some CUDA kernels (e.g. adaptive pooling backward) have no deterministic variant; warn only.
    torch.use_deterministic_algorithms(True, warn_only=True)


@dataclass
class Part:
    rows: np.ndarray
    maps: np.ndarray  # uint8 [n, 64, 64]
    labels: np.ndarray  # int64 class index into the run's class list
    lots: np.ndarray  # str


def load_index() -> pd.DataFrame:
    return pd.read_parquet(INDEX).merge(split_module.load(), on="row")


def load_part(index: pd.DataFrame, split: str, part: str, classes: list[str] = CLASSES) -> Part:
    column = f"split_{split}"
    chosen = index[(index[column] == part) & index["label"].isin(classes)]
    rows = chosen["row"].to_numpy()
    maps = np.asarray(load_maps()[rows])
    lookup = {c: i for i, c in enumerate(classes)}
    labels = chosen["label"].map(lookup).to_numpy(dtype=np.int64)
    return Part(rows, maps, labels, chosen["lot"].to_numpy())


def data_fingerprint() -> dict[str, str]:
    meta = json.loads((PROCESSED / "maps64.json").read_text(encoding="utf-8"))
    return {
        "source_parquet_sha256": meta["source_parquet_sha256"],
        "maps64_sha256": meta["maps64_sha256"],
        "splits_sha256": sha256(split_module.SPLITS),
        "index_sha256": sha256(INDEX),
    }


def environment() -> dict:
    packages = ["torch", "numpy", "pandas", "scikit-learn", "scipy", "onnx", "onnxruntime"]
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "cuda": torch.version.cuda,
        "hip": getattr(torch.version, "hip", None),
        "packages": {p: version(p) for p in packages},
    }


def mlflow_setup(experiment: str):
    import mlflow

    MLRUNS.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri("sqlite:///" + (MLRUNS / "mlflow.db").as_posix())
    if mlflow.get_experiment_by_name(experiment) is None:
        mlflow.create_experiment(experiment, artifact_location=(MLRUNS / "artifacts").as_uri())
    mlflow.set_experiment(experiment)
    return mlflow


def run_tags() -> dict[str, str]:
    return {"git_commit": git_commit(), **data_fingerprint()}


__all__ = ["CLASSES", "MAPS", "RUNS"]
