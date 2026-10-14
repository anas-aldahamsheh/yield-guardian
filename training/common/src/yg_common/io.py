"""Deterministic writers: the same content always produces the same bytes.

``numpy.savez`` stamps every member with the current time, so two identical runs give
different files and different SHA-256 digests. ``save_npz`` fixes the timestamps and
stores members uncompressed, which makes the output byte-identical across runs and
independent of the zlib build.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

_EPOCH = (1980, 1, 1, 0, 0, 0)


def dumps_json(obj: Any) -> str:
    """JSON text with two-space indentation and a final newline. NaN is rejected."""
    return json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def write_json(path: str | Path, obj: Any) -> None:
    """Write ``obj`` as UTF-8 JSON (see ``dumps_json``), creating parent folders."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dumps_json(obj), encoding="utf-8")


def save_npz(path: str | Path, arrays: Mapping[str, npt.ArrayLike]) -> None:
    """Write arrays to an ``.npz`` file readable by ``numpy.load``, byte-deterministically.

    Object arrays are refused, so files never need ``allow_pickle=True`` to be read.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for key in sorted(arrays):
            array = np.asanyarray(arrays[key])
            if array.dtype == object:
                raise TypeError(f"array {key!r} has dtype object; use a fixed-width dtype")
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, array, allow_pickle=False)
            info = zipfile.ZipInfo(f"{key}.npy", date_time=_EPOCH)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            archive.writestr(info, buffer.getvalue())


def load_npz(path: str | Path) -> dict[str, npt.NDArray[Any]]:
    """Read every array of an ``.npz`` file into memory, without allowing pickles."""
    with np.load(Path(path), allow_pickle=False) as data:
        return {key: data[key] for key in data.files}
