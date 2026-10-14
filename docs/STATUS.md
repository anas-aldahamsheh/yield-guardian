# Yield Guardian: Status

**Last updated:** 2026-10-14 08:00 UTC (updated as each item changes)
**Plan:** [PLAN.md](PLAN.md)

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
| Done | 8 of 86 |
| Current focus | SECOM pipeline (worker 2), wafer-map training setup (worker 3 on the PC), AI layer (worker 4), interface (worker 5), CI (lead) |
| Blocked | Nothing |
| Waiting on you | Put the Token Factory key in `.env` on your PC when asked |

## Measured results

Nothing below is filled in until it is measured on held-out data. No estimates appear in this table.

| Metric | Value | 95% CI | Data | Evidence |
|---|---|---|---|---|
| SECOM PR-AUC (test block) | not measured yet | | | |
| SECOM recall at 5% false-alarm rate | not measured yet | | | |
| False alarms per 100 units at that point | not measured yet | | | |
| Sensors to inspect per investigation (median) | not measured yet | | | |
| FDC false-alarm rate on held-out reference | not measured yet | | | |
| WM-811K macro-F1, official split | not measured yet | | | |
| WM-811K macro-F1, lot-grouped split | not measured yet | | | |
| Unknown-pattern AUROC (leave-one-class-out, mean) | not measured yet | | | |
| Similar-wafer precision@10 | not measured yet | | | |
| Share auto-classified at precision ≥ target | not measured yet | | | |
| Points per full investigation (Token Factory) | not measured yet | | | |

## Work items

### F: Foundations

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| F1 | Implementation plan | Cloud | ✅ | [PLAN.md](PLAN.md) |
| F2 | Status tracker | Cloud | ✅ | This file |
| F3 | Monorepo scaffold, MIT licence, editor and lint config, `.env.example` | Cloud | ✅ | Commits c212301, 9fd5a19: workspace, MIT licence, `.editorconfig`, Ruff and mypy config, `.env.example` |
| F4 | CI: lint, types, tests, build, secret scan, dependency audit | Cloud | ⏳ | |
| F5 | Contracts: OpenAPI export and generated TypeScript types, staleness check | Cloud | ✅ | [openapi.json](../packages/contracts/openapi.json) (47 operations), [schema.d.ts](../packages/contracts/src/schema.d.ts), 47 fixtures validated in pytest (74 passed); CI wiring is F4 |
| F6 | Working copy of the repo in the project folder; toolchain check (Python, uv, Node, pnpm, Docker, CUDA) | PC | ✅ | PC working copy and toolchain checked (worker 3); PyTorch 2.14.1+cu130 sees the RTX 3060 (compute 8.6) |

### D: Data

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| D1 | Download SECOM from UCI, record SHA-256 and licence | PC | ✅ | Byte-identical to the UCI archive; SHA-256 in [manifest.json](../data/manifest.json); CC BY 4.0, DOI 10.24432/C54305; committed with [ATTRIBUTION.md](../data/secom/ATTRIBUTION.md) (78ba1f3) |
| D2 | Download WM-811K (MIR Lab, Kaggle fallback), record SHA-256 and licence | PC | ✅ | MIR Lab returned HTTP 404, so the Kaggle mirror was used; LSWMD.pkl 2,095,505,977 bytes, SHA-256 in the manifest; mirror lists CC0-1.0 set by the uploader, recorded with that caveat; raw data not committed |
| D3 | EDA reports: counts, time range, missingness, constants, class balance, lot structure | Cloud + PC | 🟡 | WM-811K facts done ([wm811k_facts.md](../training/wafermap/reports/wm811k_facts.md)): 811,457 wafers, 46,293 lots (PLAN corrected from 46,393), 172,950 labelled. SECOM EDA with worker 2 |
| D4 | Validated loaders (pandera schemas) | Cloud | ⏳ | |
| D5 | Official-split lot-overlap check for WM-811K | PC | ✅ | Official split has 0 lots in both training (5,809 lots) and test (4,953 lots). Class mix differs: "none" is 67.6% of training, 93.3% of test; reported as a limitation |

### S: SECOM science

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| S1 | Chronological split and rolling-origin CV, with leakage test | Cloud | 🟡 | Worker 2: statistics toolkit done (bootstrap, metrics, BH, provenance); SECOM data delivered, pipeline running next |
| S2 | Training-only preprocessing (constants, missingness indicators) | Cloud | ⏳ | |
| S3 | Baselines: prevalence, logistic regression, random forest | Cloud | ⏳ | |
| S4 | LightGBM with class weights, Optuna tuning on validation | Cloud | ⏳ | |
| S5 | Platt calibration, reliability diagram, Brier, ECE | Cloud | ⏳ | |
| S6 | Test metrics with bootstrap CIs, paired comparison with baselines | Cloud | ⏳ | |
| S7 | Root cause: TreeSHAP, sensor groups, stability selection, permutation test, BH | Cloud | ⏳ | |
| S8 | FDC: PCA reference, T² and SPE limits, contributions, EWMA and CUSUM | Cloud | ⏳ | |
| S9 | Sensor health rules and missingness association tests | Cloud | ⏳ | |
| S10 | Artifacts and SECOM model card | Cloud | ⏳ | |

