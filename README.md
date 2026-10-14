# Yield Guardian

An investigation console for semiconductor yield engineers. It replays a real production line, scores every unit for failure risk, checks the sensors against multivariate control limits, reads wafer maps for defect patterns, and lets an AI investigator gather evidence and write a report in which every number is checked. An engineer decides what happens next.

Built for the AMD Developer Hackathon: ACT III, track Intelligent Industry.

- Live: <https://yield-guardian.anaslabs.com> (the first request after idle wakes the app, about 20 s)
- Plan: [docs/PLAN.md](docs/PLAN.md). Live status: [docs/STATUS.md](docs/STATUS.md)
- Model cards: [SECOM](docs/model-cards/secom.md), [wafer maps](docs/model-cards/wafermap.md)

## What it does

| Screen | What the engineer sees |
|---|---|
| Line | Units leaving the line in real time (a wall-clock replay of SECOM), failure risk, Hotelling T² and SPE charts with their limits, alarms written by code |
| Investigation | An AI investigator that calls read-only data tools, writes a report from that evidence only, and has every number, citation and causal word checked before the engineer approves or rejects it |
| Wafer lab | The defect pattern of a wafer map, an unknown-pattern score, and the most similar past wafers |
| Lots | Lots whose pattern counts are unusual, with stacked maps |
| Sensor health | Dead, stuck, jumping and drifting sensors, and missingness tests |
| Work orders and audit | What was approved, by whom, and what happened |
| Models | The model behind each AI role, switchable by the admin, with measured evaluation results and usage |
| Methods | Data sources with checksums, model cards, every measured result with its interval, and the limitations |
| Engineer chat | Questions about any unit, sensor, wafer or lot, answered from cited records; numbers not in the evidence are withheld, and it reads but never acts |

## Results

Every number below is measured on data the model never saw while it was fitted, with a 95% confidence interval. The full tables are in the model cards and in `training/*/reports/`.

### SECOM (1,567 units, 590 sensors, 104 failures)

Chronological split; the test block (313 units, 17 failures) was evaluated once, after every choice was fixed.

| Result | Value | 95% CI |
|---|---|---|
| Failure-risk PR-AUC, LightGBM | 0.075 (no-skill 0.054) | 0.048 to 0.181 |
| Failure-risk PR-AUC, logistic regression baseline | 0.172 | 0.098 to 0.380 |
| Recall at the 5% false-alarm threshold set on validation | 5.9% | 0.0% to 17.6% |
| False alarms per 100 units at that threshold | 1.92 | 0.64 to 3.51 |
| T² false-alarm rate on held-out in-control units, 99% limit | 1.9% | 0.2% to 6.6% |

**What this means.** On SECOM, the failure-risk model is not shown to be better than chance, and a simple logistic regression did better. We report that rather than tune until the test looks good. The product therefore leads with control charts and sensor health, and treats the risk score as an experimental signal. Sensor findings are statistical associations, not causes.

### WM-811K wafer maps (172,950 labelled maps, 9 classes)

| Result | Value | 95% CI |
|---|---|---|
| Macro-F1, lot-grouped split (no lot in two parts) | 0.900 (3 seeds, sd 0.006) | seed 0: 0.893 to 0.916 |
| Macro-F1, official split | 0.604 (3 seeds, sd 0.043) | seed 0: 0.605 to 0.634 |
| Hand-crafted feature baseline, lot-grouped split | 0.699 | |
| Similar-wafer precision@10 (macro) | 0.860 | 0.845 to 0.873 |
| Wafers classified automatically at precision ≥ 0.99 | 96.0% at precision 0.992 | 95.7% to 96.3% |
| Unknown-pattern AUROC, leave-one-class-out mean (Mahalanobis) | 0.922 | per class in `loco.json` |

The official split's test lots differ from its training lots, which is why it scores lower; both are reported. The planned unknown-pattern score (energy) was near chance (0.545), so the product uses the Mahalanobis distance on the embeddings; that choice was made using the same leave-one-class-out results, so 0.922 is not an independent estimate. The ONNX model served by the API matches PyTorch within 8e-6 on the logits.

## How AMD is used

All language-model roles run on AMD GPUs through **AMD Token Factory**, one model per role, switchable by the admin:

| Role | Default model |
|---|---|
| Investigator (plans, calls tools) | DeepSeek-V4.1-Flash |
| Report writer (strict JSON schema) | MiMo-V2.6-Flash |
| Verifier (a different family from the writer) | GLM-5.3-Flash |
| Engineer chat | Qwen3.8-Flash-Next |
| Router fallback | MiniCPM5-2B |

Language models never compute a statistic: numbers come from the plant data and the trained models, and the verifier rejects any number in a report that does not match its evidence. The API key stays on the server; the product exposes no general model proxy.

## Run it anywhere

Requirements: Docker Engine 24+ with Compose 2.24+, 4 GB of memory.

```sh
cp .env.example deploy/compose/.env
# set POSTGRES_PASSWORD and SESSION_SECRET (see the comments in the file)
docker compose -f deploy/compose/compose.yaml up -d --build --wait
```

Open <http://localhost:8080>. Details, HTTPS with a domain and every setting: [deploy/compose/README.md](deploy/compose/README.md). Without `TOKEN_FACTORY_API_KEY` everything except the AI investigator and chat works, and `/api/v1/ready` says what is missing.

The model bundles are in `artifacts/<name>/v1/`; every file is listed with its SHA-256 in `MANIFEST.json` and checked when the image builds and again when the API starts.

## Repository

| Path | What |
|---|---|
| `services/api` | FastAPI service: bundles, line replay, SECOM and wafer services, investigations, sessions, work orders |
| `apps/web` | Next.js interface |
| `packages/contracts` | OpenAPI contract and generated TypeScript types |
| `training/secom`, `training/wafermap` | Training and evaluation pipelines, reports and figures |
| `artifacts` | Versioned, verified model bundles |
| `deploy` | Dockerfiles, compose stack, artifact verification |

## Limitations

- SECOM is small (17 failures in the test block), anonymised and from 2008; every interval is wide, and its failure-risk model shows no demonstrated skill.
- No FDC reference period passed a stationarity test; the shortest candidate was used, as the stated rule says.
- WM-811K is from 2015 and labels about a fifth of its maps. Lot excursion flags on the demo subset still count wafers by the energy-based unknown flag used when the bundle was built.
- Findings are associations in historical data. Only an engineer's confirmed outcome may later be described as a cause.

## Data and licences

- Code: MIT.
- SECOM: McCann, M. and Johnston, A. (2008), UCI Machine Learning Repository, CC BY 4.0. Redistributed unmodified with [ATTRIBUTION.md](data/secom/ATTRIBUTION.md).
- WM-811K: Wu, M.-J., Jang, J.-S. R. and Chen, J.-L. (2015), Wafer map failure pattern recognition and similarity ranking for large-scale data sets, IEEE Transactions on Semiconductor Manufacturing 28(1), 1–12. The demo subset carries its own [ATTRIBUTION.md](artifacts/wafermap/v1/demo/ATTRIBUTION.md); the raw dataset is never committed.
