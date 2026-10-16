import { readFile } from "node:fs/promises";

import { SESSION_COOKIE } from "@yield-guardian/contracts";
import {
  expect,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Page,
  test,
} from "@playwright/test";

import { expectAccessible } from "../axe";
import { getJson } from "./api";

/**
 * Every visitor is a separate user, without signing in: each browser context here is one device
 * with a workspace of its own, on the real API and PostgreSQL. A run, its event stream and its
 * results belong to the workspace that made it; another visitor gets exactly the answer an ID
 * that never existed gets. Devices joined with a handoff code share one workspace.
 *
 * The runs are real: cases from the API's catalogue (SECOM units, WM-811K wafers) and real
 * samples. Nothing is investigated: the stack has no model key, and no test presses
 * Investigate. What every visitor sees alike is the product's example, the real recorded
 * investigation the API seeds at startup, read-only. The admin test signs in with
 * E2E_ADMIN_USERNAME and E2E_ADMIN_PASSWORD (the stack's own admin) and is skipped without them.
 */

type Case = { case_id: string; title: string };
type Listed = {
  run_id: string;
  title: string;
  status: string;
  alarms: number;
  view: string | null;
  label: string | null;
};

let alarming: Case;

test.beforeAll(async ({ request }) => {
  const cases = await getJson<{ items: Case[] }>(request, "/runs/cases");
  // A unit past its SPE limit raises alarms on any bundle; any case will do when it is absent.
  alarming = cases.items.find((c) => c.case_id === "spe_alarm") ?? cases.items[0]!;
});

/** A device of its own: a new browser context, so a separate visitor. */
async function device(browser: Browser): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext();
  return { context, page: await context.newPage() };
}

const work = (page: Page) => page.locator("[data-your-work]");
/** The page's alert that says `text` (Next.js keeps an empty route announcer with role alert). */
const alertWith = (page: Page, text: string) => page.getByRole("alert").filter({ hasText: text });
const NO_RUN =
  "There is no run with this link here. It may belong to another workspace, or the link is incomplete. Start a new one.";
const card = (page: Page, runId: string) => work(page).locator(`[data-run="${runId}"]`);

/** Opens a page of the Line and waits until this device's workspace is open and read. */
async function openLine(page: Page, path = "/") {
  await page.goto(path);
  await expect(work(page).getByText(/^\d+ (archived )?runs?$/)).toBeVisible();
}

/** A new run: POST /runs, or POST /runs/{id}/again for the same input. */
const RUN_CREATED = /^\/api\/v1\/runs(\/run_[0-9a-z]+\/again)?$/;

/** Waits for the run the page starts, and returns its ID once the Line shows it. */
async function started(page: Page, press: () => Promise<void>): Promise<string> {
  const created = page.waitForResponse(
    (r) => r.request().method() === "POST" && RUN_CREATED.test(new URL(r.url()).pathname),
  );
  await press();
  const response = await created;
  expect(response.status()).toBe(201);
  const { run_id: runId } = (await response.json()) as { run_id: string };
  await expect(page).toHaveURL(new RegExp(`[?&]run=${runId}(&|$)`));
  return runId;
}

async function runCase(page: Page, c: Case): Promise<string> {
  const panel = page.getByRole("region", { name: "Pick a case" });
  if (!(await panel.isVisible())) await page.getByRole("button", { name: "Pick a case" }).click();
  return started(page, () => panel.getByRole("button", { name: `Run: ${c.title}` }).click());
}

async function runSample(page: Page): Promise<string> {
  return started(page, () => page.getByRole("button", { name: "Try a real sample" }).click());
}

/** Waits until the run's card says it is done ("Done, 2 alarms, 4 warnings", or no alarms). */
async function done(page: Page, runId: string) {
  await expect(card(page, runId)).toContainText(/Done, (no alarms|\d+ (alarm|warning)s?)/, {
    timeout: 60_000,
  });
}

