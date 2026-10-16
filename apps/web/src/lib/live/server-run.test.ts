import { SESSION_COOKIE } from "@yield-guardian/contracts";

import { readStoredRun } from "./server-run";

/**
 * The Next.js server's read of a run while it renders the Line page: it carries the visitor's
 * session cookie and no other cookie of theirs, as every server-side read does, so the API
 * answers with the visitor's own workspace (another workspace's run reads as not found).
 */

vi.mock("server-only", () => ({}));
vi.mock("next/server", () => ({ connection: async () => undefined }));

/** The cookies the browser sent with the page request. */
const sent = vi.hoisted(() => new Map<string, string>());
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => (sent.has(name) ? { name, value: sent.get(name)! } : undefined),
  }),
  headers: async () =>
    new Headers({ cookie: [...sent].map(([name, value]) => `${name}=${value}`).join("; ") }),
}));

const VIEW = { station: null, focus: null };

/** The API answering `status`; returns the headers of each request it got. */
function api(status: number) {
  const requests: Headers[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
    requests.push(new Headers(init?.headers));
    return new Response(JSON.stringify({ status }), {
      status,
      headers: { "Content-Type": "application/problem+json" },
    });
  });
  return requests;
}

afterEach(() => {
  sent.clear();
});

describe("the server's read of a run", () => {
  it("carries the session cookie and no other cookie of the visitor's", async () => {
    sent.set("theme", "dark");
    sent.set(SESSION_COOKIE, "token-of-this-device");
    sent.set("_ga", "GA1.2.345.678");
    const requests = api(404);
    expect(await readStoredRun("run_0abc", VIEW)).toEqual({ kind: "not_found", runId: "run_0abc" });
    expect(requests).toHaveLength(1);
    expect(requests[0]!.get("cookie")).toBe(`${SESSION_COOKIE}=token-of-this-device`);
  });

  it("sends no cookie for a visitor without a session", async () => {
    sent.set("theme", "dark");
    const requests = api(404);
    await readStoredRun("run_0abc", VIEW);
    expect(requests[0]!.has("cookie")).toBe(false);
  });

  it("reads 404 as not found and 410 as no longer kept", async () => {
    sent.set(SESSION_COOKIE, "token-of-this-device");
    api(410);
    expect(await readStoredRun("run_0abc", VIEW)).toEqual({ kind: "gone", runId: "run_0abc" });
  });
});
