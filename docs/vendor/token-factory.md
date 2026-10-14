# AMD Token Factory: facts the code relies on

Summary of the Token Factory documentation as provided to the team for the event (2026-10-14). The live catalog changes, so the code reads `GET /v1/models` at runtime and treats this page as the starting profile.

## Endpoint

- Base URL: `https://developer.amd.com.cn/radeon/api/v1` (every path also works under `/api/v1/...`).
- Auth: `Authorization: Bearer rc-<48 hex>`. One key per team, shared by every member.
- OpenAI-compatible `POST /v1/chat/completions` (main endpoint). Also `POST /v1/messages` (Anthropic shape), `POST /v1/messages/count_tokens` (estimate only), `GET /v1/models` (catalog with pricing, context length and capability flags), `POST /v1/ocr` (MinerU2.5-Pro).
- Not served (404): legacy completions, embeddings, images, audio, rerank, `/v1/responses`.
- Usage: `GET /v1/usage?include_recent=true` returns quota, used, remaining, reset time, RPM limit and recent requests. Every response carries `X-RateLimit-*` headers.

## Chat completion parameters

- Accepted: `model, messages, stream, temperature, top_p, max_tokens, presence_penalty, frequency_penalty, response_format, tools, tool_choice, parallel_tool_calls, reasoning_effort` (or `reasoning.effort`).
- Silently dropped: `stop, seed, logit_bias, logprobs, top_logprobs, top_k, min_p, repetition_penalty`. Anything else not in the accepted list is dropped too.
- Rejected with 400: `thinking: {...}` and `reasoning.enabled`.
- Timeout: 10 minutes non-streaming; when streaming, 10 minutes is the maximum gap between chunks. Streams end with `data: [DONE]`.
- Thinking text is returned in `choices[0].message.reasoning`; its token count in `usage.completion_tokens_details.reasoning_tokens` (not for Qwen3.8-27B). Thinking tokens count toward `max_tokens`: a low limit can leave `content` empty with `finish_reason: length`.
- Every chat model supports streaming, tools, `tool_choice` and `response_format: {"type":"json_object"}`. Only MiMo-V2.6-Flash accepts strict `json_schema`. **Measured live on 2026-10-14:** MiMo-V2.6-Flash answers HTTP 400 `"Model MiMo-V2.6-Flash does not support JSON schema output mode"`, so in practice no model is known to accept it. Yield Guardian sends `json_object` everywhere and validates the answer in code.
- Images: content part `{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}` works on DeepSeek-V4.1-Flash, DeepSeek-V4-Flash-Vision-Exp, MiMo-V2.6-Flash, Qwen3.8-Flash-Next and Qwen3.8-27B. GLM-5.3-Flash rejects images.

## Models (as documented; points per 1M tokens, input / output / cache read)

| Model | Type | Context | Input | Thinks by default | reasoning_effort accepted | System message rule | Points |
|---|---|---|---|---|---|---|---|
| DeepSeek-V4-Flash | LLM | 1,048,576 | text | no | none, minimal, low, medium, high, xhigh, max | any position, several allowed; system or developer | 0.14 / 0.28 / 0.0028 |
| DeepSeek-V4.1-Flash | VLM | 1,048,576 | text, image | no | as above | as above | 0.14 / 0.28 / 0.0028 |
| DeepSeek-V4-Flash-Vision-Exp | VLM | 1,048,576 | text, image | no | as above | as above | 0.14 / 0.28 / 0.0028 |
| MiMo-V2.6-Flash | VLM | 1,048,576 | text, image, audio | yes | none (turns it off) and the usual tiers | any position; developer accepted | 0.14 / 0.28 / 0.0028 |
| GLM-5.3-Flash | LLM | 262,144 | text | yes | low, medium, high (xhigh returns 422) | any position; system only (developer returns 422) | 0.15 / 0.50 / 0.03 |
| Qwen3.8-Flash-Next | VLM | 262,144 | text, image | yes (xhigh) | none, low, medium, xhigh | exactly one, first; system only | 0.15 / 0.47 / 0.016 |
| Qwen3.8-27B | VLM | 131,072 | text, image | yes (xhigh) | low, medium, xhigh (high returns 400) | at most one, first | 0.50 / 3.00 / 0.05 |
| MiniCPM5-2B | LLM | 131,072 | text | no thinking | not applicable | any position; system | 0.124 / 0.7425 / 0.124 |
| Gemma-4-31B-IT | VLM | 262,144 | text, image | no | on or off only | system as the first message | 0.50 / 3.00 / 0.05 |
| MinerU2.5-Pro | Document OCR | n/a | PDF or image | n/a | n/a | n/a | "Limited free", billed per page |

The event dashboard also lists MiniCPM-V-4.7-1B and MiniCPM-V-4.7-35B-A3B, which this table does not document; treat them as available only if `GET /v1/models` reports them.

A request shape that works on every chat model: one system message at index 0, `reasoning_effort` of `low` or `medium` (or omitted), text-only content unless the model takes images, `max_tokens` sized to the context window.

## OCR

`POST /v1/ocr` with `{"model":"MinerU2.5-Pro","document":{"type":"document_url","document_url":"https://..."},"pages":"0-2"}` returns `pages[].markdown` and `usage_info.pages_processed`. It does not stream; use a long client timeout.

## Limits (shared endpoints)

| Limit | Scope | Typical value |
|---|---|---|
| Requests per minute | per API key (platform) | 30 |
| Requests per minute | per account (gateway, 60 s sliding window) | 20 (the team dashboard shows 20) |
| Requests per minute | per IP | 120 |
| Concurrent requests | per API key | 8 |
| Spend cap | per account, rolling daily | read from `/v1/usage` (team dashboard: 1 point per day, reset 19:00 Asia/Shanghai) |

A limited request returns 429 with `Retry-After` (60 s for per-minute limits, 1 s for concurrency). Retry only 429s (and 502/503), with exponential backoff and jitter.

## Errors

| Status | Meaning |
|---|---|
| 400 | Bad parameter, unknown model ("Requested model <name> not supported"), or not enough credits |
| 401 | Missing or invalid key |
| 403 | Account in review (`account_not_verified`) |
| 404 | Path not served |
| 422 | Value rejected while parsing (for example `xhigh` on GLM-5.3-Flash) |
| 429 | Rate limited; honour `Retry-After` |
| 502 / 503 | Gateway unreachable or saturated; retry with backoff |

Gateway errors use the OpenAI shape `{"error":{...}}`; platform errors are wrapped as `{"detail":{"error":{...}}}`. Check both.

## Terms that shape the design

- Trial and development only, no SLA; models can change or be withdrawn with little notice. The product therefore keeps recorded runs and a fallback chain, and a production deployment points the same client at a dedicated endpoint.
- No proxying, reselling or re-badging, and models must not be told to misreport which model they are. The product never exposes a general model endpoint.
- Do not send sensitive personal, health or financial data. Prompts and outputs are kept about 2 days.
