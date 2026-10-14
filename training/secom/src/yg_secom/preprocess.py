"""Training-only preprocessing for the failure-risk models.

``Preprocessor.fit`` sees only the rows it is given (a fold's training rows, or the train
block); ``transform`` applies what was learned to any rows without looking at their values
for anything but the output. Learned state:

1. Features with no reading, or a single distinct reading, in the fitting rows are dropped.
2. Missing readings stay missing (LightGBM learns a direction for them at every split).
3. A missingness indicator ``<sensor>_missing`` is added where Fisher's exact test on the
   fitting rows associates "reading missing" with failure, with Benjamini-Hochberg control
   of the false discovery rate across all sensors that have both missing and present
   readings. This includes sensors whose present readings are constant: their raw column is
   dropped by rule 1, but their missingness can still carry information.

Imputation for the linear baseline is not done here; it lives inside that model's own
pipeline, where it is also fitted on training rows only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import stats
from yg_common.multiple_testing import benjamini_hochberg

INDICATOR_SUFFIX = "_missing"


def indicator_name(sensor: str) -> str:
    return f"{sensor}{INDICATOR_SUFFIX}"


def sensor_of(column: str) -> str:
    """The sensor a model column comes from (indicators map to their sensor)."""
    return column.removesuffix(INDICATOR_SUFFIX)


@dataclass
class Preprocessor:
    """Learns which columns to keep and which missingness indicators to add."""

    fdr: float = 0.05
    features_in: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    dropped: dict[str, str] = field(default_factory=dict)
    indicators: list[str] = field(default_factory=list)
    indicator_tests: list[dict[str, Any]] = field(default_factory=list)
    n_fit_rows: int = 0
    fitted: bool = False

    def fit(self, X: pd.DataFrame, y: npt.ArrayLike) -> Preprocessor:
        labels = np.asarray(y).astype(np.int64)
        if labels.shape[0] != X.shape[0]:
            raise ValueError("X and y must have the same number of rows")
        self.features_in = [str(c) for c in X.columns]
        self.n_fit_rows = int(X.shape[0])
        nunique = X.nunique(dropna=True)
        self.dropped = {}
        self.kept = []
        for column in self.features_in:
            if nunique[column] == 0:
                self.dropped[column] = "all readings missing in the fitting rows"
            elif nunique[column] == 1:
                self.dropped[column] = "constant in the fitting rows"
            else:
                self.kept.append(column)

        missing = X.isna().to_numpy()
        n_missing = missing.sum(axis=0)
        n = X.shape[0]
        fail = labels == 1
        tested_columns: list[str] = []
        p_values: list[float] = []
        tests: list[dict[str, Any]] = []
        for j, column in enumerate(self.features_in):
            if not 0 < n_missing[j] < n:
                continue
            miss_j = missing[:, j]
            table = np.array(
                [
                    [int(np.sum(miss_j & fail)), int(np.sum(miss_j & ~fail))],
                    [int(np.sum(~miss_j & fail)), int(np.sum(~miss_j & ~fail))],
                ]
            )
            result = stats.fisher_exact(table, alternative="two-sided")
            tested_columns.append(column)
            p_values.append(float(result.pvalue))
            tests.append(
                {
                    "sensor": column,
                    "missing_failed": int(table[0, 0]),
                    "missing_passed": int(table[0, 1]),
                    "present_failed": int(table[1, 0]),
                    "present_passed": int(table[1, 1]),
                    "odds_ratio": _finite(float(result.statistic)),
                    "p_value": float(result.pvalue),
                }
            )
        q_values = benjamini_hochberg(np.asarray(p_values, dtype=np.float64))
        self.indicators = []
        for test, q in zip(tests, q_values, strict=True):
            test["q_value"] = float(q)
            test["indicator"] = bool(q <= self.fdr)
            if test["indicator"]:
                self.indicators.append(test["sensor"])
        self.indicator_tests = tests
        self.fitted = True
        return self

    @property
    def output_columns(self) -> list[str]:
        """Model columns: kept sensors in source order, then indicators in source order."""
        return [*self.kept, *(indicator_name(s) for s in self.indicators)]

    @property
    def output_sensors(self) -> list[str]:
        """Sensors that reach the model through a raw column or an indicator."""
        seen = dict.fromkeys(sensor_of(c) for c in self.output_columns)
        return [s for s in self.features_in if s in seen]

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if not self.fitted:
            raise RuntimeError("Preprocessor.transform called before fit")
        missing_columns = sorted(set(self.features_in) - {str(c) for c in X.columns})
        if missing_columns:
            raise ValueError(f"input lacks fitted features: {missing_columns[:5]}")
        out = X.loc[:, self.kept].astype(np.float64).copy()
        for sensor in self.indicators:
            out[indicator_name(sensor)] = X[sensor].isna().astype(np.float64).to_numpy()
        return out

    def fit_transform(self, X: pd.DataFrame, y: npt.ArrayLike) -> pd.DataFrame:
        return self.fit(X, y).transform(X)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_fit_rows": self.n_fit_rows,
            "features_in": len(self.features_in),
            "model_features": self.output_columns,
            "kept_sensors": self.kept,
            "dropped": [{"sensor": s, "reason": r} for s, r in self.dropped.items()],
            "missingness_indicators": [indicator_name(s) for s in self.indicators],
            "indicator_rule": (
                "Fisher's exact test (two-sided) of reading-missing versus failure on the "
                f"fitting rows; Benjamini-Hochberg across tested sensors; indicator when "
                f"q <= {self.fdr}"
            ),
            "indicator_tests": self.indicator_tests,
        }


def _finite(x: float) -> float | None:
    return x if np.isfinite(x) else None
