"""Training-only preprocessing and Platt calibration (SYNTHETIC inputs)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import special

from yg_secom.calibration import PlattCalibrator
from yg_secom.preprocess import Preprocessor, indicator_name, sensor_of


def _frame(seed: int = 0, n: int = 300) -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, 6)), columns=[f"S{i:03d}" for i in range(1, 7)])
    y = (rng.random(n) < 0.2).astype(np.int64)
    X["S002"] = 3.0  # constant
    X["S003"] = np.nan  # never measured
    X.loc[y == 1, "S004"] = np.nan  # missing exactly when failed: strongly informative
    X.loc[rng.random(n) < 0.05, "S005"] = np.nan  # uninformative missingness
    return X, y


def test_learned_state_comes_from_fitting_rows_only() -> None:
    X, y = _frame()
    train = np.arange(200)
    pre = Preprocessor(fdr=0.05).fit(X.iloc[train], y[train])
    X_changed = X.copy()
    X_changed.iloc[200:] = 99.0  # later rows changed beyond recognition
    y_changed = y.copy()
    y_changed[200:] = 1 - y_changed[200:]
    again = Preprocessor(fdr=0.05).fit(X_changed.iloc[train], y_changed[train])
    assert pre.to_dict() == again.to_dict()
    assert pre.n_fit_rows == 200


def test_drops_constants_and_adds_significant_indicators() -> None:
    X, y = _frame()
    pre = Preprocessor(fdr=0.05).fit(X, y)
    assert pre.dropped == {
        "S002": "constant in the fitting rows",
        "S003": "all readings missing in the fitting rows",
    }
    assert "S004" in pre.indicators
    assert "S005" not in pre.indicators
    out = pre.transform(X)
    assert list(out.columns) == [*pre.kept, indicator_name("S004")]
    assert out[indicator_name("S004")].tolist() == X["S004"].isna().astype(float).tolist()
    assert out["S001"].isna().sum() == 0
    assert out["S004"].isna().sum() == int(y.sum())  # missing values are kept, not imputed
    assert sensor_of("S004_missing") == "S004"
    assert pre.output_sensors == ["S001", "S004", "S005", "S006"]


def test_transform_requires_fit_and_features() -> None:
    X, y = _frame()
    with pytest.raises(RuntimeError):
        Preprocessor().transform(X)
    pre = Preprocessor().fit(X, y)
    with pytest.raises(ValueError, match="lacks"):
        pre.transform(X.drop(columns=["S001"]))


def test_platt_recovers_known_parameters() -> None:
    rng = np.random.default_rng(1)
    z = rng.normal(scale=2.0, size=20000)
    a_true, b_true = -1.3, 2.0
    y = (rng.random(z.size) < special.expit(-(a_true * z + b_true))).astype(np.int64)
    cal = PlattCalibrator.fit(z, y)
    assert cal.converged
    assert cal.a == pytest.approx(a_true, abs=0.06)
    assert cal.b == pytest.approx(b_true, abs=0.08)
    assert cal.increasing
    p = cal.predict(z)
    assert np.all(np.diff(p[np.argsort(z)]) >= 0)
    assert cal.to_contract() == {"method": "platt", "a": cal.a, "b": cal.b}


def test_platt_is_finite_with_separable_data_and_rejects_one_class() -> None:
    z = np.array([-3.0, -2.0, -1.0, 1.0, 2.0, 3.0])
    y = np.array([0, 0, 0, 1, 1, 1])
    cal = PlattCalibrator.fit(z, y)  # smoothed targets keep the fit finite
    assert cal.converged
    assert np.isfinite(cal.a)
    assert 0.0 < cal.predict(np.array([10.0]))[0] < 1.0
    with pytest.raises(ValueError, match="both classes"):
        PlattCalibrator.fit(z, np.zeros(6, dtype=np.int64))
