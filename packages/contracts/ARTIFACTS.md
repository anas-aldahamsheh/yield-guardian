# Artifact contracts

Training pipelines write versioned bundles; the API only reads them. A bundle is a folder `artifacts/<name>/<version>/` containing the files below and a `MANIFEST.json`. The lead publishes bundles as GitHub Release assets, and image builds verify every checksum.

Changing a format means a new version folder and a note to the lead. Never change a published version in place.

## Common rules

- **`MANIFEST.json`** (required in every bundle):

  ```json
  {
    "name": "secom",
    "version": "v1",
    "created_at": "2026-10-14T12:00:00Z",
    "git_commit": "<40 hex>",
    "data": [{"path": "data/raw/secom/secom.data", "sha256": "<64 hex>"}],
    "environment": {"python": "3.13.x", "packages": {"lightgbm": "4.7.0"}},
    "files": [{"path": "timeline.parquet", "bytes": 123, "sha256": "<64 hex>"}]
  }
  ```

- **Sensor IDs:** column *i* (0-based) of `secom.data` is sensor `S{i+1:03d}`, so the first column is `S001` and the last `S590`. Every file uses these IDs.
- **Model feature names** are sensor IDs, or `<sensor>_missing` for a missingness indicator (for example `S060_missing`).
- **Unit IDs:** row *r* (0-based) of `secom.data` is unit `r`. Rows are kept in the file's order; time order comes from the timestamp in `secom_labels.data`.
- **Estimates with uncertainty** are always objects: `{"value": 0.41, "ci_low": 0.30, "ci_high": 0.52, "ci_level": 0.95, "method": "stratified bootstrap, 2000 resamples", "n": 313}`. `value` is never null: a quantity that is undefined (for example precision with no positive predictions) is left out, and the reason goes in the limitations. `ci_low` and `ci_high` may be null only when a bound cannot be computed, with the reason in an optional `note`.
- **Timestamps** are ISO 8601 strings in UTC, or Parquet timestamps in UTC.
- Parquet files are written with pyarrow, compression `zstd`.

## SECOM bundle: `artifacts/secom/v1/` (worker 2)

| File | Content |
|---|---|
| `timeline.parquet` | One row per unit, sorted by timestamp. Columns below. |
| `shap.npz` | `values` float32 [units, features] (TreeSHAP in log-odds), `base_value` float (expected value of the final model), `base_values` float32 [units] (expected value of the model that explained each row, since rolling-origin fold models have their own), `features` str [features] (model feature names in model order), `unit_ids` int [units]. Rows with no out-of-sample prediction are NaN. |
| `fdc.npz` | `contrib_t2` and `contrib_spe` float32 [units, fdc_features], `features` str [fdc_features], `unit_ids` int [units]. |
| `fdc_model.npz` | `center`, `scale`, `loadings`, `eigenvalues`, `n_components`, `features`, `impute_values` (reference medians that replace missing readings before scaling), `t2_limit_99`, `t2_limit_999`, `spe_limit_99`, `spe_limit_999`, `reference_unit_ids`. Enough to score a new unit with numpy only. |
| `groups.json` | Correlated sensor groups and their statistics (schema below). |
| `health.json` | Sensor health findings (schema below). |
| `operating_points.json` | Threshold table on the test block (schema below). |
| `metrics.json` | Every metric of the main model and the baselines, with CIs, the split boundaries and the tuning record, plus the keys the API reads (below). |
| `model.txt` | LightGBM model in text format. |
| `calibrator.json` | `{"method": "platt", "a": float, "b": float}` applied to raw log-odds: p = 1 / (1 + exp(a * z + b)). |
| `preprocess.json` | Ordered model features, dropped features with the reason, missingness-indicator features. |
| `eda.json` | Counts, time range, missingness summary, constant features, class balance. |
| `model_card.md` | Intended use, data, method, results with CIs, limitations. |

`timeline.parquet` columns:

| Column | Type | Meaning |
|---|---|---|
| `unit_id` | int32 | Row index in `secom.data` |
| `timestamp` | timestamp[UTC] | From `secom_labels.data` |
| `label` | int8 | 1 = failed final test, 0 = passed (source encodes 1 and -1) |
| `block` | string | `train`, `validation` or `test` |
| `risk` | float32, nullable | Calibrated failure probability, always out of sample (see `risk_source`); null during the warm-up period |
| `risk_source` | string, nullable | `oof` (rolling-origin fold model), `validation` (model fit on train; calibrator fit on these rows, so calibration is in-sample here) or `test` (final model, untouched block) |
| `risk_band` | string, nullable | `low`, `elevated` or `high`, from the thresholds in `operating_points.json` |
| `t2`, `spe` | float32 | FDC statistics |
| `t2_limit_99`, `t2_limit_999`, `spe_limit_99`, `spe_limit_999` | float32 | Control limits |
| `fdc_alarm` | string | `none`, `warning` (beyond the 99% limit) or `alarm` (beyond the 99.9% limit) |
| `fdc_period` | string | `reference` (used to fit the FDC model) or `monitoring` |
| `ewma_alarm`, `cusum_alarm` | bool | Small-shift detectors on the leading sensor groups |

`metrics.json` may hold any record the pipeline keeps, and must hold these keys, which the API reads and validates strictly:

