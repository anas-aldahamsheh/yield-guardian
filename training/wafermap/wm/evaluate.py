"""W5: held-out evaluation of the three seeds on one split, plus the feature baseline.

    uv run python -m wm.evaluate --split lot

Temperature and every threshold are fit on validation; test is touched once, here.
Writes reports/metrics_<split>.json, predictions to artifacts/wafermap/runs/<run>/preds.npz
and reliability diagrams to artifacts/wafermap/figures/.
"""

from __future__ import annotations

import argparse
import json

import matplotlib as mpl
import numpy as np
import torch

mpl.use("Agg")
import matplotlib.pyplot as plt
from scipy.special import softmax

from wm import baseline, stats
from wm.common import (
    CLASSES,
    RUNS,
    device,
    environment,
    load_index,
    load_part,
    run_tags,
)
from wm.model import WaferNet
from wm.paths import ARTIFACTS, PROCESSED, REPORTS
from wm.train import predict

SEEDS = (0, 1, 2)
PRECISION_TARGETS = (0.95, 0.99)
FIGURES = ARTIFACTS.parent / "figures"


def load_model(name: str, num_classes: int, dev: torch.device) -> WaferNet:
    model = WaferNet(num_classes).to(dev)
    model.load_state_dict(torch.load(RUNS / name / "model.pt", map_location=dev))
    return model.eval()


def baseline_features(rows: np.ndarray, maps: np.ndarray) -> np.ndarray:
    """Cached per wafer row, so both splits reuse one computation."""
    cache = PROCESSED / "baseline_features.npz"
    store: dict[int, np.ndarray] = {}
    if cache.exists():
        data = np.load(cache)
        store = dict(zip(data["rows"].tolist(), data["features"], strict=True))
    missing = [i for i, r in enumerate(rows) if int(r) not in store]
    if missing:
        computed = baseline.feature_matrix(maps[missing])
        for i, f in zip(missing, computed, strict=True):
            store[int(rows[i])] = f
        keys = np.array(sorted(store))
        np.savez(cache, rows=keys, features=np.stack([store[k] for k in keys]))
    return np.stack([store[int(r)] for r in rows])


def selective(
    probs_val: np.ndarray, y_val: np.ndarray, probs: np.ndarray, y: np.ndarray, lots: np.ndarray
) -> list[dict]:
    """Auto-classification: accept a wafer when calibrated confidence >= t, with t the lowest
    threshold whose accepted precision on validation reaches the target."""
    out = []
    conf_val = probs_val.max(1)
    correct_val = probs_val.argmax(1) == y_val
    order = np.argsort(-conf_val)
    running = np.cumsum(correct_val[order]) / np.arange(1, len(order) + 1)
    conf = probs.max(1)
    correct = (probs.argmax(1) == y).astype(float)
    # "none" dominates, so overall precision says little about defects: also report the
    # wafers whose true class is a defect pattern.
    defect = (y != CLASSES.index("none")).astype(float)
    for target in PRECISION_TARGETS:
        ok = np.nonzero(running >= target)[0]
        if len(ok) == 0:
            out.append({"target_precision": target, "threshold": None})
            continue
        threshold = float(conf_val[order][ok.max()])
        accepted = (conf >= threshold).astype(float)

        def coverage(w: np.ndarray | None, a: np.ndarray = accepted) -> float:
            return float(np.average(a, weights=w))

        def precision(w: np.ndarray | None, a: np.ndarray = accepted) -> float:
            ww = a if w is None else a * w
            return float(np.average(correct, weights=ww)) if ww.sum() else np.nan

        def defect_coverage(w: np.ndarray | None, a: np.ndarray = accepted) -> float:
            ww = defect if w is None else defect * w
            return float(np.average(a, weights=ww))

        def defect_precision(w: np.ndarray | None, a: np.ndarray = accepted) -> float:
            ww = a * defect if w is None else a * defect * w
            return float(np.average(correct, weights=ww)) if ww.sum() else np.nan

        out.append(
            {
                "target_precision": target,
                "threshold": threshold,
                "validation_coverage": float((conf_val >= threshold).mean()),
                "test_coverage": stats.bootstrap(coverage, lots),
                "test_precision": stats.bootstrap(precision, lots),
                "test_defect_wafers": int(defect.sum()),
                "test_defect_coverage": stats.bootstrap(defect_coverage, lots),
                "test_defect_accuracy_of_accepted": stats.bootstrap(defect_precision, lots),
            }
        )
    return out


