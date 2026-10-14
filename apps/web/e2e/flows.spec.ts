import { expect, test } from "@playwright/test";

test("the line goes live over the WebSocket", async ({ page }) => {
  await page.goto("/line");
  await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Control charts (FDC)" })).toBeVisible();
});

test("an engineer approves an action and a work order opens", async ({ page }) => {
  await page.goto("/investigations/inv_01jae5x9k3m2q7r8s0t1v2w3x4");
  await page.getByRole("button", { name: "Try as engineer" }).last().click();
  await page.getByRole("checkbox", { name: "Approve action 2" }).uncheck();
  await page.getByRole("button", { name: /^Approve 1 action/ }).click();
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: "Approved" })).toContainText("Work order");
});

test("an engineer records an outcome on a work order", async ({ page }) => {
  await page.goto("/work-orders/WO-000012");
  await page.getByRole("button", { name: "Try as engineer" }).last().click();
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  await page.getByRole("radio", { name: "Done" }).click();
  await page.getByLabel("Outcome", { exact: true }).fill("Worn seal on the chamber door, replaced.");
  await page.getByRole("checkbox", { name: /I confirm this outcome/ }).check();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: "Saved" })).toContainText("WO-000012 is updated");
});

test("chat answers with a citation and a number check", async ({ page }) => {
  await page.goto("/units/1062");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  const sheet = page.getByRole("dialog");
  await sheet.getByRole("button", { name: "Try as engineer" }).click();
  await sheet.getByRole("button", { name: /Why was unit 1062 flagged/ }).click();
  await expect(sheet.getByRole("button", { name: "E1" })).toBeVisible();
  await expect(sheet).toContainText("checked against the evidence");
  await sheet.getByRole("button", { name: "E1" }).click();
  await expect(sheet).toContainText("Unit 1062: risk");
});

test("sensor field moves with the arrow keys", async ({ page }) => {
  await page.goto("/sensors?sensor=S060");
  await page.getByRole("img", { name: /Health of 590 sensors/ }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(/sensor=S061/);
});

test("a recorded run says which data it read", async ({ page }) => {
  await page.goto("/investigations/inv_01jae5x9k3m2q7r8s0t1v2w3x4");
  await expect(page.getByText("Recorded run: generated once, replayed without calling a model")).toBeVisible();
  await expect(page.getByText(/^Data as of unit 1062, \d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)).toBeVisible();
});
