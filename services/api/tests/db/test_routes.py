"""The persistence layer wired into the app: cookies, CSRF, investigations, work orders, readiness."""

from collections.abc import AsyncIterator

import httpx
import pytest

from tests.db.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, clean
from tests.db.fakes import FakeRunner
from yield_guardian.api.app import create_app
from yield_guardian.api.deps import CSRF_HEADER, SESSION_COOKIE
from yield_guardian.core.settings import Settings
from yield_guardian.services.jobs import NO_RUNNER_DETAIL
from yield_guardian.services.persistence import build_persistence
from yield_guardian.services.registry import ServiceRegistry


@pytest.fixture
async def api(database_url: str, db_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    await clean(database_url)
    registry = ServiceRegistry(settings=db_settings, runner=FakeRunner())
    build_persistence(db_settings, runner_provider=lambda: registry.runner, migrate=True).install(
        registry
    )
    app = create_app(db_settings, registry)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_readiness_reports_the_database(api: httpx.AsyncClient) -> None:
    checks = (await api.get("/api/v1/ready")).json()["checks"]
    assert {"name": "database", "ok": True, "detail": None} in checks


async def test_guest_session_cookie_and_csrf(api: httpx.AsyncClient) -> None:
    assert (await api.get("/api/v1/session")).json()["role"] == "visitor"
    started = await api.post("/api/v1/session/guest", json={"display_name": "Mia"})
    assert started.status_code == 200
    info = started.json()
    assert info["role"] == "engineer"
    assert SESSION_COOKIE in api.cookies
    assert (await api.get("/api/v1/session")).json() == info

    trigger = {"trigger": {"kind": "alarm", "ref": "AL-1043-t2"}}
    refused = await api.post("/api/v1/investigations", json=trigger)
    assert refused.status_code == 403
    assert refused.json()["code"] == "csrf_failed"
    accepted = await api.post(
        "/api/v1/investigations", json=trigger, headers={CSRF_HEADER: info["csrf_token"]}
    )
    assert accepted.status_code == 202
    investigation_id = accepted.json()["investigation_id"]

    async with api.stream("GET", f"/api/v1/investigations/{investigation_id}/events") as stream:
        body = "".join([chunk async for chunk in stream.aiter_text()])
    assert "event: end" in body
    decided = await api.post(
        f"/api/v1/investigations/{investigation_id}/decision",
        json={"verdict": "approve", "actions": [1]},
        headers={CSRF_HEADER: info["csrf_token"]},
    )
    assert decided.status_code == 200
    again = await api.post(
        f"/api/v1/investigations/{investigation_id}/decision",
        json={"verdict": "reject"},
        headers={CSRF_HEADER: info["csrf_token"]},
    )
    assert again.status_code == 409
    assert again.json()["code"] == "conflict"

    async with api.stream(
        "GET",
        f"/api/v1/investigations/{investigation_id}/events",
        headers={"Last-Event-ID": "9"},
    ) as stream:
        body = "".join([chunk async for chunk in stream.aiter_text()])
    assert "event: decision" in body
    work_orders = (await api.get("/api/v1/work-orders")).json()
    assert [w["work_order_id"] for w in work_orders["items"]] == ["WO-000001"]
    audit = (await api.get("/api/v1/audit", params={"action": "investigation.approved"})).json()
    assert audit["items"][0]["actor_name"] == "Mia"

    assert (await api.post("/api/v1/session/logout")).status_code == 204
    assert (await api.get("/api/v1/session")).json()["role"] == "visitor"


async def test_admin_login(api: httpx.AsyncClient) -> None:
    failed = await api.post("/api/v1/session/login", json={"username": "x", "password": "y"})
    assert failed.status_code == 401
    assert failed.json()["code"] == "unauthorized"
    assert SESSION_COOKIE not in api.cookies
    signed_in = await api.post(
        "/api/v1/session/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["role"] == "admin"


async def test_bad_cursor_is_a_bad_request(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/investigations", params={"cursor": "nope"})
    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"


async def test_without_an_investigator_a_live_run_is_refused_and_not_created(
    database_url: str, db_settings: Settings
) -> None:
    await clean(database_url)
    registry = ServiceRegistry(settings=db_settings, runner=None)
    build_persistence(db_settings, runner_provider=lambda: registry.runner, migrate=True).install(
        registry
    )
    app = create_app(db_settings, registry)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
            info = (await api.post("/api/v1/session/guest", json={"display_name": "Mia"})).json()
            refused = await api.post(
                "/api/v1/investigations",
                json={"trigger": {"kind": "alarm", "ref": "AL-1043-t2"}},
                headers={CSRF_HEADER: info["csrf_token"]},
            )
            assert refused.status_code == 503
            problem = refused.json()
            assert problem["code"] == "not_ready"
            assert problem["detail"] == NO_RUNNER_DETAIL
            assert (await api.get("/api/v1/investigations")).json()["items"] == []
            unsigned = await api.post(
                "/api/v1/investigations", json={"trigger": {"kind": "unit", "ref": "12"}}
            )
            assert unsigned.status_code == 403  # the session checks still come first
