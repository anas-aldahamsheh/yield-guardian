"""Every visitor is a separate user (the owner's rule of 2026-10-15), shown over HTTP against
PostgreSQL: twenty browsers, each with its own cookie, open a workspace, start a run of a real
SECOM case at the same moment and upload the real SECOM example file. Every run finishes; each
browser starts an investigation from its own run's alarm and approves it. Then each browser lists
only its own work, and for every other browser's run, event stream, upload and investigation
(and, for a neighbour, every other route that takes an ID) it gets exactly the answer a missing
ID gets. A device joined through a handoff code sees everything of its workspace; a run made
without a session is listed nowhere and opens for anyone. The one thing every visitor lists is
the product's example, the real recorded investigation of ``docs/recorded``, apart from their own
and read-only, with its work order and audit entries. The investigator is the FakeRunner double
and the chat a silent double: no model is called."""

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import update

from tests.db.browsers import (
    CASE,
    SAME_SITE,
    Browser,
    Stack,
    follow,
    never_made,
    open_browser,
    same_answer,
    stack,
)
from tests.db.conftest import ADMIN_PASSWORD, ADMIN_USERNAME
from tests.db.test_recorded import decided_before
from yield_guardian.api.deps import SESSION_COOKIE
from yield_guardian.db.tables import InvestigationRow
from yield_guardian.services.access import Viewer
from yield_guardian.services.recorded import import_recorded, read_runs

__all__ = ["stack"]  # the fixture

BROWSERS = 20
RECORDED = Path(__file__).resolve().parents[4] / "docs" / "recorded" / "investigations.json"
"""The real recorded investigation every host seeds at startup."""


Request = Callable[[str], Any]
WHY = {"role": "user", "content": "Why?"}


def neighbour_routes(b: Browser, o: Browser) -> list[tuple[str, Request]]:
    """Every other route that takes an ID of `o`'s, asked by `b`."""
    c, h = b.client, b.headers()
    return [
        (o.run_id, lambda i: c.get(f"/api/v1/runs/{i}/results.csv")),
        (o.run_id, lambda i: c.get(f"/api/v1/runs/{i}/units/0/chart")),
        (o.run_id, lambda i: c.get(f"/api/v1/runs/{b.run_id}/compare/{i}")),
        (o.run_id, lambda i: c.post(f"/api/v1/runs/{i}/again", headers=h)),
        (
            o.run_id,
            lambda i: c.patch(f"/api/v1/workspace/runs/{i}", json={"label": "x"}, headers=h),
        ),
        (o.investigation_id, lambda i: c.get(f"/api/v1/investigations/{i}/events")),
        (o.investigation_id, lambda i: c.get(f"/api/v1/investigations/{i}/evidence/E1")),
        (o.investigation_id, lambda i: c.get(f"/api/v1/investigations/{i}/report.md")),
        (
            o.investigation_id,
            lambda i: c.post(
                f"/api/v1/investigations/{i}/decision", json={"verdict": "reject"}, headers=h
            ),
        ),
        (o.investigation_id, lambda i: c.post(f"/api/v1/investigations/{i}/stop", headers=h)),
        (o.work_order_id, lambda i: c.get(f"/api/v1/work-orders/{i}")),
        (
            o.work_order_id,
            lambda i: c.patch(f"/api/v1/work-orders/{i}", json={"status": "done"}, headers=h),
        ),
    ]


