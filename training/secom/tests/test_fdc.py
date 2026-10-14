"""FDC limits against hand computation and simulation; run lengths against published
tables (all inputs SYNTHETIC)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from yg_secom.fdc import (
    cusum_arl_two_sided,
    cusum_chart,
    ewma_arl,
    ewma_chart,
    fit_fdc,
    parallel_analysis,
    select_reference,
    spe_limit,
    split_reference,
    stationarity_check,
    t2_limit,
)


def test_t2_limit_matches_the_written_formula() -> None:
    a, n, alpha = 3, 50, 0.01
    by_hand = 3 * (50**2 - 1) / (50 * (50 - 3)) * stats.f.ppf(0.99, 3, 47)
    assert t2_limit(a, n, alpha) == pytest.approx(by_hand, rel=1e-12)
    assert by_hand == pytest.approx(13.488, abs=0.001)  # 3.19021 x F(0.99; 3, 47) = 4.2279


def test_t2_limit_has_its_nominal_false_alarm_rate() -> None:
    """With every component kept, T^2 of a new Gaussian point is exactly F distributed."""
    rng = np.random.default_rng(0)
    n, p, reps = 30, 3, 4000
    exceed = 0
    for _ in range(reps):
        ref = pd.DataFrame(
            rng.normal(size=(n, p)) * [1.0, 3.0, 0.5], columns=["S001", "S002", "S003"]
        )
        model = fit_fdc(
            ref, np.arange(n), max_missing=0.5, variance_target=1.0, alphas=(0.01, 0.001)
        )
        assert model.n_components == p
        new = pd.DataFrame(rng.normal(size=(1, p)) * [1.0, 3.0, 0.5], columns=ref.columns)
        exceed += int(model.score(new)["t2"][0] > model.t2_limits[0.01])
    assert exceed / reps == pytest.approx(0.01, abs=0.005)


def test_spe_limit_matches_jackson_mudholkar_by_hand_and_by_simulation() -> None:
    lam = np.array([2.0, 1.0, 0.5])
    t1, t2, t3 = 3.5, 5.25, 9.125
    h0 = 1 - 2 * t1 * t3 / (3 * t2**2)
    c = stats.norm.ppf(0.99)
    by_hand = t1 * (c * math.sqrt(2 * t2 * h0**2) / t1 + 1 + t2 * h0 * (h0 - 1) / t1**2) ** (1 / h0)
    limit, method = spe_limit(lam, 0.01)
    assert method == "Jackson-Mudholkar"
    assert limit == pytest.approx(by_hand, rel=1e-12)
    # The approximation is meant for many residual eigenvalues, as in PCA monitoring.
    many = np.asarray(0.9 ** np.arange(40), dtype=np.float64)
    rng = np.random.default_rng(1)
    simulated = rng.normal(size=(200_000, many.size)) ** 2 @ many
    for alpha in (0.01, 0.001):
        limit, _ = spe_limit(many, alpha)
        assert limit == pytest.approx(float(np.quantile(simulated, 1 - alpha)), rel=0.03)


def test_contributions_add_up_and_missing_readings_are_imputed() -> None:
    rng = np.random.default_rng(2)
    ref = pd.DataFrame(rng.normal(size=(80, 6)), columns=[f"S{i:03d}" for i in range(1, 7)])
    ref.iloc[3, 2] = np.nan
    model = fit_fdc(ref, np.arange(80), max_missing=0.5, variance_target=0.6, alphas=(0.01, 0.001))
    assert 0 < model.n_components < 6
    new = pd.DataFrame(rng.normal(size=(10, 6)), columns=ref.columns)
    new.iloc[0, 1] = np.nan
    scored = model.score(new)
    np.testing.assert_allclose(scored["contrib_t2"].sum(axis=1), scored["t2"], rtol=1e-10)
    np.testing.assert_allclose(scored["contrib_spe"].sum(axis=1), scored["spe"], rtol=1e-10)
    assert np.all(np.isfinite(scored["t2"]))
    assert abs(float(model.standardize(ref).mean())) < 1e-12  # centred on the reference


@pytest.mark.parametrize(("h", "expected"), [(5.0, 465.0), (4.0, 168.0)])
def test_cusum_in_control_run_length_matches_tables(h: float, expected: float) -> None:
    assert cusum_arl_two_sided(0.5, h) == pytest.approx(expected, rel=0.02)


def test_ewma_in_control_run_length_matches_tables() -> None:
    assert ewma_arl(0.2, 2.962) == pytest.approx(500.0, rel=0.02)


def test_charts_signal_on_a_shift_and_restart() -> None:
    u = np.r_[np.zeros(50), np.full(50, 2.0)]
    _, limit, ewma_flags = ewma_chart(u, 0.2, 2.962)
    assert not ewma_flags[:50].any()
    assert ewma_flags[50:].any()
    assert limit == pytest.approx(2.962 * math.sqrt(0.2 / 1.8))
    upper, _, cusum_flags = cusum_chart(u, 0.5, 5.0)
    first = int(np.flatnonzero(cusum_flags)[0])
    assert 50 <= first <= 55
    assert upper[first + 1] < upper[first]  # restarted after the signal


def test_stationarity_check_and_reference_selection() -> None:
    rng = np.random.default_rng(3)
    n, p = 400, 8
    drift = np.linspace(0, 6, n)[:, None]
    X = pd.DataFrame(
        rng.normal(size=(n, p)) + drift * (np.arange(p) < 4),
        columns=[f"S{i:03d}" for i in range(1, p + 1)],
    )
    trending = stationarity_check(X.to_numpy() - X.to_numpy().mean(axis=0), 5, 0.05)
    assert not trending["stationary"]
    calm = rng.normal(size=(200, p))
    assert stationarity_check(calm - calm.mean(axis=0), 5, 0.05)["stationary"]
    labels = np.zeros(n, dtype=np.int8)
    ids = np.arange(n, dtype=np.int64)
    chosen, record = select_reference(
        ids,
        labels,
        X,
        fractions=(0.5, 0.2, 0.05),
        max_missing=0.5,
        n_components=5,
        family_alpha=0.05,
    )
    assert record["candidates"][0]["stationary"] is False
    assert chosen.size < 200
    ts = pd.Series(pd.date_range("2008-07-19", periods=n, freq="h", tz="UTC"))
    fit, held = split_reference(chosen, ts)
    assert fit.size + held.size == chosen.size
    assert fit.max() < held.min()


def test_parallel_analysis_keeps_real_structure_only() -> None:
    rng = np.random.default_rng(4)
    factor = rng.normal(size=(300, 1))
    Z = np.hstack([factor + 0.3 * rng.normal(size=(300, 4)), rng.normal(size=(300, 6))])
    retained, _ = parallel_analysis(Z, iterations=50, seed=0)
    assert retained == 1
