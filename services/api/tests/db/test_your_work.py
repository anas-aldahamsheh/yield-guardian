"""Your work over HTTP (the owner's "keep the context" ask): a workspace's runs with their live
status and what each still needs, the actions on them (name, note, saved view, archive, run the
same input again, compare two runs, the results as CSV, an investigation's report), its uploads
and investigations, the workspace session routes (first visit, handoff, fresh start, sign-out)
and the admin's session list. Real SECOM runs; the investigator is the FakeRunner double."""

import asyncio
import csv
import io
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from tests.db.browsers import CASE, SAME_SITE, Browser, Stack, follow, open_browser, stack
from tests.db.conftest import ADMIN_PASSWORD, ADMIN_USERNAME
from yield_guardian.api.deps import CSRF_HEADER, SESSION_COOKIE
from yield_guardian.services.run_export import CSV_COLUMNS, _cell

__all__ = ["stack"]  # the fixture


async def start_run(b: Browser, body: dict[str, Any] = CASE) -> str:
    created = await b.client.post("/api/v1/runs", json=body, headers=b.headers())
    assert created.status_code == 201, created.text
    run_id: str = created.json()["run_id"]
    return run_id


async def finish(b: Browser, run_id: str) -> dict[str, Any]:
    events = await follow(b.client, f"/api/v1/runs/{run_id}/events")
    assert events[-1]["event"] == "run_done"
    run: dict[str, Any] = (await b.client.get(f"/api/v1/runs/{run_id}")).json()
    return run


async def until(check: Callable[[], Awaitable[bool]]) -> None:
    async with asyncio.timeout(15):
        while True:
            if await check():
                return
            await asyncio.sleep(0.05)


async def work(b: Browser, **params: Any) -> list[dict[str, Any]]:
    listed = await b.client.get("/api/v1/workspace/runs", params=params)
    assert listed.status_code == 200, listed.text
    items: list[dict[str, Any]] = listed.json()["items"]
    return items


def counted(run: dict[str, Any]) -> tuple[int, int]:
    """A run's listed alarms as the alarms rail counts them: alarms that turn a station red,
    and warnings (every other one)."""
    red = sum(a["severity"] == "alarm" and a["kind"] != "unknown_pattern" for a in run["alarms"])
    return red, len(run["alarms"]) - red


async def test_a_run_is_listed_with_its_live_status_and_what_it_still_needs(stack: Stack) -> None:
    b = await open_browser(stack)
    assert await work(b) == []  # the empty state
    run_id = await start_run(b)
    (item,) = await work(b)  # listed at once, while it computes
    assert item["run_id"] == run_id
    assert item["status"] in {"queued", "running", "done"}
    if item["status"] != "done":
        assert item["next"]["kind"] == "running"
    run = await finish(b, run_id)
    (item,) = await work(b)
    alarms, warnings = counted(run)
    assert alarms > 0  # the case's SPE alarm
    assert (item["status"], item["stages_finished"], item["stages_total"]) == ("done", 8, 8)
    assert (item["alarms"], item["warnings"], item["alarms_open"], item["current_stage"]) == (
        alarms,
        warnings,
        alarms + warnings,
        None,
    )
    waiting = [
        f"{n} {what}{'s' if n > 1 else ''}"
        for n, what in ((alarms, "alarm"), (warnings, "warning"))
        if n
    ]
    assert item["next"] == {
        "kind": "investigate",
        "text": f"{' and '.join(waiting)} not investigated.",
    }
    assert item["title"] == run["origin"]["title"]
    assert item["expires_at"] == run["expires_at"]  # kept as long as the workspace

    # A new run never removes an old one: both keep their own status.
    second = await start_run(b)
    listed = await work(b)
    assert [r["run_id"] for r in listed] == [second, run_id]
    assert listed[1]["status"] == "done"
    await finish(b, second)


