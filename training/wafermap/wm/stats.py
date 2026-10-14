"""Metrics with lot-cluster bootstrap confidence intervals, calibration and paired tests.

Wafers of one lot are correlated, so every interval resamples lots (with replacement), not
wafers. A resample is represented by a weight per wafer: the number of times its lot was
drawn. Every metric below accepts such weights, so one resample costs one bincount.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import log_softmax, softmax

B_DEFAULT = 2000
CI_LEVEL = 0.95


# ---------------------------------------------------------------- weighted metrics


def confusion(y: np.ndarray, pred: np.ndarray, k: int, w: np.ndarray | None = None) -> np.ndarray:
    """Rows are true classes, columns predictions."""
    return np.bincount(y * k + pred, weights=w, minlength=k * k).reshape(k, k)


def per_class(cm: np.ndarray) -> dict[str, np.ndarray]:
    tp = np.diag(cm)
    support = cm.sum(1)
    predicted = cm.sum(0)
    with np.errstate(divide="ignore", invalid="ignore"):
        precision = np.where(predicted > 0, tp / predicted, 0.0)
        recall = np.where(support > 0, tp / support, np.nan)
        f1 = np.where(support > 0, np.where(tp > 0, 2 * tp / (support + predicted), 0.0), np.nan)
    return {"precision": precision, "recall": recall, "f1": f1, "support": support}


def macro_f1_from_cm(cm: np.ndarray) -> float:
    """Mean F1 over classes present in the (resampled) data."""
    return float(np.nanmean(per_class(cm)["f1"]))


# ---------------------------------------------------------------- bootstrap


def lot_weights(lots: np.ndarray, b: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (codes, counts): codes maps each wafer to its lot, counts[r, lot] = times the lot
    was drawn in resample r."""
    unique, codes = np.unique(lots, return_inverse=True)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(unique), size=(b, len(unique)))
    counts = np.zeros((b, len(unique)), dtype=np.float64)
    for r in range(b):
        counts[r] = np.bincount(draws[r], minlength=len(unique))
    return codes, counts


def estimate(
    value: float, samples: np.ndarray, n: int, lots: int, b: int, method: str | None = None
) -> dict:
    lo, hi = np.nanpercentile(samples, [100 * (1 - CI_LEVEL) / 2, 100 * (1 + CI_LEVEL) / 2])
    return {
        "value": float(value),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "ci_level": CI_LEVEL,
        "method": method or f"lot-cluster bootstrap, {b} resamples (percentile)",
        "n": int(n),
        "lots": int(lots),
    }


def bootstrap(
    stat: Callable[[np.ndarray | None], float],
    lots: np.ndarray,
    b: int = B_DEFAULT,
    seed: int = 0,
) -> dict:
    """stat(w) computes the statistic with per-wafer weights w (None = original data)."""
    codes, counts = lot_weights(lots, b, seed)
    samples = np.array([stat(counts[r][codes]) for r in range(b)])
    return estimate(stat(None), samples, len(lots), counts.shape[1], b)


