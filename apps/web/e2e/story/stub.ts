import http, { type IncomingMessage, type ServerResponse } from "node:http";
import net, { type AddressInfo } from "node:net";

import type { RunEvent, StageState } from "@yield-guardian/contracts";

import {
  RUN_ID,
  SENSORS_ONLY_ID,
  fixture,
  sampleEvents,
  sensorsOnlyEvents,
  snapshotOf,
} from "./fixture";

/**
 * Test-only stand-in for the runs API (PLAN_V2 §3.3) until the runs worker's routes are served.
 * A small proxy in front of the gateway the Playwright config starts: it answers /api/v1/runs and
 * /api/v1/uploads from the real-data run fixture and passes everything else through. The event
 * stream streams as the API's would: one stage result after another, `pace` ms apart, resuming
 * from Last-Event-ID, and, when asked, holding before a stage's result until the test releases
 * it. Tests open the page on the proxy's origin.
 */

export { SENSORS_ONLY_ID };

const RUNS: Record<string, readonly RunEvent[]> = {
  [RUN_ID]: sampleEvents,
  [SENSORS_ONLY_ID]: sensorsOnlyEvents(),
};

export interface Pacing {
  /** Delay before each stage's result, so its station is seen computing. */
  pace?: number;
  /** Hold the stream before this stage's result until release() is called. */
  holdBefore?: StageState["stage"] | null;
  /** Close the stream after this many events (once), to make the client resume. */
  dropAfter?: number | null;
}

