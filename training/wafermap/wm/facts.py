"""W1 / D5: facts about WM-811K, measured from the converted Parquet file.

    uv run python -m wm.facts

Writes reports/wm811k_facts.json and reports/wm811k_facts.md.
"""

from __future__ import annotations

import json
from collections import Counter

import numpy as np
import pyarrow.parquet as pq

from wm.paths import PARQUET, RAW_PICKLE, REPORTS, sha256

ORIGINAL_COLUMNS = ["waferMap", "dieSize", "lotName", "waferIndex", "trianTestLabel", "failureType"]


def main() -> None:
    frame = pq.read_table(PARQUET).to_pandas()
    n = len(frame)
    labelled = frame["label"].notna()

    values: Counter[int] = Counter()
    for blob in frame["map"]:
        values.update(np.unique(np.frombuffer(blob, dtype=np.uint8)).tolist())
    shapes = Counter(zip(frame["height"], frame["width"], strict=True))

    split = frame["official_split"].fillna("<absent>")
    train_lots = set(frame.loc[split == "Training", "lot"])
    test_lots = set(frame.loc[split == "Test", "lot"])
    shared = train_lots & test_lots
    shared_wafers = frame[frame["lot"].isin(shared) & split.isin(["Training", "Test"])]

    # Is (lot, wafer_index) a unique key?
    duplicate_keys = int(frame.duplicated(["lot", "wafer_index"]).sum())
    wafers_per_lot = frame.groupby("lot").size()

    facts = {
        "source": {"pickle_sha256": sha256(RAW_PICKLE), "parquet_sha256": sha256(PARQUET)},
        "rows": n,
        "original_columns": ORIGINAL_COLUMNS,
        "note_on_columns": "The split column is spelled 'trianTestLabel' in the source (sic).",
        "unique_lots": int(frame["lot"].nunique()),
        "wafers_per_lot": {
            "min": int(wafers_per_lot.min()),
            "median": float(wafers_per_lot.median()),
            "max": int(wafers_per_lot.max()),
        },
        "duplicate_lot_wafer_index_pairs": duplicate_keys,
        "wafer_index_range": [int(frame["wafer_index"].min()), int(frame["wafer_index"].max())],
        "die_size_range": [float(frame["die_size"].min()), float(frame["die_size"].max())],
        "label_encoding": (
            "failureType is a nested array such as [['Center']]; unlabelled wafers hold an empty "
            "array (size 0), converted to null"
        ),
        "labelled_rows": int(labelled.sum()),
        "unlabelled_rows": int((~labelled).sum()),
        "failure_type_counts": {k: int(v) for k, v in frame["label"].value_counts().items()},
        "split_encoding": "trianTestLabel is a nested array such as [['Training']] or empty",
        "official_split_counts": {k: int(v) for k, v in split.value_counts().items()},
        "split_by_label": {
            s: {
                k: int(v)
                for k, v in frame.loc[split == s, "label"]
                .fillna("<unlabelled>")
                .value_counts()
                .items()
            }
            for s in split.unique()
        },
        "labelled_without_split": int((labelled & (split == "<absent>")).sum()),
        "split_without_label": int((~labelled & (split != "<absent>")).sum()),
        "map_value_set": sorted(values),
        "distinct_map_shapes": len(shapes),
        "most_common_map_shapes": [
            {"height": int(h), "width": int(w), "wafers": int(c)}
            for (h, w), c in shapes.most_common(15)
        ],
        "map_height_range": [int(frame["height"].min()), int(frame["height"].max())],
        "map_width_range": [int(frame["width"].min()), int(frame["width"].max())],
        "official_split_lot_overlap": {
            "lots_in_training": len(train_lots),
            "lots_in_test": len(test_lots),
            "lots_in_both": len(shared),
            "training_wafers_in_shared_lots": int(
                (shared_wafers["official_split"] == "Training").sum()
            ),
            "test_wafers_in_shared_lots": int((shared_wafers["official_split"] == "Test").sum()),
            "test_wafers_total": int((split == "Test").sum()),
        },
    }
    lot_number = frame["lot"].str.extract(r"^lot(\d+)$")[0].astype(int)
    per_lot = frame.assign(labelled=labelled).groupby("lot")["labelled"].agg(["sum", "size"])
    labelled_split_count = frame[labelled].groupby("lot")["official_split"].nunique()
    facts["lot_structure"] = {
        "lot_name_format": "lot<integer>, every name matches ^lot[0-9]+$",
        "lot_number_range": [int(lot_number.min()), int(lot_number.max())],
        "rows_sorted_by_lot_number": bool((lot_number.diff().fillna(0) >= 0).all()),
        "lots_contiguous_in_file": bool(
            (frame["lot"] != frame["lot"].shift()).sum() == frame["lot"].nunique()
        ),
        "lots_with_any_labelled_wafer": int((per_lot["sum"] > 0).sum()),
        "lots_fully_labelled": int((per_lot["sum"] == per_lot["size"]).sum()),
        "lots_partly_labelled": int(
            ((per_lot["sum"] > 0) & (per_lot["sum"] < per_lot["size"])).sum()
        ),
        "labelled_lots_spanning_both_official_splits": int((labelled_split_count > 1).sum()),
        "lot_number_range_by_official_split": {
            k: [int(v.min()), int(v.max())] for k, v in lot_number.groupby(split)
        },
        "note": (
            "WM-811K has no timestamps. Lot numbers increase through the file, and the official "
            "test lots are the higher-numbered ones, but lot number is not documented as time "
            "order."
        ),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "wm811k_facts.json").write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(facts, indent=2))


if __name__ == "__main__":
    main()
