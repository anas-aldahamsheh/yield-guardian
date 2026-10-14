"""PostgreSQL stores of the language-model layer and the knowledge search (migration 0002).

Each test reads back through a new store object (or a new engine), as after a restart. Records
and answers here are made up for the tests; no request reaches Token Factory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import respx
from pydantic import SecretStr

from tests.db.conftest import clean
from tests.llm.helpers import PLACEHOLDER_KEY
from yield_guardian.agent.wiring import (
    AgentResource,
    KnowledgeResource,
    install_agent,
)
from yield_guardian.bootstrap import build_registry
from yield_guardian.contracts.base import Estimate
from yield_guardian.contracts.models import EvaluationResult
from yield_guardian.core.settings import Settings
from yield_guardian.db.engine import Database
from yield_guardian.knowledge.postgres import METHOD, PostgresFullTextIndex
from yield_guardian.knowledge.service import LiteratureKnowledge, load_pattern_causes
from yield_guardian.llm.calllog import CallStatus, LlmCallRecord
from yield_guardian.llm.dbstores import (
    DbCallLog,
    DbEvaluationStore,
    DbResponseCache,
    DbRoleAssignmentStore,
    DbRouteLog,
)
from yield_guardian.llm.profiles import ProfileCatalog, Usage
from yield_guardian.llm.registry import ModelChoice, ModelRegistry, ResponseMode, Role
from yield_guardian.llm.results import ChatResult
from yield_guardian.services.jobs import JobWorker
from yield_guardian.services.registry import ServiceRegistry

KNOWLEDGE_DIR = Path(__file__).resolve().parents[4] / "docs" / "knowledge"
T0 = datetime(2026, 10, 14, 8, 0, tzinfo=UTC)
BROKEN_URL = "postgresql+asyncpg://nobody:wrong@127.0.0.1:1/none"


@pytest.fixture
async def database(database_url: str) -> AsyncIterator[Database]:
    await clean(database_url)
    db = Database(database_url, migrate_on_start=False)
    try:
        yield db
    finally:
        await db.stop()


def fresh(database_url: str) -> Database:
    """A second engine, as a restarted process would open."""
    return Database(database_url, migrate_on_start=False)


def call(minutes: int, *, tokens: int | None = 100, correlation: str = "inv_a") -> LlmCallRecord:
    return LlmCallRecord(
        started_at=T0 + timedelta(minutes=minutes),
        role="investigator",
        model="DeepSeek-V4.1-Flash",
        status=CallStatus.OK,
        cache_hit=False,
        stream=False,
        tokens_in=tokens,
        tokens_out=None if tokens is None else 20,
        tokens_reasoning=None,
        tokens_cached=None,
        points=None if tokens is None else 0.0001,
        latency_ms=812.5,
        attempts=1,
        correlation_id=correlation,
    )


# -- call log -----------------------------------------------------------------------------------


async def test_call_records_survive_a_restart_with_unknown_usage_kept_null(
    database: Database, database_url: str
) -> None:
    await DbCallLog(database.sessionmaker).record(call(1))
    await DbCallLog(database.sessionmaker).record(call(5, tokens=None))
    restarted = fresh(database_url)
    try:
        records = await DbCallLog(restarted.sessionmaker).since(T0)
        later = await DbCallLog(restarted.sessionmaker).since(T0 + timedelta(minutes=2))
    finally:
        await restarted.stop()
    assert records == [call(1), call(5, tokens=None)]
    assert later == [call(5, tokens=None)]
    assert records[1].tokens_in is None
    assert not records[1].usage_known


async def test_a_call_record_waits_in_memory_while_the_database_is_down(
    database: Database,
) -> None:
    broken = Database(BROKEN_URL, migrate_on_start=False)
    log = DbCallLog(broken.sessionmaker)
    try:
        await log.record(call(1))  # the database is unreachable: kept, not raised
    finally:
        await broken.stop()
    assert log.pending == [call(1)]
    log._sessions = database.sessionmaker  # the database is back
    await log.record(call(2))
    assert log.pending == []
    assert await DbCallLog(database.sessionmaker).since(T0) == [call(1), call(2)]


# -- response cache -----------------------------------------------------------------------------


def answer() -> ChatResult:
    return ChatResult(
        model="Qwen3.8-Flash-Next",
        served_model="Qwen3.8-Flash-Next",
        content="a scripted answer",
        finish_reason="stop",
        usage=Usage(prompt_tokens=50, completion_tokens=7),
        points=0.00002,
        latency_ms=300.0,
        cache_key="k1",
        adjustments=("reasoning_effort none",),
    )


async def test_cached_answers_survive_a_restart(database: Database, database_url: str) -> None:
    cache = DbResponseCache(database.sessionmaker, wall_clock=lambda: T0)
    assert await cache.get("k1") is None
    await cache.put("k1", answer())
    await cache.put("k1", answer())  # the same key again replaces, never fails
    restarted = fresh(database_url)
    try:
        again = DbResponseCache(restarted.sessionmaker)
        assert await again.get("k1") == answer()
        assert await again.get("k1") == answer()
        assert await again.get("other") is None
    finally:
        await restarted.stop()


async def test_a_cache_on_a_broken_database_misses_and_skips_writes() -> None:
    broken = Database(BROKEN_URL, migrate_on_start=False)
    try:
        cache = DbResponseCache(broken.sessionmaker)
        await cache.put("k1", answer())
        assert await cache.get("k1") is None
    finally:
        await broken.stop()


# -- role assignments ---------------------------------------------------------------------------


async def test_role_choices_survive_a_restart(database: Database, database_url: str) -> None:
    chain = (ModelChoice(model="DeepSeek-V4-Flash", reasoning_effort="none", response_mode=ResponseMode.JSON_OBJECT),)  # fmt: skip
    registry = ModelRegistry(
        ProfileCatalog(), DbRoleAssignmentStore(database.sessionmaker), wall_clock=lambda: T0
    )
    await registry.load()
    await registry.assign(Role.ROUTER, chain, actor="Administrator")
    restarted = fresh(database_url)
    try:
        again = ModelRegistry(ProfileCatalog(), DbRoleAssignmentStore(restarted.sessionmaker))
        assert await again.load() == []
    finally:
        await restarted.stop()
    saved = again.assignment(Role.ROUTER)
    assert saved.chain == chain
    assert (saved.updated_at, saved.updated_by) == (T0, "Administrator")
    assert again.assignment(Role.CHAT) == registry.assignment(Role.CHAT)  # still the default


# -- chat routes and evaluations ----------------------------------------------------------------


async def test_route_counts_survive_a_restart(database: Database, database_url: str) -> None:
    routes = DbRouteLog(database.sessionmaker)
    await routes.record("deterministic", "unit_risk", T0)
    await routes.record("model", "general", T0 + timedelta(minutes=1))
    await routes.record("deterministic", "sensor_health", T0 + timedelta(minutes=2))
    restarted = fresh(database_url)
    try:
        again = DbRouteLog(restarted.sessionmaker)
        assert await again.counts(T0) == (2, 1)
        assert await again.counts(T0 + timedelta(minutes=1, seconds=30)) == (1, 0)
    finally:
        await restarted.stop()


async def test_evaluations_survive_a_restart(database: Database, database_url: str) -> None:
    result = EvaluationResult(
        role="router",
        model_id="MiniCPM5-2B",
        task_set="router-intents-v1",
        tasks=28,
        success_rate=Estimate(
            value=0.75,
            ci_low=0.57,
            ci_high=0.87,
            n=28,
            method="Wilson score interval",
            note="test value",
        ),
        violations=1,
        latency_ms_p50=420.0,
        tokens_in=9000,
        tokens_out=300,
        points=0.001,
        run_at=T0,
    )
    await DbEvaluationStore(database.sessionmaker).save(result)
    restarted = fresh(database_url)
    try:
        assert list(await DbEvaluationStore(restarted.sessionmaker).all()) == [result]
    finally:
        await restarted.stop()


# -- knowledge search ---------------------------------------------------------------------------


async def test_postgres_search_serves_exact_quotes_with_their_location(
    database: Database,
) -> None:
    knowledge = LiteratureKnowledge.from_directory(KNOWLEDGE_DIR)
    index = PostgresFullTextIndex(database.sessionmaker)
    stored = await index.sync(knowledge.documents)
    assert stored == sum(len(chunks) for _, chunks in knowledge.documents)
    assert await index.sync(knowledge.documents) == stored  # a second start replaces, no dupes
    knowledge.index = index
    result = await knowledge.search("Scratch handling")
    assert result.method == METHOD
    assert result.hits
    causes = load_pattern_causes(KNOWLEDGE_DIR / "pattern_causes.json")
    quotes = {(q.source_id, q.quote, q.location) for c in causes.causes for q in c.quotes}
    for hit in result.hits:
        assert (hit.source.source_id, hit.snippet, hit.location) in quotes
    ranks = [hit.rank for hit in result.hits]
    assert ranks == sorted(ranks, reverse=True)


async def test_postgres_search_stems_and_ignores_stop_words(database: Database) -> None:
    knowledge = LiteratureKnowledge.from_directory(KNOWLEDGE_DIR)
    index = PostgresFullTextIndex(database.sessionmaker)
    await index.sync(knowledge.documents)
    assert await index.search_hits("scratches") == await index.search_hits("scratch")
    assert await index.search_hits("the of and") == []
    assert await index.search_hits("!!! ''' ;; --") == []
    assert len(await index.search_hits("wafer", limit=2)) <= 2


# -- startup wiring -----------------------------------------------------------------------------


def key_settings(db_settings: Settings, tmp_path: Path) -> Settings:
    return db_settings.model_copy(
        update={
            "token_factory_api_key": SecretStr(PLACEHOLDER_KEY),
            "artifacts_dir": tmp_path,
            "migrate_on_start": False,
        }
    )


async def _start(registry: ServiceRegistry) -> None:
    for resource in registry.resources:
        await resource.start()


async def _stop(registry: ServiceRegistry) -> None:
    for resource in reversed(registry.resources):
        await resource.stop()


async def test_with_a_database_the_stores_persist_role_choices_and_usage_across_restarts(
    database: Database, db_settings: Settings, tmp_path: Path, respx_mock: respx.Router
) -> None:
    settings = key_settings(db_settings, tmp_path)
    first = build_registry(settings)
    kinds = [type(r) for r in first.resources]
    assert kinds.index(Database) < kinds.index(KnowledgeResource) < kinds.index(JobWorker)
    assert kinds.index(Database) < kinds.index(AgentResource) < kinds.index(JobWorker)
    agent = next(r for r in first.resources if isinstance(r, AgentResource))
    assert isinstance(agent.stack.call_log, DbCallLog)
    await _start(first)
    try:
        chain = (ModelChoice(model="DeepSeek-V4-Flash", reasoning_effort="none", response_mode=ResponseMode.JSON_OBJECT),)  # fmt: skip
        await agent.stack.registry.assign(Role.ROUTER, chain, actor="Administrator")
        await agent.stack.call_log.record(call(1))
        assert first.knowledge is not None
        assert (await first.knowledge.search("edge ring")).method == METHOD
    finally:
        await _stop(first)

    second = build_registry(settings)
    await _start(second)
    try:
        again = next(r for r in second.resources if isinstance(r, AgentResource))
        assert again.stack.registry.assignment(Role.ROUTER).chain == chain
        assert await again.stack.call_log.since(T0) == [call(1)]
        assert "llm_roles" not in second.problems
        assert "knowledge_search" not in second.problems
    finally:
        await _stop(second)
    assert not respx_mock.calls  # startup and the stores call no model


async def test_an_unreachable_database_leaves_defaults_and_memory_search(
    tmp_path: Path, respx_mock: respx.Router
) -> None:
    registry = ServiceRegistry(
        settings=Settings(environment="test", log_json=False, database_url=None)
    )
    broken = Database(BROKEN_URL, migrate_on_start=False)
    try:
        settings = Settings(
            environment="test",
            log_json=False,
            database_url=SecretStr(BROKEN_URL),
            artifacts_dir=tmp_path,
            token_factory_api_key=SecretStr(PLACEHOLDER_KEY),
        )
        install_agent(registry, settings, sessions=broken.sessionmaker)
        await _start(registry)
        assert "stored role assignments not read" in registry.problems["llm_roles"]
        assert "in memory" in registry.problems["knowledge_search"]
        assert registry.knowledge is not None
        assert "BM25" in (await registry.knowledge.search("edge ring")).method
        assert registry.chat is not None
    finally:
        await _stop(registry)
        await broken.stop()
    assert not respx_mock.calls
