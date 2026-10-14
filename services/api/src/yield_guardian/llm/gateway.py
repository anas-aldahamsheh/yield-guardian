"""One entry point for every model call: role chain, profile, cache, call, log.

For a role, the registry gives an ordered chain of models. For each usable entry the gateway

1. applies the entry's ``reasoning_effort`` and response mode to the request,
2. builds the body from the model's profile (refusing invalid combinations),
3. answers from the cache when the same body was answered before,
4. calls the endpoint (retries on a busy server live in the client; there are no request
   limits, by owner decision of 2026-10-14),
5. parses the answer, computes points from usage and pricing, validates structured output,
6. logs exactly one :class:`LlmCallRecord` for the attempt, whatever its outcome.

The next entry is tried only for failures specific to a model (refused by its profile,
unknown or unavailable model, invalid or empty answer). Account-wide failures
(authentication, a rate limit that outlived the retries, missing credits) stop the chain at
once, because another model on the same account would fail the same way.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Callable
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from yield_guardian.llm.cache import ResponseCache, cache_key
from yield_guardian.llm.calllog import CallStatus, LlmCallLog, LlmCallRecord
from yield_guardian.llm.client import TokenFactoryClient
from yield_guardian.llm.errors import (
    EmptyCompletionError,
    ErrorKind,
    InvalidStructuredOutputError,
    LlmError,
    NoModelAvailableError,
    ProfileViolationError,
    ResponseShapeError,
    StreamProtocolError,
    StreamReportedError,
    TokenFactoryHttpError,
    TransportError,
)
from yield_guardian.llm.messages import ChatRequest, ResponseFormat
from yield_guardian.llm.registry import (
    ModelRegistry,
    ResolvedChoice,
    ResponseMode,
    Role,
    role_name,
)
from yield_guardian.llm.request_builder import build_chat_request
from yield_guardian.llm.results import (
    ChatResult,
    ParsedCompletion,
    StreamAccumulator,
    StreamDelta,
    parse_chat_completion,
)
from yield_guardian.llm.structured import parse_structured, strict_json_schema
from yield_guardian.llm.usage import QuotaMonitor

_MODEL_SPECIFIC_HTTP = frozenset(
    {
        ErrorKind.UNKNOWN_MODEL,
        ErrorKind.NOT_FOUND,
        ErrorKind.UNPROCESSABLE,
        ErrorKind.BAD_REQUEST,
        ErrorKind.UNAVAILABLE,
        ErrorKind.SERVER_ERROR,
        ErrorKind.OTHER,
    }
)


def fallback_reason(exc: BaseException) -> str | None:
    """Why the next model of the chain may succeed, or None if the failure is account-wide."""
    if isinstance(exc, ProfileViolationError):
        return f"refused by its profile: {exc.detail}"
    if isinstance(exc, InvalidStructuredOutputError):
        return f"invalid structured output: {exc.detail}"
    if isinstance(exc, EmptyCompletionError):
        return f"empty answer (finish_reason={exc.finish_reason})"
    if isinstance(exc, TokenFactoryHttpError):
        return f"HTTP {exc.status} {exc.kind}" if exc.kind in _MODEL_SPECIFIC_HTTP else None
    if isinstance(
        exc, TransportError | ResponseShapeError | StreamProtocolError | StreamReportedError
    ):
        return str(exc)
    return None


@dataclass(frozen=True, slots=True)
class CallOptions:
    correlation_id: str | None = None
    """Investigation or chat id, recorded with each call."""
    use_cache: bool = True
    exclude_families: frozenset[str] = field(default_factory=frozenset)
    """Model families that must not serve this call (the verifier excludes the writer's)."""


@dataclass(frozen=True, slots=True)
class Structured[T: BaseModel]:
    value: T
    result: ChatResult


@dataclass(frozen=True, slots=True)
class _OutputSpec:
    name: str
    schema: dict[str, Any]


class LlmGateway:
    def __init__(
        self,
        *,
        client: TokenFactoryClient,
        registry: ModelRegistry,
        cache: ResponseCache,
        call_log: LlmCallLog,
        quota: QuotaMonitor,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.client = client
        self.registry = registry
        self.cache = cache
        self.call_log = call_log
        self.quota = quota
        self.clock = clock
        self.wall_clock = wall_clock
        client.add_header_observer(quota.observe_headers)

    @property
    def namespace(self) -> str:
        return self.client.base_url

    # -- public API ---------------------------------------------------------------------------

    async def complete(
        self, role: Role, request: ChatRequest, *, options: CallOptions | None = None
    ) -> ChatResult:
        """A free-text (or tool-calling) completion for ``role``."""
        result, _ = await self._run_chain(role, request, options or CallOptions(), None, _identity)
        return result

    async def complete_structured[T: BaseModel](
        self,
        role: Role,
        request: ChatRequest,
        output_type: type[T],
        *,
        schema_name: str,
        options: CallOptions | None = None,
    ) -> Structured[T]:
        """A JSON answer validated as ``output_type``: strict ``json_schema`` where the model
        supports it, ``json_object`` plus Pydantic validation otherwise."""
        if not any("json" in message.text().lower() for message in request.messages):
            raise ValueError("a structured request must mention JSON in its messages")
        spec = _OutputSpec(name=schema_name, schema=strict_json_schema(output_type))

        def parse(result: ChatResult) -> T:
            return parse_structured(result.content, output_type, model=result.model)

        result, value = await self._run_chain(role, request, options or CallOptions(), spec, parse)
        return Structured(value=value, result=result)

    async def stream(
        self, role: Role, request: ChatRequest, *, options: CallOptions | None = None
    ) -> AsyncGenerator[StreamDelta | ChatResult]:
        """Yield :class:`StreamDelta` items as they arrive, then one final :class:`ChatResult`.

        Fallback to the next model happens only before the first delta is yielded.
        """
        opts = options or CallOptions()
        resolution = self.registry.resolve(role, exclude_families=opts.exclude_families)
        failures: list[tuple[str, str]] = list(resolution.skipped)
        for resolved in resolution.usable:
            prepared = self._prepare(resolved, request, None)
            yielded = False
            try:
                async with aclosing(self._stream_attempt(role, resolved, prepared, opts)) as items:
                    async for item in items:
                        if isinstance(item, StreamDelta):
                            yielded = True
                        yield item
                return
            except LlmError as exc:
                reason = fallback_reason(exc)
                if yielded or reason is None:
                    raise
                failures.append((resolved.choice.model, reason))
        raise NoModelAvailableError(str(role), failures)

    # -- chain --------------------------------------------------------------------------------

    def _prepare(
        self, resolved: ResolvedChoice, request: ChatRequest, spec: _OutputSpec | None
    ) -> ChatRequest:
        if request.reasoning_effort is not None:
            raise ValueError("reasoning_effort is set per role by the registry, not by callers")
        update: dict[str, Any] = {"reasoning_effort": resolved.choice.reasoning_effort}
        if spec is not None:
            mode = resolved.choice.response_mode
            if mode is ResponseMode.JSON_SCHEMA:
                update["response_format"] = ResponseFormat.strict_schema(spec.name, spec.schema)
            elif mode is ResponseMode.JSON_OBJECT:
                update["response_format"] = ResponseFormat.json_object()
            else:
                raise ProfileViolationError(
                    resolved.profile.id, "response_mode", "structured output needs a JSON mode"
                )
        return request.model_copy(update=update)

    async def _run_chain[T](
        self,
        role: Role,
        request: ChatRequest,
        options: CallOptions,
        spec: _OutputSpec | None,
        parse: Callable[[ChatResult], T],
    ) -> tuple[ChatResult, T]:
        resolution = self.registry.resolve(role, exclude_families=options.exclude_families)
        failures: list[tuple[str, str]] = list(resolution.skipped)
        for resolved in resolution.usable:
            try:
                prepared = self._prepare(resolved, request, spec)
                return await self._attempt(role, resolved, prepared, options, parse)
            except LlmError as exc:
                reason = fallback_reason(exc)
                if reason is None:
                    raise
                failures.append((resolved.choice.model, reason))
        raise NoModelAvailableError(str(role), failures)

    # -- one attempt --------------------------------------------------------------------------

    async def _attempt[T](
        self,
        role: Role,
        resolved: ResolvedChoice,
        request: ChatRequest,
        options: CallOptions,
        parse: Callable[[ChatResult], T],
    ) -> tuple[ChatResult, T]:
        profile = resolved.profile
        log = _Logger(self, role, profile.id, options, stream=False)
        try:
            built = build_chat_request(profile, request)
        except ProfileViolationError as exc:
            await log.refused(CallStatus.REFUSED_PROFILE, exc.rule, str(exc))
            raise
        key = cache_key(built.body, namespace=self.namespace)
        if options.use_cache:
            hit = await self._from_cache(key, log, parse)
            if hit is not None:
                return hit
        try:
            reply = await self.client.chat_completion(built.body)
            parsed = parse_chat_completion(reply.payload)
        except TokenFactoryHttpError as exc:
            await log.http_error(exc, key=key)
            raise
        except (TransportError, ResponseShapeError) as exc:
            await log.error(type(exc).__name__, str(exc), key=key)
            raise
        result = self._result(
            resolved,
            parsed,
            key=key,
            latency_ms=reply.latency_ms,
            attempts=reply.attempts,
            adjustments=built.adjustments,
            headers=reply.headers,
        )
        return await self._finish(result, log, parse)

    async def _from_cache[T](
        self, key: str, log: _Logger, parse: Callable[[ChatResult], T]
    ) -> tuple[ChatResult, T] | None:
        cached = await self.cache.get(key)
        if cached is None:
            return None
        result = cached.model_copy(
            update={
                "cache_hit": True,
                "points": 0.0,
                "attempts": 0,
                "latency_ms": log.elapsed_ms(),
                "cache_key": key,
            }
        )
        try:
            value = parse(result)
        except InvalidStructuredOutputError:
            return None
        await log.done(result, CallStatus.OK)
        return result, value

    async def _finish[T](
        self, result: ChatResult, log: _Logger, parse: Callable[[ChatResult], T]
    ) -> tuple[ChatResult, T]:
        self.quota.record_spend(result.points)
        if result.is_empty:
            await log.done(result, CallStatus.EMPTY, error="empty answer")
            raise EmptyCompletionError(result.model, result.finish_reason)
        try:
            value = parse(result)
        except InvalidStructuredOutputError as exc:
            await log.done(result, CallStatus.INVALID_OUTPUT, error=exc.detail)
            raise
        if not result.truncated and result.cache_key is not None:
            await self.cache.put(result.cache_key, result)
        await log.done(result, CallStatus.OK)
        return result, value

    def _result(
        self,
        resolved: ResolvedChoice,
        parsed: ParsedCompletion,
        *,
        key: str,
        latency_ms: float,
        attempts: int,
        adjustments: tuple[str, ...],
        headers: dict[str, str],
    ) -> ChatResult:
        profile = resolved.profile
        points = profile.pricing.points(parsed.usage) if profile.pricing else None
        return ChatResult(
            model=profile.id,
            served_model=parsed.served_model,
            response_id=parsed.response_id,
            content=parsed.content,
            reasoning=parsed.reasoning,
            tool_calls=parsed.tool_calls,
            finish_reason=parsed.finish_reason,
            usage=parsed.usage,
            points=points,
            latency_ms=latency_ms,
            attempts=attempts,
            cache_key=key,
            adjustments=adjustments,
            rate_limit_headers={k: v for k, v in headers.items() if k.startswith("x-ratelimit-")},
        )

    async def _stream_attempt(
        self, role: Role, resolved: ResolvedChoice, request: ChatRequest, options: CallOptions
    ) -> AsyncGenerator[StreamDelta | ChatResult]:
        profile = resolved.profile
        log = _Logger(self, role, profile.id, options, stream=True)
        try:
            built = build_chat_request(profile, request, stream=True)
        except ProfileViolationError as exc:
            await log.refused(CallStatus.REFUSED_PROFILE, exc.rule, str(exc))
            raise
        key = cache_key(built.body, namespace=self.namespace)
        if options.use_cache:
            hit = await self._from_cache(key, log, _identity)
            if hit is not None:
                cached, _ = hit
                if cached.content:
                    yield StreamDelta(type="content", text=cached.content)
                yield cached
                return
        accumulator = StreamAccumulator()
        try:
            async with aclosing(self.client.stream_chat_completion(built.body)) as chunks:
                async for chunk in chunks:
                    for delta in accumulator.feed(chunk):
                        if delta.type in ("content", "reasoning", "tool_call"):
                            yield delta
            parsed = accumulator.result()
        except TokenFactoryHttpError as exc:
            await log.http_error(exc, key=key)
            raise
        except (
            TransportError,
            ResponseShapeError,
            StreamProtocolError,
            StreamReportedError,
        ) as exc:
            await log.error(type(exc).__name__, str(exc), key=key)
            raise
        result = self._result(
            resolved,
            parsed,
            key=key,
            latency_ms=log.elapsed_ms(),
            attempts=1,
            adjustments=built.adjustments,
            headers={},
        )
        result, _ = await self._finish(result, log, _identity)
        yield result


def _identity(result: ChatResult) -> ChatResult:
    return result


class _Logger:
    """Builds the one call record of an attempt."""

    def __init__(
        self, gateway: LlmGateway, role: Role, model: str, options: CallOptions, *, stream: bool
    ) -> None:
        self._gateway = gateway
        self._role = role
        self._model = model
        self._options = options
        self._stream = stream
        self._started_at = gateway.wall_clock()
        self._t0 = gateway.clock()

    def elapsed_ms(self) -> float:
        return (self._gateway.clock() - self._t0) * 1000.0

    async def _emit(self, **fields: Any) -> None:
        record = LlmCallRecord(
            started_at=self._started_at,
            role=role_name(self._role),
            model=self._model,
            stream=self._stream,
            correlation_id=self._options.correlation_id,
            **fields,
        )
        await self._gateway.call_log.record(record)

    async def refused(self, status: CallStatus, kind: str, message: str) -> None:
        await self._emit(
            status=status,
            cache_hit=False,
            tokens_in=0,
            tokens_out=0,
            tokens_reasoning=0,
            tokens_cached=0,
            points=0.0,
            latency_ms=self.elapsed_ms(),
            attempts=0,
            error_kind=kind,
            error_message=message[:500],
        )

    async def http_error(self, exc: TokenFactoryHttpError, *, key: str) -> None:
        await self._emit(
            status=CallStatus.ERROR,
            cache_hit=False,
            tokens_in=None,
            tokens_out=None,
            tokens_reasoning=None,
            tokens_cached=None,
            points=None,
            latency_ms=self.elapsed_ms(),
            attempts=exc.attempts,
            http_status=exc.status,
            error_kind=str(exc.kind),
            error_message=exc.error.message[:500],
            request_key=key,
        )

    async def error(self, kind: str, message: str, *, key: str) -> None:
        await self._emit(
            status=CallStatus.ERROR,
            cache_hit=False,
            tokens_in=None,
            tokens_out=None,
            tokens_reasoning=None,
            tokens_cached=None,
            points=None,
            latency_ms=self.elapsed_ms(),
            attempts=1,
            error_kind=kind,
            error_message=message[:500],
            request_key=key,
        )

    async def done(
        self, result: ChatResult, status: CallStatus, *, error: str | None = None
    ) -> None:
        usage = result.usage
        if result.cache_hit:
            tokens: dict[str, int | None] = {
                "tokens_in": 0,
                "tokens_out": 0,
                "tokens_reasoning": 0,
                "tokens_cached": 0,
            }
        else:
            tokens = {
                "tokens_in": usage.prompt_tokens if usage else None,
                "tokens_out": usage.completion_tokens if usage else None,
                "tokens_reasoning": usage.reasoning_tokens if usage else None,
                "tokens_cached": usage.cached_tokens if usage else None,
            }
        await self._emit(
            status=status,
            cache_hit=result.cache_hit,
            points=result.points,
            latency_ms=result.latency_ms,
            attempts=result.attempts,
            error_kind=None if error is None else str(status),
            error_message=None if error is None else error[:500],
            request_key=result.cache_key,
            **tokens,
        )
