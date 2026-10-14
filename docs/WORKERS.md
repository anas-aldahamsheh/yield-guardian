# Workers and ownership

Yield Guardian is built by five workers in parallel. Each worker owns a set of directories and edits nothing else. Changes another worker needs go through the lead.

| Worker | Role | Owns | Status items |
|---|---|---|---|
| W1 (lead) | Contracts, API core, CI, packaging, integration, docs | `packages/contracts/`, `services/api/src/yield_guardian/{contracts,api,core,db,services}/`, `services/api/pyproject.toml`, `deploy/`, `.github/`, root files, `docs/PLAN.md`, `docs/STATUS.md`, `docs/WORKERS.md` | F, A (except A5 and A6 science), P, Q, X |
| W2 | SECOM science | `training/secom/`, `training/common/`, `docs/model-cards/secom.md` | D3 and D4 for SECOM, S1 to S10 |
| W3 | Wafer maps and the PC lane (runs on the owner's PC) | `training/wafermap/`, `data/`, `docs/model-cards/wafermap.md` | F6, D1, D2, D5, W1 to W10, later P4 to P6 |
| W4 | AI layer | `services/api/src/yield_guardian/{llm,agent,knowledge}/`, `services/api/tests/{llm,agent,knowledge}/`, `docs/knowledge/` | L1 to L11, K1 to K3 |
| W5 | Interface | `apps/web/` | U1 to U14 |

## Rules

1. **Contracts first.** API schemas live in `services/api/src/yield_guardian/contracts/` and are exported to `packages/contracts/` (OpenAPI and generated TypeScript types). Only the lead changes them; a worker who needs a change asks for it.
2. **Artifact contracts.** Trained models reach the API as versioned bundles under `artifacts/<name>/<version>/` with a `MANIFEST.json` of SHA-256 checksums. The formats are fixed in `packages/contracts/ARTIFACTS.md`.
3. **One branch per worker** (`w2/...`, `w3/...`, `w4/...`, `w5/...`). Only the lead merges into `main`, after the same checks CI runs.
4. **STATUS.md has one editor:** the lead.
5. **Token Factory quota is shared by the team** (1 point a day). Only W4 code calls it, never in tests, and live runs need the lead's go-ahead.
6. **Real data only** in anything a user or judge sees. Synthetic values are allowed only inside unit tests of statistical functions, and are labelled as such.
