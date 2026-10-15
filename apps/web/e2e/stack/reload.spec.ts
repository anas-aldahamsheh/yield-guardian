import { expect, test, type Page } from "@playwright/test";

import { getJson } from "./api";

/**
 * Reloads of the Line page on the composed stack: real runs of the real bundles, read back from
 * PostgreSQL. A reload shows the run as the person left it, from the page the server sends:
 * every station's result, the rail with every alarm, the open drawer and the item in view, the
 * line saying the run is finished, with nothing replayed and the API asked nothing twice. Every
 * expected value is read from the API.
 */

const FINISHED = "The run is finished: every station has its result, and nothing more will arrive.";
const STATIONS = ["1 Manufacturing", "2 Monitoring", "3 Wafer test", "Final test"] as const;

type RunRead = {
  run_id: string;
  status: string;
  last_seq: number;
  alarms: { alarm_id: string; severity: string; kind: string }[];
};

/** Notes every CSS animation that starts, and whether the line plays results or waits on the run. */
function recordMotion() {
  const seen: string[] = [];
  (window as unknown as { __motion: string[] }).__motion = seen;
  document.addEventListener(
    "animationstart",
    (event) => {
      const name = event.animationName.replace(/^.*_/, "");
      if (name !== "live-ring") seen.push(name);
    },
    true,
  );
  const look = () => {
    const text = document.body?.textContent ?? "";
    if (text.includes("Show every result now")) seen.push("playing");
    if (/Connecting to the run|Reading the run|Reading this run/.test(text)) seen.push("waiting");
    if (performance.now() < 12_000) requestAnimationFrame(look);
  };
  requestAnimationFrame(look);
}

async function motion(page: Page): Promise<string[]> {
  return [
    ...new Set(await page.evaluate(() => (window as unknown as { __motion: string[] }).__motion)),
  ];
}

/** What the person sees of the run, as text (the 3D wafer's colour note, which loads later, left out). */
async function visibleLine(page: Page) {
  const squash = (s: string) => s.replace(/\s+/g, " ").trim();
  const texts = async (selector: string) =>
    (await page.locator(selector).allInnerTexts()).map(squash);
  const rail = "section[aria-labelledby=alarms-title]";
  return {
    url: page.url(),
    strip: await texts("section[aria-labelledby=line-title] h2:not(#alarms-title)"),
    stations: await Promise.all(
      STATIONS.map(async (name) =>
        squash(await page.getByRole("group", { name }).innerText()).replace(
          / Wafer colour: an assumed \d+ nm oxide film\./,
          "",
        ),
      ),
    ),
    count: await texts(`${rail} header p`),
    alarms: await texts(`${rail} h3`),
    chosen: await texts(`${rail} article[aria-current=true] h3`),
    finished: await page.getByText(FINISHED).count(),
    drawer: await texts("#station-drawer h2"),
    unit: await page.evaluate(
      () =>
        document
          .querySelector("#station-drawer [role=slider][aria-label=Unit]")
          ?.getAttribute("aria-valuetext") ?? null,
    ),
    wafer: await texts("#station-drawer ul[aria-label=Wafers] button[aria-pressed=true]"),
  };
}

/** Requests the browser makes to the API, by path, and the Last-Event-ID of each stream. */
function watchApi(page: Page) {
  const counts: Record<string, number> = {};
  const resumes: (string | null)[] = [];
  const problems: string[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (!path.startsWith("/api/")) return;
    const key = path.replace(/run_[0-9a-z]+/, "{run}");
    counts[key] = (counts[key] ?? 0) + 1;
    if (key.endsWith("/events")) resumes.push(request.headers()["last-event-id"] ?? null);
  });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && /Hydration|did not match|Content Security Policy/i.test(m.text()))
      problems.push(`console: ${m.text()}`);
  });
  return {
    counts,
    resumes,
    problems,
    reset() {
      for (const key of Object.keys(counts)) delete counts[key];
      resumes.length = 0;
    },
  };
}

async function finish(page: Page) {
  const showAll = page.getByRole("button", { name: "Show every result now" });
  await expect(async () => {
    if (await showAll.isVisible()) await showAll.click();
    await expect(page.getByText(FINISHED)).toBeVisible({ timeout: 1_000 });
    await expect(showAll).toBeHidden({ timeout: 1_000 });
  }).toPass({ timeout: 90_000 });
}

async function settled(page: Page) {
  let last = -1;
  await expect
    .poll(
      async () => {
        const y = await page.evaluate(() => window.scrollY);
        const still = y === last;
        last = y;
        return still;
      },
      { intervals: [150] },
    )
    .toBe(true);
  await page.waitForTimeout(600);
}

function runIdOf(page: Page): string {
  return new URL(page.url()).searchParams.get("run")!;
}

