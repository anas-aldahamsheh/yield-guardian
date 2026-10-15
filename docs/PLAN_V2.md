# Yield Guardian v2: Plan

| | |
|---|---|
| Version | 2.0 |
| Date | 2026-10-15 |
| Approved by | The owner, 2026-10-15 06:54 UTC ("موافق، اعمل الخطة… وزّع الشغل على الووركرات… شغل عملاق، والأنيميشن بأعلى مرحلة من الجمال والدقة") |
| Written by | Lead (W1), from the owner's decisions of 2026-10-15 and worker 3's draft (1a3d8f4) |
| Builds on | [PLAN.md](PLAN.md) v1: every ground rule in §2 stays binding |
| Owner's plan in Arabic | `/mnt/project-files/yield-guardian/docs/story-plan.md` (the agreed version) |
| Status | [STATUS.md](STATUS.md), items V1 to V14 |

v1 built the science, the AI layer and a working site (82 of 82 items). The owner then used the
product and found it hard to follow. v2 keeps every model and turns the product into one story
a visitor can follow and drive with their own data, computed live.

---

## 1. The problems, and how v2 solves them

| # | Problem in v1 | v2 solution | State |
|---|---|---|---|
| 1 | Ten pages that do not connect; no story | Three pages and a floating chat. The home page is an animated production line that tells the story station by station (§4, §6) | New |
| 2 | Nothing comes from the user: the Line replays stored results (`timeline.parquet`) in an endless loop | Live runs on the user's own input. Every result is computed when the input arrives; nothing moves until the user enters something (§3) | New |
| 3 | It is not clear what goes in and what comes out | Every station shows its input and its result in one plain sentence; details open in a drawer (§4) | New |
| 4 | "Defect type" and "cause of failure" are confused; the data has no confirmed causes | Literature causes per pattern on the wafer card, ranked by evidence, with sources (exists); the investigator tests each one for and against (§7) | Part new |
| 5 | The investigator writes one general report | A hypothesis table: each candidate cause with the evidence for and against; for units, which sensor group deviated, by how much and since when (§7) | New |
| 6 | The investigation a visitor sees is a recording | Live investigation on "Investigate", steps streaming as they happen (§3.4) | New |
| 7 | The live investigator is slow and spends points (last run 16 min, AMD endpoint) | Runs only on click, with step-by-step progress and honest elapsed time; the slowness itself is the endpoint's | Part new |
| 8 | The chat is a separate sheet that does not know what the user is looking at | Floating button on every page, run and station context, run-reading tools (§8) | New |
| 9 | Expert pages (Models, Methods) sit in the main menu | One "How it works" page: plain Arabic on top, an expert section below; model roles move to a hidden admin page | New |
| 10 | No answer to "how much does it save?" | A calculator from the fab's own costs and our measured rates, as a range from the CIs (§9) | New |
| 11 | Unit failure prediction is weak (test ROC-AUC 0.52; about 6% of failures caught at the 5% false-alarm point) and easy to overstate | Shown as a weak signal, labelled so, next to its measured skill; drift detection and the wafer classifier lead | Wording |
| 12 | SECOM and WM-811K are not the same chips | Two tracks on the line, with a banner that says so whenever both run | By design |
| 13 | Confirmed causes are never recorded, so the fab cannot learn its own | A "confirmed cause" field when a work order is closed, labelled as data collection, not prediction (§7.3) | New |

Already fixed in v1 on 2026-10-14: writer failures (Qwen3.8-Flash-Next first, 240 s deadline,
two fallbacks; one recorded run), hard-coded chat replies, the React #418 time-zone error, failed
attempts cluttering the investigation list, home Lighthouse 95 / 100 / 100 / 100.

## 2. What stays the same

- Ground rules of PLAN.md §2: real data only, held-out metrics with CIs, association not
  causation, language models never produce numbers, humans approve, reproducible, limits
  published.
- All trained models and bundles (`artifacts/secom/v1`, `artifacts/wafermap/v1`), the
  investigator graph, writer, verifier, chat number gate, work orders, audit log, hosting.
