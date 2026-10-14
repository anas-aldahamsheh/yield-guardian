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
- **Live line:** WebSocket `/ws/line` sends `LineEvent` JSON text frames, `hello` first.
- **Sessions:** everything can be read without a session. Actions need the `yg_session` cookie (from `POST /api/v1/session/guest` or `/session/login`) and the session's `csrf_token` in the `X-CSRF-Token` header.
- **Plant clock:** units after `PlantClock.position` have not come off the line yet and are never returned.
- **Wafer maps:** `WaferMap.cells` is base64 of `height x width` bytes, row-major, 0 = no die, 1 = pass, 2 = fail. Use `decodeWaferCells`.
- **Numbers:** every metric is an `Estimate` with its confidence interval. A null estimate means "not measured yet", never zero.
