# Yield Guardian: Status

**Last updated:** 2026-10-14 12:58 UTC (updated as each item changes)
**Plan:** [PLAN.md](PLAN.md)

<!-- progress:start -->
## Progress: 74 of 82 done (90%), 6 in progress, 2 not started

| Area | Done | In progress | Not started |
|---|---|---|---|
| F: Foundations | 6 of 6 | 0 | 0 |
| D: Data | 5 of 5 | 0 | 0 |
| S: SECOM science | 10 of 10 | 0 | 0 |
| W: Wafer maps | 10 of 10 | 0 | 0 |
| K: Knowledge base | 3 of 3 | 0 | 0 |
| A: API | 8 of 9 | 1 | 0 |
| L: AI layer | 10 of 11 | 1 | 0 |
| U: Interface | 12 of 14 | 2 | 0 |
| P: Packaging and deployment | 6 of 7 | 1 | 0 |
| Q: Quality | 3 of 5 | 0 | 2 |
| X: Submission | 1 of 2 | 1 | 0 |
<!-- progress:end -->

| Symbol | Meaning |
|---|---|
| ✅ | Done and verified (evidence linked) |
| 🟡 | In progress |
| ⏳ | Pending (not started) |
| ⛔ | Blocked (reason given) |
| ✂️ | Cut (reason given) |

**Where:** Cloud = this session writes and tests it. PC = runs on the owner's PC. You = needs the owner.

## Summary

| | |
|---|---|
| Done | 74 of 82 |
| Current focus | SECOM bundle (worker 2), chat and knowledge (worker 4), Line screen (worker 5), wafer service in the API (lead), Docker (helper) |
| Blocked | Nothing |
| Waiting on you | Rotate the Token Factory key when convenient (it appeared in the chat) |

## Measured results

Nothing below is filled in until it is measured on held-out data. No estimates appear in this table.

| Metric | Value | 95% CI | Data | Evidence |
|---|---|---|---|---|
| SECOM PR-AUC (test block) | 0.075 (no-skill 0.054) | [0.048, 0.181] | 313 test units, 17 failures | [results.md](../training/secom/reports/results.md) |
| SECOM recall at 5% false-alarm rate | 5.9% (threshold set on validation; achieved false-alarm rate 2.0%) | [0.0%, 17.6%] | 313 test units, 17 failures | [results.md](../training/secom/reports/results.md) |
| False alarms per 100 units at that point | 1.92 | [0.64, 3.51] | 313 test units | [results.md](../training/secom/reports/results.md) |
| Sensors to inspect per investigation (median) | not measured yet | | | |
| FDC false-alarm rate on held-out reference | 1.9% at the 99% T² limit (target 1%) and 1.9% at 99.9% (target 0.1%) | not computed | 106 held-out reference units | [results.md](../training/secom/reports/results.md); the 99.9% limit is above nominal, disclosed |
| WM-811K macro-F1, official split | 0.604 (mean of 3 seeds, sd 0.043) | seed 0: 0.621 [0.605, 0.634] | 118,595 test wafers; test lots are shifted from training | [metrics_official.json](../training/wafermap/reports/metrics_official.json) |
| WM-811K macro-F1, lot-grouped split | 0.900 (mean of 3 seeds, sd 0.006) | seed 0: 0.905 [0.893, 0.916] | 25,954 test wafers, 1,608 lots | [metrics_lot.json](../training/wafermap/reports/metrics_lot.json) |
| Unknown-pattern AUROC (leave-one-class-out, mean) | 0.922 Mahalanobis (energy 0.545) | per class in loco.json | 8 held-out classes, lot-grouped split | [loco.json](../training/wafermap/reports/loco.json); the method was chosen using these results, so 0.922 is not an independent estimate |
| Similar-wafer precision@10 | 0.860 macro (0.970 micro) | [0.845, 0.873] | Lot-grouped test, deployed model | [similarity_lot.json](../training/wafermap/reports/similarity_lot.json) |
| Share auto-classified at precision ≥ target | 96.0% at precision 0.992 (target 0.99, deployed model) | [95.7%, 96.3%] | Lot-grouped test | [metrics.json](../artifacts/wafermap/v1/metrics.json) |
| Points per full investigation (Token Factory) | not measured yet | | | |

