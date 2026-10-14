# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: flows.spec.ts >> methods: every model card renders
- Location: e2e/stack/flows.spec.ts:111:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('section, div').filter({ has: getByRole('heading', { name: 'Model cards', exact: true }) }).last().getByRole('heading').nth(1)
Expected: visible
Timeout: 20000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" locator('section, div').filter({ has: getByRole('heading', { name: 'Model cards', exact: true }) }).last().getByRole('heading').nth(1) with timeout 20000ms
  - waiting for locator('section, div').filter({ has: getByRole('heading', { name: 'Model cards', exact: true }) }).last().getByRole('heading').nth(1)

```

```yaml
- link "Skip to content":
  - /url: "#main"
- banner:
  - link "Yield Guardian":
    - /url: /
  - navigation "Main":
    - list:
      - listitem:
        - link "Line":
          - /url: /line
      - listitem:
        - link "Investigations":
          - /url: /investigations
      - listitem:
        - link "Wafer lab":
          - /url: /wafers
      - listitem:
        - link "Lots":
          - /url: /lots
      - listitem:
        - link "Sensor health":
          - /url: /sensors
      - listitem:
        - link "Work orders":
          - /url: /work-orders
      - listitem:
        - link "Models":
          - /url: /models
      - listitem:
        - link "Methods":
          - /url: /methods
  - link "Line replay at unit 623 of 1567. Open the line.":
    - /url: /line
    - text: Unit 623 of 1,567
  - button "Ask"
  - button "Choose the colour theme"
  - button "Try as engineer"
