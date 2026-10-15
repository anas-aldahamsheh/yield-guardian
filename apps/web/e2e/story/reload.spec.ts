import { expect, test, type Page } from "@playwright/test";
import {
  WAFER_CELL,
  decodeWaferCells,
  type RunAlarm,
  type WaferInput,
} from "@yield-guardian/contracts";

import { RUN_ID, eventsOf, fixture, sampleEvents } from "./fixture";
import { GATEWAY, startStoryProxy, type StoryProxy } from "./stub";

/**
 * A reload, a link opened on another device, and back and forward show the Line page as the
 * person left it: every station's result, the counts, the rail with every alarm, the open drawer
 * and the item in view, the chosen alarm and its investigation, the line saying the run is
 * finished. The stored part is in the page the server sends, so nothing waits, replays or moves
 * as if it were new; a run still computing goes on from the last event it had. The runs API is
 * the stand-in of stub.ts, which Next.js also reads while rendering.
 */

let proxy: StoryProxy;
test.beforeAll(async () => {
  proxy = await startStoryProxy(GATEWAY);
});
test.afterAll(async () => proxy.close());
test.beforeEach(async ({ page }) => {
  proxy.configure({
    run: RUN_ID,
    pacing: { pace: 0, holdBefore: null, dropAfter: null },
    gone: false,
  });
  await page.addInitScript(recordMotion);
});

const alarms = eventsOf(sampleEvents, "alarm").map((e) => e.alarm);
const turnsRed = (a: RunAlarm) => a.severity === "alarm" && a.kind !== "unknown_pattern";
const red = alarms.filter(turnsRed);
const t2 = red.find((a) => a.kind === "t2")!;
const FINISHED = "The run is finished: every station has its result, and nothing more will arrive.";
const STATIONS = ["1 Manufacturing", "2 Monitoring", "3 Wafer test", "Final test"] as const;

/**
 * Runs in the page before its own scripts: notes every CSS animation that starts (a station
 * pulsing red, an alarm sliding in, a wafer going into its slot, a panel fading in), and, in
 * the first seconds, whether the line plays results or waits on the run.
 */
function recordMotion() {
  const seen: string[] = [];
  (window as unknown as { __motion: string[] }).__motion = seen;
  document.addEventListener(
    "animationstart",
    (event) => {
      const name = event.animationName.replace(/^.*_/, "");
      // A running investigation's dot breathes for as long as it runs: that is its state.
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

/**
 * What the person sees of the run, as text. The 3D wafer's colour note is left out: it shows
 * when the 3D view has loaded, after the page, whatever the run.
 */
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
    line: (
      await page
        .getByText(
          /^(Running: each station shows its result|The run is finished: every station|The run stopped)/,
        )
        .allInnerTexts()
    ).map(squash),
    drawer: await texts("#station-drawer h2"),
    unit: await page.evaluate(
      () =>
        document
          .querySelector("#station-drawer [role=slider][aria-label=Unit]")
          ?.getAttribute("aria-valuetext") ?? null,
    ),
    wafer: await texts("#station-drawer ul[aria-label=Wafers] button[aria-pressed=true]"),
    investigations: await texts("#station-4"),
  };
}

/** Requests the browser makes to the API, by path (the run's id left out). */
function countApi(page: Page) {
  const counts: Record<string, number> = {};
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (!path.startsWith("/api/")) return;
    const key = path.replace(/run_[0-9a-z]+/, "{run}");
    counts[key] = (counts[key] ?? 0) + 1;
  });
  return counts;
}

/** Presses "Show every result now" until the run is done and nothing is left to play. */
async function finish(page: Page) {
  const showAll = page.getByRole("button", { name: "Show every result now" });
  await expect(async () => {
    if (await showAll.isVisible()) await showAll.click();
    await expect(page.getByText(FINISHED)).toBeVisible({ timeout: 500 });
    await expect(showAll).toBeHidden({ timeout: 500 });
  }).toPass({ timeout: 30_000 });
}

/** Waits until the page has stopped scrolling and any entrance is over. */
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

function alarmRow(page: Page, alarm: RunAlarm) {
  return page
    .locator("article")
    .filter({ has: page.getByText(new RegExp(`\\b${alarm.alarm_id}$`)) });
}

/** Reloads and reads the page as soon as its HTML is in, before anything could be fetched. */
async function reloadAndRead(page: Page) {
  await page.reload({ waitUntil: "domcontentloaded" });
  return visibleLine(page);
}

