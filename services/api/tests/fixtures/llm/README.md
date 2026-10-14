# Language-model test fixtures

Every file in this folder is a **hand-authored** cassette (`"hand_authored": true` in its
`meta`). None was recorded from AMD Token Factory: the team has no key in the build
environment and shares a 1-point daily quota, so tests make zero live calls.

Each cassette follows the response shapes documented in `docs/vendor/token-factory.md`
(the team's summary of the Token Factory documentation), and the OpenAI shapes that page says
the endpoint is compatible with. Every value in them (ids, token counts, texts, tool
arguments) is written for the tests; none is plant data, a model's real output or a measured
cost.

## Format

```json
{
  "meta": {"hand_authored": true, "description": "...", "source": "..."},
  "interactions": [
    {
      "request": {"method": "POST", "path": "/chat/completions", "match": {"model": "..."}},
      "response": {"status": 200, "headers": {}, "json_body": {}}
    }
  ]
}
```

A response has one body: `json_body`, `text` or `sse` (the `data:` payloads of a stream, in
order, `[DONE]` included). `chunk_size` serves the body in pieces of that many bytes, so the
stream parser meets lines and UTF-8 characters split across reads. `match` pins top-level
request body fields; a request that differs fails the test.
`yield_guardian.llm.cassette.CassettePlayer` serves the interactions in order through respx.

## Files

| File | What it covers |
|---|---|
| `chat_text_deepseek.json` | Plain completion, usage with a zero reasoning breakdown, `X-RateLimit-*` headers |
| `chat_reasoning_glm.json` | `message.reasoning`, `completion_tokens_details.reasoning_tokens`, cached prompt tokens |
| `chat_tool_calls_deepseek.json` | Two parallel tool calls, `finish_reason: tool_calls` |
| `chat_qwen27b_no_reasoning_count.json` | Usage without a reasoning count (documented for Qwen3.8-27B) |
| `chat_length_empty.json` | Thinking used up `max_tokens`: empty content, `finish_reason: length` |
| `stream_text_qwen.json` | Stream with reasoning and content deltas, usage chunk, `[DONE]`, 7-byte pieces |
| `stream_no_usage.json` | Stream without usage (the gateway drops `stream_options`) |
| `stream_tool_calls.json` | Streamed tool call with fragmented arguments |
| `error_429_retry_after.json` | 429 with `Retry-After` (gateway shape), then success |
| `error_shapes.json` | 400 unknown model, 400 credits (platform shape), 401, 403 `account_not_verified`, 422 (platform shape), 503 |
| `catalog_and_usage.json` | `GET /v1/models` and `GET /v1/usage?include_recent=true` |
| `ocr_mineru.json` | `POST /v1/ocr` with `pages[].markdown` and `usage_info.pages_processed` |
| `structured_fallback.json` | MiMo answers prose, the gateway falls back to Qwen3.8-27B with `json_object` |
| `investigation_*.json` | Investigator, writer and verifier answers for the graph tests (see `tests/agent`) |

## What is documented and what is assumed

Documented, and copied as such: the endpoint paths, status codes and their meanings, both
error body shapes, the `Requested model <name> not supported` message, the
`account_not_verified` code, `message.reasoning`, `usage.completion_tokens_details.reasoning_tokens`
(absent for Qwen3.8-27B), empty content with `finish_reason: length`, `data: [DONE]`,
`Retry-After` on 429, and the OCR request and response fields.

Assumed, because the documentation does not give them, and handled tolerantly in code:

- the names of the `X-RateLimit-*` headers (here the common OpenAI names); the code records
  every header with that prefix verbatim and interprets them only for display;
- the field names of `GET /v1/usage` (here `quota`, `used`, `remaining`, `reset_at`,
  `rpm_limit`, `recent`); the parser looks for several usual names and keeps the raw payload;
- any `GET /v1/models` field other than `id` (here `context_length`);
- `usage.prompt_tokens_details.cached_tokens` for cache reads (OpenAI's name);
- the wording of error messages other than the documented one.

The smoke script `services/api/scripts/smoke_token_factory.py` prints the real header names
and usage fields the first time it runs with a key, so these assumptions can be checked.

## Recording

`YG_LLM_CASSETTE_MODE=record` together with `TOKEN_FACTORY_API_KEY` switches
`yield_guardian.llm.cassette` to record mode: a `RecordingTransport` sends real requests and
saves each exchange with the `Authorization` header removed, and sets `hand_authored` to
false with the recording time. Without both variables, record mode refuses to start. It
spends the shared quota, so it runs only with the lead's go-ahead and never in CI.
