"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from yield_guardian import APP_NAME, __version__
from yield_guardian.api.openapi import build_openapi
from yield_guardian.api.problems import install_problem_handlers
from yield_guardian.api.routes import (
    chat,
    investigations,
    knowledge,
    line,
    llm,
    meta,
    methods,
    secom,
    session,
    wafers,
    work,
)
from yield_guardian.core.logging import configure_logging
from yield_guardian.core.settings import Settings, get_settings
from yield_guardian.services.registry import Resource, ServiceRegistry

API_PREFIX = "/api/v1"

DESCRIPTION = """\
Yield Guardian API: semiconductor yield investigation on real fab data (SECOM, WM-811K).

* Errors are RFC 9457 `application/problem+json` (schema `Problem`).
* Investigator events stream as server-sent events (schema `InvestigationEvent`).
* The live line streams on the WebSocket `/ws/line` as JSON text frames (schema `LineEvent`).
* Actions need a session cookie and the `X-CSRF-Token` header (see `/session`).
"""


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app(
    settings: Settings | None = None, registry: ServiceRegistry | None = None
) -> FastAPI:
    settings = settings or get_settings()
    if registry is None:
        from yield_guardian.bootstrap import build_registry

        registry = build_registry(settings)
    configure_logging(settings.log_level, json=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        started: list[Resource] = []
        try:
            for resource in registry.resources:
                await resource.start()
                started.append(resource)
            yield
        finally:
            for resource in reversed(started):
                await resource.stop()

    app = FastAPI(
        title=APP_NAME,
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
        separate_input_output_schemas=False,
        generate_unique_id_function=_operation_id,
    )
    app.state.registry = registry
    install_problem_handlers(app)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH"],
            allow_headers=["Content-Type", "X-CSRF-Token", "Last-Event-ID"],
        )
    for module in (
        meta,
        line,
        secom,
        investigations,
        work,
        wafers,
        knowledge,
        chat,
        llm,
        methods,
        session,
    ):
        app.include_router(module.router, prefix=API_PREFIX)
    app.include_router(line.ws_router)

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = build_openapi(app)
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app
