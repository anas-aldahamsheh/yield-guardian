"""Startup wiring of the language-model services: the model admin, the investigator, the chat.

:func:`install_agent` is called by ``bootstrap.build_registry``. Without a Token Factory key it
installs nothing and records why in ``registry.problems``, so the routes answer 503 not_ready.
With a key it sets ``registry.llm`` at once (no I/O) and adds an :class:`AgentResource` that,
when the app starts, applies the stored role assignments, opens the investigation checkpointer
(Postgres when DATABASE_URL is set, memory otherwise) and sets ``registry.chat`` and
``registry.runner``.

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
from yield_guardian.knowledge.service import KnowledgeError, LiteratureKnowledge
from yield_guardian.llm.factory import LlmStack, assemble_llm_stack, key_configured
from yield_guardian.services.registry import ServiceRegistry

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

    async def start(self) -> None:
        try:
            warnings = await self.stack.registry.load()
            if warnings:
                self.registry.problems["llm_roles"] = "; ".join(warnings)
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


def install_agent(registry: ServiceRegistry, settings: Settings) -> AgentResource | None:
    """Load the knowledge base, then wire the model admin, the investigator and the chat when a
    key is set; record why not otherwise."""
    install_knowledge(registry)
    if not key_configured(settings):
        for name in ("llm", "investigator", "chat"):
            registry.problems[name] = NO_KEY
        log.info("language_models_not_configured", reason=NO_KEY)
        return None
    try:
        stack = assemble_llm_stack(settings)
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"[:300]
        for name in ("llm", "investigator", "chat"):
            registry.problems[name] = reason
        log.warning("language_models_not_built", reason=reason)
        return None
    registry.llm = stack.admin
    resource = AgentResource(registry, stack, settings)
    registry.resources.append(resource)
    return resource
