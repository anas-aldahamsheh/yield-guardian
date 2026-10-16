import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * The screenshots of the Arabic guide (components/guide/guide-content.ts), from the real API
 * behind a production gateway: never the development fixtures. At 1440 px, light, each cropped to
 * the part its entry describes; PNGs that are then compressed to WebP under public/guide/.
 * Run on demand:
 *   GUIDE_SHOTS=<dir> GUIDE_UPLOAD=<csv> E2E_PORT=<real gateway> \
 *     pnpm exec playwright test --project=screenshots e2e/guide-screenshots.shot.ts
 * GUIDE_UPLOAD is the API's real wafer example (/api/v1/uploads/examples/wafers.csv) with one
 * cell mistyped by hand, so the check names a row and a column; the guide's caption says so.
 */
const OUT = process.env.GUIDE_SHOTS;
const UPLOAD = process.env.GUIDE_UPLOAD;
const BASE = `http://localhost:${process.env.E2E_PORT ?? 4300}`;
const PAD = 16;

test.skip(!OUT || !UPLOAD, "set GUIDE_SHOTS and GUIDE_UPLOAD to take the guide's screenshots");

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Document coordinates of an element. */
async function boxOf(locator: Locator): Promise<Box> {
  return locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    return {
      x: r.left + window.scrollX,
      y: r.top + window.scrollY,
      width: r.width,
      height: r.height,
    };
  });
}

/** Document coordinates of an element's text (narrower than a block that fills its row). */
async function textBoxOf(locator: Locator): Promise<Box> {
  return locator.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const r = range.getBoundingClientRect();
    return {
      x: r.left + window.scrollX,
      y: r.top + window.scrollY,
      width: r.width,
      height: r.height,
    };
  });
}

/** The smallest box around the boxes, with a margin, inside the page's width. */
function around(boxes: Box[], pad = PAD): Box {
  const x = Math.max(0, Math.min(...boxes.map((b) => b.x)) - pad);
  const y = Math.max(0, Math.min(...boxes.map((b) => b.y)) - pad);
  const right = Math.min(1440, Math.max(...boxes.map((b) => b.x + b.width)) + pad);
  const bottom = Math.max(...boxes.map((b) => b.y + b.height)) + pad;
  return { x, y, width: Math.round(right - x), height: Math.round(bottom - y) };
}

async function capture(page: Page, name: string, clip: Box, settle?: Locator) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(300);
  // Rows that are still sliding in would be caught half drawn.
  if (settle)
    await settle.evaluate((el) =>
      Promise.race([
        Promise.all(el.getAnimations({ subtree: true }).map((a) => a.finished)),
        new Promise((done) => setTimeout(done, 3_000)),
      ]),
    );
  await page.screenshot({ path: path.join(OUT!, `${name}.png`), fullPage: true, clip });
}

/** The floating Ask button sits over whatever is at the bottom of the screen; the crops that are not about it leave it out. */
async function hideAsk(page: Page) {
  await page.addStyleTag({
    content: 'button[aria-haspopup="dialog"].fixed { visibility: hidden !important; }',
  });
}

test.beforeAll(async ({ request }) => {
  if (OUT) mkdirSync(OUT, { recursive: true });
  // The real runs API answers /runs/cases (503 while it warms up); the development fixtures do not.
  await expect(async () => {
    const answer = await request.get(`${BASE}/api/v1/runs/cases`);
    expect(answer.status(), "the gateway must serve the real API").toBe(200);
  }).toPass({ timeout: 60_000 });
});

test.use({ viewport: { width: 1440, height: 900 }, colorScheme: "light" });

test("guide: navigation, input bar, drawing, upload check", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(`${BASE}/`);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(800);
  // The top bar with its pages, and the Ask button at the bottom of the screen: the whole screen.
  await page.screenshot({ path: path.join(OUT!, "guide-nav.png") });

  await hideAsk(page);
  const title = page.getByRole("heading", { level: 1, name: "Run real fab data down the line" });
  const note = page.getByText(/^A real sample is a run of consecutive SECOM units/);
  const bar = around([await boxOf(title), await textBoxOf(note)], 24);
  // Not as far down as the line's top rule under the note.
  await capture(page, "guide-input-bar", { ...bar, height: bar.height - 12 });

  await page.getByRole("button", { name: "Draw a defect" }).click();
  const editor = page.getByRole("application", { name: /Wafer 1 of your drawing/ });
  await expect(editor).toBeVisible();
  const e = (await editor.boundingBox())!;
  // A scratch: one stroke across the wafer, as a reader would drag it.
  await page.mouse.move(e.x + e.width * 0.3, e.y + e.height * 0.22);
  await page.mouse.down();
  for (let i = 1; i <= 24; i += 1) {
    await page.mouse.move(
      e.x + e.width * (0.3 + 0.4 * (i / 24)),
      e.y + e.height * (0.22 + 0.5 * (i / 24)),
    );
  }
  await page.mouse.up();
  await expect(page.getByText(/^Wafer 1: \d+ of \d[\d,]* dies failing\.$/)).not.toHaveText(
    /: 0 of/,
  );
  await capture(page, "guide-draw", around([await boxOf(page.locator("#way-draw"))], 8));

  await page.getByRole("button", { name: "Upload a file" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "wafers-example.csv",
    mimeType: "text/csv",
    buffer: readFileSync(UPLOAD!),
  });
  await expect(page.getByText(/This file cannot run yet/)).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(600);
  await capture(page, "guide-upload-check", around([await boxOf(page.locator("#way-upload"))], 8));
});

