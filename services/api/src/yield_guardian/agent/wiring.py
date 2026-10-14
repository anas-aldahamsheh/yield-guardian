"""Startup wiring of the language-model services: the model admin, the investigator, the chat.

:func:`install_agent` is called by ``bootstrap.build_registry``. Without a Token Factory key it
installs nothing and records why in ``registry.problems``, so the routes answer 503 not_ready.
With a key it sets ``registry.llm`` at once (no I/O) and adds an :class:`AgentResource` that,
when the app starts, applies the stored role assignments, opens the investigation checkpointer
(Postgres when DATABASE_URL is set, memory otherwise) and sets ``registry.chat`` and
``registry.runner``.

With a database (``sessions`` given), the call log, response cache, role assignments, chat
routes and evaluations are the PostgreSQL stores of ``llm.dbstores``, so usage and role choices
survive a restart, and a :class:`KnowledgeResource` moves the literature search to PostgreSQL
full-text search. A :class:`RecordedRunsResource` imports the recorded investigations of
``docs/recorded/investigations.json`` (or ``RECORDED_RUNS_FILE``) that this host lacks. These
resources are placed after the database (which migrates first) and before the job worker
(which calls ``registry.runner``).

Startup makes no Token Factory call: the live model catalog is not read here (it would be a
network call to the endpoint before anyone asked for one). Nothing here limits, delays or
refuses calls (PLAN D-009).
"""

from __future__ import annotations

import os
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from yield_guardian.agent.chat import ChatAnswerer
from yield_guardian.agent.graph import InvestigatorRunner
from yield_guardian.contracts.services import (
    KnowledgeService,
    NotReadyError,
    ScienceServices,
    SecomService,
    WaferService,
)
from yield_guardian.core.settings import Settings
from yield_guardian.knowledge.postgres import PostgresFullTextIndex
from yield_guardian.knowledge.service import KnowledgeError, LiteratureKnowledge
from yield_guardian.llm.dbstores import (
    DbCallLog,
    DbEvaluationStore,
    DbResponseCache,
    DbRoleAssignmentStore,
    DbRouteLog,
    Sessions,
)
from yield_guardian.llm.factory import LlmStack, assemble_llm_stack, key_configured
from yield_guardian.services.jobs import JobWorker
from yield_guardian.services.registry import Resource, ServiceRegistry

log = structlog.get_logger(__name__)

NO_KEY = "TOKEN_FACTORY_API_KEY is not set"
KNOWLEDGE_NOT_BUILT = "the knowledge base (literature search) is not loaded"
KNOWLEDGE_DIR_VARIABLE = "KNOWLEDGE_DIR"
DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parents[5] / "docs" / "knowledge"
MEMORY_CHECKPOINTS = (
    "investigation checkpoints are kept in memory (DATABASE_URL is not set): a restart loses "
    "investigations waiting for a decision"
)


class Unavailable:
    """Stands in for a science service that is not loaded: every read raises NotReadyError,
    which the tools report to the model as a failed call (never a made-up value)."""

    def __init__(self, name: str, reason: str) -> None:
        self._name = name
        self._reason = reason

    def __getattr__(self, attribute: str) -> Any:
        if attribute.startswith("__"):
            raise AttributeError(attribute)

        async def unavailable(*args: object, **kwargs: object) -> Any:
            raise NotReadyError(f"the {self._name} service is not available: {self._reason}")

        return unavailable


def science_services(registry: ServiceRegistry) -> ScienceServices:
    def reason(key: str, default: str) -> str:
        return registry.problems.get(key, default)

    secom = registry.secom or Unavailable("SECOM", reason("secom_bundle", "not loaded"))
    wafer = registry.wafer or Unavailable("wafer map", reason("wafermap_bundle", "not loaded"))
    knowledge = registry.knowledge or Unavailable("knowledge", KNOWLEDGE_NOT_BUILT)
    return ScienceServices(
        secom=cast(SecomService, secom),
        wafer=cast(WaferService, wafer),
        knowledge=cast(KnowledgeService, knowledge),
    )