## Work items

### F: Foundations

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| F1 | Implementation plan | Cloud | ✅ | [PLAN.md](PLAN.md) |
| F2 | Status tracker | Cloud | ✅ | This file |
| F3 | Monorepo scaffold, MIT licence, editor and lint config, `.env.example` | Cloud | ✅ | Commits c212301, 9fd5a19: workspace, MIT licence, `.editorconfig`, Ruff and mypy config, `.env.example` |
| F4 | CI: lint, types, tests, build, secret scan, dependency audit | Cloud | ✅ | [ci.yml](../.github/workflows/ci.yml): API (ruff, strict mypy, pytest, OpenAPI and fixture staleness), web (contract types, lint, typecheck, tests, production build, [fixture-leak check](../scripts/ci/check_no_fixtures.py)), training per project, gitleaks, Token Factory key history check, pip-audit, pnpm audit. [Run 3 green](https://github.com/anas-aldahamsheh/yield-guardian/actions/runs/38534177672) on a2acf5e; the web steps start running when the interface is merged |
| F5 | Contracts: OpenAPI export and generated TypeScript types, staleness check | Cloud | ✅ | [openapi.json](../packages/contracts/openapi.json) (47 operations), [schema.d.ts](../packages/contracts/src/schema.d.ts), 47 fixtures validated in pytest (74 passed), built from real SECOM records with model outputs marked as placeholders ([fixtures/README.md](../packages/contracts/fixtures/README.md)); CI wiring is F4 |
| F6 | Working copy of the repo in the project folder; toolchain check (Python, uv, Node, pnpm, Docker, CUDA) | PC | ✅ | PC working copy and toolchain checked (worker 3); PyTorch 2.14.1+cu130 sees the RTX 3060 (compute 8.6) |

### D: Data

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| D1 | Download SECOM from UCI, record SHA-256 and licence | PC | ✅ | Byte-identical to the UCI archive; SHA-256 in [manifest.json](../data/manifest.json); CC BY 4.0, DOI 10.24432/C54305; committed with [ATTRIBUTION.md](../data/secom/ATTRIBUTION.md) (78ba1f3) |
| D2 | Download WM-811K (MIR Lab, Kaggle fallback), record SHA-256 and licence | PC | ✅ | MIR Lab returned HTTP 404, so the Kaggle mirror was used; LSWMD.pkl 2,095,505,977 bytes, SHA-256 in the manifest; mirror lists CC0-1.0 set by the uploader, recorded with that caveat; raw data not committed |
| D3 | EDA reports: counts, time range, missingness, constants, class balance, lot structure | Cloud + PC | ✅ | SECOM EDA ([eda.md](../training/secom/reports/eda.md)) and WM-811K facts ([wm811k_facts.md](../training/wafermap/reports/wm811k_facts.md)) |
| D4 | Validated loaders (pandera schemas) | Cloud | ✅ | Pandera schemas for SECOM; merged (5f5c5dd) |
| D5 | Official-split lot-overlap check for WM-811K | PC | ✅ | Official split has 0 lots in both training (5,809 lots) and test (4,953 lots). Class mix differs: "none" is 67.6% of training, 93.3% of test; reported as a limitation |

### S: SECOM science

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| S1 | Chronological split and rolling-origin CV, with leakage test | Cloud | ✅ | Chronological blocks (train 376/53, validation 878/34, test 313/17), tie-safe cuts, 5 rolling-origin folds, leakage check passes; [results.md](../training/secom/reports/results.md) |
| S2 | Training-only preprocessing (constants, missingness indicators) | Cloud | ✅ | Training-only preprocessing: 116 dead sensors dropped, missingness indicators; merged |
| S3 | Baselines: prevalence, logistic regression, random forest | Cloud | ✅ | Baselines: prevalence, logistic regression (test PR-AUC 0.172), random forest; [results.md](../training/secom/reports/results.md) |
| S4 | LightGBM with class weights, Optuna tuning on validation | Cloud | ✅ | LightGBM with class weights, Optuna on out-of-fold validation only; [results.md](../training/secom/reports/results.md) |
| S5 | Platt calibration, reliability diagram, Brier, ECE | Cloud | ✅ | Platt calibration on out-of-fold scores, reliability, Brier, ECE; [results.md](../training/secom/reports/results.md) |
| S6 | Test metrics with bootstrap CIs, paired comparison with baselines | Cloud | ✅ | Test evaluated once: LightGBM PR-AUC 0.075 [0.048, 0.181] vs no-skill 0.054, not better than logistic (difference -0.097 [-0.307, 0.036]); [results.md](../training/secom/reports/results.md) |
| S7 | Root cause: TreeSHAP, sensor groups, stability selection, permutation test, BH | Cloud | ✅ | TreeSHAP, sensor groups, stability selection, permutation test, BH: 2 stable groups (4 sensors); [results.md](../training/secom/reports/results.md) |
| S8 | FDC: PCA reference, T² and SPE limits, contributions, EWMA and CUSUM | Cloud | ✅ | PCA on a 106-unit reference (no candidate passed KPSS, disclosed), 56 components for 90.1%; T² holds 1.9% on held-out units at 99%; SPE limit from leave-one-out reference SPE; EWMA and CUSUM; [results.md](../training/secom/reports/results.md) |
| S9 | Sensor health rules and missingness association tests | Cloud | ✅ | Health rules with a calibrated jump rule and per-sensor stuck rule; missingness tests (4 of 442 sensors at q ≤ 0.05); out-of-reference rule over-flags, disclosed; [results.md](../training/secom/reports/results.md) |
| S10 | Artifacts and SECOM model card | Cloud | ✅ | Bundle artifacts/secom/v1 (13 files, verified at build) and [model card](model-cards/secom.md); reproducible run in 210 s; merged (5f5c5dd) |

### W: Wafer maps

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| W1 | Preprocessing: label parsing, nearest-neighbour resize, one-hot | Cloud + PC | ✅ | Nearest-neighbour 64×64 maps for all 811,457 wafers (worker 3) |
| W2 | Official and lot-grouped splits | PC | ✅ | Official split (train 46,190 / val 8,165 / test 118,595) and lot-grouped split (121,049 / 25,947 / 25,954); 0 lots shared between any two parts ([splits.json](../training/wafermap/reports/splits.json)) |
| W3 | Residual CNN, focal loss, dihedral augmentations | Cloud | ✅ | Residual CNN 2.83M parameters, focal loss with class-balanced weights, dihedral augmentation; 16 unit tests pass |
| W4 | Training on the RTX 3060 (3 seeds, MLflow) | PC | ✅ | 3 seeds per split on the RTX 3060, MLflow runs with git commit and data SHA-256 |
| W5 | Evaluation: macro-F1, per-class, confusion matrix, CIs, temperature scaling | PC | ✅ | Lot-grouped test macro-F1 0.900 (sd 0.006 over 3 seeds), baseline 0.699; temperature scaling ECE 0.050 to 0.0045 ([metrics_lot.json](../training/wafermap/reports/metrics_lot.json)). Official split 0.604 (sd 0.043): shifted test lots, reported as a limitation |
| W6 | Embeddings and unknown-pattern score, leave-one-class-out test | PC | ✅ | Energy score near chance in leave-one-class-out (mean AUROC 0.545); Mahalanobis on embeddings works (0.922) and becomes the primary unknown score; [loco.json](../training/wafermap/reports/loco.json), merged to main (9cd6e04) |
| W7 | Similar-wafer search, precision@10 | PC | ✅ | precision@10 macro 0.860 [0.845, 0.873] on the lot-grouped test; [similarity_lot.json](../training/wafermap/reports/similarity_lot.json), merged to main (9cd6e04) |
| W8 | Lot excursion tests, stacked maps, join-count tests | Cloud + PC | ✅ | 1,608 test lots, 379 flagged (BH q 0.05); 65% of model flags confirmed by the same test on true labels; [lots.json](../training/wafermap/reports/lots.json), merged to main (9cd6e04) |
| W9 | ONNX export with parity test | PC | ✅ | ONNX opset 18, max logit difference 7.6e-6, argmax agreement 1.0 on 4,096 maps; merged to main (9cd6e04) |
| W10 | Demo bundle (derived subset with attribution) and wafer model card | PC | ✅ | Bundle artifacts/wafermap/v1 (11 files, SHA-256 in MANIFEST.json), demo subset of 479 lots with attribution, [model card](model-cards/wafermap.md); merged to main (9cd6e04) |

### K: Knowledge base

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| K1 | Curate open-access sources on wafer-pattern causes; verify every citation | Cloud | ✅ | 7 open-access sources, each fetched and checked; quotes kept only when two reads agree; licences in [docs/knowledge/README.md](knowledge/README.md) |
| K2 | One-time MinerU2.5-Pro conversion, chunking, full-text index | Cloud | ✅ | Chunking with page and section, BM25 search, MinerU ingestion for open-access files (not run); merged (578712c) |
| K3 | Pattern-to-cause table with citations | Cloud | ✅ | [Pattern-to-cause table](knowledge/pattern_causes.md): 12 entries, 4 medium and 8 low evidence, cautious wording; Loc and Near-full rest on one preprint, marked low |

### A: API

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| A1 | FastAPI app, settings, structured logs, health and readiness, problem+json errors | Cloud | ✅ | App factory, settings, logs, problem+json, health and readiness (37e271d); resources start and stop with the app (a99afd3); at startup the newest verified bundle is loaded and /ready names any reason it could not be (f224cec) |
| A2 | Database schema and Alembic migrations | Cloud | ✅ | Migrations 0001 (sessions, investigations, jobs, work orders, audit, alarm states) and 0002 (model calls, response cache, role choices, chat routes, evaluations, knowledge chunks with full-text search); tested on PostgreSQL with pgvector (d89d6b0) |
| A3 | Idempotent seed from verified artifacts | Cloud | 🟡 | Recorded runs are exported and imported with scripts/import_recorded.py; the API imports missing runs at startup from docs/recorded (code merged ffe9da1, nothing recorded yet) |
| A4 | Replay engine with wall-clock plant clock, WebSocket stream | Cloud | ✅ | Plant clock, alarm rules, line state, alarm pages, /ws/line stream, running on the real SECOM bundle (5f5c5dd) |
| A5 | Inference services: SECOM risk, SHAP, FDC, sensor health | Cloud | ✅ | SECOM service on the real bundle: risk, SHAP, FDC series and contributions, groups, health; unit pages list their investigations (30f1747) |
| A6 | Inference services: wafer CNN (ONNX), unknown score, pgvector search, lot stats | Cloud | ✅ | Wafer service on the real bundle: ONNX on CPU (parity 0.9986 top-label agreement with the training run), Mahalanobis unknown score, cosine similar-wafer search, lots, measured metrics; 31 tests (merged 5f5c5dd) |
| A7 | REST endpoints for every screen | Cloud | ✅ | All routes answer from real services, now including /results and /methods, filled from the loaded bundles' own evaluations (7144b67) |
| A8 | Sessions: "Try as engineer", admin login, roles, CSRF (no request limits, D-009) | Cloud | ✅ | Guest and admin sessions (only token hashes stored), scrypt admin hash, CSRF, logout; failed logins never lock the account (D-009); tested through the routes (b8ae0b3) |
| A9 | Work orders and audit log | Cloud | ✅ | Work orders, audit log with filters and pages, alarm states, investigation store with a PostgreSQL job queue; tested (b8ae0b3) |

### L: AI layer

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| L1 | Token Factory client with capability profiles and catalog sync | Cloud | ✅ | Token Factory client, capability profiles, request builder; merged (578712c) |
| L2 | Retries with jitter on 429, 502 and 503, response cache, usage records (no request limits, D-009) | Cloud | ✅ | Retries with jitter and a 120 s Retry-After bound, response cache, usage records; every limiter removed (D-009); merged (578712c) |
| L3 | Model registry: role to model, admin API, validation | Cloud | ✅ | Role-to-model registry with admin API and validation; merged (578712c) |
| L4 | Investigator graph with read-only tools, checkpointer, SSE events | Cloud | ✅ | Investigator graph: code-only triage, up to 8 tool calls, 2 revisions, pause for the decision, resume after restart (PostgreSQL checkpointer tested); merged (578712c) |
| L5 | Report writer with strict schema | Cloud | ✅ | Writer with strict JSON schema on MiMo, validated JSON on the fallback; merged (578712c) |
| L6 | Verifier: number check, citation check, wording check, model check | Cloud | ✅ | Verifier: numbers, citations, identifiers and causal wording checked in code, then a model from another family; failed values shown as [unverified]; merged (578712c) |
| L7 | Router: deterministic intents first | Cloud | ✅ | Router: rules first, model fallback with a closed intent set; injection and out-of-scope questions refused; merged (578712c) |
| L8 | Engineer chat, grounded and scoped | Cloud | ✅ | Engineer chat streams with a sentence gate that hides unverified numbers; merged (578712c) |
| L9 | Recorded fixtures for tests; one manual smoke script | Cloud | ✅ | Offline test fixtures and one manual smoke script (needs --yes and a key); merged (578712c) |
| L10 | Model evaluation harness per role, with cost estimate | Cloud | ✅ | Run once on the server: router MiniCPM5-2B 24/28 = 0.857 [0.685, 0.943], p50 660 ms; verifier GLM-5.3-Flash 10/10 = 1.000 [0.722, 1.000], p50 2.5 s; 0.0019 points in total ([results](evaluations/)). The router never chose out_of_scope; rules being added |
| L11 | Recorded demo investigations | Cloud | 🟡 | Recorder fixed: recorded runs read the data as of their alarm, live runs still follow the cursor (8329e4d). First live attempt failed before any model call (0 points); one rerun approved |

### U: Interface

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| U1 | Next.js app, Tailwind, shadcn/ui, layout shell, navigation | Cloud | ✅ | App shell with sliding navigation, replay position under the top bar, theme menu, chat entry, typed API client (af225fe) |
| U2 | Design tokens: typefaces, colour, type scale, motion; reviewed against the brief | Cloud | ✅ | Design tokens with contrast and colour-blind tests; merged (b7f321d) |
| U3 | 3D wafer: instanced dies from real maps, thin-film shader, step-and-scan reveal | Cloud | ✅ | 3D wafer with thin-film shader and SVG fallback; merged (b7f321d) |
| U4 | Home page with measured results | Cloud | ✅ | Home page with measured results; merged (b7f321d) |
| U5 | Line screen | Cloud | ✅ | Line screen: live charts with one cursor, KPIs, open alarms, units table, reconnecting socket; merged (b7f321d) |
| U6 | Investigation screen | Cloud | ✅ | Investigations list and detail with live events, approve or reject, work order; merged 72c1e9d; typecheck, 184 unit tests, 35 Playwright tests at 1440 and 390 px, no fixture content in the build |
| U7 | Wafer lab | Cloud | ✅ | Wafer lab: pattern, Mahalanobis unknown score, similar wafers; merged 72c1e9d; typecheck, 184 unit tests, 35 Playwright tests at 1440 and 390 px, no fixture content in the build |
| U8 | Lots and 3D lot stack | Cloud | ✅ | Lots list and lot page with a 3D cassette stack; merged 72c1e9d; typecheck, 184 unit tests, 35 Playwright tests at 1440 and 390 px, no fixture content in the build |
| U9 | Sensor health | Cloud | ✅ | Field of all 590 sensors, series against the reference band, weekly missingness, per-sensor tests; merged 72c1e9d; typecheck, 184 unit tests, 35 Playwright tests at 1440 and 390 px, no fixture content in the build |
| U10 | Work orders and audit log | Cloud | ✅ | Work orders, outcome form, audit log with filters; merged 72c1e9d; typecheck, 184 unit tests, 35 Playwright tests at 1440 and 390 px, no fixture content in the build |
| U11 | Models page | Cloud | ✅ | Roles with admin model switch, evaluations with intervals, usage, catalog; merged 72c1e9d; typecheck, 184 unit tests, 35 Playwright tests at 1440 and 390 px, no fixture content in the build |
| U12 | Methods page and model cards | Cloud | ✅ | Measured results, provenance and model cards from the API; merged 72c1e9d; typecheck, 184 unit tests, 35 Playwright tests at 1440 and 390 px, no fixture content in the build |
| U13 | Empty, loading and error states | Cloud | 🟡 | Empty, loading and not-ready states on every screen, checked against an API that answers 503; one more pass after the design work |
| U14 | Accessibility, responsive layouts, performance budget | Cloud | 🟡 | Design system, motion and 3D hero merged (af225fe): step-and-scan wafer exposure, live control-chart motion, reduced motion respected, no horizontal scroll at 390 px; axe and Lighthouse not run yet |

### P: Packaging and deployment

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| P1 | API and web Dockerfiles (non-root, healthchecks) | Cloud | ✅ | API and web images, non-root, read-only, healthchecks; CI builds them and runs the stack ([run](https://github.com/anas-aldahamsheh/yield-guardian/actions/runs/38549871531), merged da8e318) |
| P2 | Standalone compose with optional Caddy profile | Cloud | ✅ | Compose with PostgreSQL, migrate, API, web and Caddy; migrations apply 0001 and /ready reports the database ok in CI (merged da8e318) |
| P3 | GitHub Release of artifacts with SHA-256, verified at build | Cloud + PC | 🟡 | Bundles are committed (owner's request) and verified file by file against MANIFEST.json during the image build (d49c4e2); wafer-map v1 verified. Releases cannot be created from the cloud session; the release path stays available via deploy/artifacts.lock.json |
| P4 | anaslabs services: Sablier group, Traefik routes, networks | Cloud + PC | ✅ | Worker 3: yield-guardian-api and -web in anaslabs compose (Pino Yard pattern, Sablier group, hardened), own always-on PostgreSQL with pgvector; compose.yaml and .env backed up first; secrets generated without printing |
| P5 | Hub entry in `apps.js` and `<noscript>`, Sablier restart | PC | ✅ | Hub card in apps.js and <noscript> (anaslabs-src 4fcfb48); hub rebuilt, Sablier restarted |
| P6 | Live at `yield-guardian.anaslabs.com` | PC | ✅ | Live at https://yield-guardian.anaslabs.com from main 005a8ee: /api/v1/ready answers ready true (SECOM bundle, wafer bundle, database); cold wake about 20 s through Sablier; Token Factory key read from the server's .env without printing it |
| P7 | Security headers and CSP | Cloud | ✅ | CSP with per-request nonce, upgrade-insecure-requests only behind HTTPS, security headers; merged (b7f321d) |

### Q: Quality

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| Q1 | Python tests: statistics against known values, leakage, parity | Cloud | ✅ | Statistics checked against known values: bootstrap coverage on simulated truth, Benjamini-Hochberg 1995 example, exact ECE, Mann-Whitney and binomial tests equal scipy, T² and SPE limits against the formulas, join-count null mean and calibration, Wilson and Mahalanobis; no bug found, no reported number changed |
| Q2 | API tests | Cloud | ✅ | About 890 API tests pass on main with PostgreSQL (unit, database, science on the real bundles, methods); ruff and mypy strict clean; run in CI |
| Q3 | Web tests, type check, lint | Cloud | ✅ | Web: type check (both configs), lint 0 warnings, 184 unit tests, 35 Playwright tests at 1440 and 390 px on the production build (72c1e9d) |
| Q4 | Playwright end-to-end on the composed stack | Cloud + PC | ⏳ | |
| Q5 | Final review pass and performance check | Cloud | ⏳ | |

### X: Submission

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| X1 | README: what, why, how to run anywhere, results, AMD usage, limitations, licences, citations | Cloud | 🟡 | [README.md](../README.md) written with measured results, AMD usage, run-anywhere steps, limitations and licences; updated as the AI layer and remaining screens land |
| X2 | Demo video script and shot list | Cloud | ✂️ | Cut by the owner at 12:50: no submission material (form, video, slides, cover) is wanted |
| X3 | Slide deck | Cloud | ✂️ | Cut by the owner at 12:50: no submission material (form, video, slides, cover) is wanted |
| X4 | Cover image | Cloud | ✂️ | Cut by the owner at 12:50: no submission material (form, video, slides, cover) is wanted |
| X5 | Submission form texts (title, short and long description, tags) | Cloud | ✅ | [Form texts](submission/form.md): title 56 chars, short 243 chars, long 483 words, 7 tags; only measured numbers, SECOM weakness stated; checked by check_form.py |
| X6 | Submit on lablab | You | ✂️ | Cut by the owner at 12:50: no submission material (form, video, slides, cover) is wanted |

## Waiting on you

| Since | What | Why |
|---|---|---|
| 2026-10-14 12:12 | Go-ahead to record 3 demo investigations (L11), on the decision card in the thread | It spends Token Factory points: the ceiling is about 3 points per run, above the 1-point daily budget in PLAN 7.2, and a real run costs far less (the evaluation spent 0.0019). Recommended: record one, check its real cost, then the rest |
| 2026-10-14 | Rotate the Token Factory key after the event | It was pasted in chat |

## Changelog

| Time (UTC) | Change |
|---|---|
| 2026-10-14 12:58 | Mobile overflow fixed on /line, /methods and the home results table. Recorder reads data as of the alarm. Chat answers "what can you do?" from code instead of refusing (8329e4d) |
| 2026-10-14 12:50 | Owner cut the submission material: video (X2), slides (X3), cover (X4) and the lablab submission (X6). Cut items no longer count toward the total. Recorder bug found on the live server (tools read the live cursor, not the alarm time); 0 points spent, fix in progress |
| 2026-10-14 12:31 | New visual design merged: 3D wafer hero with a step-and-scan exposure, live chart motion, investigation report layout, attribution shown as one citation line (af225fe) |
| 2026-10-14 12:13 | "Waiting on you" cleaned: changelog rows moved back here; open asks are L11 go-ahead, key rotation and the lablab submission |
| 2026-10-14 12:08 | API tests (Q2) and web tests (Q3) closed with evidence; live site runs 249300b with results and every screen |
| 2026-10-14 11:52 | Merged the remaining screens U6 to U12 and the engineer chat sheet; the line screen leads with control charts, risk is labelled experimental (72c1e9d) |
| 2026-10-14 11:48 | Methods service: home page results and the methods page now show the bundles' measured numbers. Merged W4: recorder, evaluation import, router scope rules (ffe9da1) |
| 2026-10-14 11:36 | Owner found the interface visually weak: a dedicated design helper started on the visual system, motion and 3D (U14), in parallel with worker 5's screens |
| 2026-10-14 11:32 | Model evaluation run once with the owner's approval (L10 done): router 0.857, verifier 1.000, 0.0019 points. Statistics tests against known values (Q1 done) |
| 2026-10-14 11:23 | Model usage, role choices and knowledge search now live in PostgreSQL and survive restarts (migration 0002) |
| 2026-10-14 11:09 | Literature on wafer-pattern causes checked and extended (K1, K3 done); a wrong attribution in one quote was corrected |
| 2026-10-14 11:07 | AI layer merged: investigator, writer, verifier, router, chat, knowledge search (L1 to L9, K2, A7 done). README written with measured results |
| 2026-10-14 11:01 | Site fully ready on yield-guardian.anaslabs.com with both real bundles and the database (P6 done). K1 and K3 moved to worker 2 |
| 2026-10-14 10:57 | SECOM bundle and the wafer service merged; the API loads both real bundles with no problems (S1 to S10, A4 to A6 done). SECOM risk model has no demonstrated skill (PR-AUC 0.075 vs 0.054 no-skill); the product presents it as experimental and leads with control charts and root cause |
| 2026-10-14 10:49 | Live on anaslabs-hosting: API at yield-guardian.anaslabs.com, hub card added (P4, P5). Web app merged to main (U2 to U5, P7 done) |
| 2026-10-14 10:40 | Docker images and compose merged with CI green (P1, P2 done). Committed bundles are verified and baked into the API image |
| 2026-10-14 10:29 | Statuses reconciled with the branches. Wafer-map W6 to W10 done and merged (unknown score switched to Mahalanobis, AUROC 0.922; energy 0.545). SECOM test-block results measured: PR-AUC 0.075 vs 0.054 no-skill, so SECOM risk is weak and the product leans on FDC and root cause. Unit pages list their investigations (30f1747) |
| 2026-10-14 10:25 | Resumed after the pause: all workers continue from their branches. Empty environment variables now count as unset |
| 2026-10-14 08:51 | Database, sessions, work orders and audit merged and tested on PostgreSQL (A2, A8, A9 done). The API now loads the newest verified SECOM bundle at startup and /ready says why when it can't (A1 done) |
| 2026-10-14 08:47 | W1 to W5 done on the PC: wafer-map CNN trained (3 seeds per split); lot-grouped test macro-F1 0.900 against 0.699 for the baseline; official split 0.604 because its test lots are shifted. OOD, leave-one-class-out, similarity, ONNX and the bundle running next |
| 2026-10-14 08:41 | Two helpers started under the lead: database, sessions, work orders and audit (A2, A8, A9); Docker images, compose and artifact verification (P1 to P3). P7 assigned to worker 5. SECOM bundle format aligned with the API (019dd80) |
| 2026-10-14 08:36 | Line replay and SECOM service written with 33 tests (109 API tests pass); they run on the real bundle as soon as worker 2 delivers it |
| 2026-10-14 08:27 | F4 done: CI green on main (run 3) |
| 2026-10-14 08:20 | CI workflow pushed (F4 in progress); A8 wording corrected to match D-009 (no request limits) |
| 2026-10-14 08:09 | Fixtures rebuilt from real SECOM records (unit IDs, times, pass/fail, readings, missing values, block counts, sensor health); model outputs stay placeholders until the bundles exist. F4 started |
| 2026-10-14 08:00 | Decision D-009: no request limits anywhere in the product; plan and contracts updated |
| 2026-10-14 08:00 | F6, D1, D2, D5 done on the PC: SECOM and WM-811K downloaded with checksums, no lot overlap in the official split; SECOM merged to main |
| 2026-10-14 07:56 | F3 and F5 done: scaffold, API contracts (47 operations), TypeScript types and validated fixtures |
| 2026-10-14 07:20 | F1 and F2 done: plan and status written |