| Key | Content |
|---|---|
| `report` | The results exactly in the API's `SecomMetrics` shape without `bundle` (`packages/contracts/openapi.json`, `#/components/schemas/SecomMetrics`): `blocks`, `models`, `comparisons`, `calibration`, `tuning`, `fdc`, `limitations`. |
| `fdc_reference` | `{"start": "...", "end": "...", "units": 300, "stationarity": "<test used and its result>"}` for the FDC reference period. |
| `fdc_explained_variance` | Share of the reference-period variance captured by the retained components (0 to 1). |
| `methods` | `{"explanation": "...", "fdc": "...", "contributions": "..."}`: one sentence each, describing the method as it was run (for example the number of components and how the limits were set). |

`groups.json`:

```json
{
  "method": {"correlation": "spearman", "threshold": 0.8, "linkage": "average",
             "stability_refits": 100, "stability_threshold": 0.7,
             "permutations": 200, "fdr_q": 0.05},
  "groups": [
    {"group_id": "G01", "sensors": ["S060", "S061"], "representative": "S060",
     "importance": 0.12, "stability": 0.93, "p_value": 0.004, "q_value": 0.03,
     "significant": true,
     "univariate": [{"sensor": "S060", "mann_whitney_p": 0.001, "q_value": 0.02,
                     "direction": "higher_in_failures"}]}
  ]
}
```

`direction` is `higher_in_failures`, `lower_in_failures`, `no_difference` or `not_tested`; `mann_whitney_p` and `q_value` are null when the test was not run.

`health.json`:

```json
{
  "rules": ["dead: constant or never measured", "maintenance: ...", "watch: ..."],
  "windows": [{"window_id": 0, "start": "...", "end": "...", "unit_ids": [0, 1]}],
  "sensors": [
    {"sensor": "S001", "missing_rate": 0.004, "missing_by_window": [0.0, 0.01],
     "flatline_windows": [], "stuck_value": null, "jump_unit_ids": [],
     "out_of_reference_rate": 0.01,
     "missing_vs_failure": {"odds_ratio": 1.2, "p_value": 0.4, "q_value": 0.9},
     "status": "ok", "reasons": []}
  ]
}
```

`status` is one of `ok`, `watch`, `maintenance`, `dead` (constant or never measured). `rules` lists every status rule with its thresholds, worded as in the model card. `reasons` names the rules that set this sensor's status, with the values that triggered them (empty when `ok`).

`operating_points.json`:

```json
{
  "block": "test",
  "default": "fpr_0.05",
  "units": 313,
  "failures": 17,
  "prevalence": 0.0543,
  "points": [
    {"id": "fpr_0.05", "label": "5% false-alarm rate", "target_fpr": 0.05, "threshold": 0.12,
     "fpr": {"value": 0.05, "ci_low": 0.03, "ci_high": 0.07},
     "recall": {"value": 0.4, "ci_low": 0.2, "ci_high": 0.6},
     "precision": {"value": 0.2, "ci_low": 0.1, "ci_high": 0.3},
     "false_alarms_per_100": {"value": 4.7, "ci_low": 2.8, "ci_high": 6.6},
     "tp": 8, "fp": 15, "tn": 280, "fn": 12}
  ],
  "curve": [{"threshold": 0.01, "fpr": 0.9, "recall": 1.0, "precision": 0.07}]
}
```

Thresholds are chosen on the validation block and reported on the test block. `label` is plain words for the interface. `target_fpr` is the false-alarm rate the threshold was chosen for (null for points chosen another way, which `label` then states). `false_alarms_per_100` is false alarms per 100 units processed, or null.

## Wafer-map bundle: `artifacts/wafermap/v1/` (worker 3)

| File | Content |
|---|---|
| `model.onnx` | Input `maps` float32 [N, 3, 64, 64], channels `no_die`, `pass`, `fail`. Outputs `logits` float32 [N, 9] and `embedding` float32 [N, 128], L2-normalised. |
| `labels.json` | Class names in output order. |
| `preprocess.json` | `{"size": 64, "resize": "nearest", "channels": ["no_die", "pass", "fail"], "source_values": {"no_die": 0, "pass": 1, "fail": 2}}` |
| `calibration.json` | `{"method": "temperature", "temperature": float}` |
| `ood.json` | `{"method": "energy", "threshold": float, "in_distribution_recall": float}` plus the Mahalanobis section. The API uses the Mahalanobis section (`threshold`, `score`, `parameters`) as the unknown-pattern score (lead decision: leave-one-class-out mean AUROC 0.922 versus 0.545 for energy); energy is reported only as a cross-check |
| `ood_mahalanobis.npz` | `class_means` [9, 128], `precision` [128, 128] |
| `metrics.json` | Every metric with CIs for both splits and each seed, the baseline, the leave-one-class-out results and similarity precision@10 |
| `demo/wafers.parquet` | Derived demo subset: `wafer_id` (string `"<lot>-<index>"`), `lot`, `wafer_index`, `die_size`, `label` (nullable), `official_split`, `height`, `width`, `map` (uint8 bytes, row-major, values 0, 1, 2) |
| `demo/lots.json` | Per demo lot: wafers, pattern counts, binomial test per pattern (count, expected rate, p, q, flagged), stacked failure map (height, width, frequencies) |
| `demo/ATTRIBUTION.md` | Source, citation, licence of WM-811K |
| `model_card.md` | Intended use, data, method, results with CIs, limitations |