def psycopg_conninfo(url: str) -> str:
    """The libpq URL psycopg accepts, from a SQLAlchemy URL (``postgresql+asyncpg://`` ...)."""
    scheme, sep, rest = url.partition("://")
    if not sep:
        raise ValueError("DATABASE_URL is not a URL")
    return f"postgresql://{rest}" if scheme.startswith("postgres") else url


class AgentResource:
    """Opens what the investigator needs when the app starts and closes it when it stops."""

    def __init__(self, registry: ServiceRegistry, stack: LlmStack, settings: Settings) -> None:
        self.registry = registry
        self.stack = stack
        self.settings = settings
        self._exit = AsyncExitStack()

    async def _checkpointer(self) -> BaseCheckpointSaver[Any]:
        if self.settings.database_url is None:
            self.registry.problems["investigation_checkpoints"] = MEMORY_CHECKPOINTS
            return InMemorySaver()
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        url = psycopg_conninfo(self.settings.database_url.get_secret_value())
        saver = await self._exit.enter_async_context(AsyncPostgresSaver.from_conn_string(url))
        await saver.setup()
        return saver

    async def _load_roles(self) -> None:
        try:
            warnings = await self.stack.registry.load()
        except Exception as error:
            # The default chains serve; the stored choices apply on the next start.
            reason = f"stored role assignments not read ({type(error).__name__}: {error})"
            self.registry.problems["llm_roles"] = reason[:300]
            log.warning("llm_roles_not_loaded", reason=reason[:300])
            return
        if warnings:
            self.registry.problems["llm_roles"] = "; ".join(warnings)
        else:
            self.registry.problems.pop("llm_roles", None)

    async def start(self) -> None:
        try:
            await self._load_roles()
            self.registry.chat = ChatAnswerer(
                gateway=self.stack.gateway,
                services=science_services(self.registry),
                route_log=self.stack.route_log,
            )
            checkpointer = await self._checkpointer()
            self.registry.runner = InvestigatorRunner(
                gateway=self.stack.gateway,
                services=science_services(self.registry),
                checkpointer=checkpointer,
            )
        except Exception as error:
            self.registry.problems["investigator"] = f"{type(error).__name__}: {error}"[:300]
            log.warning("investigator_not_started", reason=self.registry.problems["investigator"])
        else:
            log.info("investigator_started")

    async def stop(self) -> None:
        self.registry.runner = None
        self.registry.chat = None
        await self._exit.aclose()
        await self.stack.aclose()


