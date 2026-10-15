# Yield Guardian v2: Plan

| | |
|---|---|
| Version | 2.0 draft |
| Date | 2026-10-15 |
| Approved by | The owner, 2026-10-15 06:54 UTC ("موافق، اعمل الخطة") |
| Written by | Worker 3, from the owner's decisions of 2026-10-15 |
| Builds on | [PLAN.md](PLAN.md) v1 (all ground rules in §2 stay binding) |

v1 built the science, the AI layer and a working site: 82 of 82 items done. The owner then
tried the product and found it hard to understand. v2 keeps every model and turns the
product into one story a visitor can follow and drive with their own data, live.

---

## 1. The problems, and how v2 solves them

| # | Problem in v1 | v2 solution | State |
|---|---|---|---|
| 1 | Ten technical pages that do not connect; no story | Four pages. The home page is an animated production line that tells the story station by station (§4) | New |
| 2 | Nothing comes from the user: the site replays stored data in an endless loop | Live runs on the user's own input (sample, drawn wafer, uploaded file). No loop, no stored replay (§3) | New |
| 3 | It is not clear what goes in and what comes out | Every station shows its input and its result on a plain-language card; details open in a drawer (§4, §5) | New |
| 4 | "Defect type" and "cause of failure" are confused; no causes are given | Literature causes per pattern on the wafer card (exists); the investigator tests each candidate cause with evidence for and against (§7) | Part new |
| 5 | Chat replies were hard-coded | Every reply comes from the model, which knows every tool | Done (1132e16) |
| 6 | The chat cannot see what the user entered | New read-only tools over the current run (§8) | New |
| 7 | The investigator failed at the writer (MiMo slow, refused strict schema) | Writer chain Qwen3.8-Flash-Next → DeepSeek-V4.1-Flash → MiMo, deadlines, one recorded run | Done (ab23908) |
| 8 | The investigator is slow (AMD endpoint, up to 16 min) | Runs on demand only, with a live step-by-step progress view and honest timing | New |
| 9 | Mobile overflow; home performance 79 | Lighthouse 94 / 93 / 91, accessibility 100 | Done (8ba0adc) |
| 10 | No answer to "how much does it save?" | Savings calculator from the user's own costs and our measured rates (§9) | New |
| 11 | Unit failure prediction from sensors is weak on SECOM | Worded as early warning and sensor narrowing, never "accurate prediction"; the wafer numbers lead | Wording |
| 12 | Sensor data and wafer maps are not the same chips | The story shows two real sources side by side and says so on screen; nothing is fabricated | By design |

## 2. What stays the same

- Ground rules of PLAN.md §2: real data only, held-out metrics with CIs, association not
  causation, models never produce numbers, humans approve, reproducible, limits published.
- All trained models and bundles (artifacts/secom/v1, artifacts/wafermap/v1), the
  investigator graph, writer, verifier, chat number gate, work orders, audit log, hosting.
- AMD Token Factory for every language-model role.

## 3. Live runs (replaces the replay loop)

A **run** is one submission by a user, processed now, station by station, with every result
streamed to the browser the moment it is computed.

### 3.1 Inputs

| Way | What the user does | What the server receives |
|---|---|---|
| Sample | Picks a real sample from a short catalog ("a production batch with drift", "a wafer with a scratch", "a lot with a repeating pattern") | The sample is materialised from the real datasets into the same input format a user would upload, then processed exactly like an upload |
| Draw | Paints failing dies on an empty wafer grid (one or more wafers; several wafers form a lot) | `wafers[]` of `{lot, wafer, height, width, map}` with values 0 no die, 1 pass, 2 fail |
| Upload | Excel (.xlsx) or CSV | Sensor file or wafer file (formats below) |

**Sensor file:** one row per unit, columns `unit_id, timestamp, S001 … S590, result?`
(`result` optional: `pass` or `fail`). Columns must be the 590 SECOM sensors in order; an
empty cell is a missing reading. A file with several units in time order also enables
drift (EWMA, CUSUM) and sensor-health checks.

**Wafer file:** one row per die, columns `lot, wafer, x, y, result` (`pass`/`fail`).
Positions not listed are "no die". The server builds each wafer's grid.