### W: Wafer maps

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| W1 | Preprocessing: label parsing, nearest-neighbour resize, one-hot | Cloud + PC | 🟡 | Conversion and preprocessing code written (f50e461); worker 3 |
| W2 | Official and lot-grouped splits | PC | 🟡 | Lot-grouped split written ([splits.json](../training/wafermap/reports/splits.json)); worker 3 |
| W3 | Residual CNN, focal loss, dihedral augmentations | Cloud | 🟡 | Residual CNN and training loop written (f50e461); worker 3 |
| W4 | Training on the RTX 3060 (3 seeds, MLflow) | PC | ⏳ | Final training location to be decided (D-003) |
| W5 | Evaluation: macro-F1, per-class, confusion matrix, CIs, temperature scaling | PC | ⏳ | |
| W6 | Embeddings and unknown-pattern score, leave-one-class-out test | PC | ⏳ | |
| W7 | Similar-wafer search, precision@10 | PC | ⏳ | |
| W8 | Lot excursion tests, stacked maps, join-count tests | Cloud + PC | ⏳ | |
| W9 | ONNX export with parity test | PC | ⏳ | |
| W10 | Demo bundle (derived subset with attribution) and wafer model card | PC | ⏳ | |

### K: Knowledge base

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| K1 | Curate open-access sources on wafer-pattern causes; verify every citation | Cloud | ⏳ | |
| K2 | One-time MinerU2.5-Pro conversion, chunking, full-text index | Cloud | ⏳ | Costs points; run once |
| K3 | Pattern-to-cause table with citations | Cloud | ⏳ | |

### A: API

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| A1 | FastAPI app, settings, structured logs, health and readiness, problem+json errors | Cloud | 🟡 | App factory, settings, structured logs, problem+json errors, health and readiness (37e271d); bundle loading at startup pending |
| A2 | Database schema and Alembic migrations | Cloud | ⏳ | |
| A3 | Idempotent seed from verified artifacts | Cloud | ⏳ | |
| A4 | Replay engine with wall-clock plant clock, WebSocket stream | Cloud | ⏳ | |
| A5 | Inference services: SECOM risk, SHAP, FDC, sensor health | Cloud | ⏳ | |
| A6 | Inference services: wafer CNN (ONNX), unknown score, pgvector search, lot stats | Cloud | ⏳ | |
| A7 | REST endpoints for every screen | Cloud | 🟡 | All 47 routes declared on the service interfaces (37e271d); services pending (A5, A6) |
| A8 | Sessions: "Try as engineer", admin login, roles, CSRF, rate limits | Cloud | ⏳ | |
| A9 | Work orders and audit log | Cloud | ⏳ | |

### L: AI layer

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| L1 | Token Factory client with capability profiles and catalog sync | Cloud | 🟡 | Worker 4: client core, capability profiles and request builder written (branch w4/ai) |
| L2 | Retries with jitter on 429, 502 and 503, response cache, usage records (no request limits, D-009) | Cloud | 🟡 | Worker 4: removing the limiters per D-009; keeps retries, cache and usage records |
| L3 | Model registry: role to model, admin API, validation | Cloud | 🟡 | Worker 4: registry written (branch w4/ai) |
| L4 | Investigator graph with read-only tools, checkpointer, SSE events | Cloud | ⏳ | |
| L5 | Report writer with strict schema | Cloud | ⏳ | |
| L6 | Verifier: number check, citation check, wording check, model check | Cloud | ⏳ | |
| L7 | Router: deterministic intents first | Cloud | ⏳ | |
| L8 | Engineer chat, grounded and scoped | Cloud | ⏳ | |
| L9 | Recorded fixtures for tests; one manual smoke script | Cloud | ⏳ | |
| L10 | Model evaluation harness per role, with cost estimate | Cloud | ⏳ | Costs points; run once |
| L11 | Recorded demo investigations | Cloud | ⏳ | Costs points; run once |

### U: Interface

| ID | Item | Where | Status | Evidence / notes |
|---|---|---|---|---|
| U1 | Next.js app, Tailwind, shadcn/ui, layout shell, navigation | Cloud | 🟡 | Worker 5 building the interface |
| U2 | Design tokens: typefaces, colour, type scale, motion; reviewed against the brief | Cloud | ⏳ | |
| U3 | 3D wafer: instanced dies from real maps, thin-film shader, step-and-scan reveal | Cloud | ⏳ | |
| U4 | Home page with measured results | Cloud | ⏳ | |
| U5 | Line screen | Cloud | ⏳ | |
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
| P1 | API and web Dockerfiles (non-root, healthchecks) | Cloud | ⏳ | |
| P2 | Standalone compose with optional Caddy profile | Cloud | ⏳ | |
| P3 | GitHub Release of artifacts with SHA-256, verified at build | Cloud + PC | ⏳ | |
| P4 | anaslabs services: Sablier group, Traefik routes, networks | Cloud + PC | ⏳ | Back up `compose.yaml` first |
| P5 | Hub entry in `apps.js` and `<noscript>`, Sablier restart | PC | ⏳ | |
| P6 | Live at `yield-guardian.anaslabs.com` | PC | ⏳ | |
| P7 | Security headers and CSP | Cloud | ⏳ | |

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
| 2026-10-14 08:00 | Decision D-009: no request limits anywhere in the product; plan and contracts updated |
| 2026-10-14 08:00 | F6, D1, D2, D5 done on the PC: SECOM and WM-811K downloaded with checksums, no lot overlap in the official split; SECOM merged to main |
| 2026-10-14 07:56 | F3 and F5 done: scaffold, API contracts (47 operations), TypeScript types and validated fixtures |
| 2026-10-14 07:20 | F1 and F2 done: plan and status written |
