import { expect, test } from "@playwright/test";

import { WAKING, wakingApi } from "../waking";

import { getJson } from "./api";

/**
 * The first visit after a quiet spell, on the composed stack: until the API is up, the proxy in
 * front of it answers the opening of this device's workspace 503 with Retry-After (the test plays
 * the proxy twice, then lets the opening through to the real API). The run asked for meanwhile
 * waits for the workspace, the page saying the service is starting, and is listed in Your work
 * once made: the API recorded it in the workspace that the third opening made.
 */

test("a first visit while the API wakes gets its workspace, and its first run is listed there", async ({
  page,
}) => {
  const work = page.getByRole("region", { name: "Your work" });
  const sessionReads: string[] = [];
  let runsAsked = 0;
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (pathname === "/api/v1/session") sessionReads.push(request.method());
    if (pathname === "/api/v1/runs" && request.method() === "POST") runsAsked += 1;
  });
  const api = await wakingApi(page);

  await page.goto("/");
  await api.second;
  await expect(work).toContainText("Opening this device's workspace.");
  await page.getByRole("button", { name: "Try a real sample" }).click();
  api.answerSecond();
  await expect(page.getByText(WAKING)).toBeVisible();
  await api.third;
  await expect(page.getByText(WAKING)).toBeVisible();
  await expect(work).not.toContainText("Not kept on this server right now.");
  expect(runsAsked).toBe(0);

  api.up();
  await expect(page).toHaveURL(/\?run=run_[0-9a-z]+$/);
  const runId = new URL(page.url()).searchParams.get("run")!;
  await expect(page.getByText(WAKING)).toHaveCount(0);
  // Listed in Your work, as the API keeps it for this workspace.
  await expect(work.locator(`[data-run="${runId}"]`)).toBeVisible();
  const listed = await getJson<{ items: { run_id: string }[] }>(
    page.request,
    "/workspace/runs?archived=false&limit=50",
  );
  expect(listed.items.map((run) => run.run_id)).toEqual([runId]);
  expect(runsAsked).toBe(1);
  // One opening after the wake, and the session was its answer: GET /session was never asked.
  expect(api.asked.openings).toBe(3);
  expect(sessionReads).toEqual([]);
});
