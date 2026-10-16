import {
  WAFER_CELL,
  decodeWaferCells,
  type RunAlarm,
  type WaferInput,
} from "@yield-guardian/contracts";
import { expect, test, type Page } from "@playwright/test";

import { expectAccessible } from "../axe";
import { RUN_ID, SENSORS_ONLY_ID, eventsOf, fixture, sampleEvents } from "./fixture";
import { GATEWAY, startStoryProxy, type StoryProxy } from "./stub";

/**
 * The Line page end to end: the page talks to the runs API stub (stub.ts) in front of the
 * gateway, which serves the real runs made by build_fixture.py; everything else (sessions,
 * investigations) is the gateway's.
 */

let proxy: StoryProxy;
test.beforeAll(async () => {
  proxy = await startStoryProxy(GATEWAY);
});
test.afterAll(async () => proxy.close());
test.beforeEach(() => {
  proxy.configure({
    run: RUN_ID,
    pacing: { pace: 80, holdBefore: null, dropAfter: null },
    gone: false,
  });
});

const alarms = eventsOf(sampleEvents, "alarm").map((e) => e.alarm);
const red = alarms.filter((a) => a.severity === "alarm" && a.kind !== "unknown_pattern");
const t2 = red.find((a) => a.kind === "t2")!;
const lastCreated = () => proxy.created.at(-1);

/** Presses "Show every result now" until the run is done and nothing is left to play. */
async function finish(page: Page) {
  const showAll = page.getByRole("button", { name: "Show every result now" });
  await expect(async () => {
    if (await showAll.isVisible()) await showAll.click();
    await expect(page.getByRole("group", { name: "Final test" })).toContainText(
      /Done|Needs data|Stopped/,
      { timeout: 500 },
    );
    await expect(showAll).toBeHidden({ timeout: 500 });
  }).toPass({ timeout: 30_000 });
}

/** Waits until the page has stopped scrolling and the drawer's entrance is over. */
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
  await page.waitForTimeout(600); // the drawer's entrance, before contrast is measured
}

function alarmRow(page: Page, alarm: RunAlarm) {
  return page
    .locator("article")
    .filter({ has: page.getByText(new RegExp(`\\b${alarm.alarm_id}$`)) });
}

test("nothing moves until an input is chosen", async ({ page }) => {
  const before = proxy.created.length;
  await page.goto(`${proxy.origin}/`);
  await expect(
    page.getByRole("heading", { level: 1, name: "Run real fab data down the line" }),
  ).toBeVisible();
  await page.waitForTimeout(1_000);
  expect(proxy.created).toHaveLength(before);
  await expect(page).toHaveURL(`${proxy.origin}/`);
  await expect(page.getByRole("group", { name: "2 Monitoring" })).not.toContainText(
    /Computing|Alarm|Done/,
  );
});

