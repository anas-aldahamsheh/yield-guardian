"""W7: similar-wafer search quality, precision@10 by cosine similarity of embeddings.

    uv run python -m wm.similarity --split lot

Every labelled test wafer queries all other labelled test wafers. precision@10 is the share
of its 10 nearest neighbours with the same label. Wafers of one lot look alike, so we also
report the stricter variant that ignores neighbours from the query's own lot. Intervals
resample query lots (lot-cluster bootstrap).
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import torch

from wm import stats
from wm.common import CLASSES, RUNS, device, load_index, load_part
from wm.evaluate import SEEDS
from wm.paths import REPORTS

K = 10
EXTRA = 26  # a lot holds at most 25 wafers, so K + EXTRA candidates always leave K others


def neighbours(emb: np.ndarray, lot_codes: np.ndarray, exclude_same_lot: bool) -> np.ndarray:
    dev = device()
    gallery = torch.from_numpy(emb).to(dev)
    lots = torch.from_numpy(lot_codes).to(dev)
    out = np.empty((len(emb), K), dtype=np.int64)
    for start in range(0, len(emb), 1024):
        q = gallery[start : start + 1024]
        sim = q @ gallery.T
        idx = torch.arange(start, start + len(q), device=dev)
        sim[torch.arange(len(q), device=dev), idx] = -np.inf  # never the query itself
        if exclude_same_lot:
            sim[lots[idx][:, None] == lots[None, :]] = -np.inf
        out[start : start + len(q)] = sim.topk(K, dim=1).indices.cpu().numpy()
    return out


def evaluate(split: str) -> dict:
    index = load_index()
    test = load_part(index, split, "test")
    _, lot_codes = np.unique(test.lots, return_inverse=True)
    y = test.labels
    result: dict = {"split": split, "k": K, "queries": len(y), "seeds": {}}
    for seed in SEEDS:
        preds = np.load(RUNS / f"{split}-seed{seed}" / "preds.npz")
        assert np.array_equal(preds["test_rows"], test.rows)
        emb = preds["test_embedding"]
        entry = {}
        for variant, exclude in (("all_neighbours", False), ("other_lots_only", True)):
            nn = neighbours(emb, lot_codes, exclude)
            hit = (y[nn] == y[:, None]).mean(1)

            def micro(w: np.ndarray | None, hit: np.ndarray = hit) -> float:
                return float(np.average(hit, weights=w))

            def macro(w: np.ndarray | None, hit: np.ndarray = hit) -> float:
                ww = np.ones(len(y)) if w is None else w
                per = [
                    np.average(hit[y == c], weights=ww[y == c])
                    for c in range(len(CLASSES))
                    if ww[y == c].sum() > 0
                ]
                return float(np.mean(per))

            entry[variant] = {
                "micro_precision_at_10": stats.bootstrap(micro, test.lots, b=1000),
                "macro_precision_at_10": stats.bootstrap(macro, test.lots, b=1000),
                "per_class": {c: float(hit[y == i].mean()) for i, c in enumerate(CLASSES)},
            }
        result["seeds"][str(seed)] = entry
        print(seed, {v: entry[v]["macro_precision_at_10"]["value"] for v in entry})
    for variant in ("all_neighbours", "other_lots_only"):
        for agg in ("micro", "macro"):
            vals = [
                result["seeds"][str(s)][variant][f"{agg}_precision_at_10"]["value"] for s in SEEDS
            ]
            result[f"{variant}_{agg}_across_seeds"] = {
                "mean": float(np.mean(vals)),
                "sd": float(np.std(vals, ddof=1)),
            }
    (REPORTS / f"similarity_{split}.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["official", "lot"], required=True)
    evaluate(parser.parse_args().split)


if __name__ == "__main__":
    main()
