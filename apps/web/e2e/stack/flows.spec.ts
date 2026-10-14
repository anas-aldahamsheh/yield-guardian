import { expect, type Page, test } from "@playwright/test";

import { discover, getJson } from "./api";

/**
 * The main flows on the composed stack with the real bundles. Every expected value is read
 * from the API first, so nothing here hard-codes a model number. The stack runs without
 * TOKEN_FACTORY_API_KEY: chat and live investigations must show their not-configured state
 * and must never reach Token Factory.
 */

type Ids = Awaited<ReturnType<typeof discover>>;
let ids: Ids;

test.beforeAll(async ({ request }) => {
  ids = await discover(request);
});

function watch(page: Page) {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && /Content Security Policy|Refused to|Hydration/i.test(m.text())) problems.push(`console: ${m.text()}`);
  });
  return problems;
}

test("the API is ready with both bundles verified", async ({ request }) => {
  const ready = await getJson<{ ready: boolean }>(request, "/ready");
  expect(ready.ready).toBe(true);
  const meta = await getJson<{ bundles: { verified: boolean }[]; features: { chat: boolean; live_investigations: boolean } }>(request, "/meta");
  expect(meta.bundles.length).toBeGreaterThanOrEqual(2);
  expect(meta.bundles.every((b) => b.verified)).toBe(true);
  // These tests are for a stack without a language model key.
  expect(meta.features).toMatchObject({ chat: false, live_investigations: false });
});

test("home: the results table is filled from /results", async ({ page, request }) => {
  const problems = watch(page);
  const { results } = await getJson<{ results: { label: string; estimate: unknown }[] }>(request, "/results");
  const measured = results.filter((r) => r.estimate != null);
  expect(measured.length, "the real bundles measure at least one headline result").toBeGreaterThan(0);

  await page.goto("/");
  const table = page.getByRole("table", { name: "Measured results with confidence intervals" });
  await expect(table.locator("tbody tr")).toHaveCount(results.length);
  for (const r of measured) {
    const row = table.getByRole("row").filter({ has: page.getByRole("rowheader", { name: r.label }) });
    await expect(row).toHaveCount(1);
    await expect(row).not.toContainText("Not measured yet");
  }
  expect(problems).toEqual([]);
});

test("line: goes live over the WebSocket and units arrive", async ({ page }) => {
  const problems = watch(page);
  const frames: string[] = [];
  page.on("websocket", (ws) => ws.on("framereceived", (f) => typeof f.payload === "string" && frames.push(f.payload)));

  await page.goto("/line");
  await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("heading", { name: "Control charts (FDC)" })).toBeVisible();
  const units = page.getByRole("table", { name: /Recent units/ }).locator("tbody tr");
  await expect(units.first()).toBeVisible();
  // A unit event arrives over the socket after the snapshot.
  await expect.poll(() => frames.filter((f) => f.includes('"unit"')).length, { timeout: 60_000 }).toBeGreaterThan(1);
  expect(problems).toEqual([]);
});

