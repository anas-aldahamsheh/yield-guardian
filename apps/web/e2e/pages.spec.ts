import { expect, type Page, test } from "@playwright/test";

import { TEST_DOUBLE } from "../src/mocks/test-doubles";

/**
 * v2 pages (V9, V10, V11) on the production build behind the mock gateway: redirects, the
 * three-item navigation, How it works and its calculator, the grouped Investigations with the
 * hypothesis table and the Work orders tab, and the floating chat at 360 px.
 */

const INVESTIGATION = "inv_01jae5x9k3m2q7r8s0t1v2w3x4";
/** The product's example: a recorded run every visitor sees, read-only. */
const EXAMPLE = "inv_01jadz4r8c0q2m6t9v1x3b5d7f";

/** Every v1 address and where it now lives. Relative, so it works behind any gateway. */
const REDIRECTS: [string, string][] = [
  ["/line", "/"],
  ["/wafers", "/?station=3"],
  ["/wafers?wafer=lot47542-1", "/?pick=wafer:lot47542-1"],
  ["/wafers/lot47542-1", "/?pick=wafer:lot47542-1"],
  ["/lots", "/?station=3"],
  ["/lots/lot47542", "/?pick=lot:lot47542"],
  ["/units/1062", "/?pick=unit:1062"],
  ["/units/1062?tab=shap", "/?pick=unit:1062&tab=shap"],
  ["/sensors", "/?station=2"],
  ["/sensors?sensor=S060", "/?station=2&sensor=S060"],
  ["/work-orders", "/investigations?tab=work-orders"],
  ["/work-orders/WO-000012", `/investigations/${INVESTIGATION}#work-order`],
  ["/work-orders/WO-999999", "/investigations?tab=work-orders&order=WO-999999"],
  ["/models", "/how#models"],
  ["/methods", "/how#methods"],
  ["/guide", "/how#guide"],
];

test.describe("redirects", () => {
  for (const [from, to] of REDIRECTS) {
    test(`${from} moves permanently to ${to}`, async ({ request }) => {
      const response = await request.get(from, { maxRedirects: 0 });
      expect(response.status()).toBe(308);
      expect(response.headers()["location"]).toBe(to);
    });
  }

  test("a browser following an old link lands on the section", async ({ page }) => {
    await page.goto("/methods");
    await expect(page).toHaveURL(/\/how#methods$/);
    await expect(page.locator("#methods")).toBeInViewport();
    await page.goto("/work-orders/WO-000011");
    await expect(page).toHaveURL(/\/investigations\/inv_01jae2kq0c4w6f8h1j3m5n7p9r#work-order$/);
    await expect(page.locator("#work-order [data-work-order='WO-000011']")).toBeVisible();
  });
});

async function navLabels(page: Page) {
  const nav = page.getByRole("navigation", { name: "Main" });
  const links = nav.getByRole("link");
  await expect(links).toHaveCount(3);
  return (await links.allInnerTexts()).map((t) => t.split("\n")[0]!.trim());
}

test("the navigation has three items, desktop and phone", async ({ page }) => {
  await page.goto("/how");
  expect(await navLabels(page)).toEqual(["Line", "Investigations", "How it works"]);
  await expect(
    page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "How it works" }),
  ).toHaveAttribute("aria-current", "page");
  // Nothing in the shell keeps time or moves on its own.
  await expect(page.locator("header time, header [data-plant-clock]")).toHaveCount(0);

  await page.setViewportSize({ width: 360, height: 740 });
  await page.getByRole("button", { name: "Open the menu" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("link")).toHaveCount(3);
  const names = (await dialog.getByRole("link").allInnerTexts()).map((t) =>
    t.split("\n")[0]!.trim(),
  );
  expect(names).toEqual(["Line", "Investigations", "How it works"]);
});

test.describe("How it works", () => {
  test("plain Arabic first, then the expert sections and the guide, each with its anchor", async ({
    page,
  }) => {
    await page.goto("/how");
    const plain = page.locator("[lang='ar'][dir='rtl']").first();
    await expect(plain.locator("h1")).toHaveText("كيف يعمل Yield Guardian");
    for (const id of ["what", "sources", "limits"])
      await expect(plain.locator(`#${id}`)).toHaveCount(1);
    for (const id of ["experts", "results", "models", "methods", "data", "calculator"])
      await expect(page.locator(`#${id}`)).toHaveCount(1);
    await expect(page.locator("#experts")).toHaveAttribute("lang", "en");
    await expect(page.locator("#guide")).toHaveAttribute("dir", "rtl");
    await expect(page.locator("#guide")).toHaveAttribute("lang", "ar");
    // The order on the page: plain Arabic, experts, guide.
    const top = async (sel: string) => (await page.locator(sel).boundingBox())!.y;
    expect(await top("#limits")).toBeLessThan(await top("#experts"));
    expect(await top("#calculator")).toBeLessThan(await top("#guide"));
    for (const id of ["models", "methods", "calculator", "guide"]) {
      await page.goto(`/how#${id}`);
      await expect(page.locator(`#${id}`)).toBeInViewport();
    }
  });

  test("the limits read their numbers from the API", async ({ page, request }) => {
    const metrics = await (await request.get("/api/v1/methods/secom")).json();
    const points = await (await request.get("/api/v1/secom/operating-points")).json();
    const roc = metrics.models
      .find((m: { main: boolean }) => m.main)
      .metrics.find((x: { metric: string }) => x.metric === "roc_auc").estimate.value as number;
    const point = points.points.find((p: { id: string }) => p.id === points.default) as {
      tp: number;
      fn: number;
    };
    await page.goto("/how#limits");
    const limits = page.locator("[data-limits]");
    await expect(limits).toContainText(roc.toFixed(2));
    await expect(limits.locator("bdi", { hasText: new RegExp(`^${point.tp}$`) })).toHaveCount(1);
    await expect(
      limits.locator("bdi", { hasText: new RegExp(`^${point.tp + point.fn}$`) }),
    ).toHaveCount(1);
  });

  test("the guide opens an entry from the address and searches in Arabic", async ({ page }) => {
    await page.goto("/how#guide-investigate");
    await expect(page.locator("details#guide-investigate")).toHaveAttribute("open", "");
    await page.getByRole("searchbox", { name: "ابحث في الدليل" }).fill("Upload a file");
    await expect(page.locator("details#guide-upload")).toHaveAttribute("open", "");
    // Its screenshot is served from public/guide/ by the production build, at its own size.
    const shot = page.locator("figure[data-shot='guide-upload-check'] img");
    await expect(shot).toBeVisible();
    await expect(shot).toHaveAttribute("alt", /^لوحة Upload a file/);
    await expect
      .poll(() => shot.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth))
      .toBe(1392);
  });
});