Validation answers in plain words (which column, which row, what is wrong) with RFC 9457
problems. Size guards protect the server (e.g. 20 MB, 5,000 units, 500 wafers per run);
they are not request rate limits.

### 3.2 Stations (pipeline)

Each station runs only when the input has what it needs; otherwise it is shown grey with
"needs …". Times are targets on the PC host.

| # | Station | Needs | Computes (existing model or method) | Target time |
|---|---|---|---|---|
| S1 | Intake | any input | parse, validate, summary | < 1 s |
| S2 | Sensors: risk | sensor rows | LightGBM risk (model.txt + Platt calibrator), TreeSHAP via LightGBM `pred_contrib`, top sensors and groups | < 1 s per 500 units |
| S3 | Sensors: control charts | sensor rows | T² and SPE from fdc_model.npz (center, scale, impute, loadings, limits), per-sensor contributions | < 1 s |
| S4 | Sensors: slow drift and health | ≥ 20 units in time order | EWMA (λ 0.2, L 2.962) and CUSUM (k 0.5, h 5) on leading groups; health rules from health.json (dead, flatline, stuck, jumps, out of reference range) | < 2 s |
| S5 | Wafer: pattern | wafer maps | nearest-neighbour 64×64, ONNX CNN, temperature, Mahalanobis unknown score | < 1 s per 200 wafers |
| S6 | Wafer: similar and causes | wafer maps | cosine top-10 over the 10,253 demo wafers; literature causes for the predicted pattern (PatternCauses) | < 1 s |
| S7 | Lot | ≥ 2 wafers of one lot | binomial test per pattern against the validation-lot rates (wafermap metrics.json), BH; stacked failure map; join-count test per wafer | < 2 s |
| S8 | Final test | `result` given | was the warning right? per unit and per wafer | instant |
| S9 | Alarms | any station | alarm list with plain meaning; each offers "Investigate" | instant |
| S10 | Investigation (on demand) | an alarm | investigator over the run's evidence, report, approve or reject, work order | minutes (AMD) |

### 3.3 API (contracts first, W1)

- `POST /api/v1/runs` (multipart file, or JSON `{sample_id}` or `{wafers: [...]}`) → `{run_id}`.
- `GET /api/v1/runs/{run_id}/events` (SSE): `run_started`, `stage_started`,
  `stage_result` (typed per station), `stage_skipped` (with the missing input),
  `alarm`, `run_done`, `error`. Events carry a sequence number; a reconnect resumes.
- `GET /api/v1/runs/{run_id}` (full state), `GET /api/v1/runs/samples` (catalog),
  `GET /api/v1/runs/templates/{kind}` (empty Excel/CSV template to download).
- Runs are stored per session in PostgreSQL (input digest, stage results, alarms), so the
  chat, the investigator and a page reload can read them. They expire after 24 h unless an
  investigation or work order references them.
- The wall-clock replay engine, `/ws/line` and the home hero loop are removed (A4 retired).

## 4. Pages (four, down from ten)

| v1 page | v2 |
|---|---|
| Home, Line | merged into **Line** |
| Wafer lab, Lots, Sensor health, Units | become **station drawers** inside Line |
| Investigations, Work orders | merged into **Investigations** (Work orders is a tab) |
| Methods, Models | merged into **How it works** |
| Guide | stays, rewritten for v2 |
| Chat | not a page: floating button on every page |

### 4.1 Line (the story)

Top to bottom:
1. One sentence: "Enter your production data, watch it pass through the line, and see
   where the problem is and why."
2. Input panel: **Try a real sample**, **Draw a wafer**, **Upload a file** (with template
   downloads and the format shown inline).
3. The animated line (§6): Intake → Sensors → Control charts → Wafer test → Lot → Final
   test, with an Alarms rail at the side.
4. A result card under each station: one sentence and one number, colour by state
   (grey needs data, amber computing, green ok, red alarm).
5. A card opens a drawer with the detail an expert wants: T²/SPE chart with limits,
   SHAP bars and sensor groups, sensor health table, wafer with probabilities and unknown
   score, similar wafers, literature causes with sources, lot stacked map and tests.
