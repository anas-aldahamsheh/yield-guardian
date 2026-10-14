"""W1: nearest-neighbour resize of every wafer map to 64x64, cached as a uint8 memmap.

    uv run python -m wm.preprocess

Nearest-neighbour resampling copies an existing cell for every output cell, so no value
is ever invented between 0 (no die), 1 (pass) and 2 (fail). One-hot encoding happens on
the GPU at training time (see ``one_hot``).

Writes data/processed/wm811k/maps64.npy (uint8 [811457, 64, 64]) and index.parquet
(row, lot, wafer_index, die_size, label, official_split, height, width).
"""

from __future__ import annotations

import json

import numpy as np
import pyarrow.parquet as pq
import torch

from wm.paths import PARQUET, PROCESSED, sha256

SIZE = 64
CLASSES = [
    "Center",
    "Donut",
    "Edge-Loc",
    "Edge-Ring",
    "Loc",
    "Near-full",
    "Random",
    "Scratch",
    "none",
]
CHANNELS = ["no_die", "pass", "fail"]
MAPS = PROCESSED / "maps64.npy"
INDEX = PROCESSED / "index.parquet"


def nearest_indices(source: int, size: int = SIZE) -> np.ndarray:
    """Source index sampled by each output cell: the cell whose centre is nearest."""
    centres = (np.arange(size) + 0.5) * source / size
    return np.minimum(np.floor(centres).astype(np.int64), source - 1)


def resize_nearest(grid: np.ndarray, size: int = SIZE) -> np.ndarray:
    rows = nearest_indices(grid.shape[0], size)
    cols = nearest_indices(grid.shape[1], size)
    return grid[np.ix_(rows, cols)]


def one_hot(maps: torch.Tensor) -> torch.Tensor:
    """uint8 [N, H, W] with values 0..2 -> float32 [N, 3, H, W] (no_die, pass, fail)."""
    return torch.nn.functional.one_hot(maps.long(), num_classes=3).permute(0, 3, 1, 2).float()


def load_maps() -> np.ndarray:
    return np.load(MAPS, mmap_mode="r")


def main() -> None:
    table = pq.read_table(PARQUET)
    n = table.num_rows
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out = np.lib.format.open_memmap(MAPS, mode="w+", dtype=np.uint8, shape=(n, SIZE, SIZE))
    position = 0
    for batch in table.to_batches(max_chunksize=50_000):
        heights = batch.column("height").to_numpy()
        widths = batch.column("width").to_numpy()
        blobs = batch.column("map").to_pylist()
        for blob, h, w in zip(blobs, heights, widths, strict=True):
            grid = np.frombuffer(blob, dtype=np.uint8).reshape(int(h), int(w))
            out[position] = resize_nearest(grid)
            position += 1
        print(f"  resized {position}/{n}")
    out.flush()
    del out
    pq.write_table(table.drop_columns(["map"]), INDEX, compression="zstd")
    meta = {
        "source_parquet_sha256": sha256(PARQUET),
        "maps64_sha256": sha256(MAPS),
        "rows": n,
        "size": SIZE,
        "resize": "nearest (output cell centre mapped to the source cell containing it)",
    }
    (PROCESSED / "maps64.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(meta)


if __name__ == "__main__":
    main()