test("a sample runs down the line, raises its alarms and starts an investigation", async ({
  page,
}) => {
  await page.goto(`${proxy.origin}/`);
  await page.getByRole("button", { name: "Try a real sample" }).click();
  await expect(page).toHaveURL(new RegExp(`\\?run=${RUN_ID}$`));
  expect(lastCreated()).toEqual({ source: "sample", seed: null });
  await expect(
    page.getByRole("heading", { level: 2, name: fixture.created.origin.title }),
  ).toBeVisible();

  // The line plays the results as they arrive; then every station has its result.
  await finish(page);
  await expect(page.getByRole("group", { name: "1 Manufacturing" })).toContainText("Done");
  await expect(page.getByRole("group", { name: "2 Monitoring" })).toContainText("Alarm");
  await expect(page.getByRole("group", { name: "3 Wafer test" })).toContainText("Alarm");
  await expect(
    page.getByText(
      "The run is finished: every station has its result, and nothing more will arrive.",
    ),
  ).toBeVisible();

  // The rail: alarms that turn a station red first, the count in the header.
  const warnings = alarms.length - red.length;
  await expect(page.getByText(`${red.length} alarms, ${warnings} warnings`)).toBeVisible();
  const newestRed = red.at(-1)!;
  await expect(
    page.getByRole("region", { name: "Alarms of this run" }).locator("article").first(),
  ).toContainText(newestRed.title);

  await expectAccessible(page, "line, finished run", undefined, true);

  // Show: the monitoring drawer opens on the alarm's unit, and the URL says so.
  const row = alarmRow(page, t2);
  await row.getByRole("button", { name: `Show unit ${t2.unit_id}` }).click();
  await expect(page).toHaveURL(new RegExp(`station=2&unit=${t2.unit_index}&alarm=${t2.alarm_id}$`));
  await expect(
    page.getByRole("heading", { level: 2, name: "2 Monitoring in detail" }),
  ).toBeFocused();
  await expect(row).toHaveAttribute("aria-current", "true");
  await settled(page);
  await expectAccessible(page, "line, monitoring drawer", undefined, true);

  // Investigate: an engineer session first, then the investigation of this run alarm.
  await row.getByRole("button", { name: "Investigate" }).click();
  const posted = page.waitForRequest(
    (r) => r.url().endsWith("/api/v1/investigations") && r.method() === "POST",
  );
  await row.getByRole("button", { name: "Sign in as engineer and investigate" }).click();
  expect((await posted).postDataJSON()).toEqual({
    trigger: { kind: "run_alarm", ref: `${RUN_ID}:${t2.alarm_id}` },
  });
  await expect(row.getByRole("link", { name: "Open the investigation" })).toHaveAttribute(
    "href",
    /^\/investigations\/inv_/,
  );
  // Station 4 lists it, under the alarm it investigates.
  await expect(page.locator("#station-4")).toContainText(`${t2.title} ${t2.alarm_id}`);
});

test("the wafer drawer keeps the prediction of a map the model does not know, with a calm caution", async ({
  page,
}) => {
  const unknown = alarms.find((a) => a.kind === "unknown_pattern")!;
  await page.goto(`${proxy.origin}/?run=${RUN_ID}&station=3&wafer=${unknown.wafer_index}`);
  await expect(
    page.getByRole("heading", { level: 2, name: "3 Wafer test in detail" }),
  ).toBeVisible();
  // The prediction stands; the unknown score is a caution next to it.
  await expect(page.locator("#station-drawer")).toContainText(
    "looks unlike the maps the model learned from",
  );
  await expect(page.locator("#station-drawer").getByRole("alert")).toHaveCount(0);
  await settled(page);
  await expectAccessible(page, "line, wafer drawer", undefined, true);
});

test("a mouse stroke paints the dies under it, in every part of the wafer", async ({ page }) => {
  await page.goto(`${proxy.origin}/`);
  await page.getByRole("button", { name: "Draw a defect" }).click();
  const canvas = page
    .getByRole("application", { name: /Wafer 1 of your drawing/ })
    .locator("canvas");
  const box = (await canvas.boundingBox())!;
  // A stroke across the lower right quarter, well inside the round die area.
  await page.mouse.move(box.x + box.width * 0.62, box.y + box.height * 0.72);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.78, box.y + box.height * 0.72, { steps: 8 });
  await page.mouse.up();
  await page.getByRole("button", { name: "Run your drawing" }).click();
  await expect(page).toHaveURL(new RegExp(`run=${RUN_ID}`));
  const { map } = (lastCreated() as { wafers: WaferInput[] }).wafers[0]!;
  const failed = Array.from(decodeWaferCells(map)).flatMap((c, i) =>
    c === WAFER_CELL.fail ? [{ row: Math.floor(i / map.width), col: i % map.width }] : [],
  );
  expect(failed.length).toBeGreaterThan(1);
  for (const { row, col } of failed) {
    expect(row).toBeGreaterThan(map.height / 2);
    expect(col).toBeGreaterThan(map.width / 2);
  }
});