async def test_a_run_is_named_noted_viewed_archived_and_restored(stack: Stack) -> None:
    b = await open_browser(stack)
    run_id = await start_run(b)
    await finish(b, run_id)
    path = f"/api/v1/workspace/runs/{run_id}"
    view = f"run={run_id}&station=2&unit=3"
    changes = {"label": "  Line 3 check ", "note": "Look at SPE", "view": view}
    named = await b.client.patch(path, json=changes, headers=b.headers())
    assert named.status_code == 200, named.text
    assert (named.json()["label"], named.json()["note"], named.json()["view"]) == (
        "Line 3 check",
        "Look at SPE",
        view,
    )
    unchanged = await b.client.patch(path, json={"archived": False}, headers=b.headers())
    assert unchanged.json()["label"] == "Line 3 check"  # fields left out stay as they are
    other_view = await b.client.patch(
        path, json={"view": "run=run_0000000000&station=1"}, headers=b.headers()
    )
    assert other_view.status_code == 400
    unknown_key = await b.client.patch(
        path, json={"view": f"run={run_id}&secret=1"}, headers=b.headers()
    )
    assert unknown_key.status_code == 400
    no_csrf = await b.client.patch(path, json={"label": "x"})
    assert no_csrf.status_code == 403

    archived = await b.client.patch(path, json={"archived": True}, headers=b.headers())
    assert archived.json()["archived"] is True
    assert await work(b) == []
    assert [r["run_id"] for r in await work(b, archived="true")] == [run_id]
    assert (await b.client.get(f"/api/v1/runs/{run_id}")).status_code == 200  # still opens
    await b.client.patch(path, json={"archived": False}, headers=b.headers())
    cleared = await b.client.patch(path, json={"label": None, "note": ""}, headers=b.headers())
    assert (cleared.json()["label"], cleared.json()["note"]) == (None, None)
    assert [r["run_id"] for r in await work(b)] == [run_id]


async def test_the_same_input_again_compares_and_downloads(stack: Stack) -> None:
    b = await open_browser(stack)
    first_id = await start_run(b)
    first = await finish(b, first_id)
    again = await b.client.post(f"/api/v1/runs/{first_id}/again", headers=b.headers())
    assert again.status_code == 201, again.text
    second_id = again.json()["run_id"]
    assert again.json()["origin"]["rule"].startswith(f"The same input as run {first_id}")
    second = await finish(b, second_id)
    listed = await work(b)
    assert [(r["run_id"], r["again_of"]) for r in listed] == [
        (second_id, first_id),
        (first_id, None),
    ]
    assert first["status"] == second["status"] == "done"

    compared = await b.client.get(f"/api/v1/runs/{first_id}/compare/{second_id}")
    assert compared.status_code == 200, compared.text
    body = compared.json()
    assert body["same_input"] is True
    sides = [(body[x]["alarms"], body[x]["warnings"]) for x in "ab"]
    assert sides == [counted(first)] * 2
    assert body["changes"] == []  # nothing differs
    assert [s["stage"] for s in body["stages"]] == [s["stage"] for s in first["stages"]]
    by_stage = {s["stage"]: (s["a_alarms"], s["a_warnings"]) for s in body["stages"]}
    assert sum(a for a, _ in by_stage.values()) == counted(first)[0]
    assert sum(w for _, w in by_stage.values()) == counted(first)[1]
    other = await start_run(b, {"source": "pick", "unit_ids": [1303]})
    await finish(b, other)
    different = (await b.client.get(f"/api/v1/runs/{first_id}/compare/{other}")).json()
    assert different["same_input"] is False
    units = first["units"]
    assert different["changes"][0] == f"Units: {units:,} → 1 (-{units - 1:,})."

    results = await b.client.get(f"/api/v1/runs/{first_id}/results.csv")
    assert results.status_code == 200
    assert results.headers["content-disposition"] == (
        f'attachment; filename="{first_id}-results.csv"'
    )
    assert results.content.startswith("﻿".encode())
    rows = list(csv.reader(io.StringIO(results.content.decode("utf-8-sig"))))
    assert tuple(rows[0]) == CSV_COLUMNS
    records = [r[0] for r in rows[1:]]
    assert records.count("unit") == first["units"]
    assert records.count("alarm") == len(first["alarms"])
    alarm_ids = {r[CSV_COLUMNS.index("alarm_id")] for r in rows[1:] if r[0] == "alarm"}
    assert alarm_ids == {a["alarm_id"] for a in first["alarms"]}


