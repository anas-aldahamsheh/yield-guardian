"""W8: lot excursion tests, stacked failure maps and per-wafer join-count tests.

    uv run python -m wm.lots --model lot-seed0

1. The deployed model labels every wafer (labelled or not): its predicted pattern, or
   "unknown" when the energy score is above the W6 threshold.
2. Reference rates come from the validation lots (all their wafers): the model never trained
   on them, so their predicted rates carry the same model errors as the tested lots.
3. Tested lots are those the model never saw: lot-grouped test lots and lots with no labels.
   Per lot and pattern (8 defect classes + unknown): one-sided binomial test
   P(X >= k | n, p_ref), then Benjamini-Hochberg at q = 0.05 over all lot x pattern tests.
4. Stacked failure map per lot: per die position, the share of wafers in which it failed.
5. Join-count test per wafer (Cliff and Ord, 1981): number of rook-adjacent fail-fail die
   pairs, against 999 random permutations of the fail labels over the wafer's dies.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq
import torch
from scipy.special import softmax
from scipy.stats import binom
from statsmodels.stats.multitest import multipletests

from wm.common import CLASSES, RUNS, device, load_index
from wm.evaluate import load_model
from wm.ood import energy
from wm.paths import PARQUET, PROCESSED, REPORTS
from wm.preprocess import load_maps
from wm.train import predict

PATTERNS = [*CLASSES[:-1], "unknown"]
FDR_Q = 0.05
PERMUTATIONS = 999


def predict_all(name: str) -> pd.DataFrame:
    path = PROCESSED / f"predictions-{name}.parquet"  # written for inspection, never reused
    dev = device()
    model = load_model(name, len(CLASSES), dev)
    calibration = json.loads((RUNS / name / "calibration.json").read_text(encoding="utf-8"))
    ood = json.loads((RUNS / name / "ood.json").read_text(encoding="utf-8"))
    maps = load_maps()
    logits = []
    for start in range(0, len(maps), 65536):
        chunk = torch.from_numpy(np.asarray(maps[start : start + 65536]))
        logits.append(predict(model, chunk, dev, batch=4096)[0])
    z = np.concatenate(logits)
    probs = softmax(z / calibration["temperature"], axis=1)
    e = energy(z)
    pred = np.array(CLASSES)[probs.argmax(1)]
    unknown = e > ood["energy"]["threshold"]
    frame = pd.DataFrame(
        {
            "row": np.arange(len(z), dtype=np.int32),
            "predicted": pred,
            "confidence": probs.max(1).astype(np.float32),
            "energy": e.astype(np.float32),
            "unknown": unknown,
            "pattern": np.where(unknown, "unknown", pred),
        }
    )
    frame.to_parquet(path, compression="zstd", index=False)
    return frame


def excursions(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    reference = frame[frame["split_lot_all"] == "validation"]
    p_ref = {p: float((reference["pattern"] == p).mean()) for p in PATTERNS}
    tested = frame[frame["split_lot_all"].isna() | (frame["split_lot_all"] == "test")]
    counts = pd.crosstab(tested["lot"], tested["pattern"]).reindex(columns=PATTERNS, fill_value=0)
    n = tested.groupby("lot").size().reindex(counts.index)
    records = []
    for p in PATTERNS:
        k = counts[p].to_numpy()
        pv = binom.sf(k - 1, n.to_numpy(), p_ref[p])
        records.append(
            pd.DataFrame(
                {
                    "lot": counts.index,
                    "pattern": p,
                    "wafers": n.to_numpy(),
                    "count": k,
                    "expected_rate": p_ref[p],
                    "p_value": pv,
                }
            )
        )
    tests = pd.concat(records, ignore_index=True)
    reject, q, _, _ = multipletests(tests["p_value"], alpha=FDR_Q, method="fdr_bh")
    tests["q_value"] = q
    tests["flagged"] = reject
    summary = {
        "reference": {
            "lots": int(reference["lot"].nunique()),
            "wafers": len(reference),
            "pattern_rates": p_ref,
        },
        "tested": {
            "lots": int(tested["lot"].nunique()),
            "wafers": len(tested),
            "tests": len(tests),
        },
        "flagged_lots": int(tests.loc[tests["flagged"], "lot"].nunique()),
        "flagged_tests_by_pattern": {
            p: int(tests.loc[tests["flagged"] & (tests["pattern"] == p)].shape[0]) for p in PATTERNS
        },
        "method": "one-sided binomial P(X>=k), Benjamini-Hochberg over all lot x pattern tests",
        "fdr_q": FDR_Q,
    }
    return tests, summary


def join_count(grid: np.ndarray, rng: np.random.Generator) -> dict:
    """Rook-adjacent fail-fail joins among die cells, with a permutation p-value."""
    die = grid > 0
    position = -np.ones(grid.shape, dtype=np.int64)
    position[die] = np.arange(die.sum())
    pairs = []
    for a, b in ((position[:, :-1], position[:, 1:]), (position[:-1, :], position[1:, :])):
        ok = (a >= 0) & (b >= 0)
        pairs.append(np.stack([a[ok], b[ok]], 1))
    pairs = np.concatenate(pairs)
    fail = (grid[die] == 2).astype(np.int8)
    observed = int((fail[pairs[:, 0]] & fail[pairs[:, 1]]).sum())
    if fail.sum() < 2 or len(pairs) == 0:
        return {
            "bb": observed,
            "fails": int(fail.sum()),
            "dies": int(die.sum()),
            "expected": None,
            "z": None,
            "p": None,
        }
    perms = rng.permuted(np.tile(fail, (PERMUTATIONS, 1)), axis=1)
    null = (perms[:, pairs[:, 0]] & perms[:, pairs[:, 1]]).sum(1)
    sd = null.std(ddof=1)
    return {
        "bb": observed,
        "fails": int(fail.sum()),
        "dies": int(die.sum()),
        "expected": float(null.mean()),
        "z": float((observed - null.mean()) / sd) if sd > 0 else None,
        "p": float((1 + (null >= observed).sum()) / (1 + PERMUTATIONS)),
    }


def original_maps(rows: np.ndarray) -> dict[int, np.ndarray]:
    table = pq.read_table(PARQUET, filters=pc.field("row").isin(rows.tolist()))
    out = {}
    for r, h, w, blob in zip(
        table["row"].to_pylist(),
        table["height"].to_pylist(),
        table["width"].to_pylist(),
        table["map"].to_pylist(),
        strict=True,
    ):
        out[r] = np.frombuffer(blob, dtype=np.uint8).reshape(h, w)
    return out


def stacked(grids: list[np.ndarray]) -> dict:
    shapes = {g.shape for g in grids}
    if len(shapes) != 1:
        return {"height": None, "width": None, "note": "wafers in this lot differ in shape"}
    die = np.stack([g > 0 for g in grids]).sum(0)
    fail = np.stack([g == 2 for g in grids]).sum(0)
    freq = np.where(die > 0, fail / np.maximum(die, 1), -1.0)
    h, w = grids[0].shape
    return {
        "height": h,
        "width": w,
        "wafers": len(grids),
        "fail_frequency": np.round(freq, 4).ravel().tolist(),
        "note": "row-major; -1 where no wafer has a die",
    }


def join_count_validation(frame: pd.DataFrame, rng: np.random.Generator) -> dict:
    """Sanity check on labelled lot-test wafers: Random should look unclustered, local
    patterns clustered. Up to 300 wafers per defect class."""
    out = {}
    test = frame[(frame["split_lot"] == "test") & frame["label"].isin(CLASSES[:-1])]
    for c in CLASSES[:-1]:
        rows = test.loc[test["label"] == c, "row"].to_numpy()
        rows = rng.choice(rows, size=min(300, len(rows)), replace=False)
        grids = original_maps(np.sort(rows))
        res = [join_count(g, rng) for g in grids.values()]
        ps = [r["p"] for r in res if r["p"] is not None]
        zs = [r["z"] for r in res if r["z"] is not None]
        out[c] = {
            "wafers": len(res),
            "share_p_below_0.05": float(np.mean(np.array(ps) < 0.05)),
            "median_z": float(np.median(zs)),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="lot-seed0")
    parser.add_argument("--demo-lots", type=int, default=300)
    args = parser.parse_args()
    rng = np.random.default_rng(20261014)
    index = load_index()
    frame = index.merge(predict_all(args.model), on="row")
    tests, summary = excursions(frame)
    summary["model"] = args.model

    flagged = sorted(tests.loc[tests["flagged"], "lot"].unique())
    others = sorted(set(tests["lot"]) - set(flagged))
    fill = max(0, args.demo_lots - len(flagged))
    demo = sorted(flagged + rng.choice(others, size=fill, replace=False).tolist())
    summary["demo"] = {
        "lots": len(demo),
        "flagged_included": len(flagged),
        "unflagged_random": fill,
        "selection_seed": 20261014,
    }

    demo_frame = frame[frame["lot"].isin(demo)].sort_values("row")
    grids = original_maps(demo_frame["row"].to_numpy())
    lots_out = {}
    for lot, group in demo_frame.groupby("lot", sort=True):
        wafers = []
        for row in group.itertuples():
            jc = join_count(grids[row.row], rng)
            wafers.append(
                {
                    "wafer_id": f"{lot}-{row.wafer_index}",
                    "wafer_index": int(row.wafer_index),
                    "label": row.label,
                    "predicted": row.predicted,
                    "confidence": float(row.confidence),
                    "energy": float(row.energy),
                    "unknown": bool(row.unknown),
                    "join_count": jc,
                }
            )
        t = tests[tests["lot"] == lot]
        lots_out[lot] = {
            "wafers": wafers,
            "pattern_counts": {p: int(c) for p, c in zip(t["pattern"], t["count"], strict=True)},
            "tests": [
                {
                    "pattern": r.pattern,
                    "count": int(r.count),
                    "wafers": int(r.wafers),
                    "expected_rate": float(r.expected_rate),
                    "p": float(r.p_value),
                    "q": float(r.q_value),
                    "flagged": bool(r.flagged),
                }
                for r in t.itertuples()
            ],
            "flagged": bool(t["flagged"].any()),
            "stacked_failure_map": stacked([grids[r] for r in group["row"]]),
        }
    jc_all = [w["join_count"] for lot in lots_out.values() for w in lot["wafers"]]
    summary["join_count_demo"] = {
        "wafers": len(jc_all),
        "tested": sum(j["p"] is not None for j in jc_all),
        "share_p_below_0.05": float(np.mean([j["p"] < 0.05 for j in jc_all if j["p"] is not None])),
        "permutations": PERMUTATIONS,
        "adjacency": "rook (4-neighbour) among die cells",
    }
    summary["join_count_validation"] = join_count_validation(frame, rng)
    out_dir = PROCESSED / "demo"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "lots.json").write_text(json.dumps(lots_out), encoding="utf-8")
    tests.to_parquet(PROCESSED / "lot_tests.parquet", compression="zstd", index=False)
    (REPORTS / "lots.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
