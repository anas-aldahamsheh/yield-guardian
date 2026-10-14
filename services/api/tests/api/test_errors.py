from typing import cast

import httpx

from yield_guardian.contracts.services import NotFoundError, SecomService
from yield_guardian.services.registry import ServiceRegistry

PROBLEM = "application/problem+json"


class _NoUnits:
    async def get_unit(self, unit_id: int) -> None:
        raise NotFoundError(f"Unit {unit_id} has not come off the line yet.")


async def test_missing_service_is_not_ready(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/units/12")
    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["code"] == "not_ready"
    assert body["instance"] == "/api/v1/units/12"


async def test_validation_error_is_a_problem(
    client: httpx.AsyncClient, registry: ServiceRegistry
) -> None:
    registry.secom = cast(SecomService, _NoUnits())
    response = await client.get("/api/v1/units/-1")
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["errors"][0]["loc"] == ["path", "unit_id"]


async def test_service_not_found_is_a_problem(
    client: httpx.AsyncClient, registry: ServiceRegistry
) -> None:
    registry.secom = cast(SecomService, _NoUnits())
    response = await client.get("/api/v1/units/1500")
    assert response.status_code == 404
    assert response.json() == {
        "type": "about:blank",
        "title": "Not found",
        "status": 404,
        "detail": "Unit 1500 has not come off the line yet.",
        "instance": "/api/v1/units/1500",
        "code": "not_found",
    }


async def test_unknown_route_is_a_problem(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/nothing-here")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_actions_need_a_session(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/investigations", json={"trigger": {"kind": "unit", "ref": "12"}}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_health_and_session(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/health")).json() == {"status": "ok"}
    session = (await client.get("/api/v1/session")).json()
    assert session["role"] == "visitor"
    assert session["csrf_token"] is None


async def test_readiness_reports_missing_parts(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/ready")).json()
    assert body["ready"] is False
    assert {c["name"] for c in body["checks"]} == {"secom_bundle", "wafermap_bundle", "database"}
