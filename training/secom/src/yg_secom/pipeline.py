"""Build the SECOM artifact bundle from the raw UCI files, in one command.

    uv run python -m yg_secom.pipeline --data ../../data/secom --out ../../artifacts/secom/v1

Protocol (every step is recorded in ``metrics.json``; see ``yg_secom.split``):

1. Load and validate the source files; check their SHA-256 against ``data/manifest.json``.
2. Exploratory data analysis (``eda.json``, ``reports/eda.md``).
3. Chronological blocks: train (rolling-origin warm-up), validation (rolling-origin
   evaluation slices) and test (the last block, untouched), with a leakage check. From
   here on the test labels are masked in memory until step 11.
4. Rolling-origin folds over the validation block.
5. Training-only preprocessing per fold; LightGBM tuned with Optuna on the folds; logistic
   regression's C chosen on the same folds; balanced random forest with fixed settings.
6. Out-of-fold scores for every validation unit, for every model.
7. Platt calibration and alarm thresholds (5% and 10% false-alarm rate) on the pooled
   out-of-fold validation scores (Platt, 1999: calibrate on cross-validation outputs, then
   use the model refitted on all the data).
8. Final models refitted on the whole development period (train and validation blocks).
   Root cause on the development period: TreeSHAP, correlated groups, stability
   selection, label-permutation test, univariate screen.
9. FDC: stationary reference, robust PCA, T^2 and SPE limits, contributions, EWMA, CUSUM.
10. Sensor health rules (jump threshold calibrated on the reference).
11. The single evaluation of the test block.
12. Bundle export with manifest; reports, figures and the model card.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import stats
from scipy.stats.contingency import odds_ratio
from yg_common.bootstrap import cluster_bootstrap
from yg_common.estimates import Estimate
from yg_common.metrics import (
    average_precision,
    brier_score,
    clopper_pearson_interval,
    confusion_at_threshold,
    expected_calibration_error,
    reliability_table,
    threshold_at_fpr,
    wilson_interval,
)
from yg_common.multiple_testing import benjamini_hochberg
from yg_common.provenance import (
    derive_seed,
    environment_record,
    git_commit,
    git_dirty,
    git_toplevel,
)

from yg_secom import eda as eda_module
from yg_secom import export, reports
from yg_secom.calibration import PlattCalibrator
from yg_secom.config import PipelineConfig
from yg_secom.data import SecomData, load_secom, verify_manifest
from yg_secom.evaluation import (
    ScoredModel,
    SealedLabels,
    curve_points,
    model_metrics,
    operating_point,
    paired_difference,
)
from yg_secom.fdc import (
    cusum_arl_two_sided,
    cusum_chart,
    ewma_arl,
    ewma_chart,
    fit_fdc,
    group_scores,
    parallel_analysis,
    select_reference,
    split_reference,
)
from yg_secom.health import HealthRules, analyse_health
from yg_secom.models import (
    BRF_SETTINGS,
    LGBM_FIXED,
    LGBM_SEARCH_SPACE,
    FoldData,
    brf_probability,
    fit_brf,
    fit_lgbm,
    fit_logreg,
    lgbm_raw,
    lgbm_shap,
    logreg_score,
    probability_logit,
    tune_lgbm,
    tune_logreg,
)
from yg_secom.preprocess import Preprocessor, sensor_of
from yg_secom.rootcause import (
    assemble_shap,
    correlated_groups,
    group_importance,
    permutation_null,
    permutation_p_values,
    sensor_shap,
    stability_selection,
    univariate_tests,
)
from yg_secom.schemas import validate_bundle
from yg_secom.split import (
    Blocks,
    assert_no_leakage,
    chronological_blocks,
    epoch_us,
    iso,
    rolling_origin_folds,
)

LOG = logging.getLogger("yg_secom")
BUNDLE_VERSION = "v1"
SOURCE_PATHSPECS = (
    "training/secom/src",
    "training/secom/pyproject.toml",
    "training/secom/uv.lock",
    "training/common/src",
    "training/common/pyproject.toml",
    "training/common/uv.lock",
)
PACKAGES = (
    "yg-secom",
    "yg-common",
    "numpy",
    "pandas",
    "pyarrow",
    "scipy",
    "scikit-learn",
    "imbalanced-learn",
    "lightgbm",
    "optuna",
    "statsmodels",
    "pandera",
    "pydantic",
    "matplotlib",
    "joblib",
    "mlflow-skinny",
    "jsonschema",
)
MODELS = ("lightgbm", "logistic_regression", "balanced_random_forest", "prevalence")
MODEL_LABELS = {
    "lightgbm": "LightGBM (class weights, Optuna)",
    "logistic_regression": "L2 logistic regression (C tuned)",
    "balanced_random_forest": "Balanced random forest",
    "prevalence": "Prevalence (no skill)",
}
METRIC_LABELS = {
    "pr_auc": "PR-AUC",
    "roc_auc": "ROC-AUC",
    "brier": "Brier score",
    "ece": "Expected calibration error",
}
MASKED = -1
FloatArray = npt.NDArray[np.float64]


class ProvenanceError(RuntimeError):
    """The run cannot be tied to a committed version of the code."""


@dataclass
class RunArtifacts:
    """In-memory results that the reports and figures need besides ``metrics.json``."""

    timeline: pd.DataFrame
    test_scores: dict[str, ScoredModel]
    validation_scores: dict[str, ScoredModel]
    y_test: npt.NDArray[np.int64]
    y_validation: npt.NDArray[np.int64]
    groups: dict[str, Any]
    health: dict[str, Any]
    fdc_series: dict[str, Any] = field(default_factory=dict)


def _seeds(master: int) -> dict[str, int]:
    names = (
        "optuna",
        "lightgbm",
        "brf",
        "bootstrap",
        "stability-resample",
        "permutation",
        "parallel-analysis",
        "fdc-bootstrap",
    )
    return {name: derive_seed(master, name) for name in names}


def _estimate_dict(value: float, low: float, high: float, method: str, n: int) -> dict[str, Any]:
    return Estimate(value, low, high, 0.95, method, n).to_dict()


def _band(risk: float, high: float, elevated: float) -> str:
    if risk >= high:
        return "high"
    if risk >= elevated:
        return "elevated"
    return "low"


def _fold_data(
    folds: list[Any], X: pd.DataFrame, y: npt.NDArray[np.int64], fdr: float
) -> list[FoldData]:
    out = []
    for fold in folds:
        pre = Preprocessor(fdr=fdr).fit(X.iloc[fold.train], y[fold.train])
        out.append(
            FoldData(
                index=fold.index,
                train_ids=fold.train,
                valid_ids=fold.valid,
                preprocessor=pre,
                X_train=pre.transform(X.iloc[fold.train]),
                y_train=y[fold.train],
                X_valid=pre.transform(X.iloc[fold.valid]),
                y_valid=y[fold.valid],
            )
        )
    return out


def _calibration_summary(
    y: npt.NDArray[np.int64], probability: FloatArray, n_bins: int
) -> dict[str, Any]:
    return {
        "brier": brier_score(y, probability),
        "ece": expected_calibration_error(y, probability, n_bins),
        "reliability": [
            {
                "n": b.n,
                "events": b.n_events,
                "mean_predicted": b.mean_predicted,
                "observed_rate": b.observed_rate,
                "observed_ci_low": b.observed_ci_low,
                "observed_ci_high": b.observed_ci_high,
            }
            for b in reliability_table(y, probability, n_bins)
        ],
    }


def _rate_with_intervals(
    flags: npt.NDArray[np.bool_], days: npt.NDArray[Any], seed: int, n_resamples: int
) -> dict[str, Any]:
    k, n = int(flags.sum()), int(flags.size)
    cp_low, cp_high = clopper_pearson_interval(k, n)
    clustered = cluster_bootstrap(
        lambda f: float(np.mean(f)),
        flags.astype(np.float64),
        clusters=days,
        n_resamples=n_resamples,
        seed=seed,
    ).estimate
    return {
        "alarms": k,
        "units": n,
        "rate": _estimate_dict(
            k / n, cp_low, cp_high, "Clopper-Pearson exact interval (assumes independent units)", n
        ),
        "rate_day_clustered": clustered.to_dict(),
    }


def _check_provenance(allow_dirty: bool) -> tuple[Path | None, str]:
    code_root = git_toplevel(Path(__file__).resolve().parent)
    commit = git_commit(code_root) if code_root else None
    dirty = git_dirty(code_root, SOURCE_PATHSPECS) if code_root else None
    if commit is None:
        raise ProvenanceError("the pipeline must run from a git checkout to record the commit")
    if dirty and not allow_dirty:
        raise ProvenanceError(
            "uncommitted changes in the training code; commit them first so the bundle "
            "records the exact code (or pass --allow-dirty for a development run)"
        )
    return code_root, commit


def run(
    config: PipelineConfig,
    data_dir: Path,
    out_dir: Path,
    *,
    reports_dir: Path,
    model_card_path: Path,
    manifest_path: Path,
    openapi_path: Path | None = None,
    allow_dirty: bool = False,
) -> dict[str, Any]:
    started = time.time()
    code_root, commit = _check_provenance(allow_dirty)
    dirty = bool(git_dirty(code_root, SOURCE_PATHSPECS)) if code_root else False
    seeds = _seeds(config.seed)
    environment = environment_record(PACKAGES)

    # 1. Data -----------------------------------------------------------------------
    LOG.info("loading and validating %s", data_dir)
    data = load_secom(data_dir, config.expected_units, config.expected_features)
    if config.require_data_manifest:
        data_records = verify_manifest(data.file_sha256, manifest_path)
        dataset_entry = _dataset_entry(manifest_path)
    else:
        data_records = [
            {"file": k, "manifest_path": None, "sha256": v}
            for k, v in sorted(data.file_sha256.items())
        ]
        dataset_entry = {"citation": "not recorded (manifest check disabled)", "licence": ""}
    X = data.features
    n = data.n_units

    # 2. EDA ---------------------------------------------------------------------------
    LOG.info("exploratory data analysis")
    eda = eda_module.compute_eda(data)
    eda["source_documentation"] = _names_notes(data)

    # 3. Chronological blocks; test labels sealed and masked -----------------------------
    blocks = chronological_blocks(
        data.timestamps,
        data.labels,
        config.test_fraction,
        config.warmup_fraction,
        config.min_block_failures,
    )
    assert_no_leakage(blocks, data.timestamps)
    train, valid, test = blocks.train, blocks.validation, blocks.test
    dev = blocks.development
    test_seal = SealedLabels(data.labels[test])
    y = data.labels.astype(np.int64)
    y[test] = MASKED  # any accidental use before step 11 fails loudly
    LOG.info("blocks: train %d, validation %d, test %d units", train.size, valid.size, test.size)

    # 4. Rolling-origin folds over the validation block --------------------------------
    folds, cv_record = rolling_origin_folds(
        dev,
        int(train.size),
        data.timestamps,
        data.labels,
        config.cv_folds,
        config.cv_min_fold_failures,
    )
    fold_data = _fold_data(folds, X, y, config.indicator_fdr)

    # 5. Tuning --------------------------------------------------------------------------
    LOG.info("tuning LightGBM: %d Optuna trials x %d folds", config.optuna_trials, len(folds))
    lgbm_tuning = tune_lgbm(
        fold_data,
        config.optuna_trials,
        seeds["optuna"],
        seeds["lightgbm"],
        config.lgbm_num_threads,
        config.lgbm_max_bin,
    )
    tuned = lgbm_tuning.best_params
    LOG.info("best mean fold average precision %.4f", lgbm_tuning.best_value)
    logreg_tuning = tune_logreg(fold_data, config.logreg_c_grid)
    best_c = float(logreg_tuning.best_params["C"])

    # 6. Out-of-fold scores for the validation block ------------------------------------
    oof = {name: np.full(n, np.nan) for name in MODELS if name != "prevalence"}
    shap_pieces: list[tuple[Any, ...]] = []
    fold_ap: dict[str, list[float]] = {name: [] for name in oof}
    for fd in fold_data:
        booster = fit_lgbm(
            fd.X_train,
            fd.y_train,
            tuned,
            seeds["lightgbm"],
            config.lgbm_num_threads,
            config.lgbm_max_bin,
        )
        scores = {
            "lightgbm": lgbm_raw(booster, fd.X_valid),
            "logistic_regression": logreg_score(
                fit_logreg(fd.X_train, fd.y_train, best_c), fd.X_valid
            ),
            "balanced_random_forest": probability_logit(
                brf_probability(
                    fit_brf(
                        fd.X_train, fd.y_train, config.brf_n_estimators, seeds["brf"], config.n_jobs
                    ),
                    fd.X_valid,
                )
            ),
        }
        for name, s in scores.items():
            oof[name][fd.valid_ids] = s
            fold_ap[name].append(average_precision(fd.y_valid, s))
        values, base = lgbm_shap(booster, fd.X_valid)
        shap_pieces.append((fd.valid_ids, values, list(fd.X_valid.columns), base))
    if not np.allclose(fold_ap["lightgbm"], lgbm_tuning.best_fold_values, atol=1e-12):
        raise RuntimeError("refitted fold models do not reproduce the tuning run")
    if not all(np.all(np.isfinite(oof[name][valid])) for name in oof):
        raise RuntimeError("a validation unit has no out-of-fold score")

    # 7. Calibration and thresholds on the pooled out-of-fold validation scores ------------
    y_va = y[valid]
    z_va = {name: oof[name][valid] for name in oof}
    calibrators = {name: PlattCalibrator.fit(z, y_va) for name, z in z_va.items()}
    platt = calibrators["lightgbm"]
    risk_va = platt.predict(z_va["lightgbm"])
    thresholds = {t: threshold_at_fpr(y_va, risk_va, t) for t in config.fpr_targets}
    default_threshold = thresholds[config.default_fpr]
    elevated_threshold = thresholds[max(config.fpr_targets)]
    prevalence_va = float(y_va.mean())
    validation_scores = {
        name: ScoredModel(name, z_va[name], calibrators[name].predict(z_va[name])) for name in z_va
    }
    validation_scores["prevalence"] = ScoredModel(
        "prevalence", np.full(valid.size, prevalence_va), np.full(valid.size, prevalence_va)
    )
    validation_points = []
    for target, thr in thresholds.items():
        conf = confusion_at_threshold(y_va, risk_va, thr)
        validation_points.append(
            {
                "id": f"fpr_{target:.2f}",
                "threshold": thr,
                "fpr": conf.fpr,
                "recall": conf.recall,
                "precision": conf.precision,
                "tp": conf.tp,
                "fp": conf.fp,
                "tn": conf.tn,
                "fn": conf.fn,
            }
        )
    per_fold_calibration = _per_fold_calibration(fold_data, oof["lightgbm"], platt, y)

    # 8. Final models on the development period; root cause -------------------------------
    y_dev = y[dev]
    pre = Preprocessor(fdr=config.indicator_fdr).fit(X.iloc[dev], y_dev)
    X_dev, X_te = pre.transform(X.iloc[dev]), pre.transform(X.iloc[test])
    LOG.info("final models on the development period (%d units)", dev.size)
    final = fit_lgbm(
        X_dev, y_dev, tuned, seeds["lightgbm"], config.lgbm_num_threads, config.lgbm_max_bin
    )
    logreg = fit_logreg(X_dev, y_dev, best_c)
    brf = fit_brf(X_dev, y_dev, config.brf_n_estimators, seeds["brf"], config.n_jobs)

    LOG.info(
        "root cause: groups, stability (%d), permutations (%d)",
        config.stability_refits,
        config.permutations,
    )
    sensors = pre.output_sensors
    grouping = correlated_groups(
        X.iloc[dev], sensors, config.correlation_threshold, config.correlation_min_pairs
    )
    dev_shap, _ = lgbm_shap(final, X_dev)
    per_sensor = np.abs(sensor_shap(dev_shap, list(X_dev.columns), sensors)).mean(axis=0)
    observed = group_importance(per_sensor, grouping.membership, grouping.n_groups)
    frequency, _ = stability_selection(
        X_dev,
        y_dev,
        grouping,
        tuned,
        refits=config.stability_refits,
        top_k=config.stability_top_k,
        resample_seed=seeds["stability-resample"],
        model_seeds=[
            derive_seed(config.seed, f"stability-model-{b}") for b in range(config.stability_refits)
        ],
        max_bin=config.lgbm_max_bin,
        n_jobs=config.n_jobs,
    )
    null = permutation_null(
        X.iloc[dev],
        y_dev,
        grouping,
        tuned,
        permutations=config.permutations,
        permutation_seed=seeds["permutation"],
        model_seed=seeds["lightgbm"],
        fdr=config.indicator_fdr,
        max_bin=config.lgbm_max_bin,
        n_jobs=config.n_jobs,
    )
    p_values = permutation_p_values(observed, null)
    q_values = benjamini_hochberg(p_values)
    univariate = univariate_tests(X.iloc[dev], y_dev, sensors)
    groups_doc, root_record = _groups_document(
        config, grouping, per_sensor, observed, frequency, p_values, q_values, univariate
    )

    test_shap, test_base = lgbm_shap(final, X_te)
    shap_pieces.append((test, test_shap, list(X_te.columns), test_base))
    shap_features = _shap_features(list(X_te.columns), fold_data, data.sensors)
    shap_values, shap_base = assemble_shap(n, shap_features, shap_pieces)
    base_value = float(test_base[0])

    # 9. FDC ---------------------------------------------------------------------------------
    LOG.info("FDC reference selection and PCA model")
    fdc_record, fdc_out = _fdc(config, data, blocks, y, groups_doc, grouping, seeds)

    # 10. Sensor health ----------------------------------------------------------------------
    rules = HealthRules(
        min_readings=config.health_min_window_readings,
        flatline_probability=config.health_flatline_probability,
        stuck_alpha=config.health_stuck_family_alpha,
        jump_reference_share=config.health_jump_reference_share,
        jump_fdr_q=config.fdr_q,
        watch_out_of_reference=config.health_watch_out_of_reference,
        maintenance_out_of_reference=config.health_maintenance_out_of_reference,
        watch_window_missing=config.health_watch_window_missing,
        maintenance_window_missing=config.health_maintenance_window_missing,
        normal_missing=config.health_normal_missing,
    )
    health_doc, health_summary = analyse_health(
        X,
        data.timestamps,
        y.astype(np.int8),
        blocks.order,
        dev,
        fdc_out["fit_ids"],
        fdc_out["held_ids"],
        rules,
        config.fdr_q,
    )

    # 11. The single evaluation of the test block -------------------------------------------
    LOG.info("evaluating the test block (once)")
    y_te = test_seal.open()
    y_all = y.copy()
    y_all[test] = y_te
    raw_te = {
        "lightgbm": lgbm_raw(final, X_te),
        "logistic_regression": logreg_score(logreg, X_te),
        "balanced_random_forest": probability_logit(brf_probability(brf, X_te)),
    }
    test_scores = {
        name: ScoredModel(name, raw_te[name], calibrators[name].predict(raw_te[name]))
        for name in raw_te
    }
    test_scores["prevalence"] = ScoredModel(
        "prevalence", np.full(test.size, prevalence_va), np.full(test.size, prevalence_va)
    )
    boot: dict[str, Any] = {
        "n_resamples": config.bootstrap_resamples,
        "seed": seeds["bootstrap"],
        "ci_level": config.ci_level,
    }
    test_metrics = {
        name: model_metrics(y_te, sm, n_bins=config.reliability_bins, **boot)
        for name, sm in test_scores.items()
    }
    validation_metrics = {
        name: model_metrics(y_va, sm, n_bins=config.reliability_bins, **boot)
        for name, sm in validation_scores.items()
    }
    comparisons = {
        name: paired_difference(
            y_te, test_scores["lightgbm"].score, test_scores[name].score, **boot
        )
        for name in ("logistic_regression", "balanced_random_forest", "prevalence")
    }
    risk_te = test_scores["lightgbm"].probability
    undefined: list[str] = []
    test_points = []
    for target, thr in thresholds.items():
        point = operating_point(y_te, risk_te, thr, f"fpr_{target:.2f}", target, **boot)
        missing = [k for k in ("fpr", "recall", "precision") if point[k] is None]
        if missing:
            undefined.append(
                f"operating point {point['id']} left out: {', '.join(missing)} "
                "undefined on the test block (no unit flagged)"
            )
            continue
        test_points.append(point)
    default_id = f"fpr_{config.default_fpr:.2f}"
    if default_id not in {p["id"] for p in test_points}:
        raise RuntimeError(f"the default operating point {default_id} is undefined on test")
    for name, m in test_metrics.items():
        undefined += [
            f"{MODEL_LABELS[name]}: {METRIC_LABELS[k]} undefined on the test block"
            for k in METRIC_LABELS
            if m[k] is None
        ]
    fdc_association = _fdc_failure_association(data, y_all, fdc_out)

    # 12. Export --------------------------------------------------------------------------
    risk = np.full(n, np.nan)
    source = np.full(n, None, dtype=object)
    risk[valid] = risk_va
    source[valid] = "oof"
    risk[test] = risk_te
    source[test] = "test"
    timeline = _timeline(data, blocks, risk, source, default_threshold, elevated_threshold, fdc_out)
    operating_doc = {
        "block": "test",
        "default": default_id,
        "units": int(test.size),
        "failures": int(y_te.sum()),
        "prevalence": float(y_te.mean()),
        "points": [
            {
                k: p[k]
                for k in (
                    "id",
                    "label",
                    "target_fpr",
                    "threshold",
                    "fpr",
                    "recall",
                    "precision",
                    "false_alarms_per_100",
                    "tp",
                    "fp",
                    "tn",
                    "fn",
                )
            }
            for p in test_points
        ],
        "curve": curve_points(y_te, risk_te),
    }
    metrics: dict[str, Any] = {
        "run": {
            "bundle": f"secom/{BUNDLE_VERSION}",
            "git_commit": commit,
            "git_dirty": dirty,
            "seed": config.seed,
            "derived_seeds": seeds,
            "config": config.to_dict(),
            "environment": environment,
            "data": data_records,
            "data_citation": dataset_entry.get("citation"),
            "data_licence": dataset_entry.get("licence"),
            "data_doi": dataset_entry.get("doi"),
        },
        "evaluation_protocol": {
            "primary": "test block, evaluated once after every choice was fixed",
            "validation": (
                "rolling-origin out-of-fold predictions over the validation block: each unit "
                "scored by a model fitted only on earlier units. They chose the "
                "hyperparameters, fitted the calibrators and set the thresholds, so metrics "
                "there are optimistic (selection) and calibration there is in-sample"
            ),
            "final_models": "refitted on the whole development period (train and validation "
            "blocks) with the chosen settings; the calibrator fitted on "
            "out-of-fold scores is applied to them (Platt, 1999)",
            "label_use": (
                "test labels are masked in memory until the single final evaluation; the "
                "only earlier use is the count of test failures in the split rule (at least "
                f"{config.min_block_failures}). Root cause, sensor health and FDC reference "
                "selection use development-period labels only"
            ),
        },
        "split": {
            "blocks": blocks.record,
            "cross_validation": cv_record,
            "leakage_check": "passed: train < validation < test strictly in time, "
            "every unit in exactly one block, tied timestamps never "
            "split",
        },
        "preprocessing": {
            "development_period": {
                "model_features": len(pre.output_columns),
                "kept_sensors": len(pre.kept),
                "dropped": len(pre.dropped),
                "missingness_indicators": len(pre.indicators),
                "indicator_tests": len(pre.indicator_tests),
                "smallest_indicator_q": min(
                    (t["q_value"] for t in pre.indicator_tests), default=None
                ),
            },
            "per_fold": [
                {
                    "fold": fd.index,
                    "model_features": len(fd.preprocessor.output_columns),
                    "missingness_indicators": len(fd.preprocessor.indicators),
                }
                for fd in fold_data
            ],
        },
        "tuning": {
            "objective": "mean average precision over the rolling-origin folds",
            "lightgbm": {
                "sampler": lgbm_tuning.sampler,
                "search_space": LGBM_SEARCH_SPACE,
                "fixed": {
                    **LGBM_FIXED,
                    "num_threads": config.lgbm_num_threads,
                    "max_bin": config.lgbm_max_bin,
                    "scale_pos_weight": "passed / failed units in the fitting rows",
                    "seed": seeds["lightgbm"],
                },
                "best_params": tuned,
                "best_mean_average_precision": lgbm_tuning.best_value,
                "best_fold_average_precision": lgbm_tuning.best_fold_values,
                "trials": lgbm_tuning.trials,
            },
            "logistic_regression": {
                "model": "median imputation, standardisation, L2 logistic regression with "
                "balanced class weights (lbfgs)",
                "grid": logreg_tuning.sampler,
                "best_C": best_c,
                "best_mean_average_precision": logreg_tuning.best_value,
                "trials": logreg_tuning.trials,
            },
            "balanced_random_forest": {
                "model": "median imputation, imbalanced-learn BalancedRandomForestClassifier",
                "settings": {
                    **BRF_SETTINGS,
                    "n_estimators": config.brf_n_estimators,
                    "random_state": seeds["brf"],
                },
                "tuned": False,
            },
            "fold_average_precision": fold_ap,
        },
        "models": {
            name: {"validation_out_of_fold": validation_metrics[name], "test": test_metrics[name]}
            for name in MODELS
        },
        "comparisons": {
            "statistic": "test PR-AUC of LightGBM minus PR-AUC of the baseline",
            "method": "paired stratified bootstrap on the same resamples; two-sided p-value "
            "by percentile-interval inversion",
            "pr_auc_difference": comparisons,
        },
        "calibration": {
            "method": "Platt scaling (smoothed targets, Newton fit) on the pooled out-of-fold "
            "validation raw scores",
            "lightgbm": {
                "a": platt.a,
                "b": platt.b,
                "n": platt.n,
                "events": platt.n_events,
                "converged": platt.converged,
                "increasing": platt.increasing,
            },
            "baselines": {
                name: {"a": c.a, "b": c.b, "converged": c.converged, "increasing": c.increasing}
                for name, c in calibrators.items()
                if name != "lightgbm"
            },
            "prevalence_baseline": f"constant {prevalence_va:.4f}, the validation-block "
            "failure rate (the data every calibrator was fitted on)",
            "validation_in_sample": _calibration_summary(y_va, risk_va, config.reliability_bins),
            "validation_per_fold": per_fold_calibration,
            "test": _calibration_summary(y_te, risk_te, config.reliability_bins),
            "reliability_bins": config.reliability_bins,
            "reliability_caveat": (
                "equal-count bins; with few failures per bin the observed rates are very "
                "uncertain (Wilson intervals shown)"
            ),
            "isotonic_rejected": (
                "isotonic regression has up to one free level per distinct score and "
                "overfits a calibration set with few failures; its flat steps also tie "
                "units the model ranks differently"
            ),
        },
        "operating_points": {
            "thresholds_from": "validation block: pooled out-of-fold LightGBM risks; the "
            "smallest threshold whose false-alarm rate there is at most "
            "the target",
            "validation": validation_points,
            "test": test_points,
            "risk_bands": {
                "high": f"risk >= threshold of fpr_{config.default_fpr:.2f}",
                "elevated": f"risk >= threshold of fpr_{max(config.fpr_targets):.2f}",
                "low": "otherwise",
            },
            "threshold_uncertainty": "intervals are conditional on the thresholds chosen on "
            "the validation block",
        },
        "out_of_fold": {
            "validation_units": int(valid.size),
            "warmup_units": int(cv_record["warmup_units"]),
            "fold_average_precision": fold_ap,
            "note": "validation-block risks come from the fold model whose evaluation slice "
            "holds them; train-block (warm-up) units have no out-of-sample risk",
        },
        "root_cause": root_record,
        "shap": {
            "features": len(shap_features),
            "base_value": base_value,
            "units_with_values": int(np.sum(~np.isnan(shap_base))),
            "sources": "fold models for validation units; the final model (development "
            "period) for test units; train-block units have none",
        },
        "fdc": {**fdc_record, "failure_association": fdc_association},
        "health": health_summary,
        "undefined_quantities": undefined,
    }
    limitations = reports.limitations(metrics)
    metrics["limitations"] = limitations
    metrics["report"] = _report(
        metrics,
        blocks,
        data,
        cv_record,
        lgbm_tuning,
        test_metrics,
        comparisons,
        platt,
        fold_ap,
        limitations,
        config,
    )
    fdc_model = fdc_out["model"]
    fit_ids = fdc_out["fit_ids"]
    metrics["fdc_reference"] = {
        "start": iso(data.timestamps.iloc[fit_ids].min()),
        "end": iso(data.timestamps.iloc[fit_ids].max()),
        "units": int(fit_ids.size),
        "stationarity": _stationarity_sentence(fdc_record["reference"]),
    }
    metrics["fdc_explained_variance"] = float(fdc_model.explained_variance)
    metrics["methods"] = _methods(fdc_model, fit_ids.size, config)

    out_dir.mkdir(parents=True, exist_ok=True)
    export.write_timeline(out_dir / "timeline.parquet", timeline)
    export.write_shap(out_dir / "shap.npz", shap_values, base_value, shap_base, shap_features)
    export.write_fdc(out_dir, fdc_model, fdc_out["contrib_t2"], fdc_out["contrib_spe"])
    export.write_model(out_dir / "model.txt", final)
    export.write_json_files(
        out_dir,
        {
            "groups.json": groups_doc,
            "health.json": health_doc,
            "operating_points.json": operating_doc,
            "metrics.json": metrics,
            "calibrator.json": platt.to_contract(),
            "preprocess.json": pre.to_dict(),
            "eda.json": eda,
        },
    )
    artifacts = RunArtifacts(
        timeline=timeline,
        test_scores=test_scores,
        validation_scores=validation_scores,
        y_test=y_te,
        y_validation=y_va,
        groups=groups_doc,
        health=health_doc,
        fdc_series=fdc_out,
    )
    provenance_line = reports.provenance_line(commit, data_records)
    figure_dir = reports_dir / "figures"
    eda_figures = eda_module.write_eda_figures(data, eda, figure_dir)
    (reports_dir / "eda.md").write_text(
        eda_module.eda_markdown(
            eda, {k: f"figures/{p.name}" for k, p in eda_figures.items()}, provenance_line
        ),
        encoding="utf-8",
    )
    card = reports.model_card(metrics, groups_doc, eda, provenance_line)
    (out_dir / "model_card.md").write_text(card, encoding="utf-8")
    model_card_path.parent.mkdir(parents=True, exist_ok=True)
    model_card_path.write_text(card, encoding="utf-8")
    result_figures = reports.result_figures(metrics, artifacts, figure_dir)
    (reports_dir / "results.md").write_text(
        reports.results_markdown(
            metrics,
            artifacts,
            eda,
            {k: f"figures/{p.name}" for k, p in result_figures.items()},
            provenance_line,
        ),
        encoding="utf-8",
    )
    manifest = export.write_manifest(
        out_dir,
        version=BUNDLE_VERSION,
        git_commit=commit,
        data=[
            {"path": _repo_relative(data.files[r["file"]], code_root), "sha256": r["sha256"]}
            for r in data_records
        ],
        environment=environment,
    )
    validate_bundle(out_dir, openapi_path=openapi_path)
    LOG.info("bundle written and validated: %s (%.0f s)", out_dir, time.time() - started)
    if config.mlflow:
        _log_mlflow(code_root, config, metrics, manifest, out_dir, time.time() - started)
    return metrics


def _shap_features(
    final_columns: list[str], fold_data: list[FoldData], sensors: list[str]
) -> list[str]:
    """Final-model columns in model order, then columns only fold models used."""
    rank = {s: i for i, s in enumerate(sensors)}
    extra = {c for fd in fold_data for c in fd.X_valid.columns} - set(final_columns)
    ordered_extra = sorted(extra, key=lambda c: (rank[sensor_of(c)], c != sensor_of(c)))
    return [*final_columns, *ordered_extra]


def _per_fold_calibration(
    fold_data: list[FoldData],
    oof_raw: FloatArray,
    platt: PlattCalibrator,
    y: npt.NDArray[np.int64],
) -> list[dict[str, Any]]:
    """Calibration-in-the-large per rolling-origin slice (shows drift between slices)."""
    rows = []
    for fd in fold_data:
        risk = platt.predict(oof_raw[fd.valid_ids])
        k, m = int(y[fd.valid_ids].sum()), int(fd.valid_ids.size)
        low, high = wilson_interval(k, m)
        rows.append(
            {
                "fold": fd.index,
                "units": m,
                "failures": k,
                "mean_predicted": float(risk.mean()),
                "observed_rate": k / m,
                "observed_ci_low": low,
                "observed_ci_high": high,
            }
        )
    return rows


def _report(
    metrics: dict[str, Any],
    blocks: Blocks,
    data: SecomData,
    cv_record: dict[str, Any],
    lgbm_tuning: Any,
    test_metrics: dict[str, dict[str, Any]],
    comparisons: dict[str, dict[str, Any]],
    platt: PlattCalibrator,
    fold_ap: dict[str, list[float]],
    limitations: list[str],
    config: PipelineConfig,
) -> dict[str, Any]:
    """``metrics.json`` ``report``: the API's SecomMetrics shape without ``bundle``."""
    block_rows = []
    for name, ids in (
        ("train", blocks.train),
        ("validation", blocks.validation),
        ("test", blocks.test),
    ):
        summary = next(b for b in blocks.record["blocks"] if b["block"] == name)
        block_rows.append(
            {
                "block": name,
                "start": iso(data.timestamps.iloc[ids].min()),
                "end": iso(data.timestamps.iloc[ids].max()),
                "units": int(ids.size),
                "failures": int(summary["failures"]),
            }
        )
    models = [
        {
            "model": name,
            "label": MODEL_LABELS[name],
            "main": name == "lightgbm",
            "metrics": [
                {"metric": k, "label": label, "estimate": test_metrics[name][k]}
                for k, label in METRIC_LABELS.items()
                if test_metrics[name][k] is not None
            ],
        }
        for name in MODELS
    ]
    comparison_rows = [
        {
            "baseline": name,
            "metric": "pr_auc",
            "difference": c["difference"],
            "p_value": c["p_value"],
        }
        for name, c in comparisons.items()
        if c["difference"] is not None
    ]
    calib = metrics["calibration"]["test"]
    main = test_metrics["lightgbm"]
    calibration = {
        "method": "platt",
        "a": platt.a,
        "b": platt.b,
        "brier": main["brier"],
        "ece": main["ece"],
        "bins": [
            {
                "bin": i,
                "mean_predicted": b["mean_predicted"],
                "observed_rate": b["observed_rate"],
                "units": b["n"],
            }
            for i, b in enumerate(calib["reliability"])
        ],
        "caveat": (
            "Platt scaling fitted on the pooled out-of-fold validation scores of the fold "
            "models and applied to the final model; Brier, ECE and bins are on the test "
            f"block ({config.reliability_bins} equal-count bins, few failures per bin, so the "
            "observed rates are very uncertain)"
        ),
    }
    tuning = {
        "sampler": lgbm_tuning.sampler,
        "trials": len(lgbm_tuning.trials),
        "objective": "mean average precision over the rolling-origin folds",
        "best_value": float(lgbm_tuning.best_value),
        "best_params": {k: v for k, v in lgbm_tuning.best_params.items()},
        "folds": [
            {
                "fold": f["fold"],
                "train_units": f["train_units"],
                "validation_start": f["valid_first"],
                "validation_end": f["valid_last"],
                "validation_units": f["valid_units"],
                "validation_failures": f["valid_failures"],
                "average_precision": fold_ap["lightgbm"][i],
            }
            for i, f in enumerate(cv_record["folds"])
        ],
    }
    far = metrics["fdc"]["false_alarm_rate_held_out_reference"]
    charts = metrics["fdc"]["small_shift_charts"]
    fdc = {
        "holdout_units": int(metrics["fdc"]["reference"]["held_out_units"]),
        "false_alarm_rate_99": far["99"]["either"]["rate"],
        "false_alarm_rate_999": far["99.9"]["either"]["rate"],
        "ewma": f"lambda = {charts['ewma']['lambda']}, L = {charts['ewma']['L']}, asymptotic "
        f"limits; in-control ARL {charts['ewma']['in_control_arl_normal']:.0f} units "
        "under normality",
        "cusum": f"k = {charts['cusum']['k']}, h = {charts['cusum']['h']}, two-sided, restart "
        f"after a signal; in-control ARL {charts['cusum']['in_control_arl_normal']:.0f} "
        "units under normality",
    }
    return {
        "blocks": block_rows,
        "models": models,
        "comparisons": comparison_rows,
        "calibration": calibration,
        "tuning": tuning,
        "fdc": fdc,
        "limitations": limitations,
    }