- AMD Token Factory for every language-model role. No Token Factory call in any test.
- English UI; the plain-language part of "How it works" and the guide are in Arabic.

## 3. Live runs (replace the replay loop)

A **run** is one submission, processed now, stage by stage, every result streamed to the
browser as soon as it is computed. The contract is `services/api/src/yield_guardian/contracts/runs.py`
(V1, written by the lead and binding; changes go through the lead). Engine seams are in
`live/protocols.py`.

### 3.1 Four ways in

| Way | What the user does | What the server receives |
|---|---|---|
| Try a real sample | One click | The server picks, at random with a recorded seed, a window of consecutive real SECOM units from the test block (units the risk model never saw) and every demo wafer of one real WM-811K lot. The rule and seed are shown |
| Pick a case | Chooses a real situation from a catalog ("a unit that raised an SPE alarm", "a slow drift", "a wafer with a scratch", "an unknown pattern", "a lot with a repeating pattern"), or browses real units, wafers and lots | Real items found in the data by a fixed rule, shown with the rule |
| Draw a defect | Paints failing dies on the die layout of a real WM-811K wafer (all dies start as pass), one or more wafers | `wafers[]` with values 0 no die, 1 pass, 2 fail, labelled "your drawing" |
| Upload a file | Excel (.xlsx) or CSV | Parsed and validated first (POST /uploads), then run |

Every way is materialised into the same `SensorUnitInput[]` / `WaferInput[]` and processed by
the same code, so a sample is processed exactly like an upload.

**Sensor file:** one row per unit: `unit_id, timestamp, S001 … S590, result` (`result`
optional, `pass` or `fail`). The 590 SECOM sensors, in order; an empty cell is a missing
reading. Several units in time order also enable drift (EWMA, CUSUM) and sensor health.

**Wafer file:** one row per die: `lot, wafer, x, y, result` (`pass` or `fail`). Positions not
listed are "no die". The server builds each wafer's grid; several wafers of one lot enable the
lot test.

Validation answers in plain words (which column, which row, what is wrong). Size guards: 20 MB
per file, 5,000 units and 500 wafers per run. Templates (header only) and real example files
(real SECOM units and a real WM-811K lot in the upload format) can be downloaded.

### 3.2 Stages and stations

The page draws five stations. Stages are the server's units of work; each emits its result as
soon as it is computed. A stage whose input is missing is skipped with a plain `needs` sentence
and its station shows grey.

| Station | Stage | Needs | Computes (existing model or method) |
|---|---|---|---|
| ① Manufacturing | `intake` | any input | parse, validate, counts, missing readings, unmonitored sensors, time order, two-sources flag |
| ② Monitoring | `sensor_risk` | sensor units | LightGBM (`model.txt`) + Platt calibrator; TreeSHAP via `pred_contrib`; band at the validation operating point; validity: held out, in training (in-sample) or new data |
| ② Monitoring | `control_charts` | sensor units | T² and SPE from `fdc_model.npz` (impute, centre, scale, loadings, eigenvalues, limits); per-sensor contributions; standardised readings for the sensor lights |
| ② Monitoring | `drift_health` | ≥ 20 units in time order | EWMA (λ 0.2, L 2.962) and two-sided CUSUM (k 0.5, h 5) on the leading groups' standardised scores; health rules of `health.json` (dead, flatline, stuck, jumps, out of reference range) |
| ③ Wafer test | `wafer_pattern` | wafer maps | nearest-neighbour 64×64, ONNX CNN, temperature, Mahalanobis unknown score, energy cross-check, auto-accept at the 99%-precision threshold, join-count spatial test |
| ③ Wafer test | `wafer_similar` | wafer maps | cosine top-10 over the 10,253 demo wafers; literature causes for the predicted patterns |
| ③ Wafer test | `lot` | ≥ 2 wafers of one lot | one-sided binomial test per pattern against the training-period rates, BH; stacked failure map |
| ②/③ | `final_test` | recorded results or labels | were the warnings right? per unit and per wafer |
| ④ Investigation | on demand | an alarm | the investigator over the run's evidence (§7) |
| ⑤ Decision | on demand | a report | approve (work order) or reject; confirmed cause when the work order closes |

