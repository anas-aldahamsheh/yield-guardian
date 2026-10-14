# Fixtures: synthetic examples for development and tests only

Every value in these files is **made up** to exercise the interface. None of them is a SECOM or
WM-811K result, and none may be shown to users or quoted anywhere. Production code never imports
them (apps/web enforces this with an ESLint rule); they are for MSW mocks, component stories and
tests.

- One file per API operation, named after its `operationId` (for example `get_line_state.json`).
- Streams are arrays of events: `stream_investigation_events.json` (SSE), `chat.json` (SSE) and
  `line_socket.json` (WebSocket).
- Wafer maps are drawn shapes (rings, blobs, lines), not real maps.
- Knowledge sources are placeholders, not real citations.
- The only documented facts are the model profiles in `get_model_catalog.json`, taken from
  `docs/vendor/token-factory.md`.

The files are generated from the API's Pydantic models, so they always match the contract, and a
test validates each one:

```sh
cd services/api && uv run python ../../packages/contracts/scripts/make_fixtures.py
```
