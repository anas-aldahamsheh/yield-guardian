import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

/** WCAG 2.2 A and AA rules plus axe best practices. */
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];

export const VIEWPORTS = [
  { name: "1440", width: 1440, height: 900 },
  { name: "375", width: 375, height: 812 },
] as const;
export const SCHEMES = ["light", "dark"] as const;

/** Runs axe on the page as it is; logs every finding and fails on serious or critical ones. */
export async function expectAccessible(page: Page, label: string, include?: string) {
  let builder = new AxeBuilder({ page }).withTags(TAGS);
  if (include) builder = builder.include(include);
  const results = await builder.analyze();
  const lines = results.violations.map(
    (v) =>
      `${v.impact} ${v.id}: ${v.help}\n${v.nodes
        .slice(0, 6)
        .map((n) => `    ${n.target.join(" ")}  ${n.failureSummary?.split("\n").slice(1, 2).join("") ?? ""}`)
        .join("\n")}`,
  );
  if (lines.length) console.log(`${label}\n  ${lines.join("\n  ")}`);
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => v.id), `serious or critical axe violations on ${label}`).toEqual([]);
}

/** Loads a route and lets data and entrance motion settle before axe measures contrast. */
export async function settle(page: Page, path: string) {
  const response = await page.goto(path);
  expect(response?.status()).toBe(200);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(800);
}
