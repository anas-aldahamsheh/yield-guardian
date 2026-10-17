"""Wire the language-model layer from settings.

Every store has an in-memory default for tests and single-process runs; the API passes its
database-backed implementations of the same protocols in production.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from yield_guardian.core.settings import Settings
from yield_guardian.llm.admin import (
    EvaluationStore,
    InMemoryEvaluationStore,
    InMemoryRouteLog,
    RouteLog,
    TokenFactoryAdmin,
)
from yield_guardian.llm.cache import InMemoryLruCache, ResponseCache
from yield_guardian.llm.calllog import InMemoryCallLog, LlmCallLog
from yield_guardian.llm.client import TokenFactoryClient
from yield_guardian.llm.gateway import LlmGateway
from yield_guardian.llm.profiles import ProfileCatalog, Provider
from yield_guardian.llm.registry import (
    InMemoryRoleAssignmentStore,
    ModelRegistry,
    RoleAssignmentStore,
)
from yield_guardian.llm.retry import RetryPolicy
from yield_guardian.llm.usage import QuotaMonitor

ANTHROPIC_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
ANTHROPIC_RETRY = RetryPolicy(max_retries=0)


@dataclass(frozen=True, slots=True)
class LlmStack:
    client: TokenFactoryClient
    catalog: ProfileCatalog
    registry: ModelRegistry
    quota: QuotaMonitor
    cache: ResponseCache
    call_log: LlmCallLog
    route_log: RouteLog
    evaluations: EvaluationStore
    gateway: LlmGateway
    admin: TokenFactoryAdmin
    anthropic_client: TokenFactoryClient | None = None
    """The Anthropic client, when ``ANTHROPIC_API_KEY`` is set."""

    async def aclose(self) -> None:
        await self.client.aclose()
        if self.anthropic_client is not None:
            await self.anthropic_client.aclose()


def key_configured(settings: Settings) -> bool:
    key = settings.token_factory_api_key
    return key is not None and bool(key.get_secret_value().strip())


def anthropic_key_configured(settings: Settings) -> bool:
    key = settings.anthropic_api_key
    return key is not None and bool(key.get_secret_value().strip())


def assemble_llm_stack(
    settings: Settings,
    *,
    http: httpx.AsyncClient | None = None,
    cache: ResponseCache | None = None,
    call_log: LlmCallLog | None = None,
    assignments: RoleAssignmentStore | None = None,
    route_log: RouteLog | None = None,
    evaluations: EvaluationStore | None = None,
) -> LlmStack:
    """Build the stack without any I/O (no call, no store read): for synchronous startup code.
    Call ``await stack.registry.load()`` before serving, to apply the stored role assignments."""
    has_key = key_configured(settings)
    client = TokenFactoryClient(
        api_key=settings.token_factory_api_key,
        base_url=settings.token_factory_base_url,
        http=http,
    )
    anthropic_client = (
        TokenFactoryClient(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            http=http,
            retry=ANTHROPIC_RETRY,
            timeout=ANTHROPIC_TIMEOUT,
        )
        if anthropic_key_configured(settings)
        else None
    )
    providers = [Provider.TOKEN_FACTORY]
    if anthropic_client is not None:
        providers.append(Provider.ANTHROPIC)
    extra_clients = {
        provider: client
        for provider, client in (
            (Provider.ANTHROPIC, anthropic_client),
        )
        if client is not None
    }
    catalog = ProfileCatalog()
    registry = ModelRegistry(
        catalog, assignments or InMemoryRoleAssignmentStore(), providers=providers
    )
    quota = QuotaMonitor(client.get_usage if has_key else None)
    stack_cache = cache or InMemoryLruCache()
    stack_log = call_log or InMemoryCallLog()
    stack_routes = route_log or InMemoryRouteLog()
    stack_evaluations = evaluations or InMemoryEvaluationStore()
    gateway = LlmGateway(
        client=client,
        registry=registry,
        cache=stack_cache,
        call_log=stack_log,
        quota=quota,
        providers=extra_clients or None,
    )
    admin = TokenFactoryAdmin(
        registry=registry,
        quota=quota,
        call_log=stack_log,
        route_log=stack_routes,
        evaluations=stack_evaluations,
        key_configured=has_key,
        list_models=client.list_models if has_key else None,
    )
    return LlmStack(
        client=client,
        catalog=catalog,
        registry=registry,
        quota=quota,
        cache=stack_cache,
        call_log=stack_log,
        route_log=stack_routes,
        evaluations=stack_evaluations,
        gateway=gateway,
        admin=admin,
        anthropic_client=anthropic_client,
    )


async def build_llm_stack(
    settings: Settings,
    *,
    http: httpx.AsyncClient | None = None,
    cache: ResponseCache | None = None,
    call_log: LlmCallLog | None = None,
    assignments: RoleAssignmentStore | None = None,
    route_log: RouteLog | None = None,
    evaluations: EvaluationStore | None = None,
    sync_catalog: bool = True,
) -> LlmStack:
    """Build the stack; with a key, read the live catalog once (``GET /v1/models``) so role
    validation knows which models are served, then load the stored role assignments."""
    stack = assemble_llm_stack(
        settings,
        http=http,
        cache=cache,
        call_log=call_log,
        assignments=assignments,
        route_log=route_log,
        evaluations=evaluations,
    )
    if sync_catalog:
        await stack.admin.sync_catalog()
    await stack.registry.load()
    return stack
