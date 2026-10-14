"""Convert WM-811K's LSWMD.pkl into a version-independent Parquet file.

LSWMD.pkl was written by pandas 0.x and references modules (``pandas.indexes``)
that pandas 2 no longer has, so it is read once in an isolated environment:

    uv venv data/interim/.venv-wm811k --python 3.10
    uv pip install --python data/interim/.venv-wm811k "pandas==1.5.3" "numpy<2" "pyarrow<18"
    data/interim/.venv-wm811k/Scripts/python -I training/wafermap/scripts/convert_lswmd.py \
        data/raw/wm811k/LSWMD.pkl data/interim/wm811k/wm811k.parquet

Output columns (one row per wafer, original row order kept in ``row``):
    row int32, lot string, wafer_index int32, die_size float64,
    label string (null when unlabelled), official_split string (null when absent),
    height int16, width int16, map binary (uint8, row-major, values as stored: 0, 1, 2)

Nothing is filtered or relabelled here; parsing decisions are reported by the
facts script, not hidden in this one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA = pa.schema(
    [
        ("row", pa.int32()),
        ("lot", pa.string()),
        ("wafer_index", pa.int32()),
        ("die_size", pa.float64()),
        ("label", pa.string()),
        ("official_split", pa.string()),
        ("height", pa.int16()),
        ("width", pa.int16()),
        ("map", pa.binary()),
    ]
)
BATCH = 50_000


def unwrap(value: object) -> str | None:
    """Labels are stored as nested arrays, e.g. [['Center']], or an empty array when absent."""
    array = np.asarray(value, dtype=object).ravel()
    if array.size == 0:
        return None
    if array.size != 1:
        raise ValueError(f"unexpected label shape: {value!r}")
    return str(array[0])


def main(source: Path, target: Path) -> None:
    frame = pd.read_pickle(source)
    print(f"pandas {pd.__version__}: {len(frame)} rows, columns {list(frame.columns)}")
    expected = {"waferMap", "dieSize", "lotName", "waferIndex", "trianTestLabel", "failureType"}
    missing = expected - set(frame.columns)
    if missing:
        raise SystemExit(f"missing columns: {sorted(missing)}")

    target.parent.mkdir(parents=True, exist_ok=True)
    with pq.ParquetWriter(target, SCHEMA, compression="zstd") as writer:
        for start in range(0, len(frame), BATCH):
            chunk = frame.iloc[start : start + BATCH]
            maps = [np.asarray(m) for m in chunk["waferMap"]]
            for m in maps:
                if (
                    m.ndim != 2
                    or m.min() < 0
                    or m.max() > 255
                    or not np.array_equal(m, m.astype(np.uint8))
                ):
                    raise ValueError("map is not a 2-D array of small non-negative integers")
            if not np.array_equal(chunk["waferIndex"], chunk["waferIndex"].astype(np.int32)):
                raise ValueError("non-integer waferIndex")
            table = pa.table(
                {
                    "row": np.arange(start, start + len(chunk), dtype=np.int32),
                    "lot": chunk["lotName"].astype(str).tolist(),
                    "wafer_index": chunk["waferIndex"].astype(np.int32).to_numpy(),
                    "die_size": chunk["dieSize"].astype(np.float64).to_numpy(),
                    "label": [unwrap(v) for v in chunk["failureType"]],
                    "official_split": [unwrap(v) for v in chunk["trianTestLabel"]],
                    "height": np.array([m.shape[0] for m in maps], dtype=np.int16),
                    "width": np.array([m.shape[1] for m in maps], dtype=np.int16),
                    "map": [np.ascontiguousarray(m, dtype=np.uint8).tobytes() for m in maps],
                },
                schema=SCHEMA,
            )
            writer.write_table(table)
            print(f"  wrote rows {start}..{start + len(chunk) - 1}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
