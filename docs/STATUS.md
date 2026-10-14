# Yield Guardian: Status

**Last updated:** 2026-10-14 10:49 UTC (updated as each item changes)
**Plan:** [PLAN.md](PLAN.md)

| Symbol | Meaning |
|---|---|
| ✅ | Done and verified (evidence linked) |
| 🟡 | In progress |
| ⏳ | Pending (not started) |
| ⛔ | Blocked (reason given) |
| ✂️ | Cut (reason given) |

**Where:** Cloud = this session writes and tests it. PC = runs on the owner's PC. You = needs the owner.

## Resume points (last pause)

Paused at 2026-10-14 08:55 UTC to save the usage quota; resumed at 10:25 UTC, all workers continuing from these points. Nothing half done is on main; each worker's work is on its own branch. To resume, say "continue" in the lead's thread.

| Who | Branch | State at pause | Next step |
|---|---|---|---|
| Lead | main | API core done: registry built at startup from the newest verified bundle (f224cec), database, sessions, work orders, audit (b8ae0b3); 167 tests pass with PostgreSQL | Unit to investigation links from the investigations table; declare 400 responses on investigation, work order and cursor routes and regenerate contracts; wafer service (A6) from worker 3's bundle; methods service |
| Worker 2 | w2/secom | Pipeline, bundle export, schemas, root cause, FDC, sensor health; WIP pushed | Was changing the stuck-value rule to use each sensor's own reference repeat rate, plus a synchronised-run diagnostic; then build the bundle with the ARTIFACTS.md fields |
| Worker 3 | w3/pc (your PC) | Paused at 55e9d5a: 6 training runs and both evaluations pushed (lot-grouped 0.900 ± 0.006, official 0.604 ± 0.043). The final pipeline (unknown-class runs, similarity, ONNX, lot tests, bundle) keeps running on the PC; its output stays there uncommitted | On continue: commit and push the pipeline output and bundle; then the lead wires A6 |
| Worker 4 | w4/ai | Agent foundations and the investigator graph (triage, plan, evidence, write, verify, decision) pushed (cb12237) | Graph tests; then merge main and wire runner, chat, llm and knowledge in bootstrap.py |
| Worker 5 | w5/web | Shell, API client, P7 headers, theme fix, 3D wafer, home page (c2dea39, 151 tests); Line screen half done (bbc8cec) | Finish Line: KPIs, open alarms, recent units, line-view and page; delete stray export in line-charts.tsx; then U6 to U14. Drop upgrade-insecure-requests from the CSP on plain HTTP |
| Helper | w1/packaging | Images, verified artifact fetch (34 tests), compose with Caddy, all healthy locally; main merged, WIP 19b0ba8 | Fix api-migrate.sh to use /app/services/api/alembic.ini and fail if missing; MIGRATE_ON_START=false in compose; finish .env.example; rebuild, CI green. Lead: env_ignore_empty=True in settings |

## Summary

| | |
|---|---|
| Done | 32 of 86 |
| Current focus | SECOM bundle (worker 2), chat and knowledge (worker 4), Line screen (worker 5), wafer service in the API (lead), Docker (helper) |
| Blocked | Nothing |
| Waiting on you | Add TOKEN_FACTORY_API_KEY to anaslabs-hosting/.env yourself, then restart yield-guardian-api |

## Measured results

Nothing below is filled in until it is measured on held-out data. No estimates appear in this table.