async function listed(request: APIRequestContext, archived = false): Promise<Listed[]> {
  return (
    await getJson<{ items: Listed[] }>(request, `/workspace/runs?archived=${archived}&limit=50`)
  ).items;
}

async function sessionOf(request: APIRequestContext) {
  return getJson<{ csrf_token: string | null; workspace: { workspace_id: string } | null }>(
    request,
    "/session",
  );
}

const FINISHED = "The run is finished: every station has its result, and nothing more will arrive.";

/** Waits until the line has shown every result of a run that is done. */
async function finished(page: Page) {
  const showAll = page.getByRole("button", { name: "Show every result now" });
  await expect(async () => {
    if (await showAll.isVisible()) await showAll.click();
    await expect(page.getByText(FINISHED)).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 90_000 });
}

/** What the line shows of its run: the heading, each station's result and the alarms rail. */
async function lineOf(page: Page) {
  const squash = (s: string) => s.replace(/\s+/g, " ").trim();
  const rail = "section[aria-labelledby=alarms-title]";
  return {
    title: squash(await page.locator("#run-title").innerText()),
    stations: await Promise.all(
      ["1 Manufacturing", "2 Monitoring", "3 Wafer test", "Final test"].map(async (name) =>
        // The 3D wafer's colour note loads later; it is not part of the result.
        squash(await page.getByRole("group", { name }).innerText()).replace(
          / Wafer colour: an assumed \d+ nm oxide film\./,
          "",
        ),
      ),
    ),
    count: (await page.locator(`${rail} header p`).allInnerTexts()).map(squash),
    alarms: (await page.locator(`${rail} h3`).allInnerTexts()).map(squash),
    finished: await page.getByText(FINISHED).count(),
  };
}

/** The page a visitor is shown, with `id` written as ID: what any other ID would show. */
async function pageFor(page: Page, id: string) {
  return (await page.locator("main").innerText()).replace(/\s+/g, " ").replaceAll(id, "ID");
}

/** Opens a run's menu on its card and picks an item. */
async function fromMenu(page: Page, name: string, item: string) {
  await work(page)
    .getByRole("button", { name: `More actions for ${name}` })
    .click();
  await page.getByRole("menuitem", { name: item }).click();
}

test("every visitor sees the recorded example, apart from its own work and read-only", async ({
  browser,
}) => {
  const visitors = [await device(browser), await device(browser)];
  const links: (string | null)[] = [];
  for (const { page } of visitors) {
    await page.goto("/investigations");
    await expect(page.getByText("No investigations yet")).toBeVisible();
    const example = page.locator("[data-group='example']");
    await expect(example.locator("tbody tr")).toHaveCount(1);
    await expect(example.locator("tbody tr")).toContainText("Recorded");
    links.push(await example.getByRole("link").first().getAttribute("href"));
  }
  expect(links[0]).toMatch(/^\/investigations\/inv_[0-9a-z]+$/);
  expect(links[1]).toBe(links[0]);

  // An engineer opens it: the page says it is read-only, and the API refuses a decision.
  type Shown = { status: string; decision: unknown; work_order_id: string | null };
  const before = await getJson<Shown>(visitors[0]!.page.request, links[0]!);
  const { page } = visitors[1]!;
  await page.goto(links[0]!);
  await page.getByRole("button", { name: "Try as engineer" }).first().click();
  await expect(page.getByText("Engineer", { exact: true }).first()).toBeVisible();
  // (A host where it was decided before it was read-only shows that decision instead.)
  if (before.status === "awaiting_decision")
    await expect(page.locator("[data-example-note]")).toContainText("nobody decides it");
  await expect(page.getByRole("checkbox", { name: /^Approve action/ })).toHaveCount(0);
  const { csrf_token: csrf } = await sessionOf(page.request);
  const refused = await page.request.post(`/api/v1${links[0]!}/decision`, {
    data: { verdict: "reject" },
    headers: { "X-CSRF-Token": csrf! },
  });
  expect(refused.status()).toBe(403);
  // It is unchanged for the other visitor (the page's link is the API path under /api/v1).
  const after = await getJson<Shown>(visitors[0]!.page.request, links[0]!);
  expect([after.status, after.decision, after.work_order_id]).toEqual([
    before.status,
    before.decision,
    before.work_order_id,
  ]);
  for (const v of visitors) await v.context.close();
});