- main:
  - heading "Methods" [level=1]
  - paragraph: Every number the product reports, with its confidence interval, the data it was measured on and where it comes from. Findings are associations in historical data, not causes.
  - navigation "On this page":
    - link "Measured results":
      - /url: "#results"
    - 'link "SECOM: control charts and failure risk"':
      - /url: "#secom"
    - link "Wafer maps":
      - /url: "#wafermap"
    - link "Data and provenance":
      - /url: "#provenance"
  - region "Measured results":
    - heading "Measured results" [level=2]
    - paragraph: The headline numbers. A row reads “Not measured yet” until it has been measured on held-out data.
    - table "Measured results":
      - caption: Measured results
      - rowgroup:
        - row "Quantity Value Measured on":
          - columnheader "Quantity"
          - columnheader "Value"
          - columnheader "Measured on"
      - rowgroup:
        - row "SECOM failure-risk PR-AUC, LightGBM 0.08 95% CI 0.05–0.18 (n = 313) SECOM test block, held out and used once artifacts/secom/v1/metrics.json":
          - rowheader "SECOM failure-risk PR-AUC, LightGBM"
          - cell "0.08 95% CI 0.05–0.18 (n = 313)"
          - cell "SECOM test block, held out and used once artifacts/secom/v1/metrics.json"
        - row "SECOM PR-AUC of a no-skill score (the failure rate) 0.05 95% CI 0.05–0.05 (n = 313) SECOM test block, held out and used once artifacts/secom/v1/metrics.json":
          - rowheader "SECOM PR-AUC of a no-skill score (the failure rate)"
          - cell "0.05 95% CI 0.05–0.05 (n = 313)"
          - cell "SECOM test block, held out and used once artifacts/secom/v1/metrics.json"
        - row "SECOM PR-AUC, logistic regression baseline 0.17 95% CI 0.10–0.38 (n = 313) SECOM test block, held out and used once artifacts/secom/v1/metrics.json":
          - rowheader "SECOM PR-AUC, logistic regression baseline"
          - cell "0.17 95% CI 0.10–0.38 (n = 313)"
          - cell "SECOM test block, held out and used once artifacts/secom/v1/metrics.json"
        - row "Failures caught at the 5% false-alarm rate threshold 5.9% 95% CI 0–18% (n = 313) SECOM test block, held out and used once artifacts/secom/v1/operating_points.json":
          - rowheader "Failures caught at the 5% false-alarm rate threshold"
          - cell "5.9% 95% CI 0–18% (n = 313)"
          - cell "SECOM test block, held out and used once artifacts/secom/v1/operating_points.json"
        - row "False alarms per 100 units at that threshold 1.9 95% CI 0.6–3.5 (n = 313) SECOM test block, held out and used once artifacts/secom/v1/operating_points.json":
          - rowheader "False alarms per 100 units at that threshold"
          - cell "1.9 95% CI 0.6–3.5 (n = 313)"
          - cell "SECOM test block, held out and used once artifacts/secom/v1/operating_points.json"
        - row "T² false-alarm rate on held-out in-control units (99% limit) 1.9% 95% CI 0.2–6.6% (n = 106) SECOM reference period, held-out half artifacts/secom/v1/metrics.json":
          - rowheader "T² false-alarm rate on held-out in-control units (99% limit)"
          - cell "1.9% 95% CI 0.2–6.6% (n = 106)"
          - cell "SECOM reference period, held-out half artifacts/secom/v1/metrics.json"
        - row "Sensors to inspect per investigation (median), of 590 Not measured yet Recorded investigations investigations":
          - rowheader "Sensors to inspect per investigation (median), of 590"
          - cell "Not measured yet"
          - cell "Recorded investigations investigations"
        - row "Wafer-map macro-F1, lot-grouped split 0.90 95% CI 0.89–0.91 (n = 25954) WM-811K lot-grouped test split (no lot in two parts) artifacts/wafermap/v1/metrics.json":
          - rowheader "Wafer-map macro-F1, lot-grouped split"
          - cell "0.90 95% CI 0.89–0.91 (n = 25954)"
          - cell "WM-811K lot-grouped test split (no lot in two parts) artifacts/wafermap/v1/metrics.json"
        - row "Wafer-map macro-F1, official split 0.64 95% CI 0.62–0.65 (n = 118595) WM-811K official test split (test lots differ from training lots) artifacts/wafermap/v1/metrics.json":
          - rowheader "Wafer-map macro-F1, official split"
          - cell "0.64 95% CI 0.62–0.65 (n = 118595)"
          - cell "WM-811K official test split (test lots differ from training lots) artifacts/wafermap/v1/metrics.json"
        - row "Unknown-pattern AUROC, leave-one-class-out mean (Mahalanobis) 0.92 (n = 8) WM-811K, 8 held-out classes artifacts/wafermap/v1/metrics.json":
          - rowheader "Unknown-pattern AUROC, leave-one-class-out mean (Mahalanobis)"
          - cell "0.92 (n = 8)"
          - cell "WM-811K, 8 held-out classes artifacts/wafermap/v1/metrics.json"
        - row "Similar-wafer precision@10 86% 95% CI 84–87% (n = 25954) WM-811K lot-grouped test maps artifacts/wafermap/v1/metrics.json":
          - rowheader "Similar-wafer precision@10"
          - cell "86% 95% CI 84–87% (n = 25954)"
          - cell "WM-811K lot-grouped test maps artifacts/wafermap/v1/metrics.json"
        - row "Wafer maps classified automatically at 99% precision 96% 95% CI 96–96% (n = 25954) WM-811K lot-grouped test split artifacts/wafermap/v1/metrics.json":
          - rowheader "Wafer maps classified automatically at 99% precision"
          - cell "96% 95% CI 96–96% (n = 25954)"
          - cell "WM-811K lot-grouped test split artifacts/wafermap/v1/metrics.json"
        - row "Points per full investigation (Token Factory) Not measured yet Recorded investigations investigations":
          - rowheader "Points per full investigation (Token Factory)"
          - cell "Not measured yet"
          - cell "Recorded investigations investigations"
    - paragraph:
      - text: Updated
      - time: 2026-10-14 10:46
      - text: .
  - 'region "SECOM: control charts and failure risk"':
    - 'heading "SECOM: control charts and failure risk" [level=2]'
    - paragraph: The line screen leads with multivariate control charts; the failure-risk score beside them is experimental. Here is how both were measured.
    - heading "How the units were split" [level=2]
    - paragraph: "By time, never shuffled: the model is fitted on the past and tested on the future."
    - term: train
    - definition: 376 units, 53 failed (14.1%) 2008-07-19 to 2008-08-21
    - term: validation
    - definition: 878 units, 34 failed (3.9%) 2008-08-21 to 2008-10-02
    - term: test
    - definition: 313 units, 17 failed (5.4%) 2008-10-02 to 2008-10-17
    - heading "Failure-risk models on the test block" [level=2]
    - paragraph: Each point is the estimate; the bar is its confidence interval. The vertical rule in the PR-AUC column is no skill.
    - paragraph: On PR-AUC the L2 logistic regression (C tuned) scores higher than the main model (0.172 against 0.075). No skill scores 0.054, the failure rate of the test block. The failure-risk score is therefore shown as an experimental signal, not as a prediction to act on alone.
    - table "SECOM model metrics with confidence intervals":
      - caption: SECOM model metrics with confidence intervals
      - rowgroup:
        - row "Model PR-AUC ROC-AUC Brier score (lower is better) Expected calibration error":
          - columnheader "Model"
          - columnheader "PR-AUC"
          - columnheader "ROC-AUC"
          - columnheader "Brier score (lower is better)"
          - columnheader "Expected calibration error"
      - rowgroup:
        - row "LightGBM (class weights, Optuna) Main model, behind the line’s risk trace 0.08 95% CI 0.05–0.18 0.52 95% CI 0.38–0.66 0.052 95% CI 0.051–0.053 0.016 95% CI 0.015–0.043":
          - rowheader "LightGBM (class weights, Optuna) Main model, behind the line’s risk trace"
          - cell "0.08 95% CI 0.05–0.18"
          - cell "0.52 95% CI 0.38–0.66"
          - cell "0.052 95% CI 0.051–0.053"
          - cell "0.016 95% CI 0.015–0.043"
        - row "L2 logistic regression (C tuned) 0.17 95% CI 0.10–0.38 0.75 95% CI 0.65–0.85 0.052 95% CI 0.052–0.052 0.046 95% CI 0.033–0.055":
          - rowheader "L2 logistic regression (C tuned)"
          - cell "0.17 95% CI 0.10–0.38"
          - cell "0.75 95% CI 0.65–0.85"
          - cell "0.052 95% CI 0.052–0.052"
          - cell "0.046 95% CI 0.033–0.055"
        - row "Balanced random forest 0.09 95% CI 0.05–0.24 0.49 95% CI 0.36–0.63 0.052 95% CI 0.051–0.052 0.030 95% CI 0.019–0.047":
          - rowheader "Balanced random forest"
          - cell "0.09 95% CI 0.05–0.24"
          - cell "0.49 95% CI 0.36–0.63"
          - cell "0.052 95% CI 0.051–0.052"
          - cell "0.030 95% CI 0.019–0.047"
        - row "Prevalence (no skill) 0.05 95% CI 0.05–0.05 0.50 95% CI 0.50–0.50 0.052 95% CI 0.052–0.052 0.016 95% CI 0.016–0.016":
          - rowheader "Prevalence (no skill)"
          - cell "0.05 95% CI 0.05–0.05"
          - cell "0.50 95% CI 0.50–0.50"
          - cell "0.052 95% CI 0.052–0.052"
          - cell "0.016 95% CI 0.016–0.016"
    - paragraph: "Intervals: stratified bootstrap, 2000 resamples, percentile interval."
    - heading "Main model against each baseline" [level=2]
    - paragraph: "Paired on the same test units: main model minus baseline."
    - table "Paired comparisons":
      - caption: Paired comparisons
      - rowgroup:
        - row "Baseline Metric Difference p":
          - columnheader "Baseline"
          - columnheader "Metric"
          - columnheader "Difference"
          - columnheader "p"
      - rowgroup:
        - row "L2 logistic regression (C tuned) PR-AUC −0.097 95% CI −0.307 to +0.036, includes no difference 0.13":
          - rowheader "L2 logistic regression (C tuned)"
          - cell "PR-AUC"
          - cell "−0.097 95% CI −0.307 to +0.036, includes no difference"
          - cell "0.13"
        - row "Balanced random forest PR-AUC −0.011 95% CI −0.138 to +0.099, includes no difference 0.85":
          - rowheader "Balanced random forest"
          - cell "PR-AUC"
          - cell "−0.011 95% CI −0.138 to +0.099, includes no difference"
          - cell "0.85"
        - row "Prevalence (no skill) PR-AUC +0.021 95% CI −0.007 to +0.127, includes no difference 0.17":
          - rowheader "Prevalence (no skill)"
          - cell "PR-AUC"
          - cell "+0.021 95% CI −0.007 to +0.127, includes no difference"
          - cell "0.17"
    - paragraph: "Intervals: paired stratified bootstrap, 2000 resamples, percentile interval."
    - heading "Operating points" [level=2]
    - paragraph: Thresholds chosen on the validation block, measured once on the test block.
    - paragraph: 313 test units, 17 failed.
    - img "Precision-recall curve on the test block with 2 operating points. No-skill precision is 5.4%.": "0% 0% 25% 25% 50% 50% 75% 75% 100% 100% Recall: failures caught Precision: alarms that were failures No skill 5.4% 5% false-alarm rate 10% false-alarm rate"
    - table "Operating points on the test block":
      - caption: Operating points on the test block
      - rowgroup:
        - row "Point Recall Precision False alarms per 100 TP / FP / FN":
          - columnheader "Point"
          - columnheader "Recall"
          - columnheader "Precision"
          - columnheader "False alarms per 100"
          - columnheader "TP / FP / FN"
      - rowgroup:
        - row "5% false-alarm rate Used on the line 5.9% 95% CI 0–18% 14% 95% CI 0–50% 1.9 95% CI 0.6–3.5 1 / 6 / 16":
          - rowheader "5% false-alarm rate Used on the line"
          - cell "5.9% 95% CI 0–18%"
          - cell "14% 95% CI 0–50%"
          - cell "1.9 95% CI 0.6–3.5"
          - cell "1 / 6 / 16"
        - row "10% false-alarm rate 12% 95% CI 0–29% 12% 95% CI 0–28% 4.8 95% CI 2.6–7.0 2 / 15 / 15":
          - rowheader "10% false-alarm rate"
          - cell "12% 95% CI 0–29%"
          - cell "12% 95% CI 0–28%"
          - cell "4.8 95% CI 2.6–7.0"
          - cell "2 / 15 / 15"
    - heading "Calibration" [level=2]
    - paragraph: "Platt scaling, fitted on validation: a = -0.834, b = 2.552."
    - img "Reliability diagram with 5 bins of equal size.": 0% 0% 2% 2% 4% 4% 6% 6% 8% 8% Mean predicted risk in the bin Observed failure rate
    - term: Brier score
    - definition: 0.052 95% CI 0.051–0.053
    - term: Expected calibration error
    - definition: 0.016 95% CI 0.015–0.043
    - paragraph: Platt scaling fitted on the pooled out-of-fold validation scores of the fold models and applied to the final model; Brier, ECE and bins are on the test block (5 equal-count bins, few failures per bin, so the observed rates are very uncertain)
    - heading "Control charts (FDC) on held-out reference units" [level=2]
    - paragraph: 106 units the limits were not fitted on.
    - term: False alarms at the 99% limit
    - definition: 1.9% 95% CI 0.2–6.6%
    - term: False alarms at the 99.9% limit
    - definition: 1.9% 95% CI 0.2–6.6%
    - term: EWMA
    - definition: lambda = 0.2, L = 2.962, asymptotic limits; in-control ARL 500 units under normality
    - term: CUSUM
    - definition: k = 0.5, h = 5.0, two-sided, restart after a signal; in-control ARL 465 units under normality
    - heading "Tuning" [level=2]
    - paragraph: "optuna TPESampler(seed=136952034), 80 trials, sequential, 80 trials. Objective: mean average precision over the rolling-origin folds."
    - term: Best objective value
    - definition: "0.249"
    - term: learning_rate
    - definition: "0.12891827307721757"
    - term: num_boost_round
    - definition: "52"
    - term: num_leaves
    - definition: "15"
    - term: max_depth
    - definition: "1"
    - term: min_data_in_leaf
    - definition: "75"
    - term: feature_fraction
    - definition: "0.3350737507667601"
    - term: bagging_fraction
    - definition: "0.8917400866858379"
    - term: lambda_l1
    - definition: "0.002414114319698153"
    - term: lambda_l2
    - definition: "0.4306419876250838"
    - term: min_gain_to_split
    - definition: "0.6540366511326735"
    - term: extra_trees
    - definition: "true"
    - group: Rolling-origin folds (5)
    - heading "SECOM limitations" [level=2]
    - list:
      - listitem: "Few failures: the test block holds 17 and the validation block 34, so every interval is wide and small differences between models are not distinguishable."
      - listitem: "The failure rate drifts over time (see eda.md: many failures early, fewer later); a model and calibrator fitted on earlier periods may not transfer to later ones."
      - listitem: "One fab, one product, about three months in 2008, anonymous sensors: results may not transfer to other tools, products or periods, and sensor meanings are unknown."
      - listitem: The source timestamps have no time zone; they are stored as UTC without conversion.
      - listitem: "Associations, not causes: a sensor group linked to failure may be a proxy for another, unmeasured, factor."
      - listitem: Validation-block risks come from rolling-origin fold models fitted on less data than the final model; they chose the settings and the calibrator, so their metrics are optimistic. The calibrator is fitted on fold-model scores and applied to the final model, an approximation the test block checks.
      - listitem: Operating-point intervals are conditional on the thresholds chosen on the validation block; the variability of the threshold choice itself is not included.
      - listitem: The test-block curve in operating_points.json is descriptive; choosing a new threshold from it and reporting test performance at that threshold would be optimistic.
      - listitem: Reliability bins hold few failures each, so the observed rates are very uncertain.
      - listitem: with 200 permutations the smallest p-value is 0.0050; Benjamini-Hochberg across 242 groups can declare k groups significant only if k >= 25 of them reach that floor.
      - listitem: Stability selection uses bootstrap resamples (not the half-samples of Meinshausen and Buehlmann), so their error bound does not apply; stability is descriptive.
      - listitem: FDC has no drift labels in SECOM; alarms are judged only by their false-alarm rate on held-out in-control data and by association with failure. The PCA reference holds fewer units than sensors, so the covariance is estimated with few degrees of freedom.
      - listitem: Sensor-health rules are deterministic and label-free; the jump test treats consecutive differences as independent, which a single spike violates; the stuck-value rule uses a first-order repeat model fitted on a short reference; and 61 sensors already reach the out-of-reference watch rate on held-out in-control data, so that rule alone over-flags. Statuses are prompts for inspection, not diagnoses.
      - listitem: "Missingness of sensor readings: 4 sensors associated with failure after Benjamini-Hochberg on the development period; reported as found, without searching for a test variant that would find more."
      - listitem: No candidate FDC reference passed the stationarity test; the shortest candidate is used.
  - region "Wafer maps":
    - heading "Wafer maps" [level=2]
    - paragraph: The pattern classifier, the unknown-pattern check and similar-wafer retrieval on WM-811K.
    - heading "Pattern classifier on held-out wafers" [level=2]
    - paragraph: The lot-grouped split keeps every lot on one side, so wafers from the same lot never sit in both training and test data.
    - table "Macro-F1 by split":
      - caption: Macro-F1 by split
      - rowgroup:
        - row "Model and split Test wafers Macro-F1 Accuracy Lots in both":
          - columnheader "Model and split"
          - columnheader "Test wafers"
          - columnheader "Macro-F1"
          - columnheader "Accuracy"
          - columnheader "Lots in both"
      - rowgroup:
        - row "CNN Lot-grouped split 25,954 0.900 95% CI 0.886–0.912 Mean across seeds 0.900 ± 0.006 over 3 seeds 0.978 95% CI 0.976–0.980 0":
          - rowheader "CNN Lot-grouped split"
          - cell "25,954"
          - cell "0.900 95% CI 0.886–0.912 Mean across seeds 0.900 ± 0.006 over 3 seeds"
          - cell "0.978 95% CI 0.976–0.980"
          - cell "0"
        - row "CNN Official split 118,595 0.635 95% CI 0.620–0.649 Mean across seeds 0.604 ± 0.043 over 3 seeds 0.904 95% CI 0.901–0.907 0":
          - rowheader "CNN Official split"
          - cell "118,595"
          - cell "0.635 95% CI 0.620–0.649 Mean across seeds 0.604 ± 0.043 over 3 seeds"
          - cell "0.904 95% CI 0.901–0.907"
          - cell "0"
        - row "Baseline Lot-grouped split 25,954 0.699 95% CI 0.675–0.720 0.893 95% CI 0.886–0.900 0":
          - rowheader "Baseline Lot-grouped split"
          - cell "25,954"
          - cell "0.699 95% CI 0.675–0.720"
          - cell "0.893 95% CI 0.886–0.900"
          - cell "0"
        - row "Baseline Official split 118,595 0.567 95% CI 0.552–0.581 0.893 95% CI 0.890–0.895 0":
          - rowheader "Baseline Official split"
          - cell "118,595"
          - cell "0.567 95% CI 0.552–0.581"
          - cell "0.893 95% CI 0.890–0.895"
          - cell "0"
    - paragraph: "Intervals: lot-cluster bootstrap, 2000 resamples (percentile). Deployed model lot-seed1: the seed with the highest validation macro-F1."
    - heading "Per pattern" [level=2]
    - paragraph: Precision, recall and F1 for each pattern, with the confusion matrix of the same split.
    - radiogroup "Split":
      - radio "Lot-grouped split" [checked]
      - radio "Official split"
    - table "Per-pattern metrics, Lot-grouped split":
      - caption: Per-pattern metrics, Lot-grouped split
      - rowgroup:
        - row "Pattern Support Precision Recall F1":
          - columnheader "Pattern"
          - columnheader "Support"
          - columnheader "Precision"
          - columnheader "Recall"
          - columnheader "F1"
      - rowgroup:
        - row "Center 643 0.92 95% CI 0.90–0.94 0.95 95% CI 0.93–0.97 0.93 95% CI 0.92–0.95":
          - rowheader "Center"
          - cell "643"
          - cell "0.92 95% CI 0.90–0.94"
          - cell "0.95 95% CI 0.93–0.97"
          - cell "0.93 95% CI 0.92–0.95"
        - row "Donut 82 0.81 95% CI 0.71–0.89 0.91 95% CI 0.83–0.97 0.86 95% CI 0.78–0.91":
          - rowheader "Donut"
          - cell "82"
          - cell "0.81 95% CI 0.71–0.89"
          - cell "0.91 95% CI 0.83–0.97"
          - cell "0.86 95% CI 0.78–0.91"
        - row "Edge-Loc 778 0.83 95% CI 0.80–0.86 0.89 95% CI 0.87–0.92 0.86 95% CI 0.84–0.88":
          - rowheader "Edge-Loc"
          - cell "778"
          - cell "0.83 95% CI 0.80–0.86"
          - cell "0.89 95% CI 0.87–0.92"
          - cell "0.86 95% CI 0.84–0.88"
        - row "Edge-Ring 1,452 0.99 95% CI 0.98–0.99 0.98 95% CI 0.97–0.99 0.98 95% CI 0.98–0.99":
          - rowheader "Edge-Ring"
          - cell "1,452"
          - cell "0.99 95% CI 0.98–0.99"
          - cell "0.98 95% CI 0.97–0.99"
          - cell "0.98 95% CI 0.98–0.99"
        - row "Loc 538 0.77 95% CI 0.73–0.81 0.83 95% CI 0.79–0.86 0.80 95% CI 0.77–0.83":
          - rowheader "Loc"
          - cell "538"
          - cell "0.77 95% CI 0.73–0.81"
          - cell "0.83 95% CI 0.79–0.86"
          - cell "0.80 95% CI 0.77–0.83"
        - row "Near-full 23 1.00 95% CI 1.00–1.00 1.00 95% CI 1.00–1.00 1.00 95% CI 1.00–1.00":
          - rowheader "Near-full"
          - cell "23"
          - cell "1.00 95% CI 1.00–1.00"
          - cell "1.00 95% CI 1.00–1.00"
          - cell "1.00 95% CI 1.00–1.00"
        - row "Random 130 0.82 95% CI 0.72–0.90 0.92 95% CI 0.87–0.97 0.87 95% CI 0.80–0.92":
          - rowheader "Random"
          - cell "130"
          - cell "0.82 95% CI 0.72–0.90"
          - cell "0.92 95% CI 0.87–0.97"
          - cell "0.87 95% CI 0.80–0.92"
        - row "Scratch 178 0.75 95% CI 0.69–0.81 0.87 95% CI 0.82–0.92 0.81 95% CI 0.76–0.85":
          - rowheader "Scratch"
          - cell "178"
          - cell "0.75 95% CI 0.69–0.81"
          - cell "0.87 95% CI 0.82–0.92"
          - cell "0.81 95% CI 0.76–0.85"
        - row "No pattern 22,130 0.99 95% CI 0.99–1.00 0.99 95% CI 0.99–0.99 0.99 95% CI 0.99–0.99":
          - rowheader "No pattern"
          - cell "22,130"
          - cell "0.99 95% CI 0.99–1.00"
          - cell "0.99 95% CI 0.99–0.99"
          - cell "0.99 95% CI 0.99–0.99"
    - 'table "Confusion matrix: rows are true patterns, columns predicted patterns. Cells give counts."':
      - caption: "Confusion matrix: rows are true patterns, columns predicted patterns. Cells give counts."
      - rowgroup:
        - row "True ↓ Predicted → Center Donut Edge-Loc Edge-Ring Loc Near-full Random Scratch No pattern":
          - columnheader "True ↓ Predicted →"
          - columnheader "Center"
          - columnheader "Donut"
          - columnheader "Edge-Loc"
          - columnheader "Edge-Ring"
          - columnheader "Loc"
          - columnheader "Near-full"
          - columnheader "Random"
          - columnheader "Scratch"
          - columnheader "No pattern"
      - rowgroup:
        - 'row "Center 610 3 2 True Center, predicted Edge-Ring: 0 (0.0% of the row) 9 True Center, predicted Near-full: 0 (0.0% of the row) True Center, predicted Random: 0 (0.0% of the row) True Center, predicted Scratch: 0 (0.0% of the row) 19"':
          - rowheader "Center"
          - cell "610"
          - cell "3"
          - cell "2"
          - 'cell "True Center, predicted Edge-Ring: 0 (0.0% of the row)"'
          - cell "9"
          - 'cell "True Center, predicted Near-full: 0 (0.0% of the row)"'
          - 'cell "True Center, predicted Random: 0 (0.0% of the row)"'
          - 'cell "True Center, predicted Scratch: 0 (0.0% of the row)"'
          - cell "19"
        - 'row "Donut 2 75 2 True Donut, predicted Edge-Ring: 0 (0.0% of the row) 1 True Donut, predicted Near-full: 0 (0.0% of the row) 2 True Donut, predicted Scratch: 0 (0.0% of the row) True Donut, predicted No pattern: 0 (0.0% of the row)"':
          - rowheader "Donut"
          - cell "2"
          - cell "75"
          - cell "2"
          - 'cell "True Donut, predicted Edge-Ring: 0 (0.0% of the row)"'
          - cell "1"
          - 'cell "True Donut, predicted Near-full: 0 (0.0% of the row)"'
          - cell "2"
          - 'cell "True Donut, predicted Scratch: 0 (0.0% of the row)"'
          - 'cell "True Donut, predicted No pattern: 0 (0.0% of the row)"'
        - 'row "Edge-Loc 3 1 695 7 15 True Edge-Loc, predicted Near-full: 0 (0.0% of the row) 6 3 48"':
          - rowheader "Edge-Loc"
          - cell "3"
          - cell "1"
          - cell "695"
          - cell "7"
          - cell "15"
          - 'cell "True Edge-Loc, predicted Near-full: 0 (0.0% of the row)"'
          - cell "6"
          - cell "3"
          - cell "48"
        - 'row "Edge-Ring True Edge-Ring, predicted Center: 0 (0.0% of the row) True Edge-Ring, predicted Donut: 0 (0.0% of the row) 18 1,420 True Edge-Ring, predicted Loc: 0 (0.0% of the row) True Edge-Ring, predicted Near-full: 0 (0.0% of the row) True Edge-Ring, predicted Random: 0 (0.0% of the row) True Edge-Ring, predicted Scratch: 0 (0.0% of the row) 14"':
          - rowheader "Edge-Ring"
          - 'cell "True Edge-Ring, predicted Center: 0 (0.0% of the row)"'
          - 'cell "True Edge-Ring, predicted Donut: 0 (0.0% of the row)"'
          - cell "18"
          - cell "1,420"
          - 'cell "True Edge-Ring, predicted Loc: 0 (0.0% of the row)"'
          - 'cell "True Edge-Ring, predicted Near-full: 0 (0.0% of the row)"'
          - 'cell "True Edge-Ring, predicted Random: 0 (0.0% of the row)"'
          - 'cell "True Edge-Ring, predicted Scratch: 0 (0.0% of the row)"'
          - cell "14"
        - 'row "Loc 10 7 20 True Loc, predicted Edge-Ring: 0 (0.0% of the row) 445 True Loc, predicted Near-full: 0 (0.0% of the row) 5 12 39"':
          - rowheader "Loc"
          - cell "10"
          - cell "7"
          - cell "20"
          - 'cell "True Loc, predicted Edge-Ring: 0 (0.0% of the row)"'
          - cell "445"
          - 'cell "True Loc, predicted Near-full: 0 (0.0% of the row)"'
          - cell "5"
          - cell "12"
          - cell "39"
        - 'row "Near-full True Near-full, predicted Center: 0 (0.0% of the row) True Near-full, predicted Donut: 0 (0.0% of the row) True Near-full, predicted Edge-Loc: 0 (0.0% of the row) True Near-full, predicted Edge-Ring: 0 (0.0% of the row) True Near-full, predicted Loc: 0 (0.0% of the row) 23 True Near-full, predicted Random: 0 (0.0% of the row) True Near-full, predicted Scratch: 0 (0.0% of the row) True Near-full, predicted No pattern: 0 (0.0% of the row)"':
          - rowheader "Near-full"
          - 'cell "True Near-full, predicted Center: 0 (0.0% of the row)"'
          - 'cell "True Near-full, predicted Donut: 0 (0.0% of the row)"'
          - 'cell "True Near-full, predicted Edge-Loc: 0 (0.0% of the row)"'
          - 'cell "True Near-full, predicted Edge-Ring: 0 (0.0% of the row)"'
          - 'cell "True Near-full, predicted Loc: 0 (0.0% of the row)"'
          - cell "23"
          - 'cell "True Near-full, predicted Random: 0 (0.0% of the row)"'
          - 'cell "True Near-full, predicted Scratch: 0 (0.0% of the row)"'
          - 'cell "True Near-full, predicted No pattern: 0 (0.0% of the row)"'
        - 'row "Random 1 3 2 True Random, predicted Edge-Ring: 0 (0.0% of the row) 4 True Random, predicted Near-full: 0 (0.0% of the row) 120 True Random, predicted Scratch: 0 (0.0% of the row) True Random, predicted No pattern: 0 (0.0% of the row)"':
          - rowheader "Random"
          - cell "1"
          - cell "3"
          - cell "2"
          - 'cell "True Random, predicted Edge-Ring: 0 (0.0% of the row)"'
          - cell "4"
          - 'cell "True Random, predicted Near-full: 0 (0.0% of the row)"'
          - cell "120"
          - 'cell "True Random, predicted Scratch: 0 (0.0% of the row)"'
          - 'cell "True Random, predicted No pattern: 0 (0.0% of the row)"'
        - 'row "Scratch True Scratch, predicted Center: 0 (0.0% of the row) True Scratch, predicted Donut: 0 (0.0% of the row) 1 2 6 True Scratch, predicted Near-full: 0 (0.0% of the row) 1 155 13"':
          - rowheader "Scratch"
          - 'cell "True Scratch, predicted Center: 0 (0.0% of the row)"'
          - 'cell "True Scratch, predicted Donut: 0 (0.0% of the row)"'
          - cell "1"
          - cell "2"
          - cell "6"
          - 'cell "True Scratch, predicted Near-full: 0 (0.0% of the row)"'
          - cell "1"
          - cell "155"
          - cell "13"
        - 'row "No pattern 37 4 95 7 97 True No pattern, predicted Near-full: 0 (0.0% of the row) 12 36 21,842"':
          - rowheader "No pattern"
          - cell "37"
          - cell "4"
          - cell "95"
          - cell "7"
          - cell "97"
          - 'cell "True No pattern, predicted Near-full: 0 (0.0% of the row)"'
          - cell "12"
          - cell "36"
          - cell "21,842"
    - paragraph: "Shade is the share of the true pattern’s wafers: blue on the diagonal (correct), red off it. 9 patterns."
    - heading "Unknown-pattern score (Mahalanobis)" [level=2]
    - paragraph: "Score: min over classes of (z - mean_c)^T precision (z - mean_c), on L2-normalised embeddings (shared within-class, Ledoit-Wolf shrinkage, L2-normalised embeddings). Threshold set on validation wafers. Leave-one-class-out: lot-grouped split, seed 0, training capped at 12 epochs; a model trained without each defect class scores that class against in-distribution test wafers. Mahalanobis was chosen over the energy score after these results, so they are not an independent estimate for it."
    - term: Threshold, set on the validation set
    - definition: "272.6"
    - term: Known patterns kept
    - definition: 95.0%validation; 94.5% on test
    - term: Mean AUROC, class held out
    - definition: "0.922"
    - term: Energy score, cross-check only
    - definition: "0.545"
    - heading "AUROC when each pattern is left out of training" [level=3]
    - list:
      - listitem: Center 0.91 95% CI 0.90–0.92
      - listitem: Donut 0.98 95% CI 0.97–0.98
      - listitem: Edge-Loc 0.92 95% CI 0.91–0.92
      - listitem: Edge-Ring 0.95 95% CI 0.95–0.96
      - listitem: Loc 0.91 95% CI 0.90–0.92
      - listitem: Near-full 1.00 95% CI 0.99–1.00
      - listitem: Random 0.95 95% CI 0.93–0.97
      - listitem: Scratch 0.77 95% CI 0.75–0.78
    - paragraph: Axis from 0.5 (chance) to 1.
    - heading "Calibration, retrieval and automation" [level=2]
    - term: Temperature (temperature scaling)
    - definition: "0.53"
    - term: Expected calibration error
    - definition: "0.004 95% CI 0.004–0.006before: 0.049"
    - term: Similar-wafer precision at 10
    - definition: 86% 95% CI 84–87%
    - heading "Classified automatically at a precision target" [level=3]
    - table "Automatic classification by precision target":
      - caption: Automatic classification by precision target
      - rowgroup:
        - row "Target Confidence above Share of wafers Precision reached":
          - columnheader "Target"
          - columnheader "Confidence above"
          - columnheader "Share of wafers"
          - columnheader "Precision reached"
      - rowgroup:
        - row "95% 0.38 100% 95% CI 100–100% 0.978 95% CI 0.976–0.980":
          - rowheader "95%"
          - cell "0.38"
          - cell "100% 95% CI 100–100%"
          - cell "0.978 95% CI 0.976–0.980"
        - row "99% 0.77 96% 95% CI 96–96% 0.992 95% CI 0.991–0.994":
          - rowheader "99%"
          - cell "0.77"
          - cell "96% 95% CI 96–96%"
          - cell "0.992 95% CI 0.991–0.994"
    - heading "Wafer-map limitations" [level=2]
    - list:
      - listitem: "The official test set is 93% `none`, the lot-grouped one about 85%; macro-F1 weighs every class equally, so rare classes (Near-full: 23 test wafers) have wide intervals."
      - listitem: "The official split gives a much lower macro-F1 than the lot-grouped one (0.604 ± 0.043 vs 0.900 ± 0.006). Its test lots are the higher-numbered ones and differ from its training lots: models that score well on validation lots drawn from official training call many test `none` wafers Edge-Loc, Center or Loc. One official seed stopped early (best validation epoch 15, 4, 22 for seeds 0, 1, 2) and is reported as measured; seeds were not re-run after the test results were seen."
      - listitem: Labels were assigned by the dataset's annotators; label noise is unmeasured.
      - listitem: WM-811K has no timestamps, so "reference period" for the lot tests means the validation lots, not an earlier time window. The binomial test treats wafers of a lot as independent under the null; a lot-level process problem is exactly what it is meant to detect.
      - listitem: The unknown-pattern test can only use the 8 known defect classes as stand-ins for new patterns; real novel patterns may be easier or harder to flag.
      - listitem: Maps are resized to 64x64; very large maps (up to 300x205 dies) lose detail.
      - listitem: Lot predictions for unlabelled wafers are model outputs, not ground truth.
  - region "Data and provenance":
    - heading "Data and provenance" [level=2]
    - paragraph: The datasets with their checksums, the artifact bundles the API loaded, and the model cards.
    - heading "SECOM" [level=2]
    - paragraph: Production units of a semiconductor fab, each with 590 anonymous sensor readings, a pass or fail result from final test and a timestamp.
    - term: Citation
    - definition: McCann, M. and Johnston, A. (2008). SECOM [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C54305
    - term: Source
    - definition:
      - link "https://archive.ics.uci.edu/dataset/179/secom":
        - /url: https://archive.ics.uci.edu/dataset/179/secom
    - term: Licence
    - definition: "Creative Commons Attribution 4.0 International (CC BY 4.0). Text on the dataset page, retrieved 2026-10-14: \"This dataset is licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license. This allows for the sharing and adaptation of the datasets for any purpose, provided that the appropriate credit is given.\""
    - term: Retrieved
    - definition:
      - time: 2026-10-14 07:27
    - heading "Files (SHA-256)" [level=3]
    - list:
      - listitem:
        - text: secom/secom.data 5.4M bytes
        - code: 20f0e7ee434f7dcbae0eea9ffff009a2b57f42d6b0dc9a5bd4f00782c0a3374c
      - listitem:
        - text: secom/secom.names 4.2K bytes
        - code: 6d91b0b46cdee03064ee3e3112f937c1b3f7fcd9933575794ec07974e6f1ea59
      - listitem:
        - text: raw/secom/secom.zip 2M bytes
        - code: eea568baf3c2229096d7d294cf0b096b5502bd96d92c0b80a65b84714059be8e
      - listitem:
        - text: secom/secom_labels.data 40.6K bytes
        - code: 126884cf453705c9e61a903fe906f0665a3b45ce3639e621edc5c93c89627e03
    - heading "WM-811K" [level=2]
    - paragraph: Wafer maps from real fabs (pass or fail per die), about a fifth of them labelled with one of nine defect patterns.
    - term: Citation
    - definition: Wu, M.-J., Jang, J.-S. R. and Chen, J.-L. (2015). Wafer map failure pattern recognition and similarity ranking for large-scale data sets. IEEE Transactions on Semiconductor Manufacturing, 28(1), 1-12.
    - term: Source
    - definition:
      - link "http://mirlab.org/dataSet/public/":
        - /url: http://mirlab.org/dataSet/public/
    - term: Licence
    - definition: "Kaggle mirror qingyi/wm811k-wafer-map (dataset id 14180) lists the licence CC0-1.0 in its metadata (retrieved 2026-10-14). That licence was set by the Kaggle uploader, not by the original authors (MIR Lab); the original release states no licence we could retrieve (http://mirlab.org/dataSet/public/ returned HTTP 404 on 2026-10-14). We therefore treat it as a research dataset: raw data is never redistributed, only a small derived demo subset with attribution."
    - term: Retrieved
    - definition:
      - time: 2026-10-14 07:29
    - heading "Files (SHA-256)" [level=3]
    - list:
      - listitem:
        - text: raw/wm811k/LSWMD.pkl 2.1B bytes
        - code: 1d04fccb3dd3176b276878b926b20fead7e077c5751e4d353ea9741a5e7b5c65
      - listitem:
        - text: raw/wm811k/wm811k-wafer-map.zip 156.7M bytes
        - code: 0e4bd4316a110a04e475a88071f5e1c7fe4303b12ee53c851d2cae4d995a93e2
    - heading "Artifact bundles" [level=2]
    - paragraph: Every file is checked against the SHA-256 in its MANIFEST.json when the API loads it.
    - table "Artifact bundles":
      - caption: Artifact bundles
      - rowgroup:
        - row "Bundle Built Commit Files Checksums":
          - columnheader "Bundle"
          - columnheader "Built"
          - columnheader "Commit"
          - columnheader "Files"
          - columnheader "Checksums"
      - rowgroup:
        - row "secom v1 2026-10-14 10:46 21d77afb06 13 Verified":
          - rowheader "secom v1"
          - cell "2026-10-14 10:46":
            - time: 2026-10-14 10:46
          - cell "21d77afb06"
          - cell "13"
          - cell "Verified"
        - row "wafermap v1 2026-10-14 10:27 58516138c0 11 Verified":
          - rowheader "wafermap v1"
          - cell "2026-10-14 10:27":
            - time: 2026-10-14 10:27
          - cell "58516138c0"
          - cell "11"
          - cell "Verified"
    - heading "Model cards" [level=2]
    - paragraph: Written by the training pipeline with the bundle.
    - radiogroup "Model card":
      - radio "SECOM failure risk, control charts and sensor health" [checked]
      - radio "WM-811K wafer-map patterns, unknown patterns and similar wafers"
    - 'heading "Model card: SECOM failure risk, root-cause groups, FDC and sensor health" [level=2]'
    - paragraph:
      - text: Generated by
      - code: yg_secom.pipeline
      - text: at commit
      - code: 21d77afb0655
      - text: from
      - code: secom.data
      - text: SHA-256
      - code: 20f0e7ee434f...
      - text: ","
      - code: secom.names
      - text: SHA-256
      - code: 6d91b0b46cde...
      - text: ","
      - code: secom_labels.data
      - text: SHA-256
      - code: 126884cf4537...
      - text: .
    - heading "Intended use" [level=3]
    - paragraph: "Decision support for yield and process engineers: rank production units by their risk of failing final test, point to the sensor groups statistically associated with failure, monitor the process for drift (T², SPE, EWMA, CUSUM) and flag unhealthy sensors. An engineer reviews every alarm and decides."
    - paragraph: "Not intended for: automatic scrapping or release decisions, claims about physical causes, or use on other tools, products or periods without revalidation."
    - heading "Data" [level=3]
    - list:
      - listitem:
        - text: "Source: McCann, M. and Johnston, A. (2008). SECOM [Dataset]. UCI Machine Learning Repository."
        - link "https://doi.org/10.24432/C54305":
          - /url: https://doi.org/10.24432/C54305
      - listitem: "Licence: Creative Commons Attribution 4.0 International (CC BY 4.0). Text on the dataset page, retrieved 2026-10-14: \"This dataset is licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license. This allows for the sharing and adaptation of the datasets for any purpose, provided that the appropriate credit is given.\""
      - listitem: 1567 units, 590 anonymous sensor readings, 104 failed final test, 2008-07-19 to 2008-10-17.
      - listitem: "Chronological blocks: train 376 units (53 failures, 2008-07-19 to 2008-08-21), validation 878 units (34 failures, 2008-08-21 to 2008-10-02), test 313 units (17 failures, 2008-10-02 to 2008-10-17)."
      - listitem: No synthetic data; no resampling that creates units; no row dropped.
    - heading "Method" [level=3]
    - list:
      - listitem: "Validation by rolling origin: the train block is a warm-up used only for fitting; each validation slice is predicted by a model fitted on every earlier unit; the test block (the last 20% of units) is evaluated once at the end."
      - listitem: LightGBM with class weights, tuned by Optuna (TPE, seeded) on the rolling-origin folds; preprocessing fitted on training rows only (constant features dropped, missing values kept, missingness indicators where Fisher's test with Benjamini-Hochberg shows association). Final model refitted on the whole development period (train and validation blocks).
      - listitem: "Baselines: prevalence, L2 logistic regression (C tuned on the same folds), balanced random forest."
      - listitem: Platt calibration and alarm thresholds (5% and 10% false-alarm rate) set on the pooled out-of-fold validation scores.
      - listitem: "Root cause on the development period: TreeSHAP, Spearman sensor groups (|rho| >= 0.8, average linkage), stability selection, label-permutation test with Benjamini-Hochberg, Mann-Whitney screen."
      - listitem: "FDC: PCA on autoscaled reference data, Hotelling T² (F limit) and SPE (Box chi-square approximation matched to the mean and variance of leave-one-out reference SPE (reference rows <= features)), contributions, EWMA and CUSUM on leading groups."
      - listitem: "Sensor health: written, label-free rules per sensor and calendar week; the jump threshold is calibrated on the reference period."
    - heading "Results (test block, 95% intervals)" [level=3]
    - table:
      - rowgroup:
        - row "Metric Value":
          - columnheader "Metric"
          - columnheader "Value"
      - rowgroup:
        - row "PR-AUC 0.075 (0.048 to 0.181) (no skill 0.054 (0.054 to 0.054))":
          - cell "PR-AUC"
          - cell "0.075 (0.048 to 0.181) (no skill 0.054 (0.054 to 0.054))"
        - row "ROC-AUC 0.523 (0.384 to 0.665)":
          - cell "ROC-AUC"
          - cell "0.523 (0.384 to 0.665)"
        - row "Brier score 0.0516 (0.0506 to 0.0526)":
          - cell "Brier score"
          - cell "0.0516 (0.0506 to 0.0526)"
        - 'row "At the 5% false-alarm rate threshold set on validation: recall / precision / test false-alarm rate 5.9% (0.0 to 17.6%) / 14.3% (0.0 to 50.0%) / 2.0% (0.7 to 3.7%)"':
          - 'cell "At the 5% false-alarm rate threshold set on validation: recall / precision / test false-alarm rate"'
          - cell "5.9% (0.0 to 17.6%) / 14.3% (0.0 to 50.0%) / 2.0% (0.7 to 3.7%)"
        - 'row "At the 10% false-alarm rate threshold set on validation: recall / precision / test false-alarm rate 11.8% (0.0 to 29.4%) / 11.8% (0.0 to 27.8%) / 5.1% (2.7 to 7.4%)"':
          - 'cell "At the 10% false-alarm rate threshold set on validation: recall / precision / test false-alarm rate"'
          - cell "11.8% (0.0 to 29.4%) / 11.8% (0.0 to 27.8%) / 5.1% (2.7 to 7.4%)"
        - row "False alarms per 100 units at the 5% false-alarm rate threshold 1.92 (0.64 to 3.51)":
          - cell "False alarms per 100 units at the 5% false-alarm rate threshold"
          - cell "1.92 (0.64 to 3.51)"
        - row "FDC false-alarm rate on held-out reference, T² or SPE beyond the 99% limit 1.9% (0.2 to 6.6%)":
          - cell "FDC false-alarm rate on held-out reference, T² or SPE beyond the 99% limit"
          - cell "1.9% (0.2 to 6.6%)"
        - row "Stable sensor groups / significant after permutation test 2 / 0":
          - cell "Stable sensor groups / significant after permutation test"
          - cell "2 / 0"
        - 'row "Sensor health: ok / watch / maintenance / dead 274 / 143 / 57 / 116"':
          - 'cell "Sensor health: ok / watch / maintenance / dead"'
          - cell "274 / 143 / 57 / 116"
    - paragraph: "Sensor-health status rules:"
    - list:
      - listitem: "dead: never measured, or a single distinct value over the whole period"
      - listitem: "maintenance: a flatline window (at least 5 readings in a calendar week, all identical, with reference probability p_v ** n < 0.001); or a stuck value (a run of R >= 5 identical consecutive readings with n_readings * r ** (R - 1) < 0.01, r = the sensor's reference rate of repeating its previous reading, (repeats + 1) / (pairs + 2)); or a week missing at least 50% of readings while the reference misses at most 10%; or at least 20% of readings after the reference outside the reference range"
      - listitem: "watch: jumps (|robust z of a first difference| > 120.67, a threshold exceeded by 0.1% of reference differences) more frequent after the reference than the in-control share 0.100% allows (one-sided exact binomial test, Benjamini-Hochberg q <= 0.05); or a week missing at least 20% of readings while the reference misses at most 10%; or at least 5% of readings after the reference outside the reference range"
      - listitem: "ok: none of the above"
    - paragraph:
      - text: Paired bootstrap differences in PR-AUC against each baseline, calibration details, the full group table, FDC and sensor-health results are in
      - code: training/secom/reports/results.md
      - text: in the repository.
    - heading "Limitations" [level=3]
    - list:
      - listitem: "Few failures: the test block holds 17 and the validation block 34, so every interval is wide and small differences between models are not distinguishable."
      - listitem: "The failure rate drifts over time (see eda.md: many failures early, fewer later); a model and calibrator fitted on earlier periods may not transfer to later ones."
      - listitem: "One fab, one product, about three months in 2008, anonymous sensors: results may not transfer to other tools, products or periods, and sensor meanings are unknown."
      - listitem: The source timestamps have no time zone; they are stored as UTC without conversion.
      - listitem: "Associations, not causes: a sensor group linked to failure may be a proxy for another, unmeasured, factor."
      - listitem: Validation-block risks come from rolling-origin fold models fitted on less data than the final model; they chose the settings and the calibrator, so their metrics are optimistic. The calibrator is fitted on fold-model scores and applied to the final model, an approximation the test block checks.
      - listitem: Operating-point intervals are conditional on the thresholds chosen on the validation block; the variability of the threshold choice itself is not included.
      - listitem: The test-block curve in operating_points.json is descriptive; choosing a new threshold from it and reporting test performance at that threshold would be optimistic.
      - listitem: Reliability bins hold few failures each, so the observed rates are very uncertain.
      - listitem: with 200 permutations the smallest p-value is 0.0050; Benjamini-Hochberg across 242 groups can declare k groups significant only if k >= 25 of them reach that floor.
      - listitem: Stability selection uses bootstrap resamples (not the half-samples of Meinshausen and Buehlmann), so their error bound does not apply; stability is descriptive.
      - listitem: FDC has no drift labels in SECOM; alarms are judged only by their false-alarm rate on held-out in-control data and by association with failure. The PCA reference holds fewer units than sensors, so the covariance is estimated with few degrees of freedom.
      - listitem: Sensor-health rules are deterministic and label-free; the jump test treats consecutive differences as independent, which a single spike violates; the stuck-value rule uses a first-order repeat model fitted on a short reference; and 61 sensors already reach the out-of-reference watch rate on held-out in-control data, so that rule alone over-flags. Statuses are prompts for inspection, not diagnoses.
      - listitem: "Missingness of sensor readings: 4 sensors associated with failure after Benjamini-Hochberg on the development period; reported as found, without searching for a test variant that would find more."
      - listitem: No candidate FDC reference passed the stationarity test; the shortest candidate is used.
    - heading "Provenance" [level=3]
    - list:
      - listitem:
        - text: "Code commit:"
        - code: 21d77afb06551252ca82ed9bfa85931dc4a1be24
      - listitem: "Master seed: 20261014"
      - listitem:
        - code: secom.data
        - text: SHA-256
        - code: 20f0e7ee434f7dcbae0eea9ffff009a2b57f42d6b0dc9a5bd4f00782c0a3374c
      - listitem:
        - code: secom.names
        - text: SHA-256
        - code: 6d91b0b46cdee03064ee3e3112f937c1b3f7fcd9933575794ec07974e6f1ea59
      - listitem:
        - code: secom_labels.data
        - text: SHA-256
        - code: 126884cf453705c9e61a903fe906f0665a3b45ce3639e621edc5c93c89627e03
    - heading "Limitations of the product" [level=2]
    - list:
      - listitem: "SECOM: Few failures: the test block holds 17 and the validation block 34, so every interval is wide and small differences between models are not distinguishable."
      - listitem: "SECOM: The failure rate drifts over time (see eda.md: many failures early, fewer later); a model and calibrator fitted on earlier periods may not transfer to later ones."
      - listitem: "SECOM: One fab, one product, about three months in 2008, anonymous sensors: results may not transfer to other tools, products or periods, and sensor meanings are unknown."
      - listitem: "SECOM: The source timestamps have no time zone; they are stored as UTC without conversion."
      - listitem: "SECOM: Associations, not causes: a sensor group linked to failure may be a proxy for another, unmeasured, factor."
      - listitem: "SECOM: Validation-block risks come from rolling-origin fold models fitted on less data than the final model; they chose the settings and the calibrator, so their metrics are optimistic. The calibrator is fitted on fold-model scores and applied to the final model, an approximation the test block checks."
      - listitem: "SECOM: Operating-point intervals are conditional on the thresholds chosen on the validation block; the variability of the threshold choice itself is not included."
      - listitem: "SECOM: The test-block curve in operating_points.json is descriptive; choosing a new threshold from it and reporting test performance at that threshold would be optimistic."
      - listitem: "SECOM: Reliability bins hold few failures each, so the observed rates are very uncertain."
      - listitem: "SECOM: with 200 permutations the smallest p-value is 0.0050; Benjamini-Hochberg across 242 groups can declare k groups significant only if k >= 25 of them reach that floor."
      - listitem: "SECOM: Stability selection uses bootstrap resamples (not the half-samples of Meinshausen and Buehlmann), so their error bound does not apply; stability is descriptive."
      - listitem: "SECOM: FDC has no drift labels in SECOM; alarms are judged only by their false-alarm rate on held-out in-control data and by association with failure. The PCA reference holds fewer units than sensors, so the covariance is estimated with few degrees of freedom."
      - listitem: "SECOM: Sensor-health rules are deterministic and label-free; the jump test treats consecutive differences as independent, which a single spike violates; the stuck-value rule uses a first-order repeat model fitted on a short reference; and 61 sensors already reach the out-of-reference watch rate on held-out in-control data, so that rule alone over-flags. Statuses are prompts for inspection, not diagnoses."
      - listitem: "SECOM: Missingness of sensor readings: 4 sensors associated with failure after Benjamini-Hochberg on the development period; reported as found, without searching for a test variant that would find more."
      - listitem: "SECOM: No candidate FDC reference passed the stationarity test; the shortest candidate is used."
      - listitem: "Wafer maps: The official test set is 93% `none`, the lot-grouped one about 85%; macro-F1 weighs every class equally, so rare classes (Near-full: 23 test wafers) have wide intervals."
      - listitem: "Wafer maps: The official split gives a much lower macro-F1 than the lot-grouped one (0.604 ± 0.043 vs 0.900 ± 0.006). Its test lots are the higher-numbered ones and differ from its training lots: models that score well on validation lots drawn from official training call many test `none` wafers Edge-Loc, Center or Loc. One official seed stopped early (best validation epoch 15, 4, 22 for seeds 0, 1, 2) and is reported as measured; seeds were not re-run after the test results were seen."
      - listitem: "Wafer maps: Labels were assigned by the dataset's annotators; label noise is unmeasured."
      - listitem: "Wafer maps: WM-811K has no timestamps, so \"reference period\" for the lot tests means the validation lots, not an earlier time window. The binomial test treats wafers of a lot as independent under the null; a lot-level process problem is exactly what it is meant to detect."
      - listitem: "Wafer maps: The unknown-pattern test can only use the 8 known defect classes as stand-ins for new patterns; real novel patterns may be easier or harder to flag."
      - listitem: "Wafer maps: Maps are resized to 64x64; very large maps (up to 300x205 dies) lose detail."
      - listitem: "Wafer maps: Lot predictions for unlabelled wafers are model outputs, not ground truth."
- contentinfo:
  - paragraph:
    - text: "Plant data: SECOM (UCI Machine Learning Repository). Wafer maps: WM-811K (MIR Lab, National Tsing Hua University). Findings are associations in historical data, not causes."
    - link "Methods and limitations":
      - /url: /methods
  - term: Version
  - definition: 0.1.0 (2cea140)
  - term: SECOM models
  - definition: v1, checksums verified
  - term: Wafer models
  - definition: v1, checksums verified
- region "Notifications alt+T"
- alert
```

# Test source

```ts
  21  |   page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  22  |   page.on("console", (m) => {
  23  |     if (m.type() === "error" && /Content Security Policy|Refused to|Hydration/i.test(m.text())) problems.push(`console: ${m.text()}`);
  24  |   });
  25  |   return problems;
  26  | }
  27  | 
  28  | test("the API is ready with both bundles verified", async ({ request }) => {
  29  |   const ready = await getJson<{ ready: boolean }>(request, "/ready");
  30  |   expect(ready.ready).toBe(true);
  31  |   const meta = await getJson<{ bundles: { verified: boolean }[]; features: { chat: boolean; live_investigations: boolean } }>(request, "/meta");
  32  |   expect(meta.bundles.length).toBeGreaterThanOrEqual(2);
  33  |   expect(meta.bundles.every((b) => b.verified)).toBe(true);
  34  |   // These tests are for a stack without a language model key.
  35  |   expect(meta.features).toMatchObject({ chat: false, live_investigations: false });
  36  | });
  37  | 
  38  | test("home: the results table is filled from /results", async ({ page, request }) => {
  39  |   const problems = watch(page);
  40  |   const { results } = await getJson<{ results: { label: string; estimate: unknown }[] }>(request, "/results");
  41  |   const measured = results.filter((r) => r.estimate != null);
  42  |   expect(measured.length, "the real bundles measure at least one headline result").toBeGreaterThan(0);
  43  | 
  44  |   await page.goto("/");
  45  |   const table = page.getByRole("table", { name: "Measured results with confidence intervals" });
  46  |   await expect(table.locator("tbody tr")).toHaveCount(results.length);
  47  |   for (const r of measured) {
  48  |     const row = table.getByRole("row").filter({ has: page.getByRole("rowheader", { name: r.label }) });
  49  |     await expect(row).toHaveCount(1);
  50  |     await expect(row).not.toContainText("Not measured yet");
  51  |   }
  52  |   expect(problems).toEqual([]);
  53  | });
  54  | 
  55  | test("line: goes live over the WebSocket and units arrive", async ({ page }) => {
  56  |   const problems = watch(page);
  57  |   const frames: string[] = [];
  58  |   page.on("websocket", (ws) => ws.on("framereceived", (f) => typeof f.payload === "string" && frames.push(f.payload)));
  59  | 
  60  |   await page.goto("/line");
  61  |   await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible({ timeout: 45_000 });
  62  |   await expect(page.getByRole("heading", { name: "Control charts (FDC)" })).toBeVisible();
  63  |   const units = page.getByRole("table", { name: /Recent units/ }).locator("tbody tr");
  64  |   await expect(units.first()).toBeVisible();
  65  |   // A unit event arrives over the socket after the snapshot.
  66  |   await expect.poll(() => frames.filter((f) => f.includes('"unit"')).length, { timeout: 60_000 }).toBeGreaterThan(1);
  67  |   expect(problems).toEqual([]);
  68  | });
  69  | 
  70  | test("unit: page with its control-chart contributions", async ({ page }) => {
  71  |   const problems = watch(page);
  72  |   await page.goto(`/units/${ids.unit}`);
  73  |   await expect(page.locator("h1")).toHaveText(`Unit ${ids.unit.toLocaleString("en-US")}`);
  74  |   await expect(page.getByRole("heading", { name: "Sensors behind the control-chart statistic" })).toBeVisible();
  75  |   await expect(page.getByRole("heading", { name: "Alarms and investigations" })).toBeVisible();
  76  |   await expect(page.getByText("The API did not answer")).toHaveCount(0);
  77  |   expect(problems).toEqual([]);
  78  | });
  79  | 
  80  | test("wafer lab: list and a selected wafer", async ({ page }) => {
  81  |   const problems = watch(page);
  82  |   await page.goto(`/wafers?wafer=${ids.wafer}`);
  83  |   await expect(page.locator("h1")).toHaveText("Wafer lab");
  84  |   await expect(page.getByRole("heading", { name: `Wafer ${ids.wafer}` })).toBeVisible();
  85  |   await expect(page.getByRole("heading", { name: "Most similar wafers" })).toBeVisible();
  86  |   expect(problems).toEqual([]);
  87  | });
  88  | 
  89  | test("lot: the stack and the pattern test", async ({ page }) => {
  90  |   const problems = watch(page);
  91  |   await page.goto(`/lots/${ids.lot}`);
  92  |   await expect(page.locator("h1")).toHaveText(`Lot ${ids.lot}`);
  93  |   await expect(page.getByRole("heading", { name: "The lot as a stack" })).toBeVisible();
  94  |   await expect(page.getByRole("heading", { name: "Patterns against the expected rate" })).toBeVisible();
  95  |   expect(problems).toEqual([]);
  96  | });
  97  | 
  98  | test("sensor health: field, a sensor and the groups", async ({ page }) => {
  99  |   const problems = watch(page);
  100 |   await page.goto("/sensors?sensor=S060");
  101 |   await expect(page.locator("h1")).toHaveText("Sensor health");
  102 |   const field = page.getByRole("img", { name: /Health of \d+ sensors/ });
  103 |   await expect(field).toBeVisible();
  104 |   await field.focus();
  105 |   await page.keyboard.press("ArrowRight");
  106 |   await expect(page).toHaveURL(/sensor=S061/);
  107 |   await expect(page.getByRole("heading", { name: "Sensor groups associated with failure" })).toBeVisible();
  108 |   expect(problems).toEqual([]);
  109 | });
  110 | 
  111 | test("methods: every model card renders", async ({ page, request }) => {
  112 |   const problems = watch(page);
  113 |   const methods = await getJson<{ model_cards: { name: string; title: string }[] }>(request, "/methods");
  114 |   expect(methods.model_cards.length).toBeGreaterThan(0);
  115 |   await page.goto("/methods");
  116 |   await expect(page.locator("h1")).toHaveText("Methods");
  117 |   const panel = page.locator("section, div").filter({ has: page.getByRole("heading", { name: "Model cards", exact: true }) }).last();
  118 |   for (const card of methods.model_cards) {
  119 |     if (methods.model_cards.length > 1) await page.getByRole("radio", { name: card.title }).click();
  120 |     // The card's markdown has its own headings once it loads.
> 121 |     await expect(panel.getByRole("heading").nth(1)).toBeVisible();
      |                                                     ^ Error: expect(locator).toBeVisible() failed
  122 |     await expect(panel.getByText("Loading the model card")).toHaveCount(0);
  123 |   }
  124 |   expect(problems).toEqual([]);
  125 | });
  126 | 
  127 | test("guest session: Try as engineer signs in", async ({ page }) => {
  128 |   await page.goto(`/units/${ids.unit}`);
  129 |   await page.getByRole("button", { name: "Try as engineer", exact: true }).first().click();
  130 |   await expect(page.getByText("Engineer", { exact: true }).first()).toBeVisible();
  131 |   await expect(page.getByRole("button", { name: "Investigate this unit" })).toBeVisible();
  132 | });
  133 | 
  134 | test("investigation without a key: not-configured state, no Token Factory call", async ({ page }) => {
  135 |   const outbound: string[] = [];
  136 |   page.on("request", (r) => /tokenfactory|token-factory|amd\.com/i.test(r.url()) && outbound.push(r.url()));
  137 | 
  138 |   await page.goto("/investigations");
  139 |   await expect(page.getByRole("note")).toContainText("Live investigations are not configured on this server");
  140 | 
  141 |   await page.goto(`/units/${ids.unit}`);
  142 |   await page.getByRole("button", { name: "Try as engineer", exact: true }).first().click();
  143 |   const start = page.waitForResponse((r) => r.url().endsWith("/api/v1/investigations") && r.request().method() === "POST");
  144 |   await page.getByRole("button", { name: "Investigate this unit" }).click();
  145 |   expect((await start).status()).toBe(503);
  146 |   await expect(page.locator("[data-sonner-toast]").filter({ hasText: "not configured" })).toContainText(
  147 |     "Live investigations are not configured on this server",
  148 |   );
  149 |   await expect(page).toHaveURL(new RegExp(`/units/${ids.unit}$`));
  150 |   expect(outbound).toEqual([]);
  151 | });
  152 | 
  153 | test("chat without a key: not-configured state, nothing sent", async ({ page }) => {
  154 |   const chats: string[] = [];
  155 |   page.on("request", (r) => r.url().includes("/api/v1/chat") && chats.push(r.url()));
  156 | 
  157 |   await page.goto(`/units/${ids.unit}`);
  158 |   await page.getByRole("button", { name: "Ask", exact: true }).click();
  159 |   const sheet = page.getByRole("dialog");
  160 |   await expect(sheet.getByRole("note")).toContainText("Chat is not configured on this server");
  161 |   await expect(sheet.getByRole("textbox", { name: "Question" })).toHaveCount(0);
  162 |   expect(chats).toEqual([]);
  163 | });
  164 | 
  165 | test("work orders: the list and the audit log match the API", async ({ page, request }) => {
  166 |   const problems = watch(page);
  167 |   const list = await getJson<{ total: number }>(request, "/work-orders");
  168 |   await page.goto("/work-orders");
  169 |   await expect(page.locator("h1")).toHaveText("Work orders");
  170 |   if (list.total === 0) {
  171 |     await expect(page.getByText("No work orders yet")).toBeVisible();
  172 |   } else {
  173 |     await expect(page.getByRole("link", { name: ids.workOrder! }).first()).toBeVisible();
  174 |     await page.goto(`/work-orders/${ids.workOrder}`);
  175 |     await expect(page.getByRole("heading", { name: "History" })).toBeVisible();
  176 |   }
  177 |   await expect(page.getByRole("heading", { name: /Audit log/ })).toBeVisible();
  178 |   expect(problems).toEqual([]);
  179 | });
  180 | 
```