test("guide: the line running a real sample, and a wafer's drawer", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(`${BASE}/`);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await hideAsk(page);
  await page.getByRole("button", { name: "Try a real sample" }).click();
  await expect(page).toHaveURL(/run=run_/);
  // Mid-run: the first stations done, the next ones computing.
  await expect(page.getByRole("group", { name: "1 Manufacturing" })).toContainText("Done", {
    timeout: 30_000,
  });
  // ...and the first alarm in the rail, so the picture shows where alarms arrive.
  const rail = page.locator('section[aria-labelledby="alarms-title"]');
  await expect(rail.locator("li").first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(Number(process.env.GUIDE_MIDRUN_MS ?? 600));
  const strip = page.getByRole("heading", { level: 2, name: "A random real sample" });
  const status = page.getByText(/^(Running: each station|The run is finished)/);
  await capture(
    page,
    "guide-line-run",
    around([await boxOf(strip), await boxOf(status), await boxOf(rail)]),
    rail,
  );

  const showAll = page.getByRole("button", { name: "Show every result now" });
  await expect(async () => {
    if (await showAll.isVisible()) await showAll.click();
    await expect(
      page.getByText(
        "The run is finished: every station has its result, and nothing more will arrive.",
      ),
    ).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 90_000 });
  await page.getByRole("button", { name: "Open wafer test details" }).click();
  await expect(
    page.getByRole("heading", { level: 4, name: "Pattern probabilities" }),
  ).toBeVisible();
  await page.waitForTimeout(1200);
  // The wafer's map, what the model read in it, and the most similar real wafers (not the method under them).
  const detail = page
    .getByRole("heading", { level: 4, name: "Pattern probabilities" })
    .locator("xpath=ancestor::div[contains(@class,'gap-8')][1]");
  const parts = await detail.evaluate((root) =>
    [...root.children].slice(0, 3).map((el) => {
      const r = el.getBoundingClientRect();
      return {
        x: r.left + window.scrollX,
        y: r.top + window.scrollY,
        width: r.width,
        height: r.height,
      };
    }),
  );
  await capture(page, "guide-drawer-wafer", around(parts));
});

test("guide: a recorded investigation's steps, and the work orders tab", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  // A new visitor has no investigation of its own: the recorded one is the product's example.
  const list = (await (await request.get(`${BASE}/api/v1/investigations`)).json()) as {
    items: { investigation_id: string }[];
    examples: { investigation_id: string }[];
  };
  const id = (list.items[0] ?? list.examples[0])!.investigation_id;
  await page.goto(`${BASE}/investigations/${id}`);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await hideAsk(page);
  // The steps of the recorded run in the order they ran, from the first to the evidence the
  // report cites last (the replay replays these same stored events).
  const run = page
    .locator("section.panel")
    .filter({ has: page.getByRole("heading", { level: 2, name: "Run", exact: true }) });
  const steps = run.locator("li");
  await expect(steps.nth(8)).toBeVisible();
  const panel = await boxOf(run);
  const last = await boxOf(steps.nth(8));
  await capture(page, "guide-investigation-live", {
    x: panel.x,
    y: panel.y,
    width: Math.round(panel.width),
    height: Math.round(last.y + last.height + 4 - panel.y),
  });

  await page.goto(`${BASE}/investigations?tab=work-orders`);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await hideAsk(page);
  await page.waitForTimeout(800);
  const tabs = page.getByRole("navigation", { name: "Investigations views" });
  const audit = page
    .locator("section.panel")
    .filter({ has: page.getByRole("heading", { level: 2, name: "Audit log" }) });
  await capture(page, "guide-work-orders", around([await boxOf(tabs), await boxOf(audit)]));
});

test("guide: the calculator with the reader's own example numbers", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(`${BASE}/how#calculator`);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await hideAsk(page);
  const numbers: Record<string, string> = {
    "Wafers per day": "1000",
    "Minutes an engineer spends per wafer map": "2",
    "Engineer hour cost": "50",
    "Downtime hour cost": "1000",
    "Wafer cost": "500",
  };
  for (const [label, value] of Object.entries(numbers))
    await page.getByLabel(label, { exact: true }).fill(value);
  await page.getByLabel("Wafer cost", { exact: true }).blur();
  await expect(page.getByRole("heading", { level: 2, name: "Per month" })).toBeVisible();
  await page.waitForTimeout(800);
  const yours = page
    .locator("section.panel")
    .filter({ has: page.getByRole("heading", { level: 2, name: "Your numbers" }) });
  const month = page
    .locator("section.panel")
    .filter({ has: page.getByRole("heading", { level: 2, name: "Per month" }) });
  await capture(page, "guide-calculator", around([await boxOf(yours), await boxOf(month)]));
});