6. "Investigate" on any alarm opens the investigation beside the line.
7. A banner, always visible when both tracks are present: "Sensor data (SECOM) and wafer
   maps (WM-811K) are real data from different sources, not the same chips."

### 4.2 Investigations

List (running, awaiting decision, decided). Detail: live step-by-step progress (each tool
call appears as it happens, with elapsed time), the report with every number linked to its
evidence, the hypothesis table (§7), Approve / Reject, the work order. Tab: Work orders.

### 4.3 How it works

Measured results with CIs; what each model does and what it was trained on; the AI roles on
AMD with measured latency and points; data sources and licences; limitations; savings
calculator (§9).

### 4.4 Guide

The Arabic guide rewritten for v2 (filters and search kept).

## 5. Inputs and outputs (what the user sees)

| Input | Outputs |
|---|---|
| Sensor rows | failure risk and band, top sensors and groups (SHAP), T²/SPE with contributing sensors, EWMA/CUSUM drift, sensor health, "was the warning right?" when results are given |
| Wafer maps | pattern and confidence or "unknown pattern", 10 most similar real wafers with their recorded pattern, literature causes with sources |
| A lot (≥ 2 wafers) | whether a pattern repeats more than chance (p, q), stacked failure map, spatial clustering per wafer |
| An alarm | investigator report with evidence and hypotheses; approve or reject; work order |

## 6. The animation (highest standard)

Owner's requirement: the most beautiful and precise part of the product.

- **Truthful motion:** a wafer reaches a station only when the server has finished the
  previous station. The timeline is driven by SSE events; animation never runs ahead of
  data and never fakes progress. A station that waits on the server shows a calm working
  state, not a fake bar.
- **Scene:** the Yellow Room (PLAN.md §9). One continuous line across the page, lit amber.
  The wafer is the existing thin-film 3D wafer (wafer-scene.tsx), carried by a robot arm
  between stations. Stations are drawn as simplified tool silhouettes (deposition chamber,
  prober, lot carrier, final test), not stock icons.
- **Per station:** sensors glow with their live readings (sparkline), the risk dial fills to
  the computed value, the control chart draws its new point against the limits, the prober
  steps die by die revealing the real map (existing step-and-scan), wafers stack into a
  25-slot carrier for the lot, the final test stamps pass or fail.
- **Alarm:** the station turns red with one pulse (no looping flashes), the alarm slides
  into the rail with its plain meaning.
- **Craft:** GSAP timeline per run; R3F for the wafer and the carrier only (3D only for
  objects that are 3D), SVG for the rest; 60 fps on a mid-range GPU; instancing, DPR clamp,
  on-demand frames; `prefers-reduced-motion` gives a static stepper with the same results;
  every state reachable by keyboard and announced by a live region.
- **Budgets kept:** Lighthouse mobile ≥ 90 on Line, accessibility 100, axe 0 violations,
  no horizontal scroll at 375 px. The 3D scene loads after first paint.

## 7. Causes: the investigator tests hypotheses

- Wafer track: the candidate causes for the predicted pattern come from PatternCauses
  (literature, with quotes and pages). The investigator gathers evidence for and against
  each: pattern confidence, unknown score, similar wafers and their patterns, lot repetition,
  spatial clustering.
- Sensor track: for a unit or alarm, it identifies which sensor groups deviated, by how
  much, since when (EWMA/CUSUM onset), and whether those groups are associated with failure
  across all data.
- Report contract gains `hypotheses[]: {hypothesis, source_ids[], evidence_for[],
  evidence_against[], verdict: supported | not_supported | inconclusive}`. The verifier
  checks every cited evidence ID and number as today. Wording stays "associated with".
- Limits stated in the report: SECOM sensors are anonymous (groups, not tool names); the
  two datasets are not linked, so no wafer pattern is tied to a sensor.

## 8. Chat in v2

Model-driven (done). New read-only tools: `get_run` (summary, stations, alarms),
`get_run_unit`, `get_run_wafer`, `get_run_lot`, `get_pattern_causes`, `get_results`
(measured metrics). The chat receives which run and which station the user is looking at.
Every number still passes the gate. It explains results, answers "why", gives literature
causes, compares with similar wafers, summarises the run, guides the upload, quotes
measured accuracy.

## 9. Savings calculator