def knowledge_dir(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    configured = env.get(KNOWLEDGE_DIR_VARIABLE, "").strip()
    return Path(configured) if configured else DEFAULT_KNOWLEDGE_DIR


def install_knowledge(registry: ServiceRegistry, directory: Path | None = None) -> None:
    """The literature search and pattern-cause table; needs no key (no model is called)."""
    path = directory or knowledge_dir()
    try:
        registry.knowledge = LiteratureKnowledge.from_directory(path)
    except (KnowledgeError, ValueError, OSError) as error:
        registry.problems["knowledge"] = f"{KNOWLEDGE_NOT_BUILT}: {error}"[:300]
        log.warning("knowledge_not_loaded", reason=registry.problems["knowledge"])
    else:
        registry.problems.pop("knowledge", None)
        log.info("knowledge_loaded", directory=str(path))


RECORDED_RUNS_VARIABLE = "RECORDED_RUNS_FILE"
DEFAULT_RECORDED_RUNS = DEFAULT_KNOWLEDGE_DIR.parent / "recorded" / "investigations.json"


def recorded_runs_file(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    configured = env.get(RECORDED_RUNS_VARIABLE, "").strip()
    return Path(configured) if configured else DEFAULT_RECORDED_RUNS


class RecordedRunsResource:
    """Seeds the recorded investigations at startup: imports those missing, changes none."""

    def __init__(
        self, registry: ServiceRegistry, sessions: Sessions, database_url: str, path: Path
    ) -> None:
        self.registry = registry
        self.sessions = sessions
        self.database_url = database_url
        self.path = path

    async def start(self) -> None:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        from yield_guardian.services.recorded import import_recorded, read_runs

        if not self.path.is_file():
            log.info("recorded_runs_none", path=str(self.path))
            return
        try:
            runs = read_runs(self.path)
            conninfo = psycopg_conninfo(self.database_url)
            async with AsyncPostgresSaver.from_conn_string(conninfo) as saver:
                await saver.setup()
                report = await import_recorded(self.sessions, runs, saver)
        except Exception as error:
            reason = f"recorded runs not imported ({type(error).__name__}: {error})"[:300]
            self.registry.problems["recorded_runs"] = reason
            log.warning("recorded_runs_not_imported", reason=reason)
            return
        self.registry.problems.pop("recorded_runs", None)
        log.info(
            "recorded_runs_seeded",
            imported=len(report.imported),
            present=len(report.skipped),
            without_state=len(report.without_state),
        )

    async def stop(self) -> None:
        return None


KNOWLEDGE_IN_MEMORY = "literature search runs in memory: the database copy failed"


class KnowledgeResource:
    """Copies the knowledge chunks into PostgreSQL at startup and searches them there."""

    def __init__(self, registry: ServiceRegistry, sessions: Sessions) -> None:
        self.registry = registry
        self.sessions = sessions

    async def start(self) -> None:
        knowledge = self.registry.knowledge
        if not isinstance(knowledge, LiteratureKnowledge):
            return
        index = PostgresFullTextIndex(self.sessions)
        try:
            stored = await index.sync(knowledge.documents)
        except Exception as error:
            reason = f"{KNOWLEDGE_IN_MEMORY} ({type(error).__name__}: {error})"[:300]
            self.registry.problems["knowledge_search"] = reason
            log.warning("knowledge_search_in_memory", reason=reason)
            return
        knowledge.index = index
        self.registry.problems.pop("knowledge_search", None)
        log.info("knowledge_search_in_postgres", chunks=stored)

    async def stop(self) -> None:
        return None


def add_before_jobs(registry: ServiceRegistry, resource: Resource) -> None:
    """Start ``resource`` after the database and before the job worker."""
    position = next(
        (i for i, r in enumerate(registry.resources) if isinstance(r, JobWorker)),
        len(registry.resources),
    )
    registry.resources.insert(position, resource)


def assemble_stack(settings: Settings, sessions: Sessions | None) -> LlmStack:
    if sessions is None:
        return assemble_llm_stack(settings)
    return assemble_llm_stack(
        settings,
        cache=DbResponseCache(sessions),
        call_log=DbCallLog(sessions),
        assignments=DbRoleAssignmentStore(sessions),
        route_log=DbRouteLog(sessions),
        evaluations=DbEvaluationStore(sessions),
    )


def install_agent(
    registry: ServiceRegistry,
    settings: Settings,
    *,
    sessions: Sessions | None = None,
    recorded_runs: Path | None = None,
) -> AgentResource | None:
    """Load the knowledge base, then wire the model admin, the investigator and the chat when a
    key is set; record why not otherwise. ``sessions`` (the database, when DATABASE_URL is set)
    selects the PostgreSQL stores."""
    install_knowledge(registry)
    if sessions is not None and registry.knowledge is not None:
        add_before_jobs(registry, KnowledgeResource(registry, sessions))
    if sessions is not None and settings.database_url is not None:
        url = settings.database_url.get_secret_value()
        path = recorded_runs or recorded_runs_file()
        add_before_jobs(registry, RecordedRunsResource(registry, sessions, url, path))
    if not key_configured(settings):
        for name in ("llm", "investigator", "chat"):
            registry.problems[name] = NO_KEY
        log.info("language_models_not_configured", reason=NO_KEY)
        return None
    try:
        stack = assemble_stack(settings, sessions)
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"[:300]
        for name in ("llm", "investigator", "chat"):
            registry.problems[name] = reason
        log.warning("language_models_not_built", reason=reason)
        return None
    registry.llm = stack.admin
    resource = AgentResource(registry, stack, settings)
    add_before_jobs(registry, resource)
    return resource
