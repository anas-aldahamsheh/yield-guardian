import { expect, type Page } from "@playwright/test";

/**
 * What `read` reads once nothing on the page moves any more: two reads in a row are the same,
 * with half a second of animation time between them. A unit chosen in the drawer glides the dials
 * to it for 0.45 s of animation time, which a loaded machine stretches well past 0.45 s of wall
 * time: GSAP's ticker counts a frame that comes over half a second late as 33 ms. The wait counts
 * frames the same way, so it outlasts any glide under way at the first read, and two reads that
 * match read the page at rest.
 */
export async function steady<T>(page: Page, read: () => Promise<T>): Promise<T> {
  const last: { value?: T; text?: string } = {};
  await expect
    .poll(
      async () => {
        await page.evaluate(
          () =>
            new Promise<void>((done) => {
              let before = performance.now();
              let animated = 0;
              const frame = (now: number) => {
                const gap = now - before;
                before = now;
                animated += gap > 500 ? 33 : Math.max(0, gap);
                if (animated >= 500) done();
                else requestAnimationFrame(frame);
              };
              requestAnimationFrame(frame);
            }),
        );
        const value = await read();
        const text = JSON.stringify(value);
        const same = text === last.text;
        Object.assign(last, { value, text });
        return same;
      },
      { intervals: [100], timeout: 60_000 },
    )
    .toBe(true);
  return last.value as T;
}
