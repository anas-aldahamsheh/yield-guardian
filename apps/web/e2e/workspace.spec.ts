import { SESSION_COOKIE } from "@yield-guardian/contracts";
import { expect, type Browser, type Page, test } from "@playwright/test";

import { expectAccessible } from "./axe";

/**
 * Your work, the handoff to another device and the admin's device sessions, on the production
 * build behind the mock gateway. Each browser context is one device: the mock gives it a
 * workspace of its own on its first page. The mock makes up no runs (the story tests serve runs,
 * e2e/stack/workspace.spec.ts runs real ones), so every workspace here starts and stays empty.
 */

const work = (page: Page) => page.getByRole("region", { name: "Your work" });

/** Opens the Line page and waits until this device's workspace is open and read. */
async function openLine(page: Page) {
  await page.goto("/");
  await expect(work(page).getByText("No runs yet")).toBeVisible();
}

/** A second device: a browser context of its own. */
async function device(browser: Browser) {
  const context = await browser.newContext();
  return { context, page: await context.newPage() };
}

/** Opens Continue on another device and reads the code and link it made. */
async function makeCode(page: Page) {
  await work(page).getByRole("button", { name: "Continue on another device" }).click();
  const dialog = page.getByRole("dialog", { name: "Continue on another device" });
  const shown = dialog.locator("[data-handoff-code] [aria-hidden='true']");
  await expect(shown).toHaveText(/^[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){2}$/);
  return {
    dialog,
    code: (await shown.textContent())!,
    link: await dialog.getByLabel("Link").inputValue(),
  };
}

async function workspaceOf(page: Page): Promise<string> {
  const session = (await (await page.request.get("/api/v1/session")).json()) as {
    workspace: { workspace_id: string } | null;
  };
  return session.workspace!.workspace_id;
}

test("Your work starts empty and invites the first run", async ({ page }) => {
  await openLine(page);
  await expect(work(page)).toContainText("Choose an input above and run it.");
  await expect(work(page)).toContainText("0 runs · kept 30 days after the last visit");
  await expect(
    work(page).getByRole("button", { name: "Continue on another device" }),
  ).toBeEnabled();
  await expectAccessible(page, "Your work, empty", "[data-your-work]", true);
});

test("a first visit asks for its session once, by opening its workspace", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (pathname.startsWith("/api/v1/session")) asked.push(`${request.method()} ${pathname}`);
  });
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v1/session/workspace", async (route) => {
    await held;
    await route.continue();
  });
  await page.goto("/");
  // While the workspace opens, the page waits for it: no visitor controls, no empty list yet.
  await expect(work(page)).toContainText("Opening this device's workspace.");
  await expect(page.getByRole("button", { name: "Try as engineer" })).toHaveCount(0);
  await expect(work(page).getByText("No runs yet")).toHaveCount(0);
  release();
  await expect(work(page).getByText("No runs yet")).toBeVisible();
  await expect(page.getByRole("button", { name: "Try as engineer" }).first()).toBeVisible();
  expect(asked).toEqual(["POST /api/v1/session/workspace"]);
});