| Metric | Value | 95% CI | Data | Evidence |
|---|---|---|---|---|
| SECOM PR-AUC (test block) | 0.075 (no-skill 0.054) | [0.048, 0.181] | 313 test units, 17 failures | [results.md](https://github.com/anas-aldahamsheh/yield-guardian/blob/w2/secom/training/secom/reports/results.md) (branch w2/secom) |
| SECOM recall at 5% false-alarm rate | 5.9% (threshold set on validation; achieved false-alarm rate 2.0%) | [0.0%, 17.6%] | 313 test units, 17 failures | [results.md](https://github.com/anas-aldahamsheh/yield-guardian/blob/w2/secom/training/secom/reports/results.md) (branch w2/secom) |
| False alarms per 100 units at that point | 1.92 | [0.64, 3.51] | 313 test units | [results.md](https://github.com/anas-aldahamsheh/yield-guardian/blob/w2/secom/training/secom/reports/results.md) (branch w2/secom) |
| Sensors to inspect per investigation (median) | not measured yet | | | |
| FDC false-alarm rate on held-out reference | not measured yet | | | |
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
| D3 | EDA reports: counts, time range, missingness, constants, class balance, lot structure | Cloud + PC | 🟡 | WM-811K facts done ([wm811k_facts.md](../training/wafermap/reports/wm811k_facts.md)): 811,457 wafers, 46,293 lots (PLAN corrected from 46,393), 172,950 labelled. SECOM EDA with worker 2 |
| D4 | Validated loaders (pandera schemas) | Cloud | 🟡 | Pandera schemas for SECOM (on branch w2/secom, reaches main with the bundle, 8525032) |
| D5 | Official-split lot-overlap check for WM-811K | PC | ✅ | Official split has 0 lots in both training (5,809 lots) and test (4,953 lots). Class mix differs: "none" is 67.6% of training, 93.3% of test; reported as a limitation |

### S: SECOM science

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| S1 | Chronological split and rolling-origin CV, with leakage test | Cloud | 🟡 | Chronological blocks with tie-safe cuts, rolling-origin folds, leakage check passes (a14830d, on branch w2/secom, reaches main with the bundle) |
| S2 | Training-only preprocessing (constants, missingness indicators) | Cloud | 🟡 | Written and run on the real data (8937c17, on branch w2/secom, reaches main with the bundle); results in [results.md](https://github.com/anas-aldahamsheh/yield-guardian/blob/w2/secom/training/secom/reports/results.md) |
| S3 | Baselines: prevalence, logistic regression, random forest | Cloud | 🟡 | Written and run on the real data (8937c17, on branch w2/secom, reaches main with the bundle); results in [results.md](https://github.com/anas-aldahamsheh/yield-guardian/blob/w2/secom/training/secom/reports/results.md) |
| S4 | LightGBM with class weights, Optuna tuning on validation | Cloud | 🟡 | Written and run on the real data (8937c17, on branch w2/secom, reaches main with the bundle); results in [results.md](https://github.com/anas-aldahamsheh/yield-guardian/blob/w2/secom/training/secom/reports/results.md) |
| S5 | Platt calibration, reliability diagram, Brier, ECE | Cloud | 🟡 | Written and run on the real data (8937c17, on branch w2/secom, reaches main with the bundle); results in [results.md](https://github.com/anas-aldahamsheh/yield-guardian/blob/w2/secom/training/secom/reports/results.md) |
| S6 | Test metrics with bootstrap CIs, paired comparison with baselines | Cloud | 🟡 | Written and run on the real data (8937c17, on branch w2/secom, reaches main with the bundle); results in [results.md](https://github.com/anas-aldahamsheh/yield-guardian/blob/w2/secom/training/secom/reports/results.md) |
| S7 | Root cause: TreeSHAP, sensor groups, stability selection, permutation test, BH | Cloud | 🟡 | TreeSHAP, sensor groups, stability selection, permutation test, BH written and run (12c7c70, on branch w2/secom, reaches main with the bundle) |
| S8 | FDC: PCA reference, T² and SPE limits, contributions, EWMA and CUSUM | Cloud | 🟡 | PCA reference, T² and SPE limits, contributions, EWMA and CUSUM written (12c7c70); autoscaling being finished (on branch w2/secom, reaches main with the bundle) |
| S9 | Sensor health rules and missingness association tests | Cloud | 🟡 | Health rules and missingness tests written (12c7c70); stuck-value rule being changed to each sensor's own repeat rate (on branch w2/secom, reaches main with the bundle) |
| S10 | Artifacts and SECOM model card | Cloud | 🟡 | Bundle export and schemas written (538983d); the final bundle is built after S8 and S9 |

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
| K1 | Curate open-access sources on wafer-pattern causes; verify every citation | Cloud | ⏳ | |
| K2 | One-time MinerU2.5-Pro conversion, chunking, full-text index | Cloud | ⏳ | Costs points; run once |
| K3 | Pattern-to-cause table with citations | Cloud | ⏳ | |

### A: API

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| A1 | FastAPI app, settings, structured logs, health and readiness, problem+json errors | Cloud | ✅ | App factory, settings, logs, problem+json, health and readiness (37e271d); resources start and stop with the app (a99afd3); at startup the newest verified bundle is loaded and /ready names any reason it could not be (f224cec) |
| A2 | Database schema and Alembic migrations | Cloud | ✅ | SQLAlchemy models and Alembic migration 0001, applied at startup and tested on PostgreSQL 16 with pgvector; CI runs them on pgvector/pg17 (b8ae0b3) |
| A3 | Idempotent seed from verified artifacts | Cloud | ⏳ | |
| A4 | Replay engine with wall-clock plant clock, WebSocket stream | Cloud | 🟡 | Plant clock, alarm rules, line state, alarm pages and the /ws/line stream written and tested (5e9e5ca); waits for the real SECOM bundle and the database alarm states |
| A5 | Inference services: SECOM risk, SHAP, FDC, sensor health | Cloud | 🟡 | SECOM service written and tested (5e9e5ca): bundle verified file by file, timeline checked against secom_labels.data, explanations add up to the raw score; waits for worker 2's bundle |
| A6 | Inference services: wafer CNN (ONNX), unknown score, pgvector search, lot stats | Cloud | 🟡 | Lead: wafer service from the merged bundle (ONNX, Mahalanobis unknown score, similar wafers, lots) |
| A7 | REST endpoints for every screen | Cloud | 🟡 | All 47 routes declared on the service interfaces (37e271d); services pending (A5, A6) |
| A8 | Sessions: "Try as engineer", admin login, roles, CSRF (no request limits, D-009) | Cloud | ✅ | Guest and admin sessions (only token hashes stored), scrypt admin hash, CSRF, logout; failed logins never lock the account (D-009); tested through the routes (b8ae0b3) |
| A9 | Work orders and audit log | Cloud | ✅ | Work orders, audit log with filters and pages, alarm states, investigation store with a PostgreSQL job queue; tested (b8ae0b3) |

### L: AI layer

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| L1 | Token Factory client with capability profiles and catalog sync | Cloud | 🟡 | Client, capability profiles, request builder (on branch w4/ai, tests pass, merge pending) |
| L2 | Retries with jitter on 429, 502 and 503, response cache, usage records (no request limits, D-009) | Cloud | 🟡 | Retries, cache, usage records; every limiter removed per D-009 (on branch w4/ai, tests pass, merge pending) |
| L3 | Model registry: role to model, admin API, validation | Cloud | 🟡 | Role to model registry (on branch w4/ai, tests pass, merge pending) |
| L4 | Investigator graph with read-only tools, checkpointer, SSE events | Cloud | 🟡 | Investigator graph: code-only triage, up to 8 tool calls, 2 revisions, pause for the engineer's decision, resume; 11 read-only tools (on branch w4/ai, tests pass, merge pending, cb12237) |
| L5 | Report writer with strict schema | Cloud | 🟡 | Writer with strict JSON schema (on branch w4/ai, tests pass, merge pending) |
| L6 | Verifier: number check, citation check, wording check, model check | Cloud | 🟡 | Verifier: number, citation, identifier and causal-wording checks in code, then a model from another family (on branch w4/ai, tests pass, merge pending) |
| L7 | Router: deterministic intents first | Cloud | 🟡 | Worker 4 writing the router |
| L8 | Engineer chat, grounded and scoped | Cloud | 🟡 | Worker 4 writing the engineer chat |
| L9 | Recorded fixtures for tests; one manual smoke script | Cloud | 🟡 | Test fixtures and one manual smoke script (on branch w4/ai, tests pass, merge pending) |
| L10 | Model evaluation harness per role, with cost estimate | Cloud | ⏳ | Costs points; run once |
| L11 | Recorded demo investigations | Cloud | ⏳ | Costs points; run once |

### U: Interface

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| U1 | Next.js app, Tailwind, shadcn/ui, layout shell, navigation | Cloud | 🟡 | App shell, navigation, sessions, theme menu, typed API client; merged to main (b7f321d) |
| U2 | Design tokens: typefaces, colour, type scale, motion; reviewed against the brief | Cloud | ✅ | Design tokens with contrast and colour-blind tests; merged (b7f321d) |
| U3 | 3D wafer: instanced dies from real maps, thin-film shader, step-and-scan reveal | Cloud | ✅ | 3D wafer with thin-film shader and SVG fallback; merged (b7f321d) |
| U4 | Home page with measured results | Cloud | ✅ | Home page with measured results; merged (b7f321d) |
| U5 | Line screen | Cloud | ✅ | Line screen: live charts with one cursor, KPIs, open alarms, units table, reconnecting socket; merged (b7f321d) |
| U6 | Investigation screen | Cloud | ⏳ | |
| U7 | Wafer lab | Cloud | ⏳ | |
| U8 | Lots and 3D lot stack | Cloud | ⏳ | |
| U9 | Sensor health | Cloud | ⏳ | |
| U10 | Work orders and audit log | Cloud | ⏳ | |
| U11 | Models page | Cloud | ⏳ | |
| U12 | Methods page and model cards | Cloud | ⏳ | |
| U13 | Empty, loading and error states | Cloud | ⏳ | |
| U14 | Accessibility, responsive layouts, performance budget | Cloud | ⏳ | |

### P: Packaging and deployment

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| P1 | API and web Dockerfiles (non-root, healthchecks) | Cloud | ✅ | API and web images, non-root, read-only, healthchecks; CI builds them and runs the stack ([run](https://github.com/anas-aldahamsheh/yield-guardian/actions/runs/38549871531), merged da8e318) |
| P2 | Standalone compose with optional Caddy profile | Cloud | ✅ | Compose with PostgreSQL, migrate, API, web and Caddy; migrations apply 0001 and /ready reports the database ok in CI (merged da8e318) |
| P3 | GitHub Release of artifacts with SHA-256, verified at build | Cloud + PC | 🟡 | Bundles are committed (owner's request) and verified file by file against MANIFEST.json during the image build (d49c4e2); wafer-map v1 verified. Releases cannot be created from the cloud session; the release path stays available via deploy/artifacts.lock.json |
| P4 | anaslabs services: Sablier group, Traefik routes, networks | Cloud + PC | ✅ | Worker 3: yield-guardian-api and -web in anaslabs compose (Pino Yard pattern, Sablier group, hardened), own always-on PostgreSQL with pgvector; compose.yaml and .env backed up first; secrets generated without printing |
| P5 | Hub entry in `apps.js` and `<noscript>`, Sablier restart | PC | ✅ | Hub card in apps.js and <noscript> (anaslabs-src 4fcfb48); hub rebuilt, Sablier restarted |
| P6 | Live at `yield-guardian.anaslabs.com` | PC | 🟡 | API live at https://yield-guardian.anaslabs.com (/api/v1/ready answers, database ok, wakes in about 10 s); web merged to main (b7f321d) and being deployed; ready turns true when the SECOM bundle and wafer service land |
| P7 | Security headers and CSP | Cloud | ✅ | CSP with per-request nonce, upgrade-insecure-requests only behind HTTPS, security headers; merged (b7f321d) |

### Q: Quality

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| Q1 | Python tests: statistics against known values, leakage, parity | Cloud | ⏳ | |
| Q2 | API tests | Cloud | ⏳ | |
| Q3 | Web tests, type check, lint | Cloud | ⏳ | |
| Q4 | Playwright end-to-end on the composed stack | Cloud + PC | ⏳ | |
| Q5 | Final review pass and performance check | Cloud | ⏳ | |

### X: Submission

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| X1 | README: what, why, how to run anywhere, results, AMD usage, limitations, licences, citations | Cloud | ⏳ | |
| X2 | Demo video script and shot list | Cloud | ⏳ | |
| X3 | Slide deck | Cloud | ⏳ | |
| X4 | Cover image | Cloud | ⏳ | |
| X5 | Submission form texts (title, short and long description, tags) | Cloud | ⏳ | |
| X6 | Submit on lablab | You | ⏳ | |

## Waiting on you

| Since | What | Why |
|---|---|---|
| 2026-10-14 | Put the Token Factory key in `.env` on your PC when asked | The key never goes through chat or the repository |

## Changelog

| Time (UTC) | Change |
|---|---|
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
