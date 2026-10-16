"""Browsers against the whole API on PostgreSQL, for the workspace tests: each browser is its own
HTTP client with its own cookie jar. The run engines are the real SECOM engine and sensor-file
parser (the wafer track is the wafer double, unused by these SECOM runs); the investigator is the
FakeRunner double and the chat a silent double, so no model is ever called."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest

from tests.db.conftest import clean
from tests.db.fakes import FakeRunner
from tests.db.test_runs import parse_sse, wafer_double
from tests.live.doubles import SECOM_DATA, real_secom, real_sensor_engine
from yield_guardian.api.app import create_app
from yield_guardian.api.deps import CSRF_HEADER, SESSION_COOKIE
from yield_guardian.contracts.chat import ChatEventPayload, ChatRequest
from yield_guardian.contracts.session import SessionInfo
from yield_guardian.core.settings import Settings
from yield_guardian.live.runs import Engines
from yield_guardian.live.sensor_file import SecomSensorFileParser
from yield_guardian.live.wiring import install_runs
from yield_guardian.services.access import Viewer, current_viewer
from yield_guardian.services.persistence import Persistence, build_persistence
from yield_guardian.services.registry import ServiceRegistry

SAME_SITE = {"Sec-Fetch-Site": "same-origin"}
CASE = {"source": "case", "case_id": "spe_alarm"}
"""A real SECOM situation found by the case catalog's rule; its run lists an SPE alarm."""


class SilentChat:
    """A ChatResponder double: it answers nothing and notes the workspace it answered for."""

    def __init__(self) -> None:
        self.viewers: list[Viewer | None] = []

    async def answer(
        self, request: ChatRequest, *, session: SessionInfo
    ) -> AsyncIterator[ChatEventPayload]:
        self.viewers.append(current_viewer())
        return
        yield  # an async generator that yields nothing


@dataclass
class Browser:
    client: httpx.AsyncClient
    csrf: str = ""
    workspace: str = ""
    run_id: str = ""
    upload_id: str = ""
    investigation_id: str = ""
    work_order_id: str = ""

    def headers(self) -> dict[str, str]:
        return {CSRF_HEADER: self.csrf}


@dataclass
class Stack:
    transport: httpx.ASGITransport
    chat: SilentChat
    persistence: Persistence

    def browser(self) -> Browser:
        return Browser(
            httpx.AsyncClient(transport=self.transport, base_url="http://test", timeout=300)
        )


@pytest.fixture
async def stack(database_url: str, db_settings: Settings) -> AsyncIterator[Stack]:
    await clean(database_url)
    chat = SilentChat()
    registry = ServiceRegistry(settings=db_settings, runner=FakeRunner(), chat=chat)
    persistence = build_persistence(db_settings, runner_provider=lambda: registry.runner)
    persistence.install(registry)
    install_runs(
        registry,
        persistence.runs,
        secom=real_secom(),
        wafermap=None,
        secom_attribution=SECOM_DATA / "ATTRIBUTION.md",
        engines=Engines(
            sensors=real_sensor_engine(),
            wafers=wafer_double(),
            sensor_file=SecomSensorFileParser(),
        ),
    )
    app = create_app(db_settings, registry)
    async with app.router.lifespan_context(app):
        yield Stack(httpx.ASGITransport(app=app), chat, persistence)


async def open_browser(stack: Stack, name: str | None = None) -> Browser:
    """A browser's first page (its own workspace), and "Try as engineer" when `name` is given."""
    browser = stack.browser()
    opened = await browser.client.post("/api/v1/session/workspace", headers=SAME_SITE)
    assert opened.status_code == 200, opened.text
    assert SESSION_COOKIE in browser.client.cookies
    info = opened.json()
    if name is not None:
        raised = await browser.client.post("/api/v1/session/guest", json={"display_name": name})
        info = raised.json()
        assert info["role"] == "engineer"
        assert info["workspace"]["workspace_id"] == opened.json()["workspace"]["workspace_id"]
    browser.csrf = info["csrf_token"]
    browser.workspace = info["workspace"]["workspace_id"]
    return browser


async def follow(client: httpx.AsyncClient, path: str) -> list[dict[str, str]]:
    """Every event of a stream, until the server closes it."""
    async with client.stream("GET", path) as response:
        assert response.status_code == 200, path
        body = "".join([chunk async for chunk in response.aiter_text()])
    return parse_sse(body)


def same_answer(
    hidden: httpx.Response, hidden_id: str, missing: httpx.Response, missing_id: str
) -> None:
    """`hidden` (another workspace's ID) is exactly what `missing` (an ID never made) got."""
    assert hidden.status_code == missing.status_code, (hidden.text, missing.text)
    assert hidden.headers["content-type"] == "application/problem+json"
    assert hidden.json() == json.loads(missing.text.replace(missing_id, hidden_id))


def never_made(identifier: str) -> str:
    """An ID with the same time inside it as `identifier`, that was never made."""
    return identifier[:-6] + "zzzzzz"
