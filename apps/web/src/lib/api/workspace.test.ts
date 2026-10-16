import { afterEach, describe, expect, it, vi } from "vitest";

import { codeFromHash } from "./workspace";

afterEach(() => {
  vi.resetModules();
});

const visitor = {
  role: "visitor",
  display_name: null,
  expires_at: null,
  csrf_token: "test-csrf",
  workspace: {
    workspace_id: "0b8f3c1e-6a52-4c47-9d0e-2f8a1b7c4d55",
    session_expires_at: "2026-11-14T09:00:00Z",
  },
};

describe("opening this device's workspace", () => {
  it("asks the API once per page load, however many callers wait for it", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify(visitor), { status: 200 }));
    const { openWorkspace, workspaceReady } = await import("./workspace");
    const [a, b] = await Promise.all([openWorkspace(), openWorkspace(), workspaceReady()]);
    expect(a).toEqual(visitor);
    expect(b).toBe(a);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]![0]).toBe("/api/v1/session/workspace");
    expect(fetch.mock.calls[0]![1]).toMatchObject({ method: "POST", credentials: "include" });
  });

  it("goes on without a workspace when the API keeps none or does not answer", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 503 }));
    const first = await import("./workspace");
    expect(await first.openWorkspace()).toBeNull();
    vi.resetModules();
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Network error"));
    const second = await import("./workspace");
    expect(await second.openWorkspace()).toBeNull();
    await expect(second.workspaceReady()).resolves.toBeUndefined();
  });
});

describe("a join link", () => {
  it("carries its code after #, which no server receives", () => {
    expect(codeFromHash("#code=7K2M-QX9D-4HRT")).toBe("7K2M-QX9D-4HRT");
    expect(codeFromHash("#from=phone&code=7k2m%20qx9d%204hrt")).toBe("7k2m qx9d 4hrt");
    expect(codeFromHash("")).toBeNull();
    expect(codeFromHash("#nocode")).toBeNull();
    expect(codeFromHash("#code=%E0%A4%A")).toBeNull();
    expect(codeFromHash(`#code=${"A".repeat(40)}`)).toHaveLength(24);
  });
});