export interface StoryProxy {
  origin: string;
  /** Bodies of POST /runs, in order. */
  created: unknown[];
  /** Multipart bodies of POST /uploads, as text. */
  uploads: string[];
  /** Last-Event-ID of each request to the event stream, in order (null for the first). */
  resumes: (string | null)[];
  configure(options: { run?: string; pacing?: Pacing; gone?: boolean }): void;
  /** Lets a held stream go on. */
  release(): void;
  close(): Promise<void>;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function send(res: ServerResponse, status: number, body: unknown) {
  res.writeHead(status, {
    "Content-Type": status >= 400 ? "application/problem+json" : "application/json",
  });
  res.end(JSON.stringify(body));
}

async function readBody(req: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString("latin1");
}

export async function startStoryProxy(target: string): Promise<StoryProxy> {
  const upstream = new URL(target);
  let run = RUN_ID;
  let pacing: Pacing = {};
  let gone = false;
  let dropped = false;
  let releases: (() => void)[] = [];
  const state = {
    created: [] as unknown[],
    uploads: [] as string[],
    resumes: [] as (string | null)[],
  };

  const stream = async (req: IncomingMessage, res: ServerResponse, events: readonly RunEvent[]) => {
    const after = Number(req.headers["last-event-id"] ?? "0") || 0;
    state.resumes.push((req.headers["last-event-id"] as string | undefined) ?? null);
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store" });
    res.write("retry: 300\n\n");
    let closed = false;
    req.on("close", () => {
      closed = true;
    });
    let sent = 0;
    for (const event of events) {
      if (closed) return;
      if (event.seq <= after) continue;
      if (event.type === "stage_result") {
        if (pacing.holdBefore && event.stage === pacing.holdBefore) {
          await new Promise<void>((resolve) => releases.push(resolve));
          if (closed) return;
        }
        if (pacing.pace) await sleep(pacing.pace);
      }
      res.write(`event: ${event.type}\nid: ${event.seq}\ndata: ${JSON.stringify(event)}\n\n`);
      sent += 1;
      if (pacing.dropAfter != null && !dropped && sent >= pacing.dropAfter) {
        // The connection ends before run_done, as a dropped one would; what was sent arrives.
        dropped = true;
        res.end();
        return;
      }
    }
    res.end();
  };

  const runs = async (req: IncomingMessage, res: ServerResponse, url: URL) => {
    const parts = url.pathname
      .replace(/^\/api\/v1\/runs\/?/, "")
      .split("/")
      .filter(Boolean);
    if (req.method === "POST" && parts.length === 0) {
      state.created.push(JSON.parse((await readBody(req)) || "null"));
      const started = RUNS[run]![0] as Extract<RunEvent, { type: "run_started" }>;
      return send(res, 201, {
        run_id: run,
        events_url: `/api/v1/runs/${run}/events`,
        origin: started.origin,
      });
    }
    if (parts[0] === "cases") return send(res, 200, fixture.cases);
    if (parts[0] === "layouts") return send(res, 200, fixture.layouts);
    const runId = parts[0]!;
    if (gone) return send(res, 410, fixture.gone);
    const events = RUNS[runId];
    if (!events)
      return send(res, 404, {
        title: "Not found",
        status: 404,
        code: "not_found",
        detail: `No run ${runId}.`,
      });
    if (parts[1] === "events") return stream(req, res, events);
    if (parts.length === 1) return send(res, 200, snapshotOf(events, runId));
    return send(res, 404, {
      title: "Not found",
      status: 404,
      code: "not_found",
      detail: url.pathname,
    });
  };

  const pass = (req: IncomingMessage, res: ServerResponse) => {
    const forward = http.request(
      {
        host: upstream.hostname,
        port: upstream.port,
        method: req.method,
        path: req.url,
        headers: { ...req.headers, host: upstream.host },
      },
      (answer) => {
        const headers = { ...answer.headers };
        if (typeof headers.location === "string")
          headers.location = headers.location.replace(upstream.origin, "");
        res.writeHead(answer.statusCode ?? 502, headers);
        answer.pipe(res);
      },
    );
    forward.on("error", () => {
      if (!res.headersSent) res.writeHead(502);
      res.end();
    });
    req.pipe(forward);
  };

  const server = http.createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    if (url.pathname.startsWith("/api/v1/runs")) {
      void runs(req, res, url);
      return;
    }
    if (url.pathname === "/api/v1/uploads" && req.method === "POST") {
      void readBody(req).then((body) => {
        state.uploads.push(body);
        send(
          res,
          200,
          /filename="[^"]*wafer[^"]*"/i.test(body) ? fixture.uploadBad : fixture.uploadOk,
        );
      });
      return;
    }
    pass(req, res);
  });
  // WebSockets (development hot reload) are piped through as they are.
  const sockets = new Set<{ destroy(): void }>();
  server.on("upgrade", (req, socket, head) => {
    sockets.add(socket);
    const up = net.connect(Number(upstream.port), upstream.hostname, () => {
      const lines = Object.entries({ ...req.headers, host: upstream.host }).map(
        ([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`,
      );
      up.write(`${req.method} ${req.url} HTTP/1.1\r\n${lines.join("\r\n")}\r\n\r\n`);
      up.write(head);
      socket.pipe(up).pipe(socket);
    });
    sockets.add(up);
    up.on("error", () => socket.destroy());
    socket.on("error", () => up.destroy());
  });
  await new Promise<void>((resolve) => server.listen(0, resolve));
  const { port } = server.address() as AddressInfo;

  return {
    origin: `http://localhost:${port}`,
    ...state,
    configure(options) {
      if (options.run) run = options.run;
      if (options.pacing) {
        pacing = options.pacing;
        dropped = false;
      }
      if (options.gone != null) gone = options.gone;
    },
    release() {
      const pending = releases;
      releases = [];
      for (const r of pending) r();
    },
    close: () =>
      new Promise<void>((resolve) => {
        for (const socket of sockets) socket.destroy();
        for (const r of releases) r();
        server.closeAllConnections();
        server.close(() => resolve());
      }),
  };
}

/** The gateway the Playwright config starts (or reuses). */
export const GATEWAY = `http://localhost:${process.env.E2E_PORT ?? 4300}`;