test("a drawing runs as drawn wafers", async ({ page }) => {
  await page.goto(`${proxy.origin}/`);
  await page.getByRole("button", { name: "Draw a defect" }).click();
  const editor = page.getByRole("application", { name: /Wafer 1 of your drawing/ });
  await editor.focus();
  await page.keyboard.press("Space");
  await expect(page.getByText(/1 die failing/).first()).toBeVisible();
  await page.getByRole("button", { name: "Run your drawing" }).click();
  await expect(page).toHaveURL(new RegExp(`run=${RUN_ID}`));
  const body = lastCreated() as { source: string; wafers: WaferInput[] };
  expect(body.source).toBe("drawn");
  expect(body.wafers).toHaveLength(1);
  expect(body.wafers[0]).toMatchObject({
    lot: "your drawing",
    wafer: 1,
    label: null,
    source_wafer: null,
  });
  const cells = decodeWaferCells(body.wafers[0]!.map);
  expect(cells.filter((c) => c === WAFER_CELL.fail)).toHaveLength(1);
  expect(
    fixture.layouts.items.some(
      (l) =>
        l.map.height === body.wafers[0]!.map.height && l.map.width === body.wafers[0]!.map.width,
    ),
  ).toBe(true);
});

test("an upload says what is wrong, by row and column, and a good one runs", async ({ page }) => {
  await page.goto(`${proxy.origin}/`);
  await page.getByRole("button", { name: "Upload a file" }).click();
  const input = page.locator('input[type="file"]');
  await input.setInputFiles({
    name: "wafer-lot.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("lot,wafer,x,y,result\n"),
  });
  await expect(
    page.getByText("This file cannot run yet: fix the 3 errors below and upload it again."),
  ).toBeVisible();
  await expect(
    page.locator("li").filter({ hasText: /^ErrorRow 7: "-1" is not a column \(x\)/ }),
  ).toBeVisible();
  expect(proxy.uploads.at(-1)).toContain('name="file"; filename="wafer-lot.csv"');

  await input.setInputFiles({
    name: "secom-units.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("unit_id,timestamp\n"),
  });
  await expect(
    page.getByText("Ready to run. The warning below does not stop the run."),
  ).toBeVisible();
  proxy.configure({ run: SENSORS_ONLY_ID });
  await page.getByRole("button", { name: "Run secom-units.csv" }).click();
  expect(lastCreated()).toEqual({ source: "upload", upload_id: fixture.uploadOk.upload_id });
  await finish(page);
  await expect(page.getByRole("group", { name: "3 Wafer test" })).toContainText(
    "Needs wafer maps.",
  );
});

test("an expired run says so and offers a new one", async ({ page }) => {
  proxy.configure({ gone: true });
  await page.goto(`${proxy.origin}/?run=${RUN_ID}`);
  await expect(page.getByText("This run is no longer kept. Start a new one.")).toBeVisible();
  await page.getByRole("button", { name: "Start a new one" }).click();
  await expect(page).toHaveURL(`${proxy.origin}/`);
});

test("the stream resumes where it broke off", async ({ page }) => {
  proxy.configure({ pacing: { pace: 40, dropAfter: 6 } });
  const from = proxy.resumes.length;
  await page.goto(`${proxy.origin}/`);
  await page.getByRole("button", { name: "Try a real sample" }).click();
  await finish(page);
  expect(proxy.resumes.slice(from)).toEqual([null, "6"]);
  await expect(
    page.getByText(`${red.length} alarms, ${alarms.length - red.length} warnings`),
  ).toBeVisible();
});