test("a code brings another device into this workspace, once", async ({ page, browser }) => {
  await openLine(page);
  const { dialog, code, link } = await makeCode(page);
  expect(link).toBe(`${new URL(page.url()).origin}/join#code=${code}`);
  await expect(dialog).toContainText("It works once, until");
  await expect(dialog.getByRole("listitem")).toHaveCount(1);
  await expectAccessible(page, "handoff dialog", "[role='dialog']", true);

  const phone = await device(browser);
  await phone.page.goto(link);
  await expect(
    phone.page.getByRole("heading", { level: 1, name: "Continue on this device" }),
  ).toBeVisible();
  await expect(phone.page.getByLabel("Code")).toHaveValue(code);
  // The code leaves the address bar and the history at once.
  await expect(phone.page).toHaveURL(/\/join$/);
  // Joining waits for the press.
  expect(await workspaceOf(phone.page)).not.toBe(await workspaceOf(page));
  await expectAccessible(phone.page, "join page, code from the link", undefined, true);
  await phone.page.getByRole("button", { name: "Join the workspace" }).click();
  await expect(phone.page).toHaveURL(/\/$/);
  await expect(
    phone.page
      .locator("[data-sonner-toast]")
      .filter({ hasText: "This device is in the workspace" }),
  ).toBeVisible();
  expect(await workspaceOf(phone.page)).toBe(await workspaceOf(page));

  await expect(
    dialog.getByText("Another device joined: it sees this workspace now."),
  ).toBeVisible();
  await expect(dialog.getByRole("listitem")).toHaveCount(2);
  await expect(dialog.getByRole("listitem").filter({ hasText: "This device" })).toHaveCount(1);
  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(work(page)).toContainText("on 2 devices");

  // A used code works no more.
  const laptop = await device(browser);
  await laptop.page.goto("/join");
  await laptop.page.getByLabel("Code").fill(code.toLowerCase().replaceAll("-", " "));
  await laptop.page.getByRole("button", { name: "Join the workspace" }).click();
  await expect(laptop.page.locator("#join-error")).toHaveText(
    "This code has already been used. Make a new one on the other device.",
  );
  await expect(laptop.page.getByLabel("Code")).toHaveAttribute("aria-invalid", "true");
  await phone.context.close();
  await laptop.context.close();
});

test("a wrong code says what is wrong with it", async ({ page }) => {
  await page.goto("/join");
  const code = page.getByLabel("Code");
  const join = page.getByRole("button", { name: "Join the workspace" });
  await expect(join).toBeDisabled();
  await code.fill("hello");
  await join.click();
  await expect(page.locator("#join-error")).toHaveText(
    "That is not a code: type its 12 letters and digits, for example 7K2M-QX9D-4HRT.",
  );
  await code.fill("UUUU-UUUU-UUUU");
  await join.click();
  await expect(page.locator("#join-error")).toContainText("That is not a handoff code");
  await code.fill("7K2M-QX9D-4HRT");
  await join.click();
  await expect(page.locator("#join-error")).toHaveText(
    "No device made this code. Check it, or make a new one on the other device.",
  );
  await expect(page).toHaveURL(/\/join$/);
});

test("starting a fresh workspace says first what happens to this one", async ({ page }) => {
  await openLine(page);
  const before = await workspaceOf(page);
  const ask = async () => {
    await work(page).getByRole("button", { name: "Workspace options" }).click();
    await page.getByRole("menuitem", { name: "Start a fresh workspace on this device" }).click();
    return page.getByRole("alertdialog", { name: "Start a fresh workspace on this device?" });
  };
  let confirm = await ask();
  await expect(confirm).toContainText("This one holds nothing yet.");
  await confirm.getByRole("button", { name: "Keep this workspace" }).click();
  await expect(confirm).toBeHidden();
  expect(await workspaceOf(page)).toBe(before);

  confirm = await ask();
  await confirm.getByRole("button", { name: "Start fresh" }).click();
  await expect(
    page.locator("[data-sonner-toast]").filter({ hasText: "A fresh workspace" }),
  ).toBeVisible();
  expect(await workspaceOf(page)).not.toBe(before);
  await expect(work(page).getByText("No runs yet")).toBeVisible();
});

test("device sessions are for admins, and never show a cookie", async ({ page, context }) => {
  await page.goto("/admin");
  await expect(
    page.getByText("Only an admin sees device sessions. Sign in as an admin from the top bar."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Admin sign-in" }).first().click();
  const signIn = page.getByRole("dialog", { name: "Admin sign-in" });
  // Test inputs: the mock accepts any name and password.
  await signIn.getByLabel("Username").fill("admin");
  await signIn.getByLabel("Password").fill("mock-only");
  await signIn.getByRole("button", { name: "Sign in" }).click();
  const table = page.getByRole("table", { name: "Device sessions" });
  await expect(table).toBeVisible();
  const mine = table.getByRole("row").filter({ hasText: "· this session" });
  await expect(mine).toHaveCount(1);
  await expect(mine.getByRole("button", { name: /^End session / })).toBeDisabled();
  await expect(page.getByText(/^\d+ active sessions? in \d+ workspaces?\./)).toBeVisible();

  const cookie = (await context.cookies()).find((c) => c.name === SESSION_COOKIE)!.value;
  expect(await page.content()).not.toContain(cookie);
});