test("a finished run comes back after a reload as it was, with nothing replayed or asked twice", async ({
  page,
}) => {
  await page.goto(`${proxy.origin}/`);
  await page.getByRole("button", { name: "Try a real sample" }).click();
  await finish(page);
  await page.getByRole("button", { name: "Open monitoring details" }).click();
  await page.locator("#station-drawer").getByRole("slider", { name: "Unit" }).focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(new RegExp(`\\?run=${RUN_ID}&station=2&unit=\\d+$`));
  await settled(page);
  const before = await visibleLine(page);
  expect(before.unit).toMatch(/^Unit \d+/);
  expect(before.count).toEqual([`${red.length} alarms, ${alarms.length - red.length} warnings`]);
  expect(before.line).toEqual([FINISHED]);
  const scrolled = await page.evaluate(() => window.scrollY);

  const counts = countApi(page);
  const reads = proxy.reads.length;
  const resumes = proxy.resumes.length;
  expect(await reloadAndRead(page)).toEqual(before);
  await page.waitForTimeout(2_500);
  expect(await visibleLine(page)).toEqual(before);
  expect(await motion(page)).toEqual([]);
  // The browser's own scroll restoration puts the drawer where it was.
  expect(Math.abs((await page.evaluate(() => window.scrollY)) - scrolled)).toBeLessThan(40);
  await expect(page.getByRole("heading", { name: "2 Monitoring in detail" })).toBeInViewport();

  // The server read the run once to render the page; the browser did not read or follow it.
  expect(proxy.reads.slice(reads)).toEqual([{ from: "server", status: 200, lastSeq: 35 }]);
  expect(proxy.resumes.slice(resumes)).toEqual([]);
  expect(counts["/api/v1/runs/{run}"] ?? 0).toBe(0);
  expect(counts["/api/v1/runs/{run}/events"] ?? 0).toBe(0);
  // Who the visitor is, once; what the API serves came with the page.
  expect(counts["/api/v1/session"]).toBe(1);
  expect(counts["/api/v1/meta"] ?? 0).toBeLessThanOrEqual(1);

  // Coming back to the window asks nothing again.
  await page.evaluate(() => {
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("focus"));
    window.dispatchEvent(new Event("online"));
  });
  await page.waitForTimeout(500);
  expect(counts["/api/v1/session"]).toBe(1);
  expect(counts["/api/v1/meta"] ?? 0).toBeLessThanOrEqual(1);
});

test("the chosen alarm and its wafer or lot come back after a reload", async ({ page }) => {
  await page.goto(`${proxy.origin}/?run=${RUN_ID}`);
  await expect(page.getByText(FINISHED)).toBeVisible();

  const unknown = alarms.find((a) => a.kind === "unknown_pattern")!;
  await alarmRow(page, unknown)
    .getByRole("button", { name: /^Show wafer/ })
    .click();
  await expect(page).toHaveURL(
    new RegExp(`station=3&wafer=${unknown.wafer_index}&alarm=${unknown.alarm_id}$`),
  );
  await settled(page);
  const wafer = await visibleLine(page);
  expect(wafer.chosen).toEqual([expect.stringContaining(unknown.title)]);
  expect(wafer.wafer).toHaveLength(1);
  expect(await reloadAndRead(page)).toEqual(wafer);

  const lot = alarms.find((a) => a.kind === "lot_excursion")!;
  await alarmRow(page, lot)
    .getByRole("button", { name: /^Show lot/ })
    .click();
  await expect(page).toHaveURL(new RegExp(`station=3&lot=${lot.lot}&alarm=${lot.alarm_id}$`));
  await settled(page);
  const lotView = await visibleLine(page);
  expect(lotView.chosen).toEqual([expect.stringContaining(lot.title)]);
  expect(await reloadAndRead(page)).toEqual(lotView);
  await page.waitForTimeout(1_500);
  expect(await motion(page)).toEqual([]);
});

