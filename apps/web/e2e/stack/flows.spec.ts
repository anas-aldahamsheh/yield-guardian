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
    if (m.type() === "error" && /Content Security Policy|Refused to|Hydration/i.test(m.text()))
      problems.push(`console: ${m.text()}`);
  });
  return problems;
}

test("the API is ready with both bundles verified", async ({ request }) => {
  const ready = await getJson<{ ready: boolean }>(request, "/ready");
  expect(ready.ready).toBe(true);
  const meta = await getJson<{
    bundles: { verified: boolean }[];
    features: { chat: boolean; live_investigations: boolean };
  }>(request, "/meta");
  expect(meta.bundles.length).toBeGreaterThanOrEqual(2);
  expect(meta.bundles.every((b) => b.verified)).toBe(true);
  // These tests are for a stack without a language model key.
  expect(meta.features).toMatchObject({ chat: false, live_investigations: false });
});

test("how it works: the results table is filled from /results", async ({ page, request }) => {
  const problems = watch(page);
  const { results } = await getJson<{ results: { label: string; estimate: unknown }[] }>(
    request,
    "/results",
  );
  const measured = results.filter((r) => r.estimate != null);
  expect(measured.length, "the real bundles measure at least one headline result").toBeGreaterThan(
    0,
  );

  await page.goto("/how#results");
  const table = page.locator("#results").getByRole("table", { name: "Measured results" });
  await expect(table.locator("tbody tr")).toHaveCount(results.length);
  for (const r of measured) {
    const row = table
      .getByRole("row")
      .filter({ has: page.getByRole("rowheader", { name: r.label }) });
    await expect(row).toHaveCount(1);
    await expect(row).not.toContainText("Not measured yet");
  }
  expect(problems).toEqual([]);
});

test("redirects: v1 addresses move permanently to their v2 place", async ({ request }) => {
  for (const [from, to] of [
    ["/line", "/"],
    [`/units/${ids.unit}`, `/?pick=unit:${ids.unit}`],
    [`/lots/${ids.lot}`, `/?pick=lot:${ids.lot}`],
    ["/methods", "/how#methods"],
    ["/work-orders", "/investigations?tab=work-orders"],
  ] as const) {
    const response = await request.get(from, { maxRedirects: 0 });
    expect(response.status(), from).toBe(308);
    expect(response.headers()["location"], from).toBe(to);
  }
});

test("how it works: the plain limits carry the bundle's numbers", async ({ page, request }) => {
  const problems = watch(page);
  const metrics = await getJson<{
    models: { main: boolean; metrics: { metric: string; estimate: { value: number } }[] }[];
  }>(request, "/methods/secom");
  const points = await getJson<{
    default: string;
    points: { id: string; tp: number; fn: number }[];
  }>(request, "/secom/operating-points");
  const roc = metrics.models.find((m) => m.main)!.metrics.find((x) => x.metric === "roc_auc")!
    .estimate.value;
  const point = points.points.find((p) => p.id === points.default)!;
  await page.goto("/how#limits");
  const limits = page.locator("[data-limits]");
  await expect(limits).toContainText(roc.toFixed(2));
  await expect(limits.locator("bdi", { hasText: new RegExp(`^${point.tp}$`) })).toHaveCount(1);
  await expect(
    limits.locator("bdi", { hasText: new RegExp(`^${point.tp + point.fn}$`) }),
  ).toHaveCount(1);
  expect(problems).toEqual([]);
});

test("how it works: every model card renders", async ({ page, request }) => {
  const problems = watch(page);
  const methods = await getJson<{ model_cards: { name: string; title: string }[] }>(
    request,
    "/methods",
  );
  expect(methods.model_cards.length).toBeGreaterThan(0);
  await page.goto("/how#models");
  await page.locator("#models summary", { hasText: "Model cards" }).click();
  await expect(page.getByRole("heading", { name: "Model cards", exact: true })).toBeVisible();
  const seen = new Set<string>();
  for (const card of methods.model_cards) {
    if (methods.model_cards.length > 1) await page.getByRole("radio", { name: card.title }).click();
    // Each card is the bundle's own markdown, headed "Model card: …".
    const heading = page.getByRole("heading", { name: /^Model card: / });
    await expect(heading).toBeVisible();
    await expect(page.getByText("Loading the model card")).toHaveCount(0);
    await expect.poll(async () => seen.has((await heading.textContent()) ?? "")).toBe(false);
    seen.add((await heading.textContent()) ?? "");
  }
  expect(seen.size).toBe(methods.model_cards.length);
  expect(problems).toEqual([]);
});

/** The calculator's rounding: money and values from 10 up to whole units, smaller values to one decimal. */
const shown = (v: number, money = false) =>
  v === 0
    ? "0"
    : money || v >= 10
      ? Math.round(v).toLocaleString("en-US")
      : (Math.round(v * 10) / 10).toFixed(1);