test("another visitor gets no run from a link: the same answer as an ID that never existed", async ({
  browser,
}) => {
  const a = await device(browser);
  const b = await device(browser);
  await openLine(a.page);
  const runId = await runCase(a.page, alarming);
  await done(a.page, runId);
  await expect(card(a.page, runId)).toContainText("On the line now");
  await expect(
    a.page.getByRole("heading", { level: 2, name: alarming.title }).first(),
  ).toBeVisible();

  // B opens A's link: a clear not-found state, nothing of A's run.
  await openLine(b.page, `/?run=${runId}`);
  await expect(alertWith(b.page, NO_RUN)).toBeVisible();
  await expect(b.page.getByRole("heading", { level: 2, name: alarming.title })).toHaveCount(0);
  await expect(work(b.page).getByText("No runs yet")).toBeVisible();
  await expect(work(b.page).locator("[data-run]")).toHaveCount(0);
  expect(await listed(b.page.request)).toEqual([]);

  // Every route of the run answers B as it answers for an ID that never existed.
  const never = `${runId.slice(0, -1)}${runId.endsWith("0") ? "1" : "0"}`;
  const { csrf_token: csrf } = await sessionOf(b.page.request);
  const headers = { "X-CSRF-Token": csrf ?? "" };
  const calls: [string, (id: string) => Promise<{ status(): number; text(): Promise<string> }>][] =
    [
      ["the run", (id) => b.page.request.get(`/api/v1/runs/${id}`)],
      ["its events", (id) => b.page.request.get(`/api/v1/runs/${id}/events`)],
      ["its results", (id) => b.page.request.get(`/api/v1/runs/${id}/results.csv`)],
      ["a unit's chart", (id) => b.page.request.get(`/api/v1/runs/${id}/units/0/chart`)],
      ["a comparison", (id) => b.page.request.get(`/api/v1/runs/${id}/compare/${id}`)],
      ["run it again", (id) => b.page.request.post(`/api/v1/runs/${id}/again`, { headers })],
      [
        "rename it",
        (id) =>
          b.page.request.patch(`/api/v1/workspace/runs/${id}`, {
            headers,
            data: { label: "Not mine" },
          }),
      ],
    ];
  for (const [what, call] of calls) {
    const theirs = await call(runId);
    const none = await call(never);
    expect(theirs.status(), what).toBe(404);
    expect((await theirs.text()).replaceAll(runId, "ID"), what).toBe(
      (await none.text()).replaceAll(never, "ID"),
    );
  }
  // A still has its run, unchanged by B.
  const own = await listed(a.page.request);
  expect(own.map((r) => [r.run_id, r.label])).toEqual([[runId, null]]);
  expect((await a.page.request.get(`/api/v1/runs/${runId}/results.csv`)).status()).toBe(200);

  await a.context.close();
  await b.context.close();
});