/** The rail's count, from the run as the API stores it. */
function countOf(run: RunRead): string {
  const red = run.alarms.filter((a) => a.severity === "alarm" && a.kind !== "unknown_pattern");
  const warnings = run.alarms.length - red.length;
  return [
    red.length ? `${red.length} alarm${red.length === 1 ? "" : "s"}` : null,
    warnings ? `${warnings} warning${warnings === 1 ? "" : "s"}` : null,
  ]
    .filter(Boolean)
    .join(", ");
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(recordMotion);
});

test("a real sample reloads as it stood, with the drawer and the unit in view", async ({
  page,
  request,
}) => {
  const api = watchApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Try a real sample" }).click();
  await expect(page).toHaveURL(/\?run=run_[0-9a-z]+$/);
  await finish(page);
  const run = await getJson<RunRead>(request, `/runs/${runIdOf(page)}`);
  expect(run.status).toBe("done");
  await page.getByRole("button", { name: "Open monitoring details" }).click();
  await page.locator("#station-drawer").getByRole("slider", { name: "Unit" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(/&station=2&unit=\d+$/);
  await settled(page);
  const before = await visibleLine(page);
  expect(before.count).toEqual([countOf(run)]);
  expect(before.finished).toBe(1);
  expect(before.unit).toMatch(/^Unit \d+/);

  api.reset();
  await page.reload({ waitUntil: "domcontentloaded" });
  expect(await visibleLine(page)).toEqual(before);
  await page.waitForTimeout(2_500);
  expect(await visibleLine(page)).toEqual(before);
  expect(await motion(page)).toEqual([]);
  await expect(page.getByRole("heading", { name: "2 Monitoring in detail" })).toBeInViewport();
  // The page came with the run: the browser neither read it again nor followed it.
  expect(api.counts["/api/v1/runs/{run}"] ?? 0).toBe(0);
  expect(api.resumes).toEqual([]);
  expect(api.counts["/api/v1/session"] ?? 0).toBeLessThanOrEqual(1);
  expect(api.counts["/api/v1/meta"] ?? 0).toBeLessThanOrEqual(1);
  expect(api.problems).toEqual([]);
});

test("a drawn wafer run reloads with the wafer drawer open on the wafer chosen", async ({
  page,
  request,
}) => {
  const api = watchApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Draw a defect" }).click();
  await page.getByRole("application", { name: /Wafer 1 of your drawing/ }).focus();
  for (let i = 0; i < 6; i += 1) {
    await page.keyboard.press("Space");
    await page.keyboard.press("ArrowRight");
  }
  await page.getByRole("button", { name: "Add a copy of this wafer" }).click();
  await page.getByRole("button", { name: "Run your 2 wafers" }).click();
  await expect(page).toHaveURL(/\?run=run_[0-9a-z]+$/);
  await finish(page);
  const run = await getJson<RunRead>(request, `/runs/${runIdOf(page)}`);
  await page.getByRole("button", { name: "Open wafer test details" }).click();
  await page.locator("#station-drawer ul[aria-label=Wafers] button").nth(1).click();
  await expect(page).toHaveURL(/&station=3&wafer=1$/);
  await settled(page);
  const before = await visibleLine(page);
  expect(before.strip[0]).toBe("Your drawing");
  expect(before.count).toEqual([countOf(run)]);
  expect(before.wafer).toEqual([expect.stringMatching(/^Wafer 2/)]);

  api.reset();
  await page.reload({ waitUntil: "domcontentloaded" });
  expect(await visibleLine(page)).toEqual(before);
  await page.waitForTimeout(2_500);
  expect(await visibleLine(page)).toEqual(before);
  expect(await motion(page)).toEqual([]);
  await expect(page.getByRole("heading", { name: "3 Wafer test in detail" })).toBeInViewport();
  expect(api.counts["/api/v1/runs/{run}"] ?? 0).toBe(0);
  expect(api.resumes).toEqual([]);
  expect(api.problems).toEqual([]);
});

test("a sample reloaded while it computes goes on after the last event it had", async ({
  page,
  request,
}) => {
  const api = watchApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Try a real sample" }).click();
  await expect(page).toHaveURL(/\?run=run_[0-9a-z]+$/);
  api.reset();
  await page.reload({ waitUntil: "domcontentloaded" });
  await finish(page);
  const run = await getJson<RunRead>(request, `/runs/${runIdOf(page)}`);
  expect(run.status).toBe("done");
  // Every alarm once, whether the run ended before the reload's read or after it.
  await expect(page.getByText(countOf(run), { exact: true })).toBeVisible();
  // A run still going when the page was rendered is followed from after its last stored
  // event, never from the start.
  for (const resume of api.resumes) expect(resume).toMatch(/^\d+$/);
  expect(api.resumes.every((r) => Number(r) <= run.last_seq)).toBe(true);
  expect(api.problems).toEqual([]);
});