test("savings calculator: the range comes from the measured rates' intervals", async ({
  page,
  request,
}) => {
  const problems = watch(page);
  type E = { value: number; ci_low: number; ci_high: number };
  const { results } = await getJson<{ results: { id: string; estimate: E | null }[] }>(
    request,
    "/results",
  );
  const share = results.find((r) => r.id === "auto_classified_share")?.estimate;
  const alarms = results.find((r) => r.id === "fdc_false_alarm_rate")?.estimate;
  expect(share, "the wafer bundle measures the auto-classified share").toBeTruthy();
  expect(alarms, "the SECOM bundle measures the false-alarm rate").toBeTruthy();

  await page.goto("/how#calculator");
  const calc = page.locator("#calculator");
  await expect(calc.getByText("Nothing to compute yet")).toBeVisible();
  // Test inputs, typed as a visitor would.
  const perDay = 100;
  const minutes = 2;
  const hourCost = 60;
  await calc.getByLabel("Wafers per day").fill(String(perDay));
  await calc.getByLabel("Minutes an engineer spends per wafer map").fill(String(minutes));
  await calc.getByLabel("Engineer hour cost").fill(String(hourCost));

  const hours = (rate: number) => (perDay * 30 * rate * minutes) / 60;
  const line = (id: string) => calc.locator(`[data-line='${id}']`);
  await expect(line("hours").locator(".readout")).toHaveText(shown(hours(share!.value)));
  await expect(line("hours")).toContainText(
    `${shown(hours(share!.ci_low))} to ${shown(hours(share!.ci_high))}`,
  );
  await expect(line("engineerMoney").locator(".readout")).toHaveText(
    shown(hours(share!.value) * hourCost, true),
  );
  await expect(line("engineerMoney")).toContainText(
    `${shown(hours(share!.ci_low) * hourCost, true)} to ${shown(hours(share!.ci_high) * hourCost, true)}`,
  );
  const count = (rate: number) => perDay * 30 * rate;
  await expect(line("falseAlarms").locator(".readout")).toHaveText(shown(count(alarms!.value)));
  await expect(line("falseAlarms")).toContainText(
    `${shown(count(alarms!.ci_low))} to ${shown(count(alarms!.ci_high))}`,
  );
  expect(problems).toEqual([]);
});

test("guest session: Try as engineer signs in", async ({ page }) => {
  await page.goto("/investigations");
  await page.getByRole("button", { name: "Try as engineer", exact: true }).first().click();
  await expect(page.getByText("Engineer", { exact: true }).first()).toBeVisible();
});

test("investigations without a key: not-configured state, no Token Factory call", async ({
  page,
}) => {
  const outbound: string[] = [];
  page.on(
    "request",
    (r) => /tokenfactory|token-factory|amd\.com/i.test(r.url()) && outbound.push(r.url()),
  );
  await page.goto("/investigations");
  await expect(page.getByRole("note")).toContainText(
    "Live investigations are not configured on this server",
  );
  // Every visitor lists only its own investigations, and a new visitor has none yet...
  await expect(page.getByText("No investigations yet")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open the line" })).toBeVisible();
  // ...and, apart from them, the recorded example every visitor sees, read-only.
  if (ids.investigation) {
    const example = page.locator("[data-group='example']");
    await expect(example.getByRole("link").first()).toHaveAttribute(
      "href",
      `/investigations/${ids.investigation}`,
    );
    await expect(example.locator("tbody tr").first()).toContainText("Recorded");
    await page.goto(`/investigations/${ids.investigation}`);
    await expect(
      page.getByText("Recorded run: generated once, replayed without calling a model"),
    ).toBeVisible();
  }
  expect(outbound).toEqual([]);
});

test("chat without a key: not-configured state, nothing sent", async ({ page }) => {
  const chats: string[] = [];
  page.on("request", (r) => r.url().includes("/api/v1/chat") && chats.push(r.url()));

  await page.goto("/investigations");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("note")).toContainText("Chat is not configured on this server");
  await expect(sheet.getByRole("textbox", { name: "Question" })).toHaveCount(0);
  expect(chats).toEqual([]);
});

test("work orders: the tab and the audit log match the API", async ({ page, request }) => {
  const problems = watch(page);
  const list = await getJson<{ total: number }>(request, "/work-orders");
  await page.goto("/investigations?tab=work-orders");
  await expect(page.locator("h1")).toHaveText("Investigations");
  if (list.total === 0) {
    await expect(page.getByText("No work orders yet")).toBeVisible();
  } else {
    await expect(page.getByRole("link", { name: ids.workOrder! }).first()).toBeVisible();
    await page.goto(`/work-orders/${ids.workOrder}`);
    await expect(page).toHaveURL(/\/investigations\/inv_[0-9a-z]+#work-order$/);
    await expect(
      page.locator("#work-order").getByRole("heading", { name: "History" }),
    ).toBeVisible();
    await page.goto("/investigations?tab=work-orders");
  }
  await expect(page.getByRole("heading", { name: /Audit log/ })).toBeVisible();
  expect(problems).toEqual([]);
});