Inputs from the user: wafer cost, engineer hour cost, downtime hour cost, wafers per day,
minutes an engineer spends per wafer map. Our measured rates (with CIs): share of wafers
classified automatically at the 99% precision target, FDC false-alarm rate. Output: hours
and money saved per month as a range from the CIs, with every assumption shown. No number
is invented: with empty inputs the calculator shows nothing.

## 10. Work split

| ID | Item | Owner | Depends on | Estimate |
|---|---|---|---|---|
| V1 | Run contracts (`contracts/runs.py`), SSE event schema, OpenAPI and TS types | W1 | – | 1.5 h |
| V2 | Runs store (PostgreSQL), run orchestrator, SSE endpoint with resume, samples catalog, templates | W1 | V1 | 3 h |
| V3 | Sensor engine: live risk, SHAP (`pred_contrib`), T²/SPE and contributions, EWMA/CUSUM, health rules; sensor file parser (xlsx/csv) and validation | W2 | V1 | 5 h |
| V4 | Wafer engine: classify arbitrary maps (ONNX), unknown score, similar over demo wafers, literature causes, lot tests and stacked map, join-count; die-list parser; drawn-wafer input | W3 | V1 | 4 h |
| V5 | Investigator over runs (run-scoped tools), hypothesis testing and report contract, verifier update; chat run tools | W4 | V1, V3, V4 | 4 h |
| V6 | Line page: input panel (sample, draw, upload with templates), station cards, drawers, alarms rail, two-sources banner | W5 | V1 | 6 h |
| V7 | The animation (§6) driven by run events | W5 (+ W1 review) | V6 | 6 h |
| V8 | Merge pages (four), navigation, Investigations live progress and hypotheses table, How it works, calculator | W5 + W1 | V5, V6 | 4 h |
| V9 | Remove replay loop and `/ws/line`; seed and recorded run reviewed for v2 | W1 | V2 | 1.5 h |
| V10 | Guide rewritten for v2 (Arabic) | W4 | V6 | 2 h |
| V11 | Tests: parsers (property tests), engines against bundle values, SSE ordering and resume, Playwright story (sample → alarm → investigate → approve), axe, Lighthouse | W1 + all | all | 4 h |
| V12 | Deploy, live checks, owner demo | W3 | V11 | 1 h |

Parallel critical path: V1 → (V3, V4, V6 in parallel) → V5, V7 → V8 → V11 → V12, about one
working day with five workers.

**First slice (half a day), the strongest demo path:** V1, the wafer half of V2, V4, the
draw input and wafer stations of V6/V7: draw a wafer → it passes the line → pattern,
similar wafers, literature causes → Investigate.

## 11. Acceptance (each must be shown, not claimed)

- A drawn Edge-Ring wafer returns Edge-Ring; a scribble that matches nothing returns
  "unknown"; results equal the bundle's ONNX outputs for the same map.
- A sensor sample's risk, SHAP and T²/SPE equal the bundle's precomputed values for the
  same SECOM units (to 1e-6 where deterministic).
- Malformed files get a plain message naming the column and row; nothing crashes.
- The animation never shows a station result before its `stage_result` event (test with a
  delayed server).
- Playwright: sample → alarm → Investigate → report → Approve → work order, on the live
  stack; axe 0 violations; Lighthouse mobile ≥ 90 on Line; no horizontal scroll at 375 px.
- No stored replay runs anywhere; with no input the Line shows the input panel and nothing
  else moves.
- Every number on screen and in chat traces to a computation or a bundle; the two-sources
  banner is shown whenever both tracks run.

## 12. Honest limits (published on How it works)

- Sensor-based failure prediction is weak on SECOM (about 6% of failures caught at a 5%
  false-alarm rate); the product speaks of early warning and narrowing, and the wafer
  classifier (macro-F1 0.90) carries the accuracy claim.
- SECOM sensors are anonymous; findings name sensor groups, not tools.
- The two datasets are separate real sources; the line shows them side by side, never as
  one chip.
- Causes are literature hypotheses until an engineer confirms them; recording confirmed
  causes in work orders (to learn a fab's own causes) is a proposed follow-up.
- The investigator depends on the AMD endpoint's speed; it runs on demand and shows its
  progress.