test.describe("savings calculator", () => {
  const line = (page: Page, id: string) => page.locator(`[data-line='${id}']`);

  test("shows nothing until numbers are typed, then a value with its range", async ({
    page,
    request,
  }) => {
    const results = await (await request.get("/api/v1/results")).json();
    const rate = results.results.find((r: { id: string }) => r.id === "fdc_false_alarm_rate")
      .estimate as { value: number; ci_low: number; ci_high: number };
    await page.goto("/how#calculator");
    const calc = page.locator("#calculator");
    await expect(calc.getByText("Nothing to compute yet")).toBeVisible();
    await expect(calc.locator("[data-value] .readout")).toHaveCount(0);
    for (const name of [
      "Wafers per day",
      "Minutes an engineer spends per wafer map",
      "Engineer hour cost",
      "Downtime hour cost",
      "Wafer cost",
    ])
      await expect(calc.getByLabel(name)).toHaveValue("");

    await calc.getByLabel("Wafers per day").fill("100");
    const month = 100 * 30;
    const fmt = (v: number) => Math.round(v).toLocaleString("en-US");
    await expect(calc.getByText("Nothing to compute yet")).toHaveCount(0);
    await expect(line(page, "falseAlarms").locator(".readout")).toHaveText(fmt(month * rate.value));
    await expect(line(page, "falseAlarms")).toContainText(
      `${fmt(month * rate.ci_low)} to ${fmt(month * rate.ci_high)}`,
    );
    await expect(line(page, "downtimeMoney")).toContainText("Needs downtime hour cost");

    await calc.getByLabel("Downtime hour cost").fill("2,000");
    await expect(line(page, "downtimeMoney").locator(".readout")).toHaveText(
      fmt(month * rate.value * 2000),
    );
    await expect(line(page, "downtimeMoney")).toContainText(
      `${fmt(month * rate.ci_low * 2000)} to ${fmt(month * rate.ci_high * 2000)}`,
    );
    // The formula reads the typed numbers.
    await expect(line(page, "downtimeMoney").locator("[data-formula]")).toHaveText(
      /^Formula: 100 wafers a day × 30 days × .* × 2,000 per downtime hour$/,
    );

    await calc.getByLabel("Wafers per day").fill("0");
    await expect(line(page, "falseAlarms").locator(".readout")).toHaveText("0");
    await expect(line(page, "falseAlarms")).toContainText("0 to 0");

    await calc.getByLabel("Wafer cost").fill("-3");
    await expect(calc.getByLabel("Wafer cost")).toHaveAttribute("aria-invalid", "true");
    await expect(calc).toContainText("Enter 0 or more.");

    await calc.getByRole("button", { name: "Clear" }).click();
    await expect(calc.getByText("Nothing to compute yet")).toBeVisible();
    await expect(calc.locator("[data-value] .readout")).toHaveCount(0);
  });

  test("a rate that is not measured keeps its lines empty", async ({ page, request }) => {
    const results = await (await request.get("/api/v1/results")).json();
    const auto = results.results.find((r: { id: string }) => r.id === "auto_classified_share");
    test.skip(auto?.estimate != null, "the fixture API measures the auto-classified share");
    await page.goto("/how#calculator");
    const calc = page.locator("#calculator");
    await calc.getByLabel("Wafers per day").fill("100");
    await calc.getByLabel("Minutes an engineer spends per wafer map").fill("2");
    await expect(line(page, "hours")).toContainText(
      "Needs the measured share classified automatically",
    );
    await expect(calc).toContainText(
      "Not measured yet, so the share classified automatically lines stay empty.",
    );
  });
});