test("a reload shows your own run as it stood; another visitor's, as an ID that never existed", async ({
  browser,
}) => {
  const a = await device(browser);
  const b = await device(browser);
  await openLine(a.page);
  const runId = await runCase(a.page, alarming);
  await done(a.page, runId);
  await finished(a.page);
  const before = await lineOf(a.page);
  expect(before.title).toBe(alarming.title);
  expect(before.finished).toBe(1);

  // The server reads the run for the page with A's session cookie: the page comes with it.
  const sent = await (await a.page.request.get(`/?run=${runId}`)).text();
  expect(sent).toContain(FINISHED);
  expect(sent).not.toContain("Reading the run");
  expect(sent).not.toContain(NO_RUN);
  await a.page.reload({ waitUntil: "domcontentloaded" });
  expect(await lineOf(a.page)).toEqual(before);
  await expect(card(a.page, runId)).toContainText("On the line now");

  // For B, the server reads A's run as not found: the page an ID that never existed gets.
  const never = `${runId.slice(0, -1)}${runId.endsWith("0") ? "1" : "0"}`;
  await openLine(b.page);
  for (const id of [runId, never]) {
    const html = await (await b.page.request.get(`/?run=${id}`)).text();
    expect(html, id).toContain(NO_RUN);
    expect(html, id).not.toContain(FINISHED);
    expect(html, id).not.toContain("Reading the run");
  }
  await b.page.goto(`/?run=${runId}`);
  await b.page.reload();
  await expect(alertWith(b.page, NO_RUN)).toBeVisible();
  await expect(work(b.page).getByText("No runs yet")).toBeVisible();
  await expect(b.page.locator("#run-title")).toHaveCount(0);
  const theirs = await pageFor(b.page, runId);
  await b.page.goto(`/?run=${never}`);
  await b.page.reload();
  await expect(alertWith(b.page, NO_RUN)).toBeVisible();
  await expect(work(b.page).getByText("No runs yet")).toBeVisible();
  expect(await pageFor(b.page, never)).toBe(theirs);

  // A's run is still A's, as it stood.
  await a.page.reload({ waitUntil: "domcontentloaded" });
  expect(await lineOf(a.page)).toEqual(before);

  await a.context.close();
  await b.context.close();
});

test("history: a new run keeps the old one, and each reopens where it was left", async ({
  browser,
}) => {
  const a = await device(browser);
  const page = a.page;
  await openLine(page);
  const first = await runCase(page, alarming);
  await done(page, first);

  // Open the monitoring details: the view is saved with the run.
  await page.getByRole("button", { name: "Open monitoring details" }).click();
  await expect(page).toHaveURL(new RegExp(`run=${first}&station=2`));
  await expect
    .poll(async () => (await listed(page.request)).find((r) => r.run_id === first)?.view, {
      timeout: 15_000,
    })
    .toMatch(new RegExp(`^run=${first}&station=2`));

  // A second run: the first is kept, each with its own status.
  const second = await runSample(page);
  await done(page, second);
  await expect(card(page, second)).toContainText("On the line now");
  await expect(card(page, first)).not.toContainText("On the line now");
  await expect(work(page).getByText("2 runs", { exact: true })).toBeVisible();
  const both = await listed(page.request);
  expect(both.map((r) => r.run_id)).toEqual([second, first]);
  expect(both.every((r) => r.status === "done")).toBe(true);
  await expectAccessible(page, "Your work with two runs", "[data-your-work]", true);

  // Reopen the first where it was left: on the monitoring details, which take the focus, so a
  // keyboard user goes on from there.
  await fromMenu(page, alarming.title, "Reopen where you left it");
  await expect(page).toHaveURL(new RegExp(`run=${first}&station=2`));
  const details = page.getByRole("heading", { level: 2, name: "2 Monitoring in detail" });
  await expect(details).toBeVisible();
  await expect(details).toBeFocused();
  await expect(card(page, first)).toContainText("On the line now");

  // The second was left on no station: its heading on the line takes the focus.
  const sample = both.find((r) => r.run_id === second)!.title;
  await fromMenu(page, sample, "Reopen where you left it");
  await expect(page).toHaveURL(new RegExp(`run=${second}(&|$)`));
  await expect(page.locator("#run-title")).toHaveText(sample);
  await expect(page.locator("#run-title")).toBeFocused();
  await expect(card(page, second)).toContainText("On the line now");

  // And back to the first, as it was left.
  await fromMenu(page, alarming.title, "Reopen where you left it");
  await expect(details).toBeFocused();

  // A reload keeps it all: the run on the line and both in Your work.
  await page.reload();
  await expect(page).toHaveURL(new RegExp(`run=${first}&station=2`));
  await expect(card(page, first)).toBeVisible();
  await expect(card(page, second)).toBeVisible();

  // Becoming an engineer keeps the workspace.
  await page.getByRole("button", { name: "Try as engineer", exact: true }).first().click();
  await expect(page.getByText("Engineer", { exact: true }).first()).toBeVisible();
  await expect(card(page, first)).toBeVisible();
  await expect(card(page, second)).toBeVisible();
  expect((await listed(page.request)).map((r) => r.run_id)).toEqual([second, first]);

  await a.context.close();
});

