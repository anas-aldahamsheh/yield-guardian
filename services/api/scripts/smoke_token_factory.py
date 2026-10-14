"""One live call to AMD Token Factory, to check the client against the real endpoint.

It spends points from the team's shared daily quota, so it never runs in CI, needs the key in
``TOKEN_FACTORY_API_KEY`` and asks for ``--yes``. It sends one chat completion with
``max_tokens`` 64 and prints the token counts, the points computed from the documented
pricing, and every ``X-RateLimit-*`` header the server sent, so the header names and usage
fields the code assumes (see ``tests/fixtures/llm/README.md``) can be checked.

Usage (from ``services/api``)::

    TOKEN_FACTORY_API_KEY=... uv run python scripts/smoke_token_factory.py --yes
    TOKEN_FACTORY_API_KEY=... uv run python scripts/smoke_token_factory.py --yes --with-usage

``--response-format json_object`` asks for a JSON object; ``--response-format writer-schema``
sends the writer's strict ``json_schema`` (the investigation report), to check whether a model
accepts it. With 64 tokens the answer is cut short; only the HTTP status matters then::

    uv run python scripts/smoke_token_factory.py --yes --model MiMo-V2.6-Flash \
        --effort none --response-format writer-schema

``--with-usage`` also reads ``GET /v1/usage?include_recent=true`` and ``--with-models`` reads
``GET /v1/models``; neither is a chat completion.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any, cast

from yield_guardian.contracts.investigation import Report
from yield_guardian.core.settings import Settings
from yield_guardian.llm.client import TokenFactoryClient
from yield_guardian.llm.errors import LlmError, TokenFactoryHttpError
from yield_guardian.llm.messages import (
    ALL_REASONING_EFFORTS,
    ChatMessage,
    ChatRequest,
    ReasoningEffort,
    ResponseFormat,
)
from yield_guardian.llm.profiles import DOCUMENTED_PROFILES
from yield_guardian.llm.request_builder import build_chat_request
from yield_guardian.llm.results import parse_chat_completion
from yield_guardian.llm.structured import strict_json_schema
from yield_guardian.llm.usage import parse_usage_snapshot

MAX_TOKENS = 64
PROMPT = "Reply with the single word: ready."
JSON_PROMPT = 'Reply with a JSON object: {"summary": "ready"}.'
WRITER_SCHEMA_NAME = "investigation_report"  # as the writer sends it
RESPONSE_FORMATS = ("none", "json_object", "writer-schema")
DEFAULT_MODEL = "DeepSeek-V4-Flash"  # the lowest documented price, and no thinking at "none"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--yes", action="store_true", help="confirm spending shared quota")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(DOCUMENTED_PROFILES))
    parser.add_argument(
        "--effort",
        default="none",
        choices=[*sorted(ALL_REASONING_EFFORTS), "omit"],
        help="reasoning_effort for the call ('omit' leaves it out)",
    )
    parser.add_argument(
        "--response-format",
        default="none",
        choices=RESPONSE_FORMATS,
        help="'writer-schema' sends the report writer's strict json_schema",
    )
    parser.add_argument("--with-usage", action="store_true", help="also read GET /v1/usage")
    parser.add_argument("--with-models", action="store_true", help="also read GET /v1/models")
    return parser.parse_args(argv)


def fail(message: str) -> int:
    print(f"smoke: {message}", file=sys.stderr)
    return 2


def show_headers(headers: dict[str, str]) -> None:
    rate = {k: v for k, v in sorted(headers.items()) if k.startswith("x-ratelimit-")}
    print("X-RateLimit headers:" if rate else "X-RateLimit headers: none sent")
    for name, value in rate.items():
        print(f"  {name}: {value}")
    if "retry-after" in headers:
        print(f"  retry-after: {headers['retry-after']}")


async def run(args: argparse.Namespace, settings: Settings) -> int:
    profile = DOCUMENTED_PROFILES[args.model]
    if not profile.is_chat:
        return fail(f"{args.model} is not a chat model")
    effort = None if args.effort == "omit" else cast(ReasoningEffort, args.effort)
    request = smoke_request(args.response_format, effort)
    built = build_chat_request(profile, request)  # refuses a combination the model rejects
    pricing = profile.pricing
    if pricing is not None:
        # No ASCII text has more tokens than characters, so the whole body (prompt and any
        # schema the server injects) bounds the input; the reply is capped at 64.
        size = len(json.dumps(built.body))
        bound = (size * pricing.input_per_mtok + MAX_TOKENS * pricing.output_per_mtok) / 1e6
        print(f"Upper bound for this call: {bound:.7f} points")
    print(f"Request body: {json.dumps(built.body, ensure_ascii=False)}")
    async with TokenFactoryClient(
        api_key=settings.token_factory_api_key, base_url=settings.token_factory_base_url
    ) as client:
        try:
            reply = await client.chat_completion(built.body)
        except LlmError as exc:
            if isinstance(exc, TokenFactoryHttpError) and exc.body:
                print(f"Error body: {exc.body}")
            return fail(f"call failed: {exc}")
        parsed = parse_chat_completion(reply.payload)
        print(f"HTTP {reply.status} in {reply.latency_ms:.0f} ms, {reply.attempts} attempt(s)")
        print(f"Served model: {parsed.served_model}; finish_reason: {parsed.finish_reason}")
        print(f"Content: {parsed.content!r}")
        print(f"Reasoning text returned: {'yes' if parsed.reasoning else 'no'}")
        usage = parsed.usage
        if usage is None:
            print("Usage: not reported")
        else:
            print(
                f"Tokens: prompt {usage.prompt_tokens}, completion {usage.completion_tokens}, "
                f"reasoning {usage.reasoning_tokens}, cached {usage.cached_tokens}"
            )
        points = pricing.points(usage) if pricing else None
        print(f"Points (documented pricing): {points if points is not None else 'unknown'}")
        print(f"Raw usage object: {json.dumps(_get(reply.payload, 'usage'))}")
        show_headers(reply.headers)
        if args.with_usage:
            payload = await client.get_usage()
            snapshot = parse_usage_snapshot(payload)
            print("GET /v1/usage payload:")
            print(json.dumps(payload, indent=2, ensure_ascii=False)[:4000])
            print(
                f"Parsed: quota {snapshot.quota}, used {snapshot.used}, remaining "
                f"{snapshot.remaining}, reset_at {snapshot.reset_at}, rpm {snapshot.rpm_limit}"
            )
        if args.with_models:
            entries = await client.list_models()
            print(f"GET /v1/models: {len(entries)} models")
            for entry in entries:
                print(
                    f"  {entry.id} (context {entry.context_length}) raw keys: {sorted(entry.raw)}"
                )
    return 0


def smoke_request(response_format: str, effort: ReasoningEffort | None) -> ChatRequest:
    if response_format == "none":
        fmt = None
    elif response_format == "json_object":
        fmt = ResponseFormat.json_object()
    else:
        fmt = ResponseFormat.strict_schema(WRITER_SCHEMA_NAME, strict_json_schema(Report))
    prompt = PROMPT if fmt is None else JSON_PROMPT
    return ChatRequest(
        messages=(ChatMessage.user(prompt),),
        max_tokens=MAX_TOKENS,
        reasoning_effort=effort,
        response_format=fmt,
    )


def _get(payload: object, key: str) -> Any:
    return payload.get(key) if isinstance(payload, dict) else None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if os.environ.get("CI"):
        return fail("refusing to run in CI: this script spends the team's shared quota")
    if not args.yes:
        return fail("this spends points from the shared daily quota; pass --yes to confirm")
    settings = Settings()
    key = settings.token_factory_api_key
    if key is None or not key.get_secret_value().strip():
        return fail("TOKEN_FACTORY_API_KEY is not set")
    return asyncio.run(run(args, settings))


if __name__ == "__main__":
    raise SystemExit(main())
