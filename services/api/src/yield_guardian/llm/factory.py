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
from yield_guardian.llm.profiles import ProfileCatalog
from yield_guardian.llm.registry import (
    InMemoryRoleAssignmentStore,
    ModelRegistry,
    RoleAssignmentStore,
)
from yield_guardian.llm.usage import QuotaMonitor


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

    async def aclose(self) -> None:
        await self.client.aclose()


def key_configured(settings: Settings) -> bool:
    key = settings.token_factory_api_key
    return key is not None and bool(key.get_secret_value().strip())


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
    has_key = key_configured(settings)
    client = TokenFactoryClient(
        api_key=settings.token_factory_api_key,
        base_url=settings.token_factory_base_url,
        http=http,
    )
    catalog = ProfileCatalog()
    registry = ModelRegistry(catalog, assignments or InMemoryRoleAssignmentStore())
    quota = QuotaMonitor(client.get_usage if has_key else None)
    stack_cache = cache or InMemoryLruCache()
    stack_log = call_log or InMemoryCallLog()
    stack_routes = route_log or InMemoryRouteLog()
    stack_evaluations = evaluations or InMemoryEvaluationStore()
    gateway = LlmGateway(
        client=client, registry=registry, cache=stack_cache, call_log=stack_log, quota=quota
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
    if sync_catalog:
        await admin.sync_catalog()
    await registry.load()
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
    )