**Parity, the proof that live equals the models:** for every SECOM unit, the live T², SPE and
contributions equal `timeline.parquet` and `fdc.npz`; the live risk and SHAP equal the stored
values for units the deployed model did not train on; EWMA/CUSUM alarms over the full SECOM
sequence equal the stored flags; health over the full SECOM data equals `health.json`; ONNX
outputs for every demo wafer equal the bundle's parity values; lot tests over a real lot equal
`lots.json`. These are tests, not claims.

### 3.3 API

- `POST /api/v1/runs` (JSON `RunCreate`, discriminated by `source`) → `201 RunCreated`.
- `GET /api/v1/runs/{run_id}/events` (SSE, `RunEvent`): `run_started`, `stage_started`,
  `stage_result`, `stage_skipped`, `stage_failed`, `alarm`, `run_done`. Each carries `seq`; a
  reconnect with `Last-Event-ID` resumes; the stream closes after `run_done`.
- `GET /api/v1/runs/{run_id}` → `Run` (full state, for drawers, chat, investigator, reload).
- `GET /api/v1/runs/cases` → `RunCaseList`; `GET /api/v1/runs/layouts` → real die layouts to draw on.
- `POST /api/v1/uploads` (multipart) → `UploadSummary`; `GET /api/v1/uploads/templates/{kind}.{csv|xlsx}`;
  `GET /api/v1/uploads/examples/{kind}.{csv|xlsx}` (real data in the upload format).
- Runs are stored in PostgreSQL (input, stage results, alarms, events) and expire after 24 h
  unless an investigation references them. No sign-in is needed to run; investigations and
  decisions keep the engineer session.
- The wall-clock replay (`/ws/line`, `/line/state`, plant clock) is retired from the product.
  Alarm IDs of the recorded investigation keep resolving.

### 3.4 Investigation from a run

`POST /investigations` gains trigger kind `run_alarm` with ref `<run_id>:<alarm_id>`. The
investigator reads the run through run-scoped tools, plus the existing tools when the run's
items are real SECOM units or WM-811K wafers. The story page shows the steps inline as they
stream and links to the investigation page.

## 4. Pages: three, and the chat

| v1 page | v2 |
|---|---|
| Home, Line | **Line** (`/`) |
| Wafer lab, Lots, Sensor health, unit, wafer and lot pages | drawers inside Line |
| Investigations, Work orders | **Investigations** (`/investigations`), work orders inside each investigation and as a tab |
| Methods, Models, Guide | **How it works** (`/how`): plain Arabic first, "For experts" below, the guide as a section |
| Model role settings | hidden admin page (`/admin`), not in the menu |
| Chat | floating button on every page |

Old URLs redirect to their new place, so no link breaks.

### 4.1 Line (the story)

1. One sentence: what to do and what happens.
2. Input bar: Try a real sample, Pick a case, Draw a defect, Upload a file.
3. The animated line (§6), with the alarms rail at the side; each alarm has "Investigate".
4. Under each station, its result in one sentence and one number; grey "needs data", amber
   computing, calm ok, red alarm.
5. A station opens a drawer: units (risk with its skill, SHAP bars, sensor groups, T²/SPE
   chart with limits and contributions, EWMA/CUSUM, health table); wafers (map,
   probabilities, unknown score, spatial test, similar wafers, literature causes with
   sources); lot (stacked map, tests).
6. The two-sources banner whenever both tracks run.
7. With no input, only the input bar is live: nothing moves on its own.

### 4.2 Investigations

List (running, awaiting decision, decided; failed recording attempts behind a button as
today). Detail: live progress (each tool call as it happens, elapsed time), the report with
every number linked to its evidence, the hypothesis table, approve or reject, the work order
and its confirmed cause. A Work orders tab lists all work orders and the audit log.

### 4.3 How it works

Plain Arabic on top: what the product does, where the data comes from, what it cannot do.
"For experts" below: measured results with CIs, model cards, AI roles on AMD with measured
latency and points, data sources and licences, limitations, the savings calculator, and the
Arabic guide as a section.

