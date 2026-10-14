"""Failure-risk models: LightGBM (main) and three baselines.

- Prevalence (no skill): every unit gets the training failure rate.
- L2 logistic regression: median imputation and standardisation inside its pipeline,
  balanced class weights, ``C`` chosen by the rolling-origin folds.
- Balanced random forest (Chen, Liaw and Breiman, 2004): every tree is grown on a
  bootstrap sample with equal numbers of failed and passed units (real units, resampled;
  nothing is synthesised). Median imputation inside its pipeline. Fixed, standard settings.
- LightGBM: class weights (``scale_pos_weight`` = passed / failed in the fitting rows),
  hyperparameters chosen by Optuna's TPE sampler to maximise the mean average precision
  over the rolling-origin folds, with a search space biased towards strong regularisation.
  Runs are deterministic: ``deterministic=True``, ``force_row_wise=True``, one thread and a
  fixed seed.

Chen, C., Liaw, A. and Breiman, L. (2004). Using random forest to learn imbalanced data.
Technical report 666, Department of Statistics, UC Berkeley.
Akiba, T. et al. (2019). Optuna: a next-generation hyperparameter optimization framework.
KDD 2019.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import optuna
import pandas as pd
from imblearn.ensemble import BalancedRandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from yg_common.metrics import average_precision

from yg_secom.preprocess import Preprocessor

FloatArray = npt.NDArray[np.float64]

LGBM_FIXED: dict[str, Any] = {
    "objective": "binary",
    "boosting_type": "gbdt",
    "verbosity": -1,
    "deterministic": True,
    "force_row_wise": True,
    "feature_pre_filter": False,
    "bagging_freq": 1,
}


@dataclass(frozen=True)
class FoldData:
    """Preprocessed training and evaluation rows of one fold."""

    index: int
    train_ids: npt.NDArray[np.int64]
    valid_ids: npt.NDArray[np.int64]
    preprocessor: Preprocessor
    X_train: pd.DataFrame
    y_train: npt.NDArray[np.int64]
    X_valid: pd.DataFrame
    y_valid: npt.NDArray[np.int64]


def lgbm_params(
    tuned: dict[str, Any], y_train: npt.ArrayLike, seed: int, num_threads: int, max_bin: int
) -> tuple[dict[str, Any], int]:
    """Full LightGBM parameters and the number of boosting rounds."""
    y = np.asarray(y_train)
    n_pos = int(y.sum())
    n_neg = int(y.size - n_pos)
    if n_pos == 0:
        raise ValueError("training rows contain no failure")
    params = {k: v for k, v in tuned.items() if k != "num_boost_round"}
    params.update(LGBM_FIXED)
    params.update(
        {
            "scale_pos_weight": n_neg / n_pos,
            "seed": seed,
            "num_threads": num_threads,
            "max_bin": max_bin,
        }
    )
    return params, int(tuned["num_boost_round"])


def lgbm_dataset(X: pd.DataFrame, y: npt.ArrayLike, max_bin: int) -> lgb.Dataset:
    return lgb.Dataset(
        X.to_numpy(dtype=np.float64),
        label=np.asarray(y, dtype=np.float64),
        feature_name=[str(c) for c in X.columns],
        params={"max_bin": max_bin, "verbosity": -1, "feature_pre_filter": False},
        free_raw_data=False,
    )


def fit_lgbm(
    X: pd.DataFrame,
    y: npt.ArrayLike,
    tuned: dict[str, Any],
    seed: int,
    num_threads: int = 1,
    max_bin: int = 63,
    dataset: lgb.Dataset | None = None,
) -> lgb.Booster:
    params, rounds = lgbm_params(tuned, y, seed, num_threads, max_bin)
    data = dataset if dataset is not None else lgbm_dataset(X, y, max_bin)
    return lgb.train(params, data, num_boost_round=rounds)


def lgbm_raw(booster: lgb.Booster, X: pd.DataFrame) -> FloatArray:
    """Raw scores (log-odds of the class-weighted model)."""
    return np.asarray(booster.predict(X.to_numpy(dtype=np.float64), raw_score=True), np.float64)


def lgbm_shap(booster: lgb.Booster, X: pd.DataFrame) -> tuple[FloatArray, FloatArray]:
    """TreeSHAP values [rows, columns] and the expected value per row (log-odds)."""
    contrib = np.asarray(
        booster.predict(X.to_numpy(dtype=np.float64), pred_contrib=True), dtype=np.float64
    )
    return contrib[:, :-1], contrib[:, -1]


def suggest_lgbm(trial: optuna.Trial) -> dict[str, Any]:
    """Search space, biased towards strong regularisation for a small, imbalanced sample."""
    return {
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
        "num_boost_round": trial.suggest_int("num_boost_round", 50, 800, log=True),
        "num_leaves": trial.suggest_int("num_leaves", 2, 16),
        "max_depth": trial.suggest_int("max_depth", 1, 5),
        "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 10, 80),
        "feature_fraction": trial.suggest_float("feature_fraction", 0.05, 0.5),
        "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
        "lambda_l1": trial.suggest_float("lambda_l1", 1e-3, 10.0, log=True),
        "lambda_l2": trial.suggest_float("lambda_l2", 1e-2, 100.0, log=True),
        "min_gain_to_split": trial.suggest_float("min_gain_to_split", 0.0, 1.0),
        "extra_trees": trial.suggest_categorical("extra_trees", [False, True]),
    }


LGBM_SEARCH_SPACE = {
    "learning_rate": "log-uniform [0.01, 0.2]",
    "num_boost_round": "log-uniform integer [50, 800]",
    "num_leaves": "integer [2, 16]",
    "max_depth": "integer [1, 5]",
    "min_data_in_leaf": "integer [10, 80]",
    "feature_fraction": "uniform [0.05, 0.5]",
    "bagging_fraction": "uniform [0.5, 1.0] (bagging every iteration)",
    "lambda_l1": "log-uniform [0.001, 10]",
    "lambda_l2": "log-uniform [0.01, 100]",
    "min_gain_to_split": "uniform [0, 1]",
    "extra_trees": "{false, true}",
}


@dataclass
class TuningResult:
    best_params: dict[str, Any]
    best_value: float
    best_fold_values: list[float]
    trials: list[dict[str, Any]] = field(default_factory=list)
    sampler: str = ""


def tune_lgbm(
    folds: Sequence[FoldData],
    n_trials: int,
    sampler_seed: int,
    model_seed: int,
    num_threads: int,
    max_bin: int,
) -> TuningResult:
    """Optuna TPE search maximising mean average precision over the folds."""
    optuna.logging.set_verbosity(logging.WARNING)
    datasets = [lgbm_dataset(f.X_train, f.y_train, max_bin) for f in folds]

    def objective(trial: optuna.Trial) -> float:
        tuned = suggest_lgbm(trial)
        values = []
        for fold, dataset in zip(folds, datasets, strict=True):
            booster = fit_lgbm(
                fold.X_train, fold.y_train, tuned, model_seed, num_threads, max_bin, dataset
            )
            values.append(average_precision(fold.y_valid, lgbm_raw(booster, fold.X_valid)))
        trial.set_user_attr("fold_average_precision", values)
        return float(np.mean(values))

    sampler = optuna.samplers.TPESampler(seed=sampler_seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    best = study.best_trial
    trials = [
        {
            "number": t.number,
            "params": dict(t.params),
            "mean_average_precision": t.value,
            "fold_average_precision": t.user_attrs.get("fold_average_precision"),
        }
        for t in study.trials
    ]
    return TuningResult(
        best_params=dict(best.params),
        best_value=float(best.value) if best.value is not None else float("nan"),
        best_fold_values=list(best.user_attrs["fold_average_precision"]),
        trials=trials,
        sampler=f"optuna TPESampler(seed={sampler_seed}), {n_trials} trials, sequential",
    )


def make_logreg(C: float) -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=C, l1_ratio=0.0, class_weight="balanced", solver="lbfgs", max_iter=20000
                ),
            ),
        ]
    )


def logreg_score(model: Pipeline, X: pd.DataFrame) -> FloatArray:
    """Decision function (log-odds of the class-weighted model)."""
    return np.asarray(model.decision_function(X.to_numpy(dtype=np.float64)), dtype=np.float64)


def fit_logreg(X: pd.DataFrame, y: npt.ArrayLike, C: float) -> Pipeline:
    model = make_logreg(C)
    model.fit(X.to_numpy(dtype=np.float64), np.asarray(y))
    return model


def tune_logreg(folds: Sequence[FoldData], grid: Sequence[float]) -> TuningResult:
    """Grid search over C; ties go to the smaller C (stronger regularisation)."""
    trials: list[dict[str, Any]] = []
    for C in sorted(grid):
        values = [
            average_precision(
                f.y_valid, logreg_score(fit_logreg(f.X_train, f.y_train, C), f.X_valid)
            )
            for f in folds
        ]
        trials.append(
            {
                "params": {"C": C},
                "mean_average_precision": float(np.mean(values)),
                "fold_average_precision": values,
            }
        )
    best = max(trials, key=lambda t: (t["mean_average_precision"], -t["params"]["C"]))
    return TuningResult(
        best_params=dict(best["params"]),
        best_value=float(best["mean_average_precision"]),
        best_fold_values=list(best["fold_average_precision"]),
        trials=trials,
        sampler=f"grid over C = {sorted(grid)}",
    )


BRF_SETTINGS: dict[str, Any] = {
    "sampling_strategy": "all",
    "replacement": True,
    "bootstrap": False,
    "max_features": "sqrt",
    "min_samples_leaf": 1,
}


def fit_brf(
    X: pd.DataFrame, y: npt.ArrayLike, n_estimators: int, seed: int, n_jobs: int
) -> Pipeline:
    model = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            (
                "model",
                BalancedRandomForestClassifier(
                    n_estimators=n_estimators, random_state=seed, n_jobs=n_jobs, **BRF_SETTINGS
                ),
            ),
        ]
    )
    model.fit(X.to_numpy(dtype=np.float64), np.asarray(y))
    return model


def brf_probability(model: Pipeline, X: pd.DataFrame) -> FloatArray:
    return np.asarray(model.predict_proba(X.to_numpy(dtype=np.float64))[:, 1], dtype=np.float64)


def probability_logit(p: npt.ArrayLike, eps: float = 1e-6) -> FloatArray:
    """Log-odds of a probability, clipped to [eps, 1 - eps] so it stays finite."""
    q = np.clip(np.asarray(p, dtype=np.float64), eps, 1.0 - eps)
    return np.asarray(np.log(q / (1.0 - q)), dtype=np.float64)


def fold_scores(
    folds: Sequence[FoldData], fit_and_score: Callable[[FoldData], FloatArray]
) -> list[FloatArray]:
    """Out-of-fold scores: each fold's evaluation rows scored by the model fitted on its
    training rows (``fit_and_score`` fits on ``fold.X_train`` and scores ``fold.X_valid``)."""
    return [np.asarray(fit_and_score(f), dtype=np.float64) for f in folds]