def _stationarity_sentence(reference: dict[str, Any]) -> str:
    chosen = next((c for c in reference["candidates"] if c["stationary"]), None)
    first = reference["candidates"][0] if reference["candidates"] else None
    test = first["test"] if first else "no test run"
    if chosen is None:
        return (
            f"{test}; no candidate stretch passed, so the shortest candidate is used and "
            "flagged as a limitation"
        )
    stats_text = ", ".join(
        f"PC{t['component']} {t['kpss_statistic']:.3f}" for t in chosen["components"]
    )
    return (
        f"{test}; the passing units within the first {chosen['fraction']:.0%} of the "
        f"development period passed (KPSS statistics {stats_text}; 1% critical value "
        f"{chosen['components'][0]['critical_value']:.3f})"
    )


def _methods(model: Any, n_fit: int, config: PipelineConfig) -> dict[str, str]:
    low, high = config.fdc_alphas
    return {
        "explanation": (
            "TreeSHAP from LightGBM (pred_contrib, exact for trees) in log-odds of the "
            "class-weighted model: validation units are explained by the rolling-origin fold "
            "model that scored them and test units by the final model refitted on the "
            "development period; each row's base value is its model's expected raw score."
        ),
        "fdc": (
            f"PCA on {n_fit} passing reference units and {len(model.features)} sensors "
            "(reference-median imputation, normal-consistent MAD scaling), keeping "
            f"{model.n_components} components ({100 * model.explained_variance:.1f}% of "
            f"variance); Hotelling T2 limits from the Phase II F distribution and SPE limits "
            f"by {model.spe_limit_method}, at {100 * (1 - low):g}% and {100 * (1 - high):g}%."
        ),
        "contributions": (
            "SPE contributions are the squared residuals of each sensor (they sum to SPE); "
            "T2 contributions are the complete decomposition z_j (P Lambda^-1 t)_j, which "
            "sums to T2 and can be negative for a sensor that pulls the score back."
        ),
    }


