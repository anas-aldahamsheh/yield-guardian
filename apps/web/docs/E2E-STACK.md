# End-to-end tests on the composed stack

`pnpm --filter @yield-guardian/web e2e:stack` runs `e2e/stack/` against the real stack: gateway, web, API and PostgreSQL, built from the committed artifact bundles. These tests use no mocks. Each test reads the IDs it needs (units, wafers, lots, work orders) from the API first, and checks the screens against the API's values. No model number is hard-coded.

The mock suite (`pnpm e2e`, fixture API) is separate and does not run these tests.

## What it covers

- The API is ready and both bundles are verified.
- Home: the results table has one row per `/results` entry. No measured row reads "Not measured yet".
- `/line`: the connection goes Live over the WebSocket, and unit events arrive after the snapshot.
- Pages with real data load: a unit, the wafer lab with a selected wafer, a lot, sensor health (including keyboard navigation) and every model card on `/methods`.
- A guest session starts from "Try as engineer".
- Work orders: the list and the audit log load. If the database has a work order, its page opens too.
- Without a language model key:
  - Chat and live investigations show their not-configured state.
  - No chat request and no investigation POST is sent.
  - Nothing calls Token Factory.
- At 375 px, no route scrolls sideways. The project is named `375`.

## Run it

1. Leave `TOKEN_FACTORY_API_KEY` unset, both in your shell and in `deploy/compose/.env`. The tests assert that `/meta` reports `chat: false` and `live_investigations: false`.
2. Start the stack:

   ```sh
   cp deploy/compose/.env.example deploy/compose/.env   # set POSTGRES_PASSWORD and SESSION_SECRET
   env -u TOKEN_FACTORY_API_KEY GIT_COMMIT=$(git rev-parse HEAD) \
     docker compose -f deploy/compose/compose.yaml up -d --build --wait
   ```

   If Docker Hub rate-limits the base images, use an override file kept outside the repository. In it, pass the build args `PYTHON_IMAGE` (to `migrate` and `api`) and `NODE_IMAGE` (to `web`), pointing at a mirror, for example `mirror.gcr.io/library/python:3.13-slim-trixie`.

3. Run the tests:

   ```sh
   pnpm --filter @yield-guardian/web e2e:stack
   ```

   The default base URL is `http://localhost:8080`. Set `E2E_BASE_URL` to test a different gateway. Chromium comes from `PW_CHROMIUM` or the preinstalled browser; nothing is downloaded.

Without Docker, run the same three parts by hand:

- PostgreSQL with pgvector.
- The API: `uv run uvicorn yield_guardian.main:app` with `DATABASE_URL` and `SESSION_SECRET` set.
- A production build of the web behind the gateway: `pnpm build`, then `tsx scripts/gateway.ts --mode start --port 8080 --api http://localhost:8000`.

Then point `E2E_BASE_URL` at the gateway.

The tests write to the database: the guest sessions, and the audit entries they leave. Run them against a test stack, not a demo database.
