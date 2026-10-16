import type { Page } from "@playwright/test";

/**
 * The API asleep on a first visit, for the opening of this device's workspace: the test plays
 * the proxy in front of the API, which answers 503 with Retry-After until the API is up.
 */

/** What the Line page says of a run asked for while the API wakes. */
export const WAKING =
  "The service is starting after a quiet spell; the run starts as soon as it answers.";

/** A promise, and the function that keeps it. */
function signal() {
  let fire!: () => void;
  const fired = new Promise<void>((resolve) => {
    fire = resolve;
  });
  return { fired, fire };
}

/**
 * POST /session/workspace before the API is up: the first two answer 503 with Retry-After (the
 * second only once `answerSecond` is called), and the third goes through to the API once `up` is
 * called. `second` and `third` are kept when those requests arrive.
 */
export async function wakingApi(page: Page) {
  const second = signal();
  const answerSecond = signal();
  const third = signal();
  const up = signal();
  const asked = { openings: 0 };
  await page.route("**/api/v1/session/workspace", async (route) => {
    asked.openings += 1;
    if (asked.openings === 2) {
      second.fire();
      await answerSecond.fired;
    }
    if (asked.openings >= 3) {
      third.fire();
      await up.fired;
      return route.continue();
    }
    return route.fulfill({
      status: 503,
      headers: { "Retry-After": "1" },
      contentType: "text/plain",
      body: "Starting.",
    });
  });
  return {
    asked,
    second: second.fired,
    answerSecond: answerSecond.fire,
    third: third.fired,
    up: up.fire,
  };
}