async def test_twenty_browsers_at_once_each_see_only_their_own_work(stack: Stack) -> None:
    started = time.perf_counter()
    browsers = list(
        await asyncio.gather(*(open_browser(stack, f"Engineer {n}") for n in range(BROWSERS)))
    )
    assert len({b.workspace for b in browsers}) == BROWSERS

    # Every browser starts a run at the same moment, and uploads the real example file.
    async def start(b: Browser) -> None:
        created = await b.client.post("/api/v1/runs", json=CASE, headers=b.headers())
        assert created.status_code == 201, created.text
        b.run_id = created.json()["run_id"]

    await asyncio.gather(*(start(b) for b in browsers))
    example = (await browsers[0].client.get("/api/v1/uploads/examples/sensors.csv")).content

    async def upload(b: Browser) -> None:
        sent = await b.client.post(
            "/api/v1/uploads",
            files={"file": ("sensors.csv", example)},
            headers=b.headers(),
        )
        assert sent.status_code == 201, sent.text
        assert sent.json()["runnable"]
        b.upload_id = sent.json()["upload_id"]

    await asyncio.gather(*(upload(b) for b in browsers))

    # Every run finishes, each followed on its own event stream.
    streams = await asyncio.gather(
        *(follow(b.client, f"/api/v1/runs/{b.run_id}/events") for b in browsers)
    )
    assert all(events[-1]["event"] == "run_done" for events in streams)
    runs = [(await b.client.get(f"/api/v1/runs/{b.run_id}")).json() for b in browsers]
    assert [r["status"] for r in runs] == ["done"] * BROWSERS
    assert all(r["alarms"] for r in runs)
    computed = time.perf_counter() - started

    # Each starts an investigation from its own run's first alarm and approves the report.
    async def investigate(b: Browser, run: dict[str, Any]) -> None:
        ref = f"{b.run_id}:{run['alarms'][0]['alarm_id']}"
        created = await b.client.post(
            "/api/v1/investigations",
            json={"trigger": {"kind": "run_alarm", "ref": ref}},
            headers=b.headers(),
        )
        assert created.status_code == 202, created.text
        b.investigation_id = created.json()["investigation_id"]
        await follow(b.client, f"/api/v1/investigations/{b.investigation_id}/events")
        decided = await b.client.post(
            f"/api/v1/investigations/{b.investigation_id}/decision",
            json={"verdict": "approve", "actions": [0]},
            headers=b.headers(),
        )
        assert decided.status_code == 200, decided.text
        async with asyncio.timeout(30):
            while not b.work_order_id:
                found = (await b.client.get(f"/api/v1/investigations/{b.investigation_id}")).json()
                b.work_order_id = found["work_order_id"] or ""
                await asyncio.sleep(0.05)

    await asyncio.gather(*(investigate(b, r) for b, r in zip(browsers, runs, strict=True)))

    # Each lists exactly its own work.
    for b in browsers:
        listed = (await b.client.get("/api/v1/workspace/runs")).json()
        assert [r["run_id"] for r in listed["items"]] == [b.run_id]
        assert listed["items"][0]["investigations"][0]["investigation_id"] == b.investigation_id
        uploads = (await b.client.get("/api/v1/workspace/uploads")).json()
        assert [u["upload_id"] for u in uploads["items"]] == [b.upload_id]
        mine = (await b.client.get("/api/v1/workspace/investigations")).json()
        assert [i["investigation"]["investigation_id"] for i in mine["items"]] == [
            b.investigation_id
        ]
        investigations = (await b.client.get("/api/v1/investigations")).json()
        assert [i["investigation_id"] for i in investigations["items"]] == [b.investigation_id]
        orders = (await b.client.get("/api/v1/work-orders")).json()
        assert [o["work_order_id"] for o in orders["items"]] == [b.work_order_id]
        audit = (await b.client.get("/api/v1/audit", params={"limit": 200})).json()
        own = {b.investigation_id, b.work_order_id}
        targets = {e["target_id"] for e in audit["items"] if e["target_kind"] != "session"}
        assert targets == own, targets

    # Another browser's run, event stream, upload and investigation: what a missing ID gets.
    def cross(b: Browser, o: Browser) -> list[Callable[[], Any]]:
        def pair(make: Callable[[str], Any], identifier: str) -> Callable[[], Any]:
            async def check() -> None:
                hidden, missing = await make(identifier), await make(never_made(identifier))
                same_answer(hidden, identifier, missing, never_made(identifier))

            return check

        c = b.client
        return [
            pair(lambda i: c.get(f"/api/v1/runs/{i}"), o.run_id),
            pair(lambda i: c.get(f"/api/v1/runs/{i}/events"), o.run_id),
            pair(
                lambda i: c.post(
                    "/api/v1/runs", json={"source": "upload", "upload_id": i}, headers=b.headers()
                ),
                o.upload_id,
            ),
            pair(lambda i: c.get(f"/api/v1/investigations/{i}"), o.investigation_id),
        ]

    for b in browsers:
        others = [o for o in browsers if o is not b]
        await asyncio.gather(*(check() for o in others for check in cross(b, o)))

    # And every other route that takes an ID, against a neighbour.
    for n, b in enumerate(browsers):
        o = browsers[(n + 1) % BROWSERS]
        for hidden_id, make in neighbour_routes(b, o):
            missing_id = (
                f"WO-{999_999 - n:06d}" if hidden_id.startswith("WO-") else never_made(hidden_id)
            )
            same_answer(await make(hidden_id), hidden_id, await make(missing_id), missing_id)
        asked = await b.client.post(
            "/api/v1/chat",
            json={"messages": [WHY], "context": {"run_id": o.run_id}},
            headers=b.headers(),
        )
        assert asked.status_code == 404, asked.text
    # Nothing of another changed: its run keeps its name, its investigation its decision.
    for b in browsers:
        results = await b.client.get(f"/api/v1/runs/{b.run_id}/results.csv")
        assert results.status_code == 200
        listed = (await b.client.get("/api/v1/workspace/runs")).json()["items"]
        assert listed[0]["label"] is None
        assert (await b.client.get(f"/api/v1/investigations/{b.investigation_id}")).json()[
            "status"
        ] == "approved"
        order = (await b.client.get(f"/api/v1/work-orders/{b.work_order_id}")).json()
        assert order["status"] == "open"
    # The chat answers about one's own run, for one's own workspace.
    first = browsers[0]
    own_chat = await first.client.post(
        "/api/v1/chat",
        json={"messages": [WHY], "context": {"run_id": first.run_id}},
        headers=first.headers(),
    )
    assert own_chat.status_code == 200
    assert stack.chat.viewers == [Viewer(first.workspace)]

    # A second device joined with a handoff code is the same workspace and sees everything.
    code = (await first.client.post("/api/v1/workspace/handoffs", headers=first.headers())).json()
    phone = stack.browser()
    await phone.client.post("/api/v1/session/workspace", headers=SAME_SITE)
    phone.csrf = (await phone.client.get("/api/v1/session")).json()["csrf_token"]
    joined = await phone.client.post(
        "/api/v1/workspace/join", json={"code": code["code"]}, headers=phone.headers()
    )
    assert joined.status_code == 200, joined.text
    assert joined.json()["workspace"]["workspace_id"] == first.workspace
    assert (await phone.client.get(f"/api/v1/runs/{first.run_id}")).status_code == 200
    phone_runs = (await phone.client.get("/api/v1/workspace/runs")).json()["items"]
    assert [r["run_id"] for r in phone_runs] == [first.run_id]
    late = stack.browser()
    await late.client.post("/api/v1/session/workspace", headers=SAME_SITE)
    late.csrf = (await late.client.get("/api/v1/session")).json()["csrf_token"]
    reused = await late.client.post(
        "/api/v1/workspace/join", json={"code": code["code"]}, headers=late.headers()
    )
    assert reused.status_code == 410  # a code attaches one device, once
    assert (await late.client.get(f"/api/v1/runs/{first.run_id}")).status_code == 404

    # A run made without a session opens for anyone by its ID and is in nobody's list.
    anonymous = stack.browser()
    made = await anonymous.client.post("/api/v1/runs", json=CASE)  # fmt: skip
    assert made.status_code == 201
    assert SESSION_COOKIE not in anonymous.client.cookies
    nobodys = made.json()["run_id"]
    for b in browsers[:3]:
        assert (await b.client.get(f"/api/v1/runs/{nobodys}")).status_code == 200
        assert nobodys not in (await b.client.get("/api/v1/workspace/runs")).text

    # The admin sees every session and its counts, never a cookie or a token.
    admin = stack.browser()
    signed_in = await admin.client.post(
        "/api/v1/session/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    assert signed_in.status_code == 200
    listed = await admin.client.get("/api/v1/admin/sessions", params={"limit": 200})
    assert listed.status_code == 200
    page = listed.json()
    assert page["total"] == BROWSERS + 3  # the browsers, the phone, the late one, the admin
    by_workspace = {s["workspace_id"]: s for s in page["items"]}
    for b in browsers:
        counts = by_workspace[b.workspace]
        assert (counts["runs"], counts["uploads"], counts["investigations"]) == (1, 1, 1)
    for b in [*browsers, phone, late, admin]:
        assert b.client.cookies[SESSION_COOKIE] not in listed.text
        assert not b.csrf or b.csrf not in listed.text
    visitor = await browsers[1].client.get("/api/v1/admin/sessions")
    assert visitor.status_code == 403

    for b in [*browsers, phone, late, anonymous, admin]:
        await b.client.aclose()
    print(f"{BROWSERS} browsers: runs computed at once in {computed:.1f} s")


async def seed_the_example(stack: Stack) -> tuple[str, int]:
    """Import the real recorded run as a host does at startup; its ID and its event count."""
    runs = read_runs(RECORDED)
    report = await import_recorded(stack.persistence.database.sessionmaker, runs, None)
    (example,) = report.imported
    return example, len(runs.runs[0].events)


async def investigate_unit(b: Browser, unit: str) -> None:
    """`b` starts an investigation of its own, of a SECOM unit, and waits for its report."""
    created = await b.client.post(
        "/api/v1/investigations",
        json={"trigger": {"kind": "unit", "ref": unit}},
        headers=b.headers(),
    )
    assert created.status_code == 202, created.text
    b.investigation_id = created.json()["investigation_id"]
    await follow(b.client, f"/api/v1/investigations/{b.investigation_id}/events")


async def test_two_fresh_workspaces_both_see_the_recorded_example_and_not_each_other(
    stack: Stack,
) -> None:
    example, events = await seed_the_example(stack)
    a, b = await asyncio.gather(open_browser(stack, "Ana"), open_browser(stack, "Ben"))
    assert a.workspace != b.workspace
    await asyncio.gather(investigate_unit(a, "1304"), investigate_unit(b, "1305"))

    for me, other in ((a, b), (b, a)):
        page = (await me.client.get("/api/v1/investigations")).json()
        # Its own investigation in its list, counted; the example apart, the same for both.
        assert ([i["investigation_id"] for i in page["items"]], page["total"]) == (
            [me.investigation_id],
            1,
        )
        assert [(i["investigation_id"], i["recorded"]) for i in page["examples"]] == [
            (example, True)
        ]
        assert other.investigation_id not in str(page)
        # The example opens with its stored events, and is read-only.
        opened = await me.client.get(f"/api/v1/investigations/{example}")
        assert (opened.status_code, opened.json()["status"]) == (200, "awaiting_decision")
        assert len(await follow(me.client, f"/api/v1/investigations/{example}/events")) == events
        refused = await me.client.post(
            f"/api/v1/investigations/{example}/decision",
            json={"verdict": "approve"},
            headers=me.headers(),
        )
        assert refused.status_code == 403, refused.text
        assert (refused.json()["code"], refused.json()["title"]) == ("forbidden", "Read-only")
        # The other's investigation is what a missing ID is, on every route.
        hidden, missing = other.investigation_id, never_made(other.investigation_id)
        for route in ("", "/events", "/evidence/E1", "/report.md"):
            same_answer(
                await me.client.get(f"/api/v1/investigations/{hidden}{route}"),
                hidden,
                await me.client.get(f"/api/v1/investigations/{missing}{route}"),
                missing,
            )

    # Nobody changed it, and a request without a session lists the example and nothing else.
    assert (await a.client.get(f"/api/v1/investigations/{example}")).json()["decision"] is None
    anonymous = stack.browser()
    page = (await anonymous.client.get("/api/v1/investigations")).json()
    assert (page["items"], [i["investigation_id"] for i in page["examples"]]) == ([], [example])

    # An investigation of no workspace that is not recorded (one made before workspaces
    # existed) stays unlisted for everyone.
    async with stack.persistence.database.sessionmaker() as db, db.begin():
        await db.execute(
            update(InvestigationRow)
            .where(InvestigationRow.investigation_id == b.investigation_id)
            .values(workspace_id=None)
        )
    for viewer in (a, b, anonymous):
        page = (await viewer.client.get("/api/v1/investigations")).json()
        assert b.investigation_id not in str(page)
        assert [i["investigation_id"] for i in page["examples"]] == [example]
    for browser in (a, b, anonymous):
        await browser.client.aclose()


async def test_the_examples_work_order_and_audit_entries_are_listed_for_everyone_read_only(
    stack: Stack,
) -> None:
    example, _ = await seed_the_example(stack)
    # A host where a visitor approved the example before it was read-only keeps that decision.
    await decided_before(stack.persistence, example, "approve", "Lee")
    order = (await stack.persistence.investigations.get(example)).work_order_id
    assert order is not None
    a, b = await asyncio.gather(open_browser(stack, "Ana"), open_browser(stack, "Ben"))
    await investigate_unit(a, "1304")

    for me in (a, b):
        listed = (await me.client.get("/api/v1/work-orders")).json()
        assert [(o["work_order_id"], o["example"]) for o in listed["items"]] == [(order, True)]
        opened = await me.client.get(f"/api/v1/work-orders/{order}")
        assert (opened.status_code, opened.json()["example"]) == (200, True)
        changed = await me.client.patch(
            f"/api/v1/work-orders/{order}", json={"status": "done"}, headers=me.headers()
        )
        assert (changed.status_code, changed.json()["title"]) == (403, "Read-only")
        audit = (await me.client.get("/api/v1/audit", params={"limit": 200})).json()
        about = [(e["action"], e["target_id"]) for e in audit["items"] if e["example"]]
        assert about == [("investigation.approved", example), ("work_order.created", order)]
        # Everything else in its log is its own: its sessions, and its own investigation.
        rest = {(e["target_kind"], e["target_id"]) for e in audit["items"] if not e["example"]}
        own = {("investigation", me.investigation_id)} if me is a else set()
        assert {t for t in rest if t[0] != "session"} == own
        refused = await me.client.post(
            f"/api/v1/investigations/{example}/decision",
            json={"verdict": "reject"},
            headers=me.headers(),
        )
        assert refused.status_code == 403  # read-only, not "already decided"
    unchanged = (await b.client.get(f"/api/v1/work-orders/{order}")).json()
    assert (unchanged["status"], unchanged["note"]) == ("open", None)
    for browser in (a, b):
        await browser.client.aclose()