def _repo_relative(path: Path, root: Path | None) -> str:
    resolved = path.resolve()
    if root is not None:
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return resolved.as_posix()


def _dataset_entry(manifest_path: Path) -> dict[str, Any]:
    entry = json.loads(manifest_path.read_text(encoding="utf-8")).get("secom", {})
    return {k: entry.get(k) for k in ("citation", "licence", "licence_url", "doi", "page")}


def _names_notes(data: SecomData) -> dict[str, Any]:
    notes: dict[str, Any] = {"file": "secom.names", "present": "secom.names" in data.files}
    if notes["present"]:
        text = data.files["secom.names"].read_text(encoding="latin-1")
        stated = "591" if ("591 features" in text or "1567 x 591" in text) else "not found"
        notes["stated_attributes"] = stated
        notes["observed_feature_columns"] = data.n_features
        if stated == "591":
            notes["note"] = (
                "secom.names states 591 attributes and a 1567 x 591 matrix; secom.data holds "
                f"{data.n_features} columns per line (verified at load). The pipeline uses "
                "what the file contains."
            )
    return notes


def _groups_document(
    config: PipelineConfig,
    grouping: Any,
    per_sensor: FloatArray,
    observed: FloatArray,
    frequency: FloatArray,
    p_values: FloatArray,
    q_values: FloatArray,
    univariate: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    sensors = grouping.sensors
    members: dict[int, list[int]] = {}
    for i, g in enumerate(grouping.membership):
        members.setdefault(int(g), []).append(i)
    order = sorted(members, key=lambda g: (-observed[g], members[g][0]))
    width = max(3, len(str(len(order))))
    groups = []
    for rank, g in enumerate(order, start=1):
        idx = members[g]
        representative = sensors[max(idx, key=lambda i: (per_sensor[i], -i))]
        groups.append(
            {
                "group_id": f"G{rank:0{width}d}",
                "sensors": [sensors[i] for i in idx],
                "representative": representative,
                "importance": float(observed[g]),
                "stability": float(frequency[g]),
                "p_value": float(p_values[g]),
                "q_value": float(q_values[g]),
                "significant": bool(q_values[g] <= config.fdr_q),
                "univariate": [
                    {
                        k: univariate[sensors[i]][k]
                        for k in ("sensor", "mann_whitney_p", "q_value", "direction")
                    }
                    for i in idx
                ],
            }
        )
    document = {
        "method": {
            "correlation": "spearman",
            "threshold": config.correlation_threshold,
            "linkage": "average",
            "stability_refits": config.stability_refits,
            "stability_threshold": config.stability_threshold,
            "permutations": config.permutations,
            "fdr_q": config.fdr_q,
        },
        "groups": groups,
    }
    stable = [gr for gr in groups if gr["stability"] >= config.stability_threshold]
    significant = [gr for gr in groups if gr["significant"]]
    both = [gr for gr in stable if gr["significant"]]
    m = len(groups)
    p_floor = 1.0 / (config.permutations + 1)
    used = int(np.sum(observed > 0))
    uni_rows = list(univariate.values())
    record = {
        "grouping": grouping.record,
        "importance": "sum over members of mean |TreeSHAP| (log-odds) over development-period "
        "units, final model (fitted on the development period)",
        "groups_total": m,
        "groups_used_by_model": used,
        "stability": {
            "refits": config.stability_refits,
            "top_k": config.stability_top_k,
            "threshold": config.stability_threshold,
            "resampling": "stratified bootstrap of the development period; preprocessing "
            "fixed; one seed per refit",
            "stable_groups": [gr["group_id"] for gr in stable],
        },
        "permutation_test": {
            "permutations": config.permutations,
            "p_value": "(1 + #{null >= observed}) / (1 + permutations)",
            "smallest_attainable_p": p_floor,
            "smallest_attainable_q_for_one_discovery": min(1.0, p_floor * m),
            "groups_at_smallest_p": int(np.sum(np.isclose(p_values, p_floor))),
            "smallest_q": float(np.min(q_values)) if q_values.size else None,
            "fdr_q": config.fdr_q,
            "significant_groups": [gr["group_id"] for gr in significant],
            "power_note": (
                f"with {config.permutations} permutations the smallest p-value is "
                f"{p_floor:.4f}; Benjamini-Hochberg across {m} groups can declare k groups "
                f"significant only if k >= {math.ceil(p_floor * m / config.fdr_q)} of them "
                "reach that floor"
            ),
        },
        "stable_and_significant": [gr["group_id"] for gr in both],
        "univariate": {
            "test": "Mann-Whitney U, two-sided, failed versus passed development-period "
            "units, missing readings excluded; Benjamini-Hochberg across tested sensors",
            "tested": int(sum(r["mann_whitney_p"] is not None for r in uni_rows)),
            "significant": [
                r["sensor"]
                for r in uni_rows
                if r["q_value"] is not None and r["q_value"] <= config.fdr_q
            ],
            "effect_size_auc": {r["sensor"]: r["auc"] for r in uni_rows if r["auc"] is not None},
        },
        "sensors_to_inspect": {
            "all_sensors": len(sensors),
            "stable_groups": len(stable),
            "sensors_in_stable_groups": int(sum(len(gr["sensors"]) for gr in stable)),
            "median_sensors_per_stable_group": (
                float(np.median([len(gr["sensors"]) for gr in stable])) if stable else None
            ),
            "stable_and_significant_groups": len(both),
            "sensors_in_stable_and_significant_groups": int(sum(len(gr["sensors"]) for gr in both)),
        },
    }
    return document, record


def _fdc(
    config: PipelineConfig,
    data: SecomData,
    blocks: Blocks,
    y_masked: npt.NDArray[np.int64],
    groups_doc: dict[str, Any],
    grouping: Any,
    seeds: dict[str, int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    X = data.features
    reference, ref_record = select_reference(
        blocks.development,
        y_masked.astype(np.int8),
        X,
        fractions=config.fdc_reference_fractions,
        max_missing=config.fdc_max_missing,
        n_components=config.fdc_stationarity_components,
        family_alpha=config.fdc_stationarity_alpha,
    )
    fit_ids, held_ids = split_reference(reference, data.timestamps)
    model = fit_fdc(
        X.iloc[fit_ids],
        fit_ids,
        max_missing=config.fdc_max_missing,
        variance_target=config.fdc_variance_target,
        alphas=config.fdc_alphas,
    )
    Z_fit = model.standardize(X.iloc[fit_ids])
    pa_components, _ = parallel_analysis(
        Z_fit, config.fdc_parallel_iterations, seeds["parallel-analysis"]
    )
    scored = model.score(X)
    low, high = config.fdc_alphas
    t2, spe = scored["t2"], scored["spe"]
    warning = (t2 > model.t2_limits[low]) | (spe > model.spe_limits[low])
    alarm = (t2 > model.t2_limits[high]) | (spe > model.spe_limits[high])
    fdc_alarm = np.where(alarm, "alarm", np.where(warning, "warning", "none"))
    fdc_period = np.full(data.n_units, "monitoring", dtype=object)
    fdc_period[fit_ids] = "reference"

    days = data.timestamps.dt.floor("D").to_numpy()
    held_days = days[held_ids]
    far: dict[str, Any] = {}
    for label, alpha in (("99", low), ("99.9", high)):
        flags = {
            "t2": t2[held_ids] > model.t2_limits[alpha],
            "spe": spe[held_ids] > model.spe_limits[alpha],
        }
        flags["either"] = flags["t2"] | flags["spe"]
        far[label] = {
            "nominal_per_statistic": alpha,
            "nominal_either_at_most": 2 * alpha,
            **{
                k: _rate_with_intervals(
                    v, held_days, seeds["fdc-bootstrap"], config.bootstrap_resamples
                )
                for k, v in flags.items()
            },
        }

    # Leading groups: stable groups first, then by importance; members must reach FDC.
    feature_index = {f: i for i, f in enumerate(model.features)}
    ranked = sorted(
        groups_doc["groups"],
        key=lambda g: (g["stability"] < config.stability_threshold, -g["importance"]),
    )
    Z_all = model.standardize(X)
    order = blocks.order
    spearman = grouping.spearman
    ewma_any = np.zeros(data.n_units, dtype=np.bool_)
    cusum_any = np.zeros(data.n_units, dtype=np.bool_)
    leading: list[dict[str, Any]] = []
    is_held = np.zeros(data.n_units, dtype=np.bool_)
    is_held[held_ids] = True
    for g in ranked:
        if len(leading) >= config.leading_groups:
            break
        rep = g["representative"]
        signs = []
        for s in g["sensors"]:
            rho = spearman.loc[s, rep] if s != rep else 1.0
            signs.append(-1.0 if (not np.isnan(rho) and rho < 0) else 1.0)
        score = group_scores(Z_all, feature_index, g["sensors"], signs)
        if score is None:
            continue
        mean, sd = float(score[fit_ids].mean()), float(score[fit_ids].std(ddof=1))
        if not sd > 0:
            continue
        u = (score - mean) / sd
        u_time = u[order]
        ewma_stat, ewma_limit, ewma_flag = ewma_chart(u_time, config.ewma_lambda, config.ewma_l)
        c_up, c_down, cusum_flag = cusum_chart(u_time, config.cusum_k, config.cusum_h)
        ewma_unit = np.zeros(data.n_units, dtype=np.bool_)
        cusum_unit = np.zeros(data.n_units, dtype=np.bool_)
        ewma_unit[order] = ewma_flag
        cusum_unit[order] = cusum_flag
        ewma_any |= ewma_unit
        cusum_any |= cusum_unit
        leading.append(
            {
                "group_id": g["group_id"],
                "representative": rep,
                "members_used": [s for s in g["sensors"] if s in feature_index],
                "ewma_limit": ewma_limit,
                "ewma_alarms": int(ewma_unit.sum()),
                "cusum_alarms": int(cusum_unit.sum()),
                "held_out_reference_ewma_alarms": int(ewma_unit[is_held].sum()),
                "held_out_reference_cusum_alarms": int(cusum_unit[is_held].sum()),
                "series": {
                    "ewma": ewma_stat.tolist(),
                    "cusum_upper": c_up.tolist(),
                    "cusum_lower": c_down.tolist(),
                },
            }
        )
    record = {
        "reference": {
            **ref_record,
            "fit_units": int(fit_ids.size),
            "held_out_units": int(held_ids.size),
            "fit_unit_ids": fit_ids.tolist(),
            "held_out_unit_ids": held_ids.tolist(),
        },
        "model": {
            "features": len(model.features),
            "features_dropped": model.dropped,
            "scaling": "reference median imputation (FDC only); normal-consistent MAD scale; "
            "centred at the reference mean after imputation",
            "n_components": model.n_components,
            "explained_variance": model.explained_variance,
            "variance_target": config.fdc_variance_target,
            "parallel_analysis_components": pa_components,
            "parallel_analysis": f"Horn, {config.fdc_parallel_iterations} column permutations, "
            "95th percentile",
            "t2_limits": {"99": model.t2_limits[low], "99.9": model.t2_limits[high]},
            "spe_limits": {"99": model.spe_limits[low], "99.9": model.spe_limits[high]},
            "t2_limit_method": "Phase II F limit for a new observation",
            "spe_limit_method": model.spe_limit_method,
            "contributions": "SPE: squared residual per feature; T2: complete decomposition",
        },
        "false_alarm_rate_held_out_reference": far,
        "alarm_counts": {
            "warning_or_alarm": int(warning.sum()),
            "alarm": int(alarm.sum()),
            "units": int(data.n_units),
        },
        "small_shift_charts": {
            "group_score": "sign-aligned mean of the members' FDC-standardised values, "
            "standardised by the fit-reference mean and SD",
            "ewma": {
                "lambda": config.ewma_lambda,
                "L": config.ewma_l,
                "limits": "asymptotic, +/- L sqrt(lambda / (2 - lambda))",
                "in_control_arl_normal": ewma_arl(config.ewma_lambda, config.ewma_l),
            },
            "cusum": {
                "k": config.cusum_k,
                "h": config.cusum_h,
                "restart": "both sums restart at zero after a signal",
                "in_control_arl_normal": cusum_arl_two_sided(config.cusum_k, config.cusum_h),
            },
            "leading_groups": [{k: v for k, v in lg.items() if k != "series"} for lg in leading],
            "held_out_reference_units": int(held_ids.size),
            "units_with_ewma_alarm": int(ewma_any.sum()),
            "units_with_cusum_alarm": int(cusum_any.sum()),
        },
        "limitations": "SECOM has no drift labels: these alarms cannot be scored as correct "
        "or incorrect, only checked for their false-alarm rate on held-out "
        "in-control data and for association with failure",
    }
    out = {
        "model": model,
        "t2": t2,
        "spe": spe,
        "contrib_t2": scored["contrib_t2"],
        "contrib_spe": scored["contrib_spe"],
        "fdc_alarm": fdc_alarm,
        "fdc_period": fdc_period,
        "warning": warning,
        "alarm": alarm,
        "ewma_alarm": ewma_any,
        "cusum_alarm": cusum_any,
        "fit_ids": fit_ids,
        "held_ids": held_ids,
        "reference_ids": reference,
        "leading": leading,
    }
    return record, out


def _fdc_failure_association(
    data: SecomData, y: npt.NDArray[np.int64], fdc_out: dict[str, Any]
) -> dict[str, Any]:
    """Failure rate with and without an FDC flag, over units outside the reference stretch.

    Runs after the test block was opened (it includes test units).
    """
    outside = np.ones(data.n_units, dtype=np.bool_)
    outside[fdc_out["reference_ids"]] = False
    rows = {}
    for name in ("warning", "alarm"):
        flag = fdc_out["alarm"] if name == "alarm" else (fdc_out["warning"] | fdc_out["alarm"])
        f, yy = flag[outside], y[outside]
        table = np.array(
            [
                [int(np.sum(f & (yy == 1))), int(np.sum(f & (yy == 0)))],
                [int(np.sum(~f & (yy == 1))), int(np.sum(~f & (yy == 0)))],
            ]
        )
        entry: dict[str, Any] = {
            "flag": "beyond the 99% limit (T2 or SPE)"
            if name == "warning"
            else "beyond the 99.9% limit (T2 or SPE)",
            "table": {
                "flagged_failed": int(table[0, 0]),
                "flagged_passed": int(table[0, 1]),
                "unflagged_failed": int(table[1, 0]),
                "unflagged_passed": int(table[1, 1]),
            },
            "fisher_p": float(stats.fisher_exact(table).pvalue),
        }
        for key, row in (("failure_rate_flagged", 0), ("failure_rate_unflagged", 1)):
            k, m = int(table[row, 0]), int(table[row].sum())
            if m:
                entry[key] = _estimate_dict(
                    k / m, *wilson_interval(k, m), "Wilson score interval", m
                )
        ratio = odds_ratio(table, kind="conditional")
        if np.isfinite(ratio.statistic):
            ci = ratio.confidence_interval(0.95)
            entry["odds_ratio_conditional_mle"] = Estimate(
                float(ratio.statistic),
                float(ci.low),
                float(ci.high),
                0.95,
                "conditional maximum likelihood, exact interval",
                int(table.sum()),
            ).to_dict()
        rows[name] = entry
    return {
        "units": int(outside.sum()),
        "scope": "all units outside the FDC reference stretch (later development units and "
        "the test block); association only, not causation",
        "includes_test_block": True,
        **rows,
    }


def _timeline(
    data: SecomData,
    blocks: Blocks,
    risk: FloatArray,
    source: npt.NDArray[Any],
    high: float,
    elevated: float,
    fdc_out: dict[str, Any],
) -> pd.DataFrame:
    model = fdc_out["model"]
    low_a, high_a = model.alphas
    n = data.n_units
    frame = pd.DataFrame(
        {
            "unit_id": np.arange(n, dtype=np.int32),
            "timestamp": data.timestamps.reset_index(drop=True),
            "label": data.labels.astype(np.int8),
            "block": blocks.labels_per_unit(n),
            "risk": risk.astype(np.float32),
            "risk_source": source,
            "risk_band": [None if np.isnan(r) else _band(float(r), high, elevated) for r in risk],
            "t2": fdc_out["t2"].astype(np.float32),
            "spe": fdc_out["spe"].astype(np.float32),
            "t2_limit_99": np.float32(model.t2_limits[low_a]),
            "t2_limit_999": np.float32(model.t2_limits[high_a]),
            "spe_limit_99": np.float32(model.spe_limits[low_a]),
            "spe_limit_999": np.float32(model.spe_limits[high_a]),
            "fdc_alarm": fdc_out["fdc_alarm"],
            "fdc_period": fdc_out["fdc_period"],
            "ewma_alarm": fdc_out["ewma_alarm"],
            "cusum_alarm": fdc_out["cusum_alarm"],
        }
    )
    sort_key = epoch_us(data.timestamps)
    return frame.iloc[np.lexsort((np.arange(n), sort_key))].reset_index(drop=True)


def _log_mlflow(
    root: Path | None,
    config: PipelineConfig,
    metrics: dict[str, Any],
    manifest: dict[str, Any],
    out_dir: Path,
    seconds: float,
) -> None:
    """Record the run in a local MLflow store (SQLite under <repo>/mlruns, git-ignored).

    MLflow 3.17 refuses new runs in its file store (maintenance mode), so a SQLite store is
    used; ``metrics.json`` remains the complete run record either way.
    """
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    try:
        import mlflow
    except ImportError:  # pragma: no cover - mlflow-skinny is a declared dependency
        LOG.warning("mlflow not installed; the JSON run record in metrics.json stands alone")
        return
    base = (root or out_dir).resolve() / "mlruns"
    base.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(f"sqlite:///{base / 'mlflow.db'}")
    name = "yield-guardian-secom"
    if mlflow.get_experiment_by_name(name) is None:
        mlflow.create_experiment(name, artifact_location=(base / "artifacts").as_uri())
    mlflow.set_experiment(name)
    test = metrics["models"]["lightgbm"]["test"]
    with mlflow.start_run(run_name=f"secom-{manifest['created_at']}"):
        mlflow.set_tags({"git_commit": manifest["git_commit"], "bundle": "secom/v1"})
        mlflow.log_params(
            {f"lgbm.{k}": v for k, v in metrics["tuning"]["lightgbm"]["best_params"].items()}
        )
        mlflow.log_params(
            {
                "seed": config.seed,
                "optuna_trials": config.optuna_trials,
                "logreg_C": metrics["tuning"]["logistic_regression"]["best_C"],
            }
        )
        mlflow.log_metrics(
            {
                f"test_{k}": test[k]["value"]
                for k in ("pr_auc", "roc_auc", "brier")
                if test[k] is not None
            }
            | {"duration_seconds": seconds}
        )
        mlflow.log_artifact(str(out_dir / "MANIFEST.json"))
        mlflow.log_artifact(str(out_dir / "metrics.json"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data", type=Path, required=True, help="folder with secom.data etc.")
    parser.add_argument("--out", type=Path, required=True, help="bundle folder to write")
    parser.add_argument(
        "--reports", type=Path, default=None, help="report folder (default: training/secom/reports)"
    )
    parser.add_argument(
        "--model-card",
        type=Path,
        default=None,
        help="model card path (default: docs/model-cards/secom.md)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="data manifest (default: <data>/../manifest.json)",
    )
    parser.add_argument(
        "--openapi",
        type=Path,
        default=None,
        help="API schema to validate metrics.json report against "
        "(default: packages/contracts/openapi.json)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="JSON file overriding configuration fields (development only)",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="allow uncommitted training code (development runs only)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr
    )
    config = PipelineConfig.from_json(args.config) if args.config else PipelineConfig()
    package_root = Path(__file__).resolve().parents[2]
    repo_root = git_toplevel(package_root) or package_root.parents[1]
    openapi = args.openapi or repo_root / "packages" / "contracts" / "openapi.json"
    run(
        config,
        args.data.resolve(),
        args.out.resolve(),
        reports_dir=(args.reports or package_root / "reports").resolve(),
        model_card_path=(args.model_card or repo_root / "docs" / "model-cards" / "secom.md"),
        manifest_path=(args.manifest or args.data.resolve().parent / "manifest.json"),
        openapi_path=openapi if openapi.is_file() else None,
        allow_dirty=args.allow_dirty,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
