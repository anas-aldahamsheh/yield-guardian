"""W6: unknown-pattern scores and the leave-one-class-out (LOCO) test.

    uv run python -m wm.ood fit --split lot --seed 0   # thresholds for a trained model
    uv run python -m wm.ood loco   # needs the 8 loco-* runs (wm.train --exclude)

Energy score (Liu et al., 2020): E(x) = -logsumexp(logits). Higher means less familiar.
Cross-check: Mahalanobis distance (Lee et al., 2018) of the L2-normalised embedding to the
nearest class mean, with a shared, Ledoit-Wolf-shrunk covariance from training embeddings.
Both thresholds are set so that 95% of validation wafers (in distribution) are accepted.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import torch
from scipy.special import logsumexp
from sklearn.covariance import LedoitWolf
from sklearn.metrics import roc_auc_score

from wm import stats
from wm.common import CLASSES, RUNS, Part, device, load_index, load_part, run_tags
from wm.evaluate import load_model
from wm.paths import REPORTS
from wm.preprocess import load_maps
from wm.train import predict

ID_RECALL = 0.95
LOCO_EPOCHS = 12
LOCO_SEED = 0


def energy(logits: np.ndarray) -> np.ndarray:
    return -logsumexp(logits, axis=1)


def fit_mahalanobis(embeddings: np.ndarray, labels: np.ndarray, k: int) -> dict[str, np.ndarray]:
    means = np.stack([embeddings[labels == c].mean(0) for c in range(k)])
    centred = embeddings - means[labels]
    precision = LedoitWolf(assume_centered=True).fit(centred).precision_
    return {"class_means": means.astype(np.float32), "precision": precision.astype(np.float32)}


def mahalanobis(embeddings: np.ndarray, params: dict[str, np.ndarray]) -> np.ndarray:
    means, precision = params["class_means"], params["precision"]
    best = np.full(len(embeddings), np.inf)
    for mu in means:
        d = embeddings - mu
        best = np.minimum(best, np.einsum("ij,jk,ik->i", d, precision, d))
    return best


def threshold(scores_val: np.ndarray) -> float:
    return float(np.quantile(scores_val, ID_RECALL))


def class_thresholds(scores_val: np.ndarray, pred_val: np.ndarray, k: int) -> np.ndarray:
    """Variant: one threshold per predicted class, each accepting 95% of the validation wafers
    predicted as that class, so rare classes are not flagged more often than common ones."""
    return np.array(
        [
            threshold(scores_val[pred_val == c]) if (pred_val == c).any() else np.inf
            for c in range(k)
        ]
    )


def scores_for(name: str, split: str, classes: list[str], parts: dict) -> dict:
    """Energy and Mahalanobis scores for each named part (uint8 maps) under one model."""
    dev = device()
    model = load_model(name, len(classes), dev)
    out = {}
    for key, part in parts.items():
        logits, emb = predict(model, torch.from_numpy(part.maps), dev)
        out[key] = {"logits": logits, "embedding": emb}
    return out


def fit(split: str, seed: int) -> dict:
    index = load_index()
    parts = {p: load_part(index, split, p) for p in ("train", "validation", "test")}
    name = f"{split}-seed{seed}"
    s = scores_for(name, split, CLASSES, parts)
    params = fit_mahalanobis(s["train"]["embedding"], parts["train"].labels, len(CLASSES))
    e_val, e_test = energy(s["validation"]["logits"]), energy(s["test"]["logits"])
    m_val = mahalanobis(s["validation"]["embedding"], params)
    m_test = mahalanobis(s["test"]["embedding"], params)
    t_e, t_m = threshold(e_val), threshold(m_val)
    y = parts["test"].labels
    pred_val = s["validation"]["logits"].argmax(1)
    pred_test = s["test"]["logits"].argmax(1)
    tc_e = class_thresholds(e_val, pred_val, len(CLASSES))
    tc_m = class_thresholds(m_val, pred_val, len(CLASSES))
    flag_ce, flag_cm = e_test > tc_e[pred_test], m_test > tc_m[pred_test]
    flagged = {
        c: {
            "energy": float((e_test[y == i] > t_e).mean()),
            "mahalanobis": float((m_test[y == i] > t_m).mean()),
            "energy_class_thresholds": float(flag_ce[y == i].mean()),
            "mahalanobis_class_thresholds": float(flag_cm[y == i].mean()),
        }
        for i, c in enumerate(CLASSES)
    }
    result = {
        "model": name,
        "energy": {
            "threshold": t_e,
            "in_distribution_recall_validation": float((e_val <= t_e).mean()),
            "in_distribution_recall_test": float((e_test <= t_e).mean()),
        },
        "mahalanobis": {
            "threshold": t_m,
            "in_distribution_recall_validation": float((m_val <= t_m).mean()),
            "in_distribution_recall_test": float((m_test <= t_m).mean()),
            "covariance": "shared within-class, Ledoit-Wolf shrinkage, L2-normalised embeddings",
        },
        "class_conditional_variant": {
            "rule": "flag when score > threshold of the predicted class",
            "energy_thresholds": dict(zip(CLASSES, tc_e.tolist(), strict=True)),
            "mahalanobis_thresholds": dict(zip(CLASSES, tc_m.tolist(), strict=True)),
            "in_distribution_recall_test_energy": float(1 - flag_ce.mean()),
            "in_distribution_recall_test_mahalanobis": float(1 - flag_cm.mean()),
        },
        "test_share_flagged_by_class": flagged,
        "agreement_test": {
            "both": float(((e_test > t_e) & (m_test > t_m)).mean()),
            "energy_only": float(((e_test > t_e) & (m_test <= t_m)).mean()),
            "mahalanobis_only": float(((e_test <= t_e) & (m_test > t_m)).mean()),
            "spearman_rho": float(
                np.corrcoef(np.argsort(np.argsort(e_test)), np.argsort(np.argsort(m_test)))[0, 1]
            ),
        },
    }
    np.savez(RUNS / name / "ood_mahalanobis.npz", **params)
    (RUNS / name / "ood.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def weighted_auroc(y: np.ndarray, score: np.ndarray, w: np.ndarray | None) -> float:
    if w is not None and (w[y == 1].sum() == 0 or w[y == 0].sum() == 0):
        return np.nan
    return float(roc_auc_score(y, score, sample_weight=w))


def loco() -> dict:
    """For each defect class c, a model trained without c must flag wafers of class c."""
    index = load_index()
    results = {"epochs_cap": LOCO_EPOCHS, "seed": LOCO_SEED, "split": "lot", "classes": {}}
    for held in CLASSES[:-1]:
        classes = [c for c in CLASSES if c != held]
        name = f"loco-{held}-lot-seed{LOCO_SEED}"
        parts = {p: load_part(index, "lot", p, classes) for p in ("train", "validation", "test")}
        # Every labelled wafer of the held-out class is unseen by this model (it was removed
        # from train and validation), so all of them form the out-of-distribution set.
        unseen = index[index["label"] == held]
        rows = unseen["row"].to_numpy()
        parts["unseen"] = Part(
            rows, np.asarray(load_maps()[rows]), np.zeros(len(rows), int), unseen["lot"].to_numpy()
        )
        s = scores_for(name, "lot", classes, parts)
        params = fit_mahalanobis(s["train"]["embedding"], parts["train"].labels, len(classes))
        entry = {"run": name, "unseen_wafers": len(rows), "id_test_wafers": len(parts["test"].rows)}
        for method in ("energy", "mahalanobis"):

            def score(
                key: str, method: str = method, s: dict = s, params: dict = params
            ) -> np.ndarray:
                if method == "energy":
                    return energy(s[key]["logits"])
                return mahalanobis(s[key]["embedding"], params)

            val, test, ood = score("validation"), score("test"), score("unseen")
            t = threshold(val)
            tc = class_thresholds(val, s["validation"]["logits"].argmax(1), len(classes))
            ood_flag_c = ood > tc[s["unseen"]["logits"].argmax(1)]
            test_ok_c = test <= tc[s["test"]["logits"].argmax(1)]
            y = np.r_[np.zeros(len(test)), np.ones(len(ood))]
            sc = np.r_[test, ood]
            lots = np.r_[parts["test"].lots, parts["unseen"].lots]
            entry[method] = {
                "auroc": stats.bootstrap(
                    lambda w, y=y, sc=sc: weighted_auroc(y, sc, w), lots, b=500
                ),
                "threshold": t,
                "unseen_flagged_at_threshold": float((ood > t).mean()),
                "id_test_accepted_at_threshold": float((test <= t).mean()),
                "unseen_flagged_class_thresholds": float(ood_flag_c.mean()),
                "id_test_accepted_class_thresholds": float(test_ok_c.mean()),
            }
        history = json.loads((RUNS / name / "history.json").read_text(encoding="utf-8"))
        entry["epochs_run"] = history["epochs_run"]
        entry["validation_macro_f1"] = history["best"]["macro_f1"]
        results["classes"][held] = entry
        print(held, entry["energy"]["auroc"]["value"], entry["mahalanobis"]["auroc"]["value"])
    for method in ("energy", "mahalanobis"):
        values = [results["classes"][c][method]["auroc"]["value"] for c in CLASSES[:-1]]
        results[f"mean_auroc_{method}"] = float(np.mean(values))
    results["tags"] = run_tags()
    (REPORTS / "loco.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit")
    f.add_argument("--split", choices=["official", "lot"], required=True)
    f.add_argument("--seed", type=int, required=True)
    sub.add_parser("loco")
    args = parser.parse_args()
    if args.cmd == "fit":
        print(json.dumps(fit(args.split, args.seed), indent=2))
    else:
        loco()


if __name__ == "__main__":
    main()
