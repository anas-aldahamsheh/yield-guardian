"""Every tunable constant of the SECOM pipeline, in one place.

The defaults are the values used for the published bundle. A run records the full
configuration in ``metrics.json``. Tests override fields to run the same code quickly on
small synthetic data; such runs are never published.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PipelineConfig:
    """Configuration of one pipeline run."""

    # Reproducibility. Every random stream is derived from this seed by name.
    seed: int = 20261014

    # Expected shape of the source data (UCI documentation; verified at load).
    expected_units: int = 1567
    expected_features: int = 590

    # Chronological blocks. The test block is the last ``test_fraction`` of units in time
    # order; everything before it is the development period. The train block is the first
    # ``warmup_fraction`` of the development period (the rolling-origin warm-up, used only
    # for fitting); the validation block is the rest of the development period, cut into
    # rolling-origin evaluation slices. Each block must hold ``min_block_failures``.
    test_fraction: float = 0.2
    warmup_fraction: float = 0.3
    min_block_failures: int = 15

    # Rolling-origin cross-validation over the validation block.
    cv_folds: int = 5
    cv_min_fold_failures: int = 5

    # Preprocessing: missingness indicators where Fisher's exact test is significant.
    indicator_fdr: float = 0.05

    # LightGBM and its tuning.
    optuna_trials: int = 80
    lgbm_num_threads: int = 1
    lgbm_max_bin: int = 63

    # Baselines.
    logreg_c_grid: tuple[float, ...] = (
        1e-5,
        3e-5,
        1e-4,
        3e-4,
        1e-3,
        3e-3,
        1e-2,
        3e-2,
        1e-1,
        3e-1,
        1.0,
        3.0,
    )
    brf_n_estimators: int = 500

    # Calibration and evaluation.
    reliability_bins: int = 5
    bootstrap_resamples: int = 2000
    ci_level: float = 0.95
    fpr_targets: tuple[float, ...] = (0.05, 0.10)
    default_fpr: float = 0.05

    # Root cause.
    correlation_threshold: float = 0.8
    correlation_min_pairs: int = 30
    stability_refits: int = 100
    stability_top_k: int = 20
    stability_threshold: float = 0.7
    permutations: int = 200
    fdr_q: float = 0.05

    # Fault detection and classification (FDC).
    fdc_reference_fractions: tuple[float, ...] = (0.5, 0.4, 0.3, 0.2)
    fdc_max_missing: float = 0.5
    fdc_variance_target: float = 0.9
    fdc_parallel_iterations: int = 200
    fdc_stationarity_components: int = 5
    fdc_stationarity_alpha: float = 0.05
    fdc_alphas: tuple[float, float] = (0.01, 0.001)
    ewma_lambda: float = 0.2
    ewma_l: float = 2.962
    cusum_k: float = 0.5
    cusum_h: float = 5.0
    leading_groups: int = 5

    # Sensor health.
    health_min_window_readings: int = 5
    health_flatline_probability: float = 1e-3
    health_stuck_family_alpha: float = 0.01
    health_jump_reference_share: float = 0.001
    health_watch_out_of_reference: float = 0.05
    health_maintenance_out_of_reference: float = 0.20
    health_watch_window_missing: float = 0.20
    health_maintenance_window_missing: float = 0.50
    health_normal_missing: float = 0.10

    # Parallel workers for independent refits (each refit is single-threaded and seeded,
    # so results do not depend on this number).
    n_jobs: int = 4

    # Data integrity: require the SHA-256 of each source file to match data/manifest.json.
    require_data_manifest: bool = True

    # Experiment tracking (local MLflow store under <repo>/mlruns).
    mlflow: bool = True

    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def with_overrides(self, overrides: dict[str, Any]) -> PipelineConfig:
        """A copy with some fields replaced; unknown names are an error."""
        names = {f.name for f in dataclasses.fields(self)}
        unknown = sorted(set(overrides) - names)
        if unknown:
            raise ValueError(f"unknown configuration fields: {unknown}")
        converted: dict[str, Any] = {}
        for key, value in overrides.items():
            current = getattr(self, key)
            converted[key] = tuple(value) if isinstance(current, tuple) else value
        return dataclasses.replace(self, **converted)

    @classmethod
    def from_json(cls, path: Path) -> PipelineConfig:
        return cls().with_overrides(json.loads(path.read_text(encoding="utf-8")))
