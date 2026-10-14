"""W2: the two evaluation splits, both grouped by lot.

    uv run python -m wm.splits

(a) ``official``: the train/test labels shipped with WM-811K (already lot-disjoint, see
    reports/wm811k_facts.md); validation is carved from official training by lot.
(b) ``lot``: all labelled wafers, lots assigned 70/15/15 to train/validation/test.

Both use StratifiedGroupKFold with 20 folds (lot = group, class = stratum, seed 20261014):
3 folds (15%) form each held-out part. Unlabelled wafers inherit their lot's split in
``split_lot_all`` (used only by the lot excursion tests, never for supervised training).

Writes data/processed/wm811k/splits.parquet (row, split_official, split_lot, split_lot_all) and
reports/splits.json.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from wm.paths import PROCESSED, REPORTS, sha256
from wm.preprocess import INDEX

SPLITS = PROCESSED / "splits.parquet"
SPLIT_SEED = 20261014
FOLDS = 20
HELD_OUT_FOLDS = 3


def fold_of(labels: pd.Series, lots: pd.Series) -> np.ndarray:
    folds = np.full(len(labels), -1)
    splitter = StratifiedGroupKFold(n_splits=FOLDS, shuffle=True, random_state=SPLIT_SEED)
    for k, (_, held) in enumerate(splitter.split(np.zeros(len(labels)), labels, lots)):
        folds[held] = k
    assert (folds >= 0).all()
    return folds


def build(index: pd.DataFrame) -> pd.DataFrame:
    labelled = index[index["label"].notna()]
    out = pd.DataFrame({"row": index["row"].to_numpy()}).set_index("row")
    out["split_official"] = None
    out["split_lot"] = None

    train = labelled[labelled["official_split"] == "Training"]
    folds = fold_of(train["label"], train["lot"])
    out.loc[train["row"], "split_official"] = np.where(
        folds < HELD_OUT_FOLDS, "validation", "train"
    )
    test = labelled[labelled["official_split"] == "Test"]
    out.loc[test["row"], "split_official"] = "test"

    folds = fold_of(labelled["label"], labelled["lot"])
    part = np.select(
        [folds < HELD_OUT_FOLDS, folds < 2 * HELD_OUT_FOLDS], ["test", "validation"], "train"
    )
    out.loc[labelled["row"], "split_lot"] = part
    lot_part = dict(zip(labelled["lot"], part, strict=True))
    out["split_lot_all"] = index.set_index("row")["lot"].map(lot_part)
    return out.reset_index()


def summary(index: pd.DataFrame, splits: pd.DataFrame) -> dict:
    frame = index.merge(splits, on="row")
    report: dict = {"seed": SPLIT_SEED, "folds": FOLDS, "held_out_folds": HELD_OUT_FOLDS}
    for key in ("official", "lot"):
        name = f"split_{key}"
        parts = frame[frame[name].notna()]
        lots_per_part = parts.groupby(name)["lot"].apply(set)
        overlap = {
            f"{a}&{b}": len(lots_per_part[a] & lots_per_part[b])
            for i, a in enumerate(lots_per_part.index)
            for b in lots_per_part.index[i + 1 :]
        }
        report[key] = {
            "wafers": {k: int(v) for k, v in parts[name].value_counts().items()},
            "lots": {k: len(v) for k, v in lots_per_part.items()},
            "lot_overlap": overlap,
            "class_counts": {
                part: {k: int(v) for k, v in grp["label"].value_counts().items()}
                for part, grp in parts.groupby(name)
            },
        }
    report["lot_all_wafers"] = {
        k: int(v)
        for k, v in frame["split_lot_all"].fillna("<lot has no labels>").value_counts().items()
    }
    return report


def load() -> pd.DataFrame:
    return pd.read_parquet(SPLITS)


def main() -> None:
    index = pd.read_parquet(INDEX)
    splits = build(index)
    splits.to_parquet(SPLITS, compression="zstd", index=False)
    report = summary(index, splits)
    report["splits_sha256"] = sha256(SPLITS)
    (REPORTS / "splits.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("official", "lot")}, indent=1)[:3000])


if __name__ == "__main__":
    main()