def test_a_csv_cell_never_runs_as_a_spreadsheet_formula() -> None:
    assert [_cell(v) for v in ("=SUM(A1)", "+1", "-2", "@x", "lot 7", "")] == [
        "'=SUM(A1)",
        "'+1",
        "'-2",
        "'@x",
        "lot 7",
        "",
    ]
    assert [_cell(v) for v in (None, True, False, 3, -0.5)] == ["", "true", "false", "3", "-0.5"]


async def test_an_investigation_shows_on_its_run_and_its_report_downloads(stack: Stack) -> None:
    b = await open_browser(stack, "Mia")
    run_id = await start_run(b)
    run = await finish(b, run_id)
    alarm = run["alarms"][0]["alarm_id"]
    created = await b.client.post(
        "/api/v1/investigations",
        json={"trigger": {"kind": "run_alarm", "ref": f"{run_id}:{alarm}"}},
        headers=b.headers(),
    )
    assert created.status_code == 202
    investigation_id = created.json()["investigation_id"]
    await follow(b.client, f"/api/v1/investigations/{investigation_id}/events")
    (item,) = await work(b)
    assert [i["investigation_id"] for i in item["investigations"]] == [investigation_id]
    assert item["investigations"][0]["alarm_id"] == alarm
    assert item["alarms_open"] == len(run["alarms"]) - 1
    assert item["next"] == {"kind": "decide", "text": "A report is waiting for your decision."}
    listed = (await b.client.get("/api/v1/workspace/investigations")).json()["items"]
    assert [(i["run_id"], i["alarm_id"], i["run_kept"]) for i in listed] == [(run_id, alarm, True)]
    assert listed[0]["next"]["kind"] == "decide"
    report = await b.client.get(f"/api/v1/investigations/{investigation_id}/report.md")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/markdown")
    text = report.text
    assert text.startswith(f"# {created.json()['title']}\n")
    for heading in ("## Summary", "## Findings", "## Actions", "## Limitations", "## Evidence"):
        assert heading in text

    await b.client.post(
        f"/api/v1/investigations/{investigation_id}/decision",
        json={"verdict": "reject"},
        headers=b.headers(),
    )

    async def rejected() -> bool:
        return bool((await work(b))[0]["investigations"][0]["status"] == "rejected")

    await until(rejected)
    (item,) = await work(b)
    left = "investigate" if len(run["alarms"]) > 1 else "none"  # the other alarms still wait
    assert item["next"]["kind"] == left
    assert (
        "## Decision"
        in (await b.client.get(f"/api/v1/investigations/{investigation_id}/report.md")).text
    )


async def test_an_upload_is_listed_with_the_runs_started_from_it(stack: Stack) -> None:
    b = await open_browser(stack)
    example = (await b.client.get("/api/v1/uploads/examples/sensors.csv")).content
    sent = await b.client.post(
        "/api/v1/uploads", files={"file": ("sensors.csv", example)}, headers=b.headers()
    )
    assert sent.status_code == 201
    upload_id = sent.json()["upload_id"]
    (listed,) = (await b.client.get("/api/v1/workspace/uploads")).json()["items"]
    assert (listed["upload_id"], listed["runs"], listed["runnable"]) == (upload_id, [], True)
    kept = datetime.fromisoformat(listed["expires_at"])
    assert kept > datetime.now(UTC) + timedelta(days=29)  # as long as the workspace
    run_id = await start_run(b, {"source": "upload", "upload_id": upload_id})
    await finish(b, run_id)
    (listed,) = (await b.client.get("/api/v1/workspace/uploads")).json()["items"]
    assert listed["runs"] == [run_id]
    (item,) = await work(b)
    assert item["upload_id"] == upload_id


async def test_runs_and_uploads_are_refused_from_another_site(stack: Stack) -> None:
    b = await open_browser(stack)
    elsewhere = {"Sec-Fetch-Site": "cross-site"}
    refused = await b.client.post("/api/v1/runs", json=CASE, headers=elsewhere)
    assert refused.status_code == 403
    assert refused.json()["code"] == "csrf_failed"
    # This site's own page may start a run without the token (the first ?pick= run).
    own_page = await b.client.post("/api/v1/runs", json=CASE, headers=SAME_SITE)
    assert own_page.status_code == 201
    assert [r["run_id"] for r in await work(b)] == [own_page.json()["run_id"]]
    fresh = stack.browser()
    opened = await fresh.client.post("/api/v1/session/workspace", headers=elsewhere)
    assert opened.status_code == 403  # another site cannot open a workspace for a browser
    assert SESSION_COOKIE not in fresh.client.cookies
    await finish(b, own_page.json()["run_id"])