def reliability_figure(before: dict, after: dict, title: str, path) -> None:
    fig, ax = plt.subplots(figsize=(4.2, 4.2), dpi=150)
    ax.plot([0, 1], [0, 1], color="#888", lw=1, ls="--")
    for rel, label in ((before, "raw"), (after, "temperature-scaled")):
        rows = [r for r in rel["table"] if r["n"]]
        ax.plot(
            [r["confidence"] for r in rows],
            [r["accuracy"] for r in rows],
            marker="o",
            ms=3,
            label=f"{label} (ECE {rel['ece']:.3f})",
        )
    ax.set(xlabel="confidence", ylabel="accuracy", title=title, xlim=(0, 1), ylim=(0, 1))
    ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def evaluate(split: str) -> dict:
    dev = device()
    index = load_index()
    train = load_part(index, split, "train")
    val = load_part(index, split, "validation")
    test = load_part(index, split, "test")
    k = len(CLASSES)
    result: dict = {
        "split": split,
        "classes": CLASSES,
        "test_wafers": len(test.labels),
        "test_lots": len(set(test.lots)),
        "validation_wafers": len(val.labels),
        "seeds": {},
        "tags": run_tags(),
        "environment": environment(),
    }
    seed_preds = {}
    for seed in SEEDS:
        name = f"{split}-seed{seed}"
        model = load_model(name, k, dev)
        history = json.loads((RUNS / name / "history.json").read_text(encoding="utf-8"))
        val_logits, val_emb = predict(model, torch.from_numpy(val.maps), dev)
        test_logits, test_emb = predict(model, torch.from_numpy(test.maps), dev)
        np.savez(
            RUNS / name / "preds.npz",
            val_rows=val.rows,
            val_logits=val_logits,
            val_embedding=val_emb,
            test_rows=test.rows,
            test_logits=test_logits,
            test_embedding=test_emb,
        )
        temperature = stats.fit_temperature(val_logits, val.labels)
        (RUNS / name / "calibration.json").write_text(
            json.dumps({"method": "temperature", "temperature": temperature}), encoding="utf-8"
        )
        p_raw = softmax(test_logits, axis=1)
        p_cal = softmax(test_logits / temperature, axis=1)
        rel_raw = stats.reliability(p_raw, test.labels)
        rel_cal = stats.reliability(p_cal, test.labels)
        ece_cal = stats.bootstrap(
            lambda w, p=p_cal: stats.reliability(p, test.labels, w=w)["ece"], test.lots, b=500
        )
        reliability_figure(
            rel_raw, rel_cal, f"{split} split, seed {seed}", FIGURES / f"reliability-{name}.png"
        )
        p_val_cal = softmax(val_logits / temperature, axis=1)
        result["seeds"][str(seed)] = {
            "best_epoch": history["best"]["epoch"],
            "epochs_run": history["epochs_run"],
            "validation_macro_f1": history["best"]["macro_f1"],
            "test": stats.classification_report(test.labels, test_logits, test.lots, CLASSES),
            "calibration": {
                "temperature": temperature,
                "test_ece_raw": rel_raw["ece"],
                "test_ece_calibrated": ece_cal,
                "test_nll_raw": stats.nll(p_raw, test.labels),
                "test_nll_calibrated": stats.nll(p_cal, test.labels),
                "reliability_calibrated": rel_cal,
            },
            "auto_classification": selective(p_val_cal, val.labels, p_cal, test.labels, test.lots),
        }
        seed_preds[seed] = test_logits.argmax(1)
        print(f"{name}: test macro-F1 {result['seeds'][str(seed)]['test']['macro_f1']}")

    def spread(path: list[str]) -> dict:
        values = []
        for s in SEEDS:
            node = result["seeds"][str(s)]
            for p in path:
                node = node[p]
            values.append(node["value"] if isinstance(node, dict) else node)
        return {
            "mean": float(np.mean(values)),
            "sd": float(np.std(values, ddof=1)),
            "values": values,
        }

    result["across_seeds"] = {
        "macro_f1": spread(["test", "macro_f1"]),
        "accuracy": spread(["test", "accuracy"]),
        "top2_accuracy": spread(["test", "top2_accuracy"]),
        "ece_calibrated": spread(["calibration", "test_ece_calibrated"]),
        "per_class_f1": {c: spread(["test", "per_class", c, "f1"]) for c in CLASSES},
        "note": "mean and sample standard deviation (ddof=1) over 3 training seeds",
    }

    # Baseline: logistic regression on radial and density features.
    f_train = baseline_features(train.rows, train.maps)
    f_val = baseline_features(val.rows, val.maps)
    f_test = baseline_features(test.rows, test.maps)
    clf, tuning = baseline.fit(f_train, train.labels, f_val, val.labels, k)
    base_logits = np.log(np.clip(clf.predict_proba(f_test), 1e-12, 1))
    base_pred = base_logits.argmax(1)
    result["baseline"] = {
        "model": "multinomial logistic regression, class_weight=balanced, standardised features",
        "features": baseline.FEATURE_NAMES,
        "tuning": tuning,
        "test": stats.classification_report(test.labels, base_logits, test.lots, CLASSES),
    }

    def macro_of(pred: np.ndarray):
        return lambda w: stats.macro_f1_from_cm(stats.confusion(test.labels, pred, k, w))

    result["paired_cnn_minus_baseline_macro_f1"] = {
        str(s): stats.paired_difference(macro_of(seed_preds[s]), macro_of(base_pred), test.lots)
        for s in SEEDS
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"metrics_{split}.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["official", "lot"], required=True)
    args = parser.parse_args()
    result = evaluate(args.split)
    print(json.dumps(result["across_seeds"]["macro_f1"]))
    print(json.dumps(result["baseline"]["test"]["macro_f1"]))


if __name__ == "__main__":
    main()
