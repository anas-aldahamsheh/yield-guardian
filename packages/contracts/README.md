# @yield-guardian/contracts

The contract between the API and the web app.

| File | What it is |
|---|---|
| `openapi.json` | OpenAPI 3.1 schema exported from the API's Pydantic models (`services/api/src/yield_guardian/contracts/`). |
| `src/schema.d.ts` | TypeScript types generated from `openapi.json`. Never edit by hand. |
| `src/index.ts` | Re-exports every schema by name, plus constants and `decodeWaferCells`. |
| `ARTIFACTS.md` | Formats of the artifact bundles that training writes and the API reads. |
| `fixtures/` | Synthetic examples for development and tests only (see `fixtures/README.md`). |

## Regenerate

```sh
cd services/api && uv run python -m yield_guardian.api.openapi ../../packages/contracts/openapi.json
cd ../.. && pnpm contracts:generate
```

CI fails when either file is stale.

## Conventions

- Base path `/api/v1`. Errors are RFC 9457 `application/problem+json` (schema `Problem`, with a machine-readable `code`).
- **Investigator events:** `GET /api/v1/investigations/{id}/events` is a server-sent event stream. Each event has `event: <type>`, `id: <seq>` and `data: <InvestigationEvent JSON>`. Reconnect with `Last-Event-ID` to resume. The stream closes after an `end` event.
- **Chat:** `POST /api/v1/chat` answers with a server-sent event stream of `ChatEvent`.
- **Runs:** `POST /api/v1/runs` answers `201 RunCreated`; `GET /api/v1/runs/{id}/events` is a server-sent event stream of `RunEvent` (`event: <type>`, `id: <seq>`), resumable with `Last-Event-ID`, closed after `run_done`. `GET /api/v1/runs/{id}` carries `z` for the first 200 units; `GET /api/v1/runs/{id}/units/{index}/chart` has it for any unit. Runs and uploads need no session and expire after 24 hours (`410 gone`) unless an investigation uses the run.
- **Uploads:** `POST /api/v1/uploads` (multipart `file`, optional `kind`) answers `UploadSummary`; `GET /api/v1/uploads/templates/{kind}.{csv|xlsx}` and `/uploads/examples/{kind}.{csv|xlsx}` are files (the examples carry `X-Data-Attribution` and `Link: <doi>; rel="cite-as"`).
- **Sessions:** everything can be read without a session. Actions need the `yg_session` cookie (from `POST /api/v1/session/guest` or `/session/login`) and the session's `csrf_token` in the `X-CSRF-Token` header.
- **Wafer maps:** `WaferMap.cells` is base64 of `height x width` bytes, row-major, 0 = no die, 1 = pass, 2 = fail. Use `decodeWaferCells`.
- **Numbers:** every metric is an `Estimate` with its confidence interval. A null estimate means "not measured yet", never zero.