# The session of this device --------------------------------------------------------------------


async def test_a_first_visit_keeps_its_workspace_on_every_page(stack: Stack) -> None:
    b = stack.browser()
    assert (await b.client.get("/api/v1/session")).json()["workspace"] is None
    assert (await b.client.get("/api/v1/workspace")).status_code == 404
    first = await b.client.post("/api/v1/session/workspace", headers=SAME_SITE)
    token = b.client.cookies[SESSION_COOKIE]
    cookie = first.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()
    assert f"Max-Age={30 * 86_400}" in cookie
    again = await b.client.post("/api/v1/session/workspace", headers=SAME_SITE)
    assert again.json() == first.json()  # the same workspace, the cookie renewed
    assert b.client.cookies[SESSION_COOKIE] == token
    summary = (await b.client.get("/api/v1/workspace")).json()
    assert (summary["runs"], summary["session_days"], summary["handoff_minutes"]) == (0, 30, 10)
    assert [d["current"] for d in summary["devices"]] == [True]

    csrf = {CSRF_HEADER: first.json()["csrf_token"]}
    raised = await b.client.post("/api/v1/session/guest", json={"display_name": "Mia"})
    workspace_id = first.json()["workspace"]["workspace_id"]
    assert raised.json()["workspace"]["workspace_id"] == workspace_id
    assert b.client.cookies[SESSION_COOKIE] != token  # a new token with the role
    signed_out = await b.client.post("/api/v1/session/logout")
    assert signed_out.status_code == 204
    back = (await b.client.get("/api/v1/session")).json()
    assert (back["role"], back["workspace"]["workspace_id"]) == ("visitor", workspace_id)

    assert (await b.client.post("/api/v1/workspace/handoffs")).status_code == 403  # no CSRF
    made = await b.client.post("/api/v1/workspace/handoffs", headers=csrf)
    assert made.status_code == 201
    assert made.json()["join_path"] == f"/join#code={made.json()['code']}"
    for code, status in (("nope", 422), ("0000-0000-000", 400), ("ABCD-EFGH-JKMN", 404)):
        tried = await b.client.post("/api/v1/workspace/join", json={"code": code}, headers=csrf)
        assert tried.status_code == status, (code, tried.text)
    own = await b.client.post(
        "/api/v1/workspace/join", json={"code": made.json()["code"]}, headers=csrf
    )
    assert own.status_code == 400  # this device is already in that workspace

    moved = await b.client.post("/api/v1/workspace/fresh", headers=csrf)
    assert moved.status_code == 200
    assert moved.json()["workspace"]["workspace_id"] != workspace_id
    assert moved.json()["csrf_token"] == first.json()["csrf_token"]


async def test_the_admin_lists_and_revokes_sessions(stack: Stack) -> None:
    visitor = await open_browser(stack)
    await start_run(visitor)
    assert (await visitor.client.get("/api/v1/admin/sessions")).status_code == 403
    admin = stack.browser()
    signed_in = await admin.client.post(
        "/api/v1/session/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    admin.csrf = signed_in.json()["csrf_token"]
    page = (await admin.client.get("/api/v1/admin/sessions")).json()
    assert (page["total"], page["workspaces"]) == (2, 2)
    row = next(s for s in page["items"] if s["workspace_id"] == visitor.workspace)
    assert (row["role"], row["runs"], row["current"]) == ("visitor", 1, False)
    path = f"/api/v1/admin/sessions/{row['session_id']}"
    assert (await admin.client.delete(path)).status_code == 403  # the CSRF token is needed
    assert (await admin.client.delete(path, headers=admin.headers())).status_code == 204
    assert (await admin.client.delete(path, headers=admin.headers())).status_code == 404
    ended = await visitor.client.get("/api/v1/session")
    assert ended.json()["workspace"] is None  # the revoked device starts again
    entries = (await admin.client.get("/api/v1/audit", params={"action": "session.revoked"})).json()
    assert [e["target_id"] for e in entries["items"]] == [row["session_id"]]
    for client in (visitor.client, admin.client):
        await client.aclose()