## 5. Inputs and outputs

| Input | Outputs |
|---|---|
| Sensor units | risk and band with its measured skill, top sensors and groups (SHAP), T²/SPE with contributing sensors, EWMA/CUSUM drift, sensor health, "was the warning right?" when results are given |
| Wafer maps | pattern and confidence or "unknown pattern", auto-accepted or "for review", spatial clustering, the most similar real wafers with their recorded pattern, literature causes with sources |
| A lot (≥ 2 wafers) | whether a pattern repeats more than chance (p, q), stacked failure map |
| An alarm | investigator report with evidence and the hypothesis table; approve or reject; work order |

## 6. The animation (the owner's highest standard)

- **Truthful:** a unit or wafer reaches a station only after that stage's `stage_result`
  event has arrived. The timeline is driven by events; it never runs ahead of data and never
  fakes progress. Waiting on the server shows a calm working state with the real elapsed time.
- **Precise:** every lit sensor, dial, chart point and die is the computed value at the right
  scale; limits are the model's limits; the prober reveals the real map die by die.
- **Scene:** the Yellow Room (PLAN.md §9), one continuous line lit amber. The wafer is the
  existing thin-film 3D wafer; stations are drawn tool silhouettes (process chamber with its
  sensor bank, monitoring console, prober, lot carrier), not stock icons. 3D only for the wafer
  and the carrier; SVG for everything read precisely.
- **Per station:** sensors light with their standardised readings (dead and unmonitored stay
  dark); the T² and SPE needles move to the computed value against the real limits; the risk
  dial fills to the calibrated value with its weak-skill label; the prober steps die by die;
  wafers stack into a 25-slot carrier; the final-test stamp shows pass or fail.
- **Alarm:** the station turns red with one pulse, the alarm slides into the rail with its
  plain meaning.
- **Craft:** one GSAP timeline per run, R3F on demand frames, instancing, DPR clamp, 60 fps on
  a mid-range GPU; `prefers-reduced-motion` gives a static stepper with the same results;
  keyboard reachable, results announced by a live region.
- **Budgets:** Lighthouse mobile ≥ 90 on Line, accessibility 100, axe 0 violations, no
  horizontal scroll at 360 px; the 3D scene loads after first paint.

## 7. Causes

### 7.1 Wafer track

The candidate causes for the predicted pattern come from the literature table (quotes, pages,
evidence level). For each, the investigator gathers evidence for and against from the run:
pattern confidence, unknown score, similar wafers and their recorded patterns, lot repetition,
spatial clustering, the stacked map.

### 7.2 Sensor track

For a unit or alarm: which sensor groups deviated (T²/SPE contributions, SHAP), by how much
(share of the statistic, standardised values), since when (EWMA/CUSUM onset in the run), and
whether the same groups are associated with failure across all SECOM data (groups.json).
SECOM sensors are anonymous, so findings name groups, not tools.

### 7.3 Report contract and confirmed causes

The report gains `hypotheses[]: {hypothesis, source_ids[], evidence_for[], evidence_against[],
assessment: supported | not_supported | inconclusive}`. The verifier checks every cited
evidence ID and number as today; wording stays "associated with". Closing a work order can
record a confirmed cause (free text and the hypothesis it confirms, if any), stored and shown
as the fab's own record, never used as a prediction.

## 8. Chat

Model-driven (done). New read-only tools: `get_run` (summary, stages, alarms), `get_run_unit`,
`get_run_wafer`, `get_run_lot`. The chat receives which run, station and item the user is
looking at. Every number passes the gate. It explains results, answers "why", gives literature
causes, compares with similar wafers, summarises a run, guides an upload, and offers to start an
investigation (the user clicks).

## 9. Savings calculator

Inputs from the user: wafer cost, engineer hour cost, downtime hour cost, wafers per day,
minutes an engineer spends per wafer map. Measured rates (with CIs): share of wafers classified
automatically at the 99% precision target, FDC false-alarm rate. Output: engineer hours and
money per month as a range from the CIs, with every assumption shown. With empty inputs it
shows nothing; no default cost is invented.