test("a run reloaded while it computes goes on from the last event it had, replaying nothing", async ({
  page,
}) => {
  proxy.configure({ pacing: { pace: 30, holdBefore: "wafer_pattern" } });
  await page.goto(`${proxy.origin}/`);
  await page.getByRole("button", { name: "Try a real sample" }).click();
  // Everything before the wafer maps has arrived and is shown; the wafer test is computing.
  const held = sampleEvents.filter((e) => e.seq < 21);
  const shownSoFar = eventsOf(held, "alarm").map((e) => e.alarm);
  const count = `${shownSoFar.filter(turnsRed).length} alarms, ${shownSoFar.filter((a) => !turnsRed(a)).length} warnings`;
  const showAll = page.getByRole("button", { name: "Show every result now" });
  await expect(async () => {
    if (await showAll.isVisible()) await showAll.click();
    await expect(page.getByText(count)).toBeVisible({ timeout: 500 });
    await expect(showAll).toBeHidden({ timeout: 500 });
  }).toPass({ timeout: 30_000 });
  await expect(page.getByRole("group", { name: "3 Wafer test" })).toContainText("Computing");
  await settled(page); // the dials glide to the unit they rest on
  const before = await visibleLine(page);

  const reads = proxy.reads.length;
  const resumes = proxy.resumes.length;
  const after = await reloadAndRead(page);
  // The two stations that had their results show them at once; the wafer test is still at it.
  expect(after.stations.slice(0, 2)).toEqual(before.stations.slice(0, 2));
  expect(after.stations[2]).toContain("Computing");
  expect(after.count).toEqual([count]);
  expect(after.alarms).toEqual(before.alarms);
  expect(after.line).toEqual(["Running: each station shows its result as it arrives."]);
  await page.waitForTimeout(1_000);
  expect(await motion(page)).toEqual([]);
  // The run as stored when the page was rendered, then the stream after its last event.
  expect(proxy.reads.slice(reads)).toEqual([{ from: "server", status: 200, lastSeq: 20 }]);
  await expect.poll(() => proxy.resumes.slice(resumes)).toEqual(["20"]);

  // What comes after the reload arrives live, and the run ends as a run with no reload does.
  proxy.release();
  await finish(page);
  await expect(
    page.getByText(`${red.length} alarms, ${alarms.length - red.length} warnings`),
  ).toBeVisible();
  // (Their animations start on the frame after they are shown.)
  await expect.poll(() => motion(page)).toContain("slot-in");
  expect(proxy.resumes.slice(resumes)).toEqual(["20"]);
});

test("an alarm keeps its investigation after a reload, and on another device", async ({
  page,
  browser,
}) => {
  await page.goto(`${proxy.origin}/?run=${RUN_ID}`);
  const row = alarmRow(page, t2);
  await row.getByRole("button", { name: "Investigate" }).click();
  await row.getByRole("button", { name: "Sign in as engineer and investigate" }).click();
  const link = row.getByRole("link", { name: "Open the investigation" });
  await expect(link).toHaveAttribute("href", /^\/investigations\/inv_/);
  const href = (await link.getAttribute("href"))!;
  await expect(page).toHaveURL(new RegExp(`alarm=${t2.alarm_id}$`));

  // The server has the link: the page it sends shows it, with the investigation's status.
  const html = await (await page.request.get(page.url())).text();
  expect(html).toContain(`href="${href}"`);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(row.getByRole("link", { name: "Open the investigation" })).toHaveAttribute(
    "href",
    href,
    { timeout: 1 },
  );
  await expect(row).toContainText("Awaiting decision", { timeout: 1 });
  await expect(row).toHaveAttribute("aria-current", "true", { timeout: 1 });
  await expect(page.locator("#station-4")).toContainText(`${t2.title} ${t2.alarm_id}`);

  // Another device, with no session of its own here, opening a link to the alarm's unit: the
  // link is there, and so is the drawer, brought into view as there is no place to go back to.
  const other = await browser.newContext();
  try {
    const second = await other.newPage();
    await second.goto(
      `${proxy.origin}/?run=${RUN_ID}&station=2&unit=${t2.unit_index}&alarm=${t2.alarm_id}`,
      { waitUntil: "domcontentloaded" },
    );
    await expect(
      alarmRow(second, t2).getByRole("link", { name: "Open the investigation" }),
    ).toHaveAttribute("href", href, { timeout: 1 });
    await expect(second.getByRole("heading", { name: "2 Monitoring in detail" })).toBeInViewport();
    await expect(second.getByRole("heading", { name: "2 Monitoring in detail" })).toBeFocused();
  } finally {
    await other.close();
  }
});

test("a link to a run that is not here says so at once, and never waits on it", async ({
  page,
}) => {
  const counts = countApi(page);
  const resumes = proxy.resumes.length;
  await page.goto(`${proxy.origin}/?run=run_01notheremissing0000000000&station=3`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.getByRole("alert")).toHaveText(
    /^There is no run with this link here\. It may belong to another workspace, or the link is incomplete\. Start a new one\./,
    { timeout: 1 },
  );
  await page.waitForTimeout(1_500);
  expect(await motion(page)).not.toContain("waiting");
  expect(proxy.resumes.slice(resumes)).toEqual([]);
  expect(counts["/api/v1/runs/{run}"] ?? 0).toBe(0);
  await page.getByRole("button", { name: "Start a new one" }).click();
  await expect(page).toHaveURL(`${proxy.origin}/`);
});