test("an old station link lights the input bar, and the station opens on the run", async ({
  page,
}) => {
  await page.goto(`${proxy.origin}/?station=2`);
  await expect(
    page.getByText("Choose an input to start a run; the monitoring details open with its results."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Try a real sample" }).click();
  await expect(page).toHaveURL(new RegExp(`run=${RUN_ID}&station=2`));
  await expect(
    page.getByRole("heading", { level: 2, name: "2 Monitoring in detail" }),
  ).toBeVisible();
});

test("an old unit link runs that unit once and keeps the run's address", async ({ page }) => {
  const before = proxy.created.length;
  await page.goto(`${proxy.origin}/?pick=unit:1062`);
  await expect(page).toHaveURL(new RegExp(`\\?run=${RUN_ID}$`));
  expect(proxy.created.slice(before)).toEqual([
    { source: "pick", unit_ids: [1062], wafer_ids: [], lot: null },
  ]);
  await page.goBack().catch(() => undefined);
  expect(proxy.created.length - before).toBe(1);
});

test.describe("the alarms rail and the Ask button", () => {
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 768, height: 900 },
    { width: 360, height: 800 },
  ]) {
    test(`no line of the rail sits under the Ask button at ${viewport.width} px`, async ({
      page,
    }) => {
      await page.setViewportSize(viewport);
      proxy.configure({ pacing: { pace: 0 } });
      await page.goto(`${proxy.origin}/?run=${RUN_ID}`);
      await finish(page);
      const rail = page.getByRole("region", { name: "Alarms of this run" });
      const ask = page.getByRole("button", { name: "Ask", exact: true });
      await expect(ask).toBeVisible();
      const clear = async (label: string) => {
        await page.waitForTimeout(150); // the rail's room is measured on the next frame
        const r = (await rail.boundingBox())!;
        const a = (await ask.boundingBox())!;
        const overlaps =
          r.x < a.x + a.width &&
          a.x < r.x + r.width &&
          r.y < a.y + a.height &&
          a.y < r.y + r.height;
        expect(
          overlaps,
          `${label}: rail ${JSON.stringify(r)} against Ask ${JSON.stringify(a)}`,
        ).toBe(false);
      };
      if (viewport.width >= 1280) {
        // Beside the line the rail ends above the button wherever the page is scrolled.
        for (const y of [0, 150, 300, 450]) {
          await page.evaluate((top) => window.scrollTo(0, top), y);
          await clear(`scrolled to ${y}`);
        }
      } else {
        // Under the line, the rail in view (its top under the site bar) ends above the button.
        await rail.evaluate((el) => el.closest("section")!.scrollIntoView({ block: "start" }));
        await clear("in view");
      }
    });
  }
});

test.describe("with reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("every result shows as it arrives, without 3D or replay", async ({ page }) => {
    proxy.configure({ pacing: { pace: 0 } });
    await page.goto(`${proxy.origin}/`);
    await page.getByRole("button", { name: "Try a real sample" }).click();
    await expect(page.getByRole("group", { name: "3 Wafer test" })).toContainText("Alarm", {
      timeout: 10_000,
    });
    await expect(page.getByRole("button", { name: "Show every result now" })).toBeHidden();
    await expect(page.locator("canvas[data-engine]")).toHaveCount(0);
    await expect(page.getByRole("group", { name: "Final test" })).toContainText("Done");
    await expectAccessible(page, "line, reduced motion", undefined, true);
  });
});

test.describe("at 360 px", () => {
  test.use({ viewport: { width: 360, height: 800 } });

  test("nothing scrolls sideways, idle, finished or with a drawer open", async ({ page }) => {
    const noSideways = async (label: string) => {
      const width = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(width, label).toBeLessThanOrEqual(360);
    };
    await page.goto(`${proxy.origin}/`);
    await noSideways("idle");
    await page.getByRole("button", { name: "Try a real sample" }).click();
    await finish(page);
    await noSideways("finished");
    for (const name of [
      "Open monitoring details",
      "Open wafer test details",
      "Open manufacturing details",
    ]) {
      await page.getByRole("button", { name }).click();
      await settled(page);
      await noSideways(name);
    }
    await expectAccessible(page, "line at 360 px", undefined, true);
  });
});