## 10. Work split

All code is written in the cloud container on `v2/*` branches; the lead merges, runs the gates
and keeps STATUS. Worker 3 (the owner's PC) deploys and checks the live site from lines the
owner pastes.

| ID | Item | Owner | Depends on |
|---|---|---|---|
| V1 | Run contracts (`contracts/runs.py`), engine seams (`live/protocols.py`), this plan | Lead | – |
| V2 | Sensor engine: live risk, SHAP, T²/SPE and contributions, EWMA/CUSUM, health; SECOM materialiser and sampler; sensor file parser (CSV, XLSX); parity tests | Sensors worker | V1 |
| V3 | Wafer engine: ONNX on any map, unknown score, auto-accept, join-count, similar, causes, lot tests and stacked map; demo materialiser, sampler, draw layouts; wafer file parser; parity tests | Wafers worker | V1 |
| V4 | Runs: store (PostgreSQL, 24 h TTL), orchestrator, SSE with resume, cases catalog, uploads, templates and real example files, OpenAPI and TS types; retire the replay loop | Runs worker | V1 (V2, V3 to finish) |
| V5 | Investigator over runs: `run_alarm` trigger, run-scoped tools, hypothesis testing in the report, verifier update; confirmed cause on work orders | AI worker | V1 |
| V6 | Chat: run tools, page context (run, station, item), suggest an investigation | AI worker | V1 |
| V7 | Line page: input bar, case picker and dataset browsers, drawing tool, upload with validation view, station cards, drawers, alarms rail, two-sources banner | Story worker | V1 |
| V8 | The animation (§6), driven by run events | Story worker | V7 |
| V9 | Pages: three-item navigation, Investigations (live progress, hypothesis table, work orders tab), How it works (plain Arabic, experts, guide), hidden admin, redirects, floating chat with context | Pages worker | V1 |
| V10 | Savings calculator | Pages worker | V9 |
| V11 | Guide rewritten for v2 (Arabic) | Pages worker | V7 |
| V12 | Tests: parsers (property tests), engines against bundles, SSE ordering and resume, Playwright story (sample → alarm → investigate → approve, mocked model calls), axe, Lighthouse | Every worker for its part; lead for the end-to-end run | all |
| V13 | Merge, gates, STATUS, PR | Lead | all |
| V14 | Deploy, live checks, owner demo | Worker 3 (PC) | V13 |

## 11. Acceptance (each shown, not claimed)

- A drawn Edge-Ring wafer returns Edge-Ring; a scribble far from every class returns
  "unknown pattern"; results equal ONNX outputs for the same map.
- Every parity test of §3.2 passes on the full bundles.
- Malformed files get a plain message naming the column and row; nothing crashes; the size
  guards hold.
- The animation never shows a stage result before its `stage_result` event (tested with a
  delayed server).
- Playwright on the local stack: sample → alarm → Investigate → report → Approve → work order,
  with recorded model calls; axe 0 violations; Lighthouse mobile ≥ 90 on Line; no horizontal
  scroll at 360 px; reduced motion shows every result.
- No stored replay anywhere in the product; with no input the Line shows the input bar and
  nothing moves.
- Every number on screen and in chat traces to a computation or a bundle; the two-sources
  banner is shown whenever both tracks run.

## 12. Honest limits (published on How it works)

- Sensor-based failure prediction is weak on SECOM: test ROC-AUC 0.52, and at the 5%
  false-alarm operating point it caught 1 of 17 test failures. The product speaks of early
  warning and narrowing; the wafer classifier (lot-split macro-F1 0.90) carries the accuracy
  claim, and it drops to about 0.60 on the official WM-811K split.
- SECOM sensors are anonymous; findings name sensor groups, not tools.
- The two datasets are separate real sources, never shown as one chip.
- Causes are literature hypotheses until an engineer confirms them.
- The investigator depends on the AMD endpoint's speed; it runs on demand and shows its
  progress.
- Uploaded sensor data must be in the SECOM layout (590 sensors); another fab's sensors need
  retraining.