test("a run's actions: rename, run again, compare, download, archive and restore", async ({
  browser,
}) => {
  const a = await device(browser);
  const page = a.page;
  await openLine(page);
  const first = await runCase(page, alarming);
  await done(page, first);

  // Rename and note (test inputs).
  await fromMenu(page, alarming.title, "Rename or add a note");
  const rename = page.getByRole("dialog", { name: "Rename or note this run" });
  await rename.getByLabel("Name").fill("Tool 7 after the fix");
  await rename.getByLabel("Note").fill("Chamber seal replaced before this run.");
  await rename.getByRole("button", { name: "Save" }).click();
  await expect(rename).toBeHidden();
  await expect(card(page, first).getByRole("heading", { level: 3 })).toHaveText(
    "Tool 7 after the fix",
  );
  await expect(card(page, first)).toContainText("Chamber seal replaced before this run.");

  // Run the same input again: a new run, the first kept.
  const again = await started(page, () =>
    fromMenu(page, "Tool 7 after the fix", "Run the same input again"),
  );
  expect(again).not.toBe(first);
  await done(page, again);
  await expect(work(page).locator("[data-run]")).toHaveCount(2);

  // Compare the new run with the one it repeats.
  await fromMenu(page, alarming.title, "Compare with another run");
  const compare = page.getByRole("dialog", { name: "Compare two runs" });
  await expect(compare.getByText("Both runs computed exactly the same input.")).toBeVisible();
  await expect(compare.getByRole("table", { name: "The two runs side by side" })).toBeVisible();
  await expect(compare.getByRole("table", { name: "The stages of the two runs" })).toBeVisible();
  await expectAccessible(page, "compare dialog", "[role='dialog']", true);
  await page.keyboard.press("Escape");
  await expect(compare).toBeHidden();

  // The results as CSV: the API's own file for this run.
  const download = page.waitForEvent("download");
  await fromMenu(page, "Tool 7 after the fix", "Download the results (CSV)");
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.csv$/);
  const csv = await readFile((await file.path())!, "utf8");
  const fromApi = await (await page.request.get(`/api/v1/runs/${first}/results.csv`)).text();
  expect(csv).toBe(fromApi);
  expect(csv.split("\n").filter(Boolean).length).toBeGreaterThan(1);

  // Archive: out of Your work, into the archived runs, and back.
  await fromMenu(page, "Tool 7 after the fix", "Archive");
  await expect(card(page, first)).toHaveCount(0);
  await expect(work(page).getByText("1 run", { exact: true })).toBeVisible();
  await work(page).getByRole("button", { name: "Workspace options" }).click();
  await page.getByRole("menuitem", { name: "Show archived runs" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Your archived runs" })).toBeVisible();
  await expect(card(page, first)).toBeVisible();
  await card(page, first).getByRole("button", { name: "Restore" }).click();
  await expect(work(page).getByText("No archived runs")).toBeVisible();
  await work(page).getByRole("button", { name: "Show your runs" }).click();
  await expect(work(page).locator("[data-run]")).toHaveCount(2);
  expect((await listed(page.request)).map((r) => [r.run_id, r.label])).toEqual([
    [again, null],
    [first, "Tool 7 after the fix"],
  ]);

  await a.context.close();
});

test("Investigate alarms shows the run's alarms; nothing is investigated without a press", async ({
  browser,
}) => {
  const a = await device(browser);
  const page = a.page;
  const investigations: string[] = [];
  page.on(
    "request",
    (r) =>
      r.method() === "POST" &&
      new URL(r.url()).pathname.startsWith("/api/v1/investigations") &&
      investigations.push(r.url()),
  );
  await openLine(page);
  const runId = await runCase(page, alarming);
  await done(page, runId);
  const run = (await listed(page.request)).find((r) => r.run_id === runId)!;
  test.skip(run.alarms === 0, "this bundle raises no alarm on the case");

  // Leave the run, then come back to it from its card.
  await page.getByRole("button", { name: "Open monitoring details" }).click();
  await runSample(page);
  await card(page, runId).getByRole("button", { name: "Investigate alarms" }).click();
  await expect(page).toHaveURL(new RegExp(`run=${runId}`));
  await expect(page.locator("#alarms-title")).toBeInViewport();
  await expect(
    page.getByRole("region", { name: "Alarms of this run" }).locator("article").first(),
  ).toBeVisible();
  expect(investigations).toEqual([]);

  await a.context.close();
});

test("continue on another device: a code brings it into the workspace, once", async ({
  browser,
}) => {
  const a = await device(browser);
  await openLine(a.page);
  const runId = await runCase(a.page, alarming);
  await done(a.page, runId);

  await work(a.page).getByRole("button", { name: "Continue on another device" }).click();
  const dialog = a.page.getByRole("dialog", { name: "Continue on another device" });
  const shown = dialog.locator("[data-handoff-code] [aria-hidden='true']");
  await expect(shown).toHaveText(/^[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){2}$/);
  const code = (await shown.textContent())!;
  const link = await dialog.getByLabel("Link").inputValue();
  expect(link).toBe(`${new URL(a.page.url()).origin}/join#code=${code}`);
  await expectAccessible(a.page, "handoff dialog", "[role='dialog']", true);

  // C opens the link: the code fills in and leaves the address bar; joining waits for a press.
  const c = await device(browser);
  await c.page.goto(link);
  await expect(c.page.getByLabel("Code")).toHaveValue(code);
  await expect(c.page).toHaveURL(/\/join$/);
  const before = (await sessionOf(c.page.request)).workspace?.workspace_id;
  expect(before).not.toBe((await sessionOf(a.page.request)).workspace!.workspace_id);
  await c.page.getByRole("button", { name: "Join the workspace" }).click();
  await expect(c.page).toHaveURL(/\/$/);
  await expect(card(c.page, runId)).toBeVisible();
  expect((await sessionOf(c.page.request)).workspace!.workspace_id).toBe(
    (await sessionOf(a.page.request)).workspace!.workspace_id,
  );
  await expect(
    dialog.getByText("Another device joined: it sees this workspace now."),
  ).toBeVisible();

  // C opens the run as A does.
  await openLine(c.page, `/?run=${runId}`);
  await expect(
    c.page.getByRole("heading", { level: 2, name: alarming.title }).first(),
  ).toBeVisible();
  await expect(c.page.getByText(NO_RUN)).toHaveCount(0);
  await expect(work(c.page)).toContainText("on 2 devices");

  // What C starts is A's too.
  const fromC = await runSample(c.page);
  await expect
    .poll(async () => (await listed(a.page.request)).map((r) => r.run_id))
    .toEqual([fromC, runId]);

  // The code is used up.
  const d = await device(browser);
  await d.page.goto("/join");
  await d.page.getByLabel("Code").fill(code);
  await d.page.getByRole("button", { name: "Join the workspace" }).click();
  await expect(d.page.locator("#join-error")).toHaveText(
    "This code has already been used. Make a new one on the other device.",
  );
  await openLine(d.page, `/?run=${runId}`);
  await expect(alertWith(d.page, NO_RUN)).toBeVisible();

  for (const x of [a, c, d]) await x.context.close();
});

test("admin: device sessions with counts and an end, never a cookie or another's runs", async ({
  browser,
}) => {
  const username = process.env.E2E_ADMIN_USERNAME ?? "admin";
  const password = process.env.E2E_ADMIN_PASSWORD;
  test.skip(!password, "set E2E_ADMIN_PASSWORD to the stack's admin password");

  // X: a visitor with a run.
  const x = await device(browser);
  await openLine(x.page);
  const runId = await runCase(x.page, alarming);
  await done(x.page, runId);
  const xWorkspace = (await sessionOf(x.page.request)).workspace!.workspace_id;

  // The admin's device makes a run as a visitor first; signing in keeps it.
  const admin = await device(browser);
  await openLine(admin.page);
  const own = await runSample(admin.page);
  await done(admin.page, own);
  await admin.page.goto("/admin");
  await admin.page.getByRole("button", { name: "Admin sign-in" }).first().click();
  const signIn = admin.page.getByRole("dialog", { name: "Admin sign-in" });
  await signIn.getByLabel("Username").fill(username);
  await signIn.getByLabel("Password").fill(password!);
  await signIn.getByRole("button", { name: "Sign in" }).click();
  await expect(signIn).toBeHidden();

  const table = admin.page.getByRole("table", { name: "Device sessions" });
  await expect(table).toBeVisible();
  const mine = table.getByRole("row").filter({ hasText: "· this session" });
  await expect(mine).toContainText("Admin");
  await expect(mine).toContainText("1 run");
  await expect(mine.getByRole("button", { name: /^End session / })).toBeDisabled();
  const row = table.getByRole("row").filter({ hasText: xWorkspace.slice(0, 8) });
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("Visitor");
  await expect(row).toContainText("1 run");
  await expectAccessible(admin.page, "admin device sessions", undefined, false);

  // Counts only: no cookie value, token or run of another visitor on the page or in the API.
  const secrets = [...(await x.context.cookies()), ...(await admin.context.cookies())]
    .filter((cookie) => cookie.name === SESSION_COOKIE)
    .map((cookie) => cookie.value);
  expect(secrets).toHaveLength(2);
  const tokens = [
    (await sessionOf(x.page.request)).csrf_token!,
    (await sessionOf(admin.page.request)).csrf_token!,
  ];
  const html = await admin.page.content();
  const api = await (await admin.page.request.get("/api/v1/admin/sessions?limit=200")).text();
  for (const secret of [...secrets, ...tokens]) {
    expect(html).not.toContain(secret);
    expect(api).not.toContain(secret);
  }
  expect(html).not.toContain(runId);
  expect(api).not.toContain(runId);
  // Signing in kept the admin's own workspace; another visitor's run stays out of it.
  expect((await listed(admin.page.request)).map((r) => r.run_id)).toEqual([own]);
  expect((await admin.page.request.get(`/api/v1/runs/${runId}`)).status()).toBe(404);

  // End X's session: X goes on as a new visitor with an empty workspace.
  await row.getByRole("button", { name: /^End session / }).click();
  const confirm = admin.page.getByRole("alertdialog", { name: "End this device session?" });
  await expect(confirm).toContainText("No other device uses its workspace");
  await confirm.getByRole("button", { name: "End the session" }).click();
  await expect(
    admin.page.locator("[data-sonner-toast]").filter({ hasText: "Session ended" }),
  ).toBeVisible();
  await expect(row).toHaveCount(0);
  await openLine(x.page, `/?run=${runId}`);
  await expect(alertWith(x.page, NO_RUN)).toBeVisible();
  await expect(work(x.page).getByText("No runs yet")).toBeVisible();
  expect((await sessionOf(x.page.request)).workspace!.workspace_id).not.toBe(xWorkspace);

  await x.context.close();
  await admin.context.close();
});
