import { SESSION_COOKIE } from "@yield-guardian/contracts";
import { expect, test, type Request } from "@playwright/test";

import { WAKING, wakingApi } from "../waking";

import { RUN_ID, fixture } from "./fixture";
import { GATEWAY, startStoryProxy, type StoryProxy } from "./stub";

/**
 * The first visit after a quiet spell: the API is asleep, and the proxy in front of it answers
 * 503 with Retry-After until it is up (the test plays the proxy for POST /session/workspace).
 * The page waits for the API to open this device's workspace, saying the service is starting and
 * never that something failed, and a run asked for meanwhile is made once the workspace is open,
 * with its session. The runs API is the stand-in of stub.ts; the session and the workspace are
 * the gateway's development double, which lists no runs (it makes none up): that the run is then
 * listed in Your work is shown with the real API, in e2e/stack/opening.spec.ts.
 */

let proxy: StoryProxy;
test.beforeAll(async () => {
  proxy = await startStoryProxy(GATEWAY);
});
test.afterAll(async () => proxy.close());
test.beforeEach(() => {
  proxy.configure({
    run: RUN_ID,
    pacing: { pace: 0, holdBefore: null, dropAfter: null },
    gone: false,
    browserReadDelay: 0,
  });
});

test("a first visit while the API wakes gets its workspace, and a run asked for meanwhile is made in it", async ({
  page,
}) => {
  const work = page.getByRole("region", { name: "Your work" });
  const sessionReads: string[] = [];
  const runs: Request[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (pathname === "/api/v1/session") sessionReads.push(request.method());
    if (pathname === "/api/v1/runs" && request.method() === "POST") runs.push(request);
  });
  const api = await wakingApi(page);
  const created = proxy.created.length;

  await page.goto(`${proxy.origin}/`);
  await api.second;
  // The opening waits for the API and asks again: the page waits with it and fails nothing.
  await expect(work).toContainText("Opening this device's workspace.");
  await expect(page.getByRole("button", { name: "Try as engineer" })).toHaveCount(0);

  // A run asked for now waits for the workspace, and says why once the API answered that it wakes.
  await page.getByRole("button", { name: "Try a real sample" }).click();
  await expect(page.getByRole("button", { name: "Starting the run" })).toBeDisabled();
  api.answerSecond();
  await expect(page.getByText(WAKING)).toBeVisible();
  await api.third;
  await expect(page.getByText(WAKING)).toBeVisible();
  await expect(work).toContainText("Opening this device's workspace.");
  await expect(work).not.toContainText("Not kept on this server right now.");
  await expect(page.getByText(/^The (service is starting|API did not answer)\. /)).toHaveCount(0);
  expect(runs).toHaveLength(0);
  expect(proxy.created).toHaveLength(created);

  // The API is up: the workspace opens, and the run is made in it, with its session.
  api.up();
  await expect(page).toHaveURL(new RegExp(`\\?run=${RUN_ID}$`));
  await expect(
    page.getByRole("heading", { level: 2, name: fixture.created.origin.title }),
  ).toBeVisible();
  await expect(page.getByText(WAKING)).toHaveCount(0);
  await expect(work).not.toContainText("Opening this device's workspace.");
  await expect(work.getByRole("button", { name: "Continue on another device" })).toBeEnabled();
  const session = (await page.context().cookies()).find((c) => c.name === SESSION_COOKIE);
  expect(session?.value).toBeTruthy();
  expect(runs).toHaveLength(1);
  expect((await runs[0]!.allHeaders()).cookie).toContain(`${SESSION_COOKIE}=${session!.value}`);
  expect(proxy.created).toHaveLength(created + 1);

  // One opening after the wake, and the session was its answer: GET /session was never asked.
  expect(api.asked.openings).toBe(3);
  expect(sessionReads).toEqual([]);
});