test.describe("Investigations", () => {
  test("groups the list by where each investigation stands", async ({ page }) => {
    await page.goto("/investigations");
    for (const g of ["running", "awaiting", "decided"])
      await expect(page.locator(`[data-group='${g}']`)).toBeVisible();
    await expect(
      page.locator("[data-group='awaiting']").getByRole("link", { name: /./ }).first(),
    ).toHaveAttribute("href", `/investigations/${INVESTIGATION}`);
    await expect(
      page
        .getByRole("navigation", { name: "Investigations views" })
        .getByRole("link", { name: "Investigations" }),
    ).toHaveAttribute("aria-current", "page");
  });

  test("the recorded example is listed apart from the visitor's own, and is read-only", async ({
    page,
  }) => {
    await page.goto("/investigations");
    const example = page.locator("[data-group='example']");
    await expect(example.getByRole("heading", { name: /^Example\b/ })).toBeVisible();
    await expect(example.locator("tbody tr")).toHaveCount(1);
    await expect(example.locator("tbody tr")).toContainText("Recorded");
    await expect(example.getByRole("link", { name: /./ }).first()).toHaveAttribute(
      "href",
      `/investigations/${EXAMPLE}`,
    );
    // The visitor's own stay in their groups, without it.
    await expect(page.locator("[data-group='awaiting'] tbody tr")).toHaveCount(1);
    await expect(page.locator("[data-group='awaiting']")).not.toContainText("Recorded");

    // An engineer opens it: nothing to approve or reject, and where to decide one's own.
    await page.goto(`/investigations/${EXAMPLE}`);
    await page.getByRole("button", { name: "Try as engineer" }).last().click();
    await expect(page.getByText("Engineer", { exact: true }).first()).toBeVisible();
    const note = page.locator("[data-example-note]");
    await expect(note).toContainText(
      "This recorded example is the same for every visitor, so nobody decides it.",
    );
    await expect(note.getByRole("link", { name: "Open the line" })).toHaveAttribute("href", "/");
    await expect(page.getByRole("checkbox", { name: /^Approve action/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Approve \d/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Reject report" })).toHaveCount(0);
  });

  test("the Work orders tab lists every work order with the audit log", async ({ page }) => {
    await page.goto("/investigations");
    await page
      .getByRole("navigation", { name: "Investigations views" })
      .getByRole("link", { name: "Work orders" })
      .click();
    await expect(page).toHaveURL(/\/investigations\?tab=work-orders$/);
    const table = page.getByRole("table", { name: "Work orders" });
    await expect(table.getByRole("link", { name: "WO-000012" })).toHaveAttribute(
      "href",
      `/investigations/${INVESTIGATION}#work-order`,
    );
    await expect(table.getByRole("link", { name: "WO-000011" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Audit log" })).toBeVisible();

    await page.goto("/investigations?tab=work-orders&order=WO-000011");
    await expect(page.locator("#work-order [data-work-order='WO-000011']")).toBeVisible();
    await expect(
      page.locator("#work-order").getByRole("link", { name: /^investigation inv_/ }),
    ).toBeVisible();
  });

  test("a report with hypotheses shows the table, linked to its evidence", async ({ page }) => {
    await page.goto(`/investigations/${TEST_DOUBLE.investigationId}`);
    const table = page.locator("[data-hypotheses]");
    await expect(table.getByRole("heading", { name: "Hypotheses" })).toBeVisible();
    await expect(table.locator("tbody tr")).toHaveCount(2);
    for (const col of ["Hypothesis", "Sources", "Evidence for", "Evidence against", "Assessment"])
      await expect(table.getByRole("columnheader", { name: col })).toBeVisible();
    const first = table.locator("tbody tr").first();
    await expect(first).toHaveAttribute("data-assessment", "supported");
    await expect(table.locator("tbody tr").nth(1)).toHaveAttribute(
      "data-assessment",
      "not_supported",
    );
    await expect(first.getByRole("cell", { name: "Supported" })).toBeVisible();
    // Each observation carries the evidence it comes from.
    await expect(first).toContainText("Test double: similar units did not raise the alarm.");
    await expect(first).toContainText("Example source title");
    await first.getByRole("button", { name: "Show evidence E3" }).click();
    await expect(page.getByRole("button", { name: "Show evidence E3" }).first()).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // A number in a hypothesis links to its evidence value, like any number in the report.
    await first.getByRole("button", { name: /from evidence E2/ }).click();
    await expect(first.getByRole("button", { name: /from evidence E2/ })).toHaveClass(/lit/);
  });

  test("a report that tests no hypothesis shows no table", async ({ page }) => {
    await page.goto(`/investigations/${INVESTIGATION}`);
    await expect(page.getByRole("heading", { name: "Findings" })).toBeVisible();
    await expect(page.locator("[data-hypotheses]")).toHaveCount(0);
  });

  test("the work order sits inside its investigation, with the confirmed cause", async ({
    page,
  }) => {
    await page.goto(`/investigations/${TEST_DOUBLE.investigationId}#work-order`);
    const order = page.locator("#work-order");
    await expect(order).toBeInViewport();
    await expect(
      order.getByRole("heading", { name: `Work order ${TEST_DOUBLE.workOrderId}` }),
    ).toBeVisible();
    const cause = order.locator("[data-confirmed-cause]");
    await expect(cause).toContainText("Test double: the engineer found the cause on the tool.");
    await expect(cause.locator("[data-confirms]")).toHaveText(
      "Confirms hypothesis 1 of the report: Test double: the sensor group with the largest T² share is associated with the alarm.",
    );
    // The decision links to it in place.
    await expect(
      page.getByRole("link", { name: `Work order ${TEST_DOUBLE.workOrderId}` }),
    ).toHaveAttribute("href", `/investigations/${TEST_DOUBLE.investigationId}#work-order`);
  });

  test("an engineer edits the confirmed cause of a closed work order", async ({ page }) => {
    await page.goto(`/investigations/${TEST_DOUBLE.investigationId}#work-order`);
    const order = page.locator("#work-order");
    await order.getByRole("button", { name: "Try as engineer" }).click();
    const editor = order.locator("[data-cause-editor]");
    await expect(editor.getByLabel("What caused it")).toHaveValue(
      "Test double: the engineer found the cause on the tool.",
    );
    await expect(editor.getByRole("radio", { name: /^1\. / })).toBeChecked();
    await expect(order.getByRole("button", { name: "Save" })).toBeDisabled();

    await editor.getByLabel("What caused it").fill("A worn seal on the chamber door.");
    await editor.getByRole("radio", { name: /^2\. / }).check();
    await order.getByRole("button", { name: "Save" }).click();
    await expect(page.locator("[data-sonner-toast]").filter({ hasText: "Saved" })).toBeVisible();
    const cause = order.locator("[data-confirmed-cause]");
    await expect(cause).toContainText("A worn seal on the chamber door.");
    await expect(cause.locator("[data-confirms]")).toContainText(
      "Confirms hypothesis 2 of the report",
    );

    // The cause belongs to a closed work order: reopening it says the cause is withdrawn.
    await order.getByRole("radio", { name: "In progress" }).click();
    await expect(editor).toHaveCount(0);
    await expect(order.getByRole("note")).toHaveText(
      "Reopening the work order withdraws its confirmed cause.",
    );
  });

  test("a finished run states how long it took", async ({ page }) => {
    await page.goto(`/investigations/${INVESTIGATION}`);
    await expect(page.locator("[data-run-elapsed]")).toContainText(
      /^Took (\d+ s|\d+ min \d{2} s|\d+ h \d{2} min)$/,
    );
  });
});

test.describe("floating chat at 360 px", () => {
  test.use({ viewport: { width: 360, height: 740 } });

  for (const path of ["/how", "/investigations", `/investigations/${INVESTIGATION}`]) {
    test(`on ${path} it is reachable by keyboard and covers no content`, async ({ page }) => {
      await page.goto(path);
      const ask = page.getByRole("button", { name: "Ask", exact: true });
      await expect(ask).toBeEnabled();
      // The button is the last stop in the tab order: Shift+Tab from the top reaches it.
      await page.locator("body").focus();
      await page.keyboard.press("Shift+Tab");
      await expect(ask).toBeFocused();

      // At the very bottom, the footer's last line ends above the button.
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      const button = (await ask.boundingBox())!;
      const footer = (await page.locator("footer").getByRole("link").last().boundingBox())!;
      expect(footer.y + footer.height).toBeLessThanOrEqual(button.y);
      expect(button.x + button.width).toBeLessThanOrEqual(360);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
      ).toBeLessThanOrEqual(1);

      await page.keyboard.press("Enter");
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(ask).toBeFocused();
    });
  }
});
