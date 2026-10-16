import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import type { SessionInfo } from "@yield-guardian/contracts";

import { WorkspaceOpener } from "@/components/workspace/workspace-opener";

import type * as Config from "./config";
import { ApiProvider } from "./context";
import { forgetOpening } from "./opening";
import { useSession } from "./session";

/**
 * A first visit: the page opens this device's workspace (POST /session/workspace) and reads the
 * session from that answer, so it asks the API once and shows no session-less state meanwhile.
 */

// Node's Request needs an absolute URL; in a browser the API is on the page's own origin.
vi.mock("./config", async (importOriginal) => ({
  ...(await importOriginal<typeof Config>()),
  BROWSER_API_BASE: "http://localhost",
}));

const OPENED: SessionInfo = {
  role: "visitor",
  display_name: null,
  expires_at: null,
  csrf_token: "test-csrf",
  workspace: {
    workspace_id: "0b8f3c1e-6a52-4c47-9d0e-2f8a1b7c4d55",
    session_expires_at: "2026-11-14T09:00:00Z",
  },
};

const NO_WORKSPACE: SessionInfo = {
  role: "visitor",
  display_name: null,
  expires_at: null,
  csrf_token: null,
  workspace: null,
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** fetch answered by `answer`, recording each request as "METHOD /path". */
function api(answer: (call: string) => Promise<Response>) {
  const calls: string[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const request = input instanceof Request ? input : null;
    const url = new URL(request ? request.url : String(input), "http://localhost");
    const call = `${request?.method ?? init?.method ?? "GET"} ${url.pathname}`;
    calls.push(call);
    return answer(call);
  });
  return calls;
}

/** What the page shows of the session, in order, each change once. */
function Probe({ seen }: { seen: string[] }) {
  const { session, loading } = useSession();
  const shown = loading
    ? "loading"
    : session.workspace
      ? `workspace ${session.workspace.workspace_id}`
      : "no workspace";
  if (seen.at(-1) !== shown) seen.push(shown);
  return <p data-testid="session">{shown}</p>;
}

function page(seen: string[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  render(
    <ApiProvider>
      <QueryClientProvider client={client}>
        <WorkspaceOpener />
        <Probe seen={seen} />
      </QueryClientProvider>
    </ApiProvider>,
  );
  return client;
}

beforeEach(() => {
  forgetOpening();
});

describe("the session on a first visit", () => {
  it("is the answer of opening the workspace: one request, and loading until it is open", async () => {
    let open!: (response: Response) => void;
    const calls = api((call) =>
      call === "POST /api/v1/session/workspace"
        ? new Promise((resolve) => {
            open = resolve;
          })
        : Promise.resolve(json(NO_WORKSPACE)),
    );
    const seen: string[] = [];
    page(seen);
    await waitFor(() => expect(calls).toEqual(["POST /api/v1/session/workspace"]));
    // The workspace is still opening: the page waits, and says nothing of a missing workspace.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByTestId("session")).toHaveTextContent("loading");

    await act(async () => open(json(OPENED)));
    await waitFor(() =>
      expect(screen.getByTestId("session")).toHaveTextContent(
        `workspace ${OPENED.workspace!.workspace_id}`,
      ),
    );
    expect(seen).toEqual(["loading", `workspace ${OPENED.workspace!.workspace_id}`]);
    expect(calls).toEqual(["POST /api/v1/session/workspace"]);
  });

  it("reads GET /session for any later read, such as the one after signing out", async () => {
    const calls = api((call) =>
      Promise.resolve(json(call === "POST /api/v1/session/workspace" ? OPENED : NO_WORKSPACE)),
    );
    const client = page([]);
    await waitFor(() => expect(screen.getByTestId("session")).toHaveTextContent(/^workspace /));
    await act(async () => client.invalidateQueries({ queryKey: ["session"] }));
    await waitFor(() => expect(screen.getByTestId("session")).toHaveTextContent("no workspace"));
    expect(calls).toEqual(["POST /api/v1/session/workspace", "GET /api/v1/session"]);
  });

  it("asks GET /session once when the API keeps no workspaces", async () => {
    const calls = api((call) =>
      Promise.resolve(
        call === "POST /api/v1/session/workspace" ? json({}, 503) : json(NO_WORKSPACE),
      ),
    );
    const seen: string[] = [];
    page(seen);
    await waitFor(() => expect(screen.getByTestId("session")).toHaveTextContent("no workspace"));
    expect(seen).toEqual(["loading", "no workspace"]);
    expect(calls).toEqual(["POST /api/v1/session/workspace", "GET /api/v1/session"]);
  });
});