def classification_report(
    y: np.ndarray,
    logits: np.ndarray,
    lots: np.ndarray,
    classes: list[str],
    b: int = B_DEFAULT,
    seed: int = 0,
) -> dict:
    """Macro-F1, accuracy, top-2 accuracy and per-class precision/recall/F1, all with
    lot-cluster bootstrap CIs, plus the confusion matrix."""
    k = len(classes)
    pred = logits.argmax(1)
    top2 = (np.argsort(-logits, axis=1)[:, :2] == y[:, None]).any(1).astype(float)
    correct = (pred == y).astype(float)
    codes, counts = lot_weights(lots, b, seed)

    def cm_of(w: np.ndarray | None) -> np.ndarray:
        return confusion(y, pred, k, w)

    full = cm_of(None)
    full_pc = per_class(full)
    samples_macro, samples_acc, samples_top2 = [], [], []
    samples_pc = {m: [] for m in ("precision", "recall", "f1")}
    for r in range(b):
        w = counts[r][codes]
        cm = cm_of(w)
        pc = per_class(cm)
        samples_macro.append(np.nanmean(pc["f1"]))
        samples_acc.append(np.average(correct, weights=w))
        samples_top2.append(np.average(top2, weights=w))
        for m in samples_pc:
            samples_pc[m].append(pc[m])
    n, nl, est = len(y), counts.shape[1], estimate
    report = {
        "macro_f1": est(np.nanmean(full_pc["f1"]), np.array(samples_macro), n, nl, b),
        "accuracy": est(correct.mean(), np.array(samples_acc), n, nl, b),
        "top2_accuracy": est(top2.mean(), np.array(samples_top2), n, nl, b),
        "per_class": {},
        "confusion_matrix": {"classes": classes, "rows_true_cols_pred": full.astype(int).tolist()},
    }
    for i, c in enumerate(classes):
        report["per_class"][c] = {
            "support": int(full_pc["support"][i]),
            **{
                m: est(full_pc[m][i], np.array(samples_pc[m])[:, i], n, nl, b)
                for m in ("precision", "recall", "f1")
            },
        }
    return report


def paired_difference(
    stat_a: Callable[[np.ndarray | None], float],
    stat_b: Callable[[np.ndarray | None], float],
    lots: np.ndarray,
    b: int = B_DEFAULT,
    seed: int = 0,
) -> dict:
    """Paired lot-cluster bootstrap of stat_a - stat_b on the same resamples. The two-sided
    p-value is twice the smaller tail mass of the bootstrap distribution beyond 0."""
    codes, counts = lot_weights(lots, b, seed)
    diffs = np.array([stat_a(counts[r][codes]) - stat_b(counts[r][codes]) for r in range(b)])
    p = min(1.0, 2 * min((diffs <= 0).mean(), (diffs >= 0).mean()))
    out = estimate(stat_a(None) - stat_b(None), diffs, len(lots), counts.shape[1], b)
    out["p_value_two_sided"] = float(max(p, 1 / b))
    out["p_value_note"] = f"bootstrap p; values below 1/{b} reported as 1/{b}"
    return out


# ---------------------------------------------------------------- calibration


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """Guo et al. (2017): one scalar T minimising validation NLL of softmax(logits / T)."""

    def nll(log_t: float) -> float:
        lp = log_softmax(logits / np.exp(log_t), axis=1)
        return float(-lp[np.arange(len(y)), y].mean())

    result = minimize_scalar(nll, bounds=(np.log(0.05), np.log(20.0)), method="bounded")
    return float(np.exp(result.x))


def reliability(
    probs: np.ndarray, y: np.ndarray, bins: int = 15, w: np.ndarray | None = None
) -> dict:
    """Expected calibration error (equal-width confidence bins) and the reliability table."""
    w = np.ones(len(y)) if w is None else w
    confidence = probs.max(1)
    correct = (probs.argmax(1) == y).astype(float)
    edges = np.linspace(0, 1, bins + 1)
    which = np.clip(np.digitize(confidence, edges[1:-1]), 0, bins - 1)
    total = w.sum()
    ece = 0.0
    table = []
    for i in range(bins):
        m = which == i
        weight = w[m].sum()
        if weight == 0:
            table.append({"lo": edges[i], "hi": edges[i + 1], "n": 0})
            continue
        acc = np.average(correct[m], weights=w[m])
        conf = np.average(confidence[m], weights=w[m])
        ece += weight / total * abs(acc - conf)
        table.append(
            {
                "lo": float(edges[i]),
                "hi": float(edges[i + 1]),
                "n": int(m.sum()),
                "accuracy": float(acc),
                "confidence": float(conf),
            }
        )
    return {"ece": float(ece), "bins": bins, "table": table}


def nll(probs: np.ndarray, y: np.ndarray) -> float:
    return float(-np.log(np.clip(probs[np.arange(len(y)), y], 1e-12, 1)).mean())


__all__ = ["softmax"]