test("unit: page with its control-chart contributions", async ({ page }) => {
  const problems = watch(page);
  await page.goto(`/units/${ids.unit}`);
  await expect(page.locator("h1")).toHaveText(`Unit ${ids.unit.toLocaleString("en-US")}`);
  await expect(page.getByRole("heading", { name: "Sensors behind the control-chart statistic" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Alarms and investigations" })).toBeVisible();
  await expect(page.getByText("The API did not answer")).toHaveCount(0);
  expect(problems).toEqual([]);
});

test("wafer lab: list and a selected wafer", async ({ page }) => {
  const problems = watch(page);
  await page.goto(`/wafers?wafer=${ids.wafer}`);
  await expect(page.locator("h1")).toHaveText("Wafer lab");
  await expect(page.getByRole("heading", { name: `Wafer ${ids.wafer}` })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Most similar wafers" })).toBeVisible();
  expect(problems).toEqual([]);
});

test("lot: the stack and the pattern test", async ({ page }) => {
  const problems = watch(page);
  await page.goto(`/lots/${ids.lot}`);
  await expect(page.locator("h1")).toHaveText(`Lot ${ids.lot}`);
  await expect(page.getByRole("heading", { name: "The lot as a stack" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Patterns against the expected rate" })).toBeVisible();
  expect(problems).toEqual([]);
});

test("sensor health: field, a sensor and the groups", async ({ page }) => {
  const problems = watch(page);
  await page.goto("/sensors?sensor=S060");
  await expect(page.locator("h1")).toHaveText("Sensor health");
  const field = page.getByRole("img", { name: /Health of \d+ sensors/ });
  await expect(field).toBeVisible();
  await field.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(/sensor=S061/);
  await expect(page.getByRole("heading", { name: "Sensor groups associated with failure" })).toBeVisible();
  expect(problems).toEqual([]);
});

test("methods: every model card renders", async ({ page, request }) => {
  const problems = watch(page);
  const methods = await getJson<{ model_cards: { name: string; title: string }[] }>(request, "/methods");
  expect(methods.model_cards.length).toBeGreaterThan(0);
  await page.goto("/methods");
  await expect(page.locator("h1")).toHaveText("Methods");
  const panel = page.locator("section, div").filter({ has: page.getByRole("heading", { name: "Model cards", exact: true }) }).last();
  for (const card of methods.model_cards) {
    if (methods.model_cards.length > 1) await page.getByRole("radio", { name: card.title }).click();
    // The card's markdown has its own headings once it loads.
    await expect(panel.getByRole("heading").nth(1)).toBeVisible();
    await expect(panel.getByText("Loading the model card")).toHaveCount(0);
  }
  expect(problems).toEqual([]);
});

test("guest session: Try as engineer signs in", async ({ page }) => {
  await page.goto(`/units/${ids.unit}`);
  await page.getByRole("button", { name: "Try as engineer", exact: true }).first().click();
  await expect(page.getByText("Engineer", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Investigate this unit" })).toBeVisible();
});

test("investigation without a key: not-configured state, no Token Factory call", async ({ page }) => {
  const outbound: string[] = [];
  page.on("request", (r) => /tokenfactory|token-factory|amd\.com/i.test(r.url()) && outbound.push(r.url()));

  await page.goto("/investigations");
  await expect(page.getByRole("note")).toContainText("Live investigations are not configured on this server");

  await page.goto(`/units/${ids.unit}`);
  await page.getByRole("button", { name: "Try as engineer", exact: true }).first().click();
  const start = page.waitForResponse((r) => r.url().endsWith("/api/v1/investigations") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Investigate this unit" }).click();
  expect((await start).status()).toBe(503);
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: "not configured" })).toContainText(
    "Live investigations are not configured on this server",
  );
  await expect(page).toHaveURL(new RegExp(`/units/${ids.unit}$`));
  expect(outbound).toEqual([]);
});

test("chat without a key: not-configured state, nothing sent", async ({ page }) => {
  const chats: string[] = [];
  page.on("request", (r) => r.url().includes("/api/v1/chat") && chats.push(r.url()));

  await page.goto(`/units/${ids.unit}`);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("note")).toContainText("Chat is not configured on this server");
  await expect(sheet.getByRole("textbox", { name: "Question" })).toHaveCount(0);
  expect(chats).toEqual([]);
});

test("work orders: the list and the audit log match the API", async ({ page, request }) => {
  const problems = watch(page);
  const list = await getJson<{ total: number }>(request, "/work-orders");
  await page.goto("/work-orders");
  await expect(page.locator("h1")).toHaveText("Work orders");
  if (list.total === 0) {
    await expect(page.getByText("No work orders yet")).toBeVisible();
  } else {
    await expect(page.getByRole("link", { name: ids.workOrder! }).first()).toBeVisible();
    await page.goto(`/work-orders/${ids.workOrder}`);
    await expect(page.getByRole("heading", { name: "History" })).toBeVisible();
  }
  await expect(page.getByRole("heading", { name: /Audit log/ })).toBeVisible();
  expect(problems).toEqual([]);
});