test("while the API wakes the page says so, then shows the run as it stands", async ({ page }) => {
  const counts = countApi(page);
  proxy.sleep(3_500);
  await page.goto(`${proxy.origin}/?run=${RUN_ID}&station=3`);
  await expect(page.getByRole("heading", { level: 2, name: "Reading the run" })).toBeVisible();
  await expect(
    page.getByText(
      "The service is starting after a quiet spell; the run shows as soon as it answers.",
    ),
  ).toBeVisible();
  await expect(page.getByText(FINISHED)).toBeVisible({ timeout: 15_000 });
  await expect(
    page.getByRole("heading", { level: 2, name: "3 Wafer test in detail" }),
  ).toBeVisible();
  await expect(
    page.getByText(`${red.length} alarms, ${alarms.length - red.length} warnings`),
  ).toBeVisible();
  // Shown as it stands once read: not played as if it were arriving.
  const seen = await motion(page);
  expect(seen).not.toContain("playing");
  expect(seen).not.toContain("arrive-from");
  // Each read waits longer than the last (and at least as long as asked): a few tries, not a storm.
  expect(counts["/api/v1/runs/{run}"]).toBeLessThanOrEqual(4);
  expect(counts["/api/v1/session"]).toBeLessThanOrEqual(4);
  expect(counts["/api/v1/meta"] ?? 0).toBeLessThanOrEqual(1);
});

test("back and forward come back to the run as it was", async ({ page }) => {
  await page.goto(`${proxy.origin}/`);
  await page.getByRole("button", { name: "Try a real sample" }).click();
  await finish(page);
  await page.getByRole("button", { name: "Open wafer test details" }).click();
  await settled(page);
  const before = await visibleLine(page);
  const resumes = proxy.resumes.length;
  await page.goBack();
  await expect(page).toHaveURL(`${proxy.origin}/`);
  await page.goForward();
  await expect(page).toHaveURL(new RegExp(`\\?run=${RUN_ID}&station=3$`));
  expect(await visibleLine(page)).toEqual(before);
  await page.waitForTimeout(1_000);
  expect(await visibleLine(page)).toEqual(before);
  expect(proxy.resumes.slice(resumes)).toEqual([]);
});

test.describe("with reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("a reload shows the finished run as it was, without motion", async ({ page }) => {
    await page.goto(
      `${proxy.origin}/?run=${RUN_ID}&station=2&unit=${t2.unit_index}&alarm=${t2.alarm_id}`,
    );
    await expect(page.getByText(FINISHED)).toBeVisible();
    await settled(page);
    const before = await visibleLine(page);
    expect(before.chosen).toEqual([expect.stringContaining(t2.title)]);
    expect(await reloadAndRead(page)).toEqual(before);
    await page.waitForTimeout(1_000);
    expect(await motion(page)).toEqual([]);
    await expect(page.locator("canvas[data-engine]")).toHaveCount(0);
  });
});

test("an unsent drawing and a checked upload are still there after a reload", async ({ page }) => {
  await page.goto(`${proxy.origin}/`);
  await page.getByRole("button", { name: "Draw a defect" }).click();
  const editor = page.getByRole("application", { name: /Wafer 1 of your drawing/ });
  await editor.focus();
  await page.keyboard.press("Space");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Space");
  const painted = page.getByText("Wafer 1: 2 of 515 dies failing.");
  await expect(painted).toBeVisible();
  await page.waitForTimeout(600); // the drawing is kept a moment after the last stroke
  await page.reload();
  await expect(page.getByRole("region", { name: "Draw a defect" })).toBeVisible();
  await expect(painted).toBeVisible();
  await page.getByRole("button", { name: "Run your drawing" }).click();
  await expect(page).toHaveURL(new RegExp(`run=${RUN_ID}`));
  const drawn = proxy.created.at(-1) as { source: string; wafers: WaferInput[] };
  expect(drawn.source).toBe("drawn");
  expect(drawn.wafers).toHaveLength(1);
  const cells = decodeWaferCells(drawn.wafers[0]!.map);
  expect(cells.filter((c) => c === WAFER_CELL.fail)).toHaveLength(2);

  // The drawing went with its run: the next one starts empty.
  await page.goto(`${proxy.origin}/`);
  await page.getByRole("button", { name: "Draw a defect" }).click();
  await expect(page.getByText("Wafer 1: 0 of 515 dies failing.")).toBeVisible();

  await page.getByRole("button", { name: "Upload a file" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "secom-units.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("unit_id,timestamp\n"),
  });
  await expect(
    page.getByText("Ready to run. The warning below does not stop the run."),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("Ready to run. The warning below does not stop the run."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Run secom-units.csv" }).click();
  expect(proxy.created.at(-1)).toEqual({ source: "upload", upload_id: fixture.uploadOk.upload_id });
});
