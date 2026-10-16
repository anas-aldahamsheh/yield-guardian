import { expect, test } from "@playwright/test";

test("an engineer approves an action and a work order opens", async ({ page }) => {
  await page.goto("/investigations/inv_01jae5x9k3m2q7r8s0t1v2w3x4");
  await page.getByRole("button", { name: "Try as engineer" }).last().click();
  await page.getByRole("checkbox", { name: "Approve action 2" }).uncheck();
  await page.getByRole("button", { name: /^Approve 1 action/ }).click();
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: "Approved" })).toContainText(
    "Work order",
  );
});

test("an engineer records an outcome on a work order", async ({ page }) => {
  await page.goto("/investigations?tab=work-orders&order=WO-000012");
  await page.getByRole("button", { name: "Try as engineer" }).last().click();
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  await page.getByRole("radio", { name: "Done" }).click();
  await page
    .getByLabel("Outcome", { exact: true })
    .fill("Worn seal on the chamber door, replaced.");
  await page.getByRole("checkbox", { name: /I confirm this outcome/ }).check();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: "Saved" })).toContainText(
    "WO-000012 is updated",
  );
});

test("chat answers with a citation and a number check", async ({ page }) => {
  // The Line with a real unit picked: the chat knows which unit is on screen.
  await page.goto("/?pick=unit:1062");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  const sheet = page.getByRole("dialog");
  await sheet.getByRole("button", { name: "Try as engineer" }).click();
  await sheet.getByRole("button", { name: /Why was unit 1062 flagged/ }).click();
  await expect(sheet.getByRole("button", { name: "E1" })).toBeVisible();
  await expect(sheet).toContainText("checked against the evidence");
  await sheet.getByRole("button", { name: "E1" }).click();
  await expect(sheet).toContainText("Unit 1062: risk");
  // The answer offers an investigation; only the click starts it (POST /investigations).
  const offer = sheet.locator("[data-chat-offer]");
  await expect(offer).toContainText("Suggested investigation: Unit 1062");
  const started = page.waitForRequest(
    (r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/v1/investigations",
  );
  await offer.getByRole("button", { name: "Start investigation" }).click();
  expect((await started).postDataJSON()).toEqual({ trigger: { kind: "unit", ref: "1062" } });
  await expect(page).toHaveURL(/\/investigations\/inv_[0-9a-z]+$/);
});

test("a recorded run says which data it read", async ({ page }) => {
  await page.goto("/investigations/inv_01jadz4r8c0q2m6t9v1x3b5d7f");
  await expect(
    page.getByText("Recorded run: generated once, replayed without calling a model"),
  ).toBeVisible();
  await expect(
    page.getByText(/^Data as of unit 1062, \d{4}-\d{2}-\d{2} \d{2}:\d{2}$/),
  ).toBeVisible();
});
