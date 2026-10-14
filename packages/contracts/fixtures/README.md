# Fixtures for development and tests

These files let the interface and the tests run before the real API is ready. They are never part
of the product: production code cannot import them (ESLint rule in apps/web) and CI fails if the
built web app contains them. One file per API operation, named after its `operationId`; streams
are arrays of events (`stream_investigation_events.json`, `chat.json`, `line_socket.json`).

## What is real

Taken directly from SECOM (`data/secom/`, checksums in `data/manifest.json`):

- unit IDs, timestamps and final-test results (pass or fail) of all 1,567 units;
- sensor readings and missing values (unit detail, contributions, the S060 series);
- block sizes and failure counts (with the provisional 60/20/20 time split; worker 2 sets the real one);
- sensor health, computed from the real readings with the rules of PLAN 6.4 applied provisionally,
  including Fisher exact tests of missingness against failure with Benjamini-Hochberg q-values.

The model profiles in `get_model_catalog.json` come from `docs/vendor/token-factory.md`.

## What is a placeholder until the real results exist

Model outputs: risk, T² and SPE with their limits and alarms, SHAP values, sensor-group statistics,
operating points, metrics and calibration, and the investigation and chat texts that quote them;
language-model usage and evaluation numbers; wafer maps (drawn shapes) and wafer-model results;
knowledge sources (placeholders, not citations).

When the SECOM bundle (worker 2) and the wafer-map bundle (worker 3) exist, the fixtures are
regenerated from them and these placeholders disappear.

## Regenerate

```sh
cd services/api && uv run python ../../packages/contracts/scripts/make_fixtures.py
```

Each file is built from the API's Pydantic models and validated against its operation in
`services/api/tests/contracts/test_fixtures.py`.
