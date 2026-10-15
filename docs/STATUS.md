# Yield Guardian: Status

**Last updated:** 2026-10-15 13:14 UTC (updated as each item changes)
**Plan:** [PLAN.md](PLAN.md) (v1, done) and [PLAN_V2.md](PLAN_V2.md) (v2, done and live); the owner's requests after v2 are section R

<!-- progress:start -->
## Progress: 96 of 100 done (96%), 3 in progress, 1 not started

| Area | Done | In progress | Not started |
|---|---|---|---|
| F: Foundations | 6 of 6 | 0 | 0 |
| D: Data | 5 of 5 | 0 | 0 |
| S: SECOM science | 10 of 10 | 0 | 0 |
| W: Wafer maps | 10 of 10 | 0 | 0 |
| K: Knowledge base | 3 of 3 | 0 | 0 |
| A: API | 9 of 9 | 0 | 0 |
| L: AI layer | 11 of 11 | 0 | 0 |
| U: Interface | 15 of 15 | 0 | 0 |
| P: Packaging and deployment | 6 of 6 | 0 | 0 |
| Q: Quality | 5 of 5 | 0 | 0 |
| X: Submission | 2 of 2 | 0 | 0 |
| V: Version 2, the live story | 14 of 14 | 0 | 0 |
| R: Requests after v2 | 0 of 4 | 3 | 1 |
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
| Done | 96 of 100 (v1: 82 of 82; v2: 14 of 14; requests after v2: 0 of 4) |
| Current focus | The owner's requests after v2: a refresh keeps everything, a fully separate workspace for every visitor, and a redesign of the whole interface |
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
| FDC false-alarm rate on held-out reference | 1.9% at the 99% T² limit (target 1%) and 1.9% at 99.9% (target 0.1%) | 99%: [0.2%, 6.6%] | 106 held-out reference units | [results.md](../training/secom/reports/results.md); the 99.9% limit is above nominal, disclosed |
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
| A3 | Idempotent seed from verified artifacts | Cloud | ✅ | docs/recorded/investigations.json (1 run, 388,104 B, no secrets) ships in the API image; live startup log: recorded_runs_seeded imported 0, present 1 (idempotent). The run opens on the site as "Recorded run: generated once, replayed without calling a model" |
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
| L5 | Report writer with strict schema | Cloud | ✅ | Writer with JSON output validated in code (MiMo refused strict json_schema on the live endpoint, 2026-10-14); merged (578712c) |
| L6 | Verifier: number check, citation check, wording check, model check | Cloud | ✅ | Verifier: numbers, citations, identifiers and causal wording checked in code, then a model from another family; failed values shown as [unverified]; merged (578712c) |
| L7 | Router: deterministic intents first | Cloud | ✅ | Router: rules first, model fallback with a closed intent set; injection and out-of-scope questions refused; merged (578712c) |
| L8 | Engineer chat, grounded and scoped | Cloud | ✅ | Engineer chat streams with a sentence gate that hides unverified numbers; merged (578712c) |
| L9 | Recorded fixtures for tests; one manual smoke script | Cloud | ✅ | Offline test fixtures and one manual smoke script (needs --yes and a key); merged (578712c) |
| L10 | Model evaluation harness per role, with cost estimate | Cloud | ✅ | Run once on the server: router MiniCPM5-2B 24/28 = 0.857 [0.685, 0.943], p50 660 ms; verifier GLM-5.3-Flash 10/10 = 1.000 [0.722, 1.000], p50 2.5 s; 0.0019 points in total ([results](evaluations/)). The router never chose out_of_scope; rules being added |
| L11 | Recorded demo investigations | Cloud | ✅ | One recorded run committed (ab23908): AL-1303-risk reached the engineer's decision; 7 evidence records, 4 findings, 3 actions, numbers 23/23 matched; two issues shown flagged (causal wording, verifier unavailable in the last round). Investigator DeepSeek-V4.1-Flash, writer Qwen3.8-Flash-Next then DeepSeek-V4.1-Flash, verifier GLM-5.3-Flash then DeepSeek-V4-Flash; 16 min, 0.0112 points. The owner stopped further recordings, so one run instead of three |

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
| U13 | Empty, loading and error states | Cloud | ✅ | Empty, loading, not-ready (neutral PendingState) and not-configured states on every screen; Investigate and chat check /meta and send nothing when the key is missing (dda51e7) |
| U14 | Accessibility, responsive layouts, performance budget | Cloud | ✅ | Live site (21e851b), Lighthouse 12.8.2 mobile, median of 3 (performance / accessibility / best practices / SEO): home 94 / 100 / 96 / 100, /line 93 / 100 / 100 / 100, /methods 91 / 100 / 100 / 100. Axe on home after 7e45f7f (live, 8ba0adc): 0 violations on desktop and at 375 px. Home best practices 96 was a hydration error (React #418, event times in the viewer's zone); fixed in 189406d and checked on a production build: the old build throws it on / and /investigations, the new one has 0 console errors on 5 pages in 3 time zones. Live check (ab23908): home best practices 100, no console errors |
| U15 | Arabic usage guide page (/guide): what it does, how to use it, data, models, problems and fixes, testing; filters and search | Cloud (guide thread) | ✅ | Live on the site (d37fc64): 89 entries in 10 categories, filters and Arabic search, right-to-left, no sideways scroll at 375 px |

### P: Packaging and deployment

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| P1 | API and web Dockerfiles (non-root, healthchecks) | Cloud | ✅ | API and web images, non-root, read-only, healthchecks; CI builds them and runs the stack ([run](https://github.com/anas-aldahamsheh/yield-guardian/actions/runs/38549871531), merged da8e318) |
| P2 | Standalone compose with optional Caddy profile | Cloud | ✅ | Compose with PostgreSQL, migrate, API, web and Caddy; migrations apply 0001 and /ready reports the database ok in CI (merged da8e318) |
| P3 | GitHub Release of artifacts with SHA-256, verified at build | Cloud + PC | ✂️ | Replaced: a GitHub Release could not be created from this environment (HTTP 403), so the bundles are committed and verified file by file against MANIFEST.json at image build and again at API start (same guarantee) |
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
| Q4 | Playwright end-to-end on the composed stack | Cloud + PC | ✅ | Playwright on the real compose stack (real bundles, PostgreSQL): 25 passed, 1 skipped (no work order yet); 375 px no-scroll on 13 routes; no Token Factory call (dda51e7). Run: pnpm --filter @yield-guardian/web e2e:stack, see apps/web/docs/E2E-STACK.md |
| Q5 | Final review pass and performance check | Cloud | ✅ | Review done: nothing blocking (no secrets in history, numbers match sources, no fixtures in the build, no rate limits, no general model proxy); doc drift fixed (fd5c12a); performance measured (see U14) |

### X: Submission

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| X1 | README: what, why, how to run anywhere, results, AMD usage, limitations, licences, citations | Cloud | ✅ | [README.md](../README.md): what it does (every screen), measured results with intervals, AMD Token Factory roles, run anywhere, limitations, licences and citations |
| X2 | Demo video script and shot list | Cloud | ✂️ | Cut by the owner at 12:50: no submission material (form, video, slides, cover) is wanted |
| X3 | Slide deck | Cloud | ✂️ | Cut by the owner at 12:50: no submission material (form, video, slides, cover) is wanted |
| X4 | Cover image | Cloud | ✂️ | Cut by the owner at 12:50: no submission material (form, video, slides, cover) is wanted |
| X5 | Submission form texts (title, short and long description, tags) | Cloud | ✅ | [Form texts](submission/form.md): title 56 chars, short 243 chars, long 483 words, 7 tags; only measured numbers, SECOM weakness stated; checked by check_form.py |
| X6 | Submit on lablab | You | ✂️ | Cut by the owner at 12:50: no submission material (form, video, slides, cover) is wanted |

### V: Version 2, the live story

Plan: [PLAN_V2.md](PLAN_V2.md). Approved by the owner on 2026-10-15 at 06:54 UTC.

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| V1 | Run contracts, engine seams, plan v2 | Cloud | ✅ | [contracts/runs.py](../services/api/src/yield_guardian/contracts/runs.py), [live/protocols.py](../services/api/src/yield_guardian/live/protocols.py), [PLAN_V2.md](PLAN_V2.md) |
| V2 | Sensor engine (live risk, SHAP, T²/SPE, EWMA/CUSUM, health), SECOM sampler, sensor file parser, parity tests | Cloud | ✅ | Merged f46d40c: [live/sensors.py](../services/api/src/yield_guardian/live/sensors.py), [live/sensor_file.py](../services/api/src/yield_guardian/live/sensor_file.py), 79 tests. Parity on all 1,567 units: T², SPE, contributions, 313 held-out risks and SHAP equal the bundle at float32 (0 mismatches); EWMA/CUSUM flags and health equal the stored ones exactly. 5,000 units: risk and charts 1.1 to 1.7 s |
| V3 | Wafer engine (ONNX on any map, unknown, similar, causes, lot tests), demo sampler, draw layouts, wafer file parser, parity tests | Cloud | ✅ | Merged 391edeb: [live/wafers.py](../services/api/src/yield_guardian/live/wafers.py), [live/wafer_file.py](../services/api/src/yield_guardian/live/wafer_file.py), [live/causes.py](../services/api/src/yield_guardian/live/causes.py), 95 tests. Parity on all 10,253 demo wafers: probabilities, unknown and energy scores equal the bundle exactly; similar wafers equal v1; join-count statistic exact, p-values within 6 Monte Carlo SE. Lot p-values equal lots.json on 446 of 475 lots (the other 29 have a wafer whose fp32 label or energy differs from the stored bf16); stacked maps 475 of 475 |
| V4 | Runs: store, orchestrator, SSE with resume, cases, uploads, templates, example files; replay loop retired | Cloud | ✅ | Merged 660816b: [services/runs.py](../services/api/src/yield_guardian/services/runs.py), [live/runs.py](../services/api/src/yield_guardian/live/runs.py), migration 0003, 48 tests. Real engines only in the product. Measured on this machine: a 40-unit sample with one real lot reaches run_done in 2.0 s; a 5,000-unit upload in 18.6 s (7.4 s compute). Replay clock removed |
| V5 | Investigator over runs, hypothesis table, confirmed cause on work orders | Cloud | ✅ | Merged 13b4a82: run_alarm trigger, run tools, hypotheses with evidence for and against checked by the verifier, confirmed cause on closing a work order (migration 0004) |
| V6 | Chat run tools and page context | Cloud | ✅ | Merged 13b4a82: ChatContext carries the run, station and item; run tools; a suggestion event offers an investigation the user starts |
| V7 | Line page: input bar, cases and browsers, drawing, upload, station cards, drawers, alarms rail, banner | Cloud | ✅ | Merged 39b0b14: four ways in on the real runs API, five stations, drawers that reuse the v1 views, alarms rail with Investigate, two-sources banner, URL state (run, station, item, alarm, pick). Story e2e 14 of 14, all Playwright projects 115 passed and 2 conditional skips, 297 web unit tests |
| V8 | The line animation, driven by run events | Cloud | ✅ | Merged 39b0b14: one timeline per run advanced only by arrived results; sensor bank, T²/SPE and risk gauges at the computed values against the model's limits, prober in real die order, 25-slot carrier, final-test stamp; reduced motion gives a static stepper. Lighthouse mobile on / (median of 5): performance 94, accessibility 100, best practices 100; axe 0 at 360, 768 and 1440 px |
| V9 | Three pages, Investigations merge, How it works, hidden admin, redirects, floating chat | Cloud | ✅ | Merged 6bf8d10: Line, Investigations (live progress, hypothesis table, work orders tab, confirmed cause), How it works (plain Arabic, then experts), hidden /admin, permanent redirects for every v1 address, floating Ask with run context and investigation suggestions. 224 web unit tests; mock e2e 59 of 59; axe strict on /how and /investigations |
| V10 | Savings calculator | Cloud | ✅ | On /how#calculator: empty until the user types costs; rates and their 95% CIs read from the API (96.0% auto-classified, 1.9% control-chart false alarms); every line shows its formula and range |
| V11 | Guide rewritten for v2 (Arabic) | Cloud | ✅ | /how#guide (ef29c23): Arabic text plus nine screenshots taken from the real API behind the production gateway, each 150 KB or less with Arabic alt text; the hypotheses slot is text only (no real investigation with hypotheses exists yet). Web: 303 unit tests pass |
| V12 | Tests: parsers, parity, SSE order and resume, Playwright story, axe, Lighthouse | Cloud | ✅ | Local main 727014a: API pytest 1,218 passed; web 297 unit tests, lint, typecheck, format, production build; Playwright desktop, mobile and axe 115 passed (2 conditional skips); stack e2e on the real API and bundles 40 passed (5 skipped: no investigation or work order in that database); Lighthouse mobile on / 94, 100, 100; a real 40-unit sample run reaches run_done in 1.1 s |
| V13 | Merge, gates, STATUS, PR | Cloud | ✅ | [PR #2](https://github.com/anas-aldahamsheh/yield-guardian/pull/2) merged into main as f754631. Gates run locally (no Actions minutes): API 1,216 passed; web 303 unit tests, lint, typecheck, format, production build, no fixture in the build; Playwright 115 passed (2 conditional skips) on a fresh build |
| V14 | Deploy, live checks, owner demo | PC | ✅ | Worker 3: live at https://yield-guardian.anaslabs.com since 11:29 UTC, /api/v1/meta git_commit f754631; compose backed up, /ws removed from the Traefik rule; /ready true, alembic head 0004. A real sample run finished its 8 stages in about 0.5 s and streamed through the tunnel to run_done (24 alarms); a reload mid-run resumed. A drawn edge ring: Edge-Ring at 0.999, marked unknown. The real sensors example upload ran; a 33 MiB body got the API's 413 problem+json. /, /investigations and /how at 375 px dark and 1440 px light: no console error, no sideways scroll; v1 addresses answer 308. Lighthouse mobile on /: performance 95, accessibility 100, best practices 100, SEO 100. No model call |

### R: Requests after v2

The owner's requests of 2026-10-15 after v2 went live (12:50 to 13:06 UTC), each built by its own worker.

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| R1 | A refresh keeps everything: the stored run renders at once with no replay, the open drawer, focus and alarm stay, an alarm keeps its investigation, the API is asked for the session and meta once | Cloud | 🟡 | Reload worker. Live finding: a finished run showed "Connecting to the run" for seconds after a refresh; the alarm-to-investigation link lived only in the browser; /session and /meta were each fetched about 10 times on one live load |
| R2 | A separate workspace for every visitor, with no login (login is for later): each one's checks, uploads and investigations are theirs alone, kept with their live status, with actions on each check, continue on another device, and an admin view of sessions | Cloud | 🟡 | Sessions worker. Defaults: another visitor's check answers 404 like a missing one; a workspace and its checks are kept 30 days after its last use instead of 24 h |
| R3 | The whole interface redesigned: layout, colour, type, hover, motion and page transitions, with the line's motion still driven only by arrived results | Cloud | 🟡 | Redesign worker, with Motion as the owner asked. Budgets: Lighthouse mobile 90 / 100 / 100 on / and /how, axe 0, reduced-motion path |
| R4 | Deploy R1 to R3 and check them live | PC | ⏳ | Worker 3, after the merge |

## Waiting on you

| Since | What | Why |
|---|---|---|
| 2026-10-14 | Rotate the Token Factory key after the event | It was pasted in chat |

## Changelog

| Time (UTC) | Change |
|---|---|
| 2026-10-15 13:14 | R1 to R4 added for the owner's requests after v2: a refresh keeps everything, a fully separate workspace for every visitor with no login, and a redesign of the whole interface. The reload, sessions and redesign workers are running; worker 3 stopped its own three workers before they committed anything. 96 of 100 |
| 2026-10-15 12:50 | V14 done: v2 live from main f754631 with the live checks passing (worker 3). Two notes from the live checks: the 413 message named the body limit (33 MB) instead of the 32 MB file limit, fixed on main; automated mouse strokes on the draw canvas only registered in its top-left half, which a new browser test shows is the automation tool, not the page. 96 of 96 |
| 2026-10-15 11:13 | V13 done: PR #2 merged into main (f754631). A stale build had failed two browser tests; on a fresh build all 115 pass. One fixture lot ID in a code comment reached the production source maps and was replaced. Worker 3 deploys with short checks. 95 of 96 |
| 2026-10-15 10:56 | V11 done and merged (ef29c23): guide screenshots from real runs; wafer views mark the wafers the lot test counts as unknown. The owner chose the fast deploy: worker 3 builds from the integration branch while the lead merges to main. 94 of 96 |
| 2026-10-15 10:41 | V12 done: every suite passes on local main (727014a), including the stack browser tests against the real API and bundles. One stale v1 stack test now reads the results table on How it works; unused v1 home components removed. 93 of 96 |
| 2026-10-15 10:18 | V7 and V8 done and merged on local main (39b0b14): the Line page and its animation on the real runs API. Station 3 counts match the lot test; unknown maps are a caution beside the prediction. Wafer pattern result now carries the lot test's energy threshold (cb76555). 92 of 96 |
| 2026-10-15 09:14 | V9 and V10 done and merged on local main (6bf8d10): three pages, How it works with the savings calculator, redirects, floating chat; Arabic guide text in place (screenshots after V7). Web: typecheck, lint, 224 unit tests pass. 90 of 96 |
| 2026-10-15 08:48 | V4, V5 and V6 done and merged on local main (328ca1a): live runs with real engines, run investigations with hypotheses, chat over runs. Full API suite 1,218 passed; web typecheck, lint and 216 unit tests pass. GitHub Actions minutes are used up: pushes paused, every gate runs locally, CI limited to main and pull requests. 88 of 96 |
| 2026-10-15 08:10 | V3 done and merged (391edeb): the live wafer engine equals the stored model on all 10,253 demo wafers; wafer file parser round-trips demo wafers. Size guard of 2 million dies per run added (join-count cost). Full API suite on main: 1,126 passed. 85 of 96 |
| 2026-10-15 07:52 | V2 done and merged (f46d40c): the live sensor engine equals the stored models on every SECOM unit (float32, 0 mismatches) and the upload parser round-trips SECOM units as CSV and XLSX. Upload size guard raised to 32 MB so 5,000 units fit in a CSV. Contract additions agreed with the workers: named risk skill, elevated band edge, processed wafer map, per-item final test, alarm cap count, runs kept while an investigation uses them, per-unit chart read. 84 of 96 |
| 2026-10-15 07:15 | All six v2 workers started: sensors (V2), wafers (V3), runs (V4), AI (V5, V6), story (V7, V8: the Line page and its animation), pages (V9 to V11: three pages, calculator, Arabic guide). Worker 3 keeps V14 (deploy and live checks) only. 83 of 96 |
| 2026-10-15 07:05 | v2 approved by the owner (06:54). Plan v2 written from the owner's agreed plan and worker 3's draft (1a3d8f4): three pages and a floating chat, live runs on four kinds of input, the animated line, hypotheses, calculator. V1 done (run contracts and engine seams); V2 to V5, V7 and V9 started in parallel. 83 of 96 |
| 2026-10-14 17:25 | Polish: the full investigations list keeps failed recording attempts behind a "Show N failed recording attempts" button (Failed filter unchanged). Fresh-database seed checked locally: recorded_runs_seeded imported 1; the recorded run's page has no console errors in Asia/Amman or UTC |
| 2026-10-14 17:12 | L11 and A3 done: recorded run committed (ab23908), seeded idempotently on the live site and opens as a recorded run. Live home: Lighthouse 95 / 100 / 100 / 100, no console errors. 82 of 82 |
| 2026-10-14 17:00 | Merged 189406d (W5): event times render in UTC on the server and switch to local time after hydration, fixing React #418 on home and /investigations; verified on a production build in Asia/Amman, America/Los_Angeles and UTC. One L11 recording started on the owner's "يلا بسرعة" (writer Qwen3.8-Flash-Next first) |
| 2026-10-14 16:50 | Live 8ba0adc: axe on home has 0 violations on desktop and mobile (target-size fixed) |
| 2026-10-14 16:58 | U14 done: live Lighthouse mobile home 94, /line 93, /methods 91 (accessibility 100 on all). Attribution toggle made a 24 px target (7e45f7f). Hydration warning on home being fixed |
| 2026-10-14 16:50 | Merged 05e9669 (W5): home Lighthouse mobile 94 (poster image as LCP, menus and toasts load on first use, no Intl in hydration, CSS as a file, one preloaded font); sign-out menu regression fixed; 194 unit and 104 e2e tests pass |
| 2026-10-14 16:24 | Second writer attempt (DeepSeek) failed on AMD 504 (0.003 points). Merged b2cecce: Qwen3.8-Flash-Next writes first, writer deadline 240 s; run bound raised to 30 min; 940 tests pass. Owner chose to stop recording here; L11 and A3 stay open |
| 2026-10-14 16:02 | Owner approved one more recording with DeepSeek as writer; deploy and record line sent |
| 2026-10-14 15:55 | 4f7e92b live: both chat checks pass (full answer, list markers shown, 173 = 116 + 57 verified; 0.0125 points). Recording failed at the writer (timeout). Merged 53106d8: DeepSeek-V4.1-Flash writes, MiMo is fallback, Qwen3.8-27B dropped; 939 tests pass |
| 2026-10-14 15:25 | Chat is fully model-written: no canned replies, the model knows every tool and the product, and the number check stays as a check. Accessibility and performance work merged (4e1e524) |
| 2026-10-14 15:16 | Final review: nothing blocking; docs corrected (writer JSON validated in code, Mahalanobis named in the wafer model card, bundles committed not released, T² interval, language-model results in README). Third recording reached a full report; the verifier rejected it on rounding and labels, then the writer timed out (0.0074 points); fixes in progress |
| 2026-10-14 14:02 | Arabic guide live (U15 done). Writer fix and "no key means 503" deployed (d37fc64) |
| 2026-10-14 13:23 | End-to-end tests on the real stack pass (Q4); not-configured states (U13). Live site verified at 375 px with no sideways scroll. Recorded run reached the writer and failed there (0.023 points); writer fix in progress |
| 2026-10-14 13:07 | New item U15: an Arabic usage guide page, built in its own thread. Chart widths fixed on phones (1086c92) |
| 2026-10-14 13:00 | README finished (X1 done). P3 replaced by committed bundles verified at build and start (a Release was not possible from here) |
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
