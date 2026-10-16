import http, { type IncomingMessage, type ServerResponse } from "node:http";
import net, { type AddressInfo } from "node:net";

import type {
  Investigation,
  InvestigationCreate,
  RunAlarm,
  RunEvent,
  StageState,
} from "@yield-guardian/contracts";

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
 *
 * As the API does, GET /runs/{id} answers with the run as far as it has gone: up to the last
 * event its stream has sent since the run was created here (the whole run when none was), with
 * each alarm's investigation, from the investigations started through the proxy (their status as
 * the gateway's investigator double has it). The proxy registers itself with the gateway, so
 * the pages Next.js renders read the same runs as the browser (scripts/gateway.ts).
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
  /** Each GET /runs/{id}: who asked (the browser, or Next.js rendering the page) and its answer. */
  reads: { from: "browser" | "server"; status: number; lastSeq: number | null }[];
  /**
   * `run` also starts afresh: no run has progressed, no alarm is investigated, the API is up.
   * `browserReadDelay`: the browser's GET /runs/{id} answers that many ms late, as a large run's
   * full state does over a slow network (the page Next.js renders reads it at once).
   */
  configure(options: {
    run?: string;
    pacing?: Pacing;
    gone?: boolean;
    browserReadDelay?: number;
  }): void;
  /** Lets a held stream go on; streams opened after it do not hold. */
  release(): void;
  /**
   * The API asleep for `ms`: every API request through the proxy, the browser's and the ones
   * Next.js makes for a run while rendering, answers 503 with Retry-After: 1 until then.
   */
  sleep(ms: number): void;
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
  let browserReadDelay = 0;
  let asleepUntil = 0;
  let dropped = false;
  let releases: (() => void)[] = [];
  /** How far each run created here has gone: the seq of the last event its stream sent. */
  const progress = new Map<string, number>();
  /** Investigations started through the proxy, by trigger ref (`run:alarm`). */
  const investigations = new Map<string, { id: string; status: Investigation["status"] }>();
  const state = {
    created: [] as unknown[],
    uploads: [] as string[],
    resumes: [] as (string | null)[],
    reads: [] as StoryProxy["reads"],
  };

  const stream = async (
    req: IncomingMessage,
    res: ServerResponse,
    runId: string,
    events: readonly RunEvent[],
  ) => {
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
        if (closed) return;
      }
      res.write(`event: ${event.type}\nid: ${event.seq}\ndata: ${JSON.stringify(event)}\n\n`);
      if (progress.has(runId)) progress.set(runId, Math.max(progress.get(runId)!, event.seq));
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
      progress.set(run, started.seq);
      return send(res, 201, {
        run_id: run,
        events_url: `/api/v1/runs/${run}/events`,
        origin: started.origin,
      });
    }
    if (parts[0] === "cases") return send(res, 200, fixture.cases);
    if (parts[0] === "layouts") return send(res, 200, fixture.layouts);
    const runId = parts[0]!;
    const from = req.headers["x-forwarded-host"] ? "server" : "browser";
    const read = (status: number, lastSeq: number | null = null) => {
      if (parts.length === 1) state.reads.push({ from, status, lastSeq });
    };
    if (gone) {
      read(410);
      return send(res, 410, fixture.gone);
    }
    const events = RUNS[runId];
    if (!events) {
      read(404);
      return send(res, 404, {
        title: "Not found",
        status: 404,
        code: "not_found",
        detail: `No run ${runId}.`,
      });
    }
    if (parts[1] === "events") return stream(req, res, runId, events);
    if (parts.length === 1) {
      if (from === "browser" && browserReadDelay) await sleep(browserReadDelay);
      const upTo = progress.get(runId);
      const snapshot = snapshotOf(
        upTo == null ? events : events.filter((e) => e.seq <= upTo),
        runId,
      );
      snapshot.alarms = await Promise.all(snapshot.alarms.map((a) => investigated(runId, a)));
      read(200, snapshot.last_seq);
      return send(res, 200, snapshot);
    }
    return send(res, 404, {
      title: "Not found",
      status: 404,
      code: "not_found",
      detail: url.pathname,
    });
  };

  /** An alarm with the investigation started from it, its status read now, as the API does. */
  const investigated = async (runId: string, alarm: RunAlarm): Promise<RunAlarm> => {
    const link = investigations.get(`${runId}:${alarm.alarm_id}`);
    if (!link) return alarm;
    const answer = await fetch(`${upstream.origin}/api/v1/investigations/${link.id}`).catch(
      () => null,
    );
    const now = answer?.ok ? ((await answer.json()) as Investigation).status : link.status;
    return { ...alarm, investigation_id: link.id, investigation_status: now };
  };

  /** POST /investigations goes to the gateway; one started from a run alarm is noted. */
  const investigate = async (req: IncomingMessage, res: ServerResponse) => {
    const body = await readBody(req);
    const answer = await fetch(`${upstream.origin}/api/v1/investigations`, {
      method: "POST",
      headers: Object.fromEntries(
        Object.entries(req.headers)
          .filter(([k, v]) => typeof v === "string" && !["host", "content-length"].includes(k))
          .map(([k, v]) => [k, v as string]),
      ),
      body,
    });
    const text = await answer.text();
    if (answer.ok) {
      const trigger = (JSON.parse(body || "null") as InvestigationCreate | null)?.trigger;
      const investigation = JSON.parse(text) as Investigation;
      if (trigger?.kind === "run_alarm")
        investigations.set(trigger.ref, {
          id: investigation.investigation_id,
          status: investigation.status,
        });
    }
    res.writeHead(answer.status, {
      "Content-Type": answer.headers.get("content-type") ?? "application/json",
    });
    res.end(text);
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
    if (url.pathname.startsWith("/api/") && Date.now() < asleepUntil) {
      // The proxy in front of a sleeping API: nothing reaches it until it is up.
      req.resume();
      res.writeHead(503, { "Content-Type": "text/plain", "Retry-After": "1" });
      res.end("Starting.");
      return;
    }
    if (url.pathname.startsWith("/api/v1/runs")) {
      void runs(req, res, url);
      return;
    }
    if (url.pathname === "/api/v1/investigations" && req.method === "POST") {
      investigate(req, res).catch(() => {
        if (!res.headersSent) res.writeHead(502);
        res.end();
      });
      return;
    }
    if (url.pathname === "/api/v1/uploads" && req.method === "POST") {
      void readBody(req).then((body) => {
        state.uploads.push(body);
        const summary = /filename="[^"]*wafer[^"]*"/i.test(body)
          ? fixture.uploadBad
          : fixture.uploadOk;
        // Kept for an hour from now, as the API keeps a checked file.
        send(res, 200, { ...summary, expires_at: new Date(Date.now() + 3_600_000).toISOString() });
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
  const registered = await fetch(`${upstream.origin}/__mock/runs-upstream`, {
    method: "PUT",
    body: `http://127.0.0.1:${port}`,
  }).catch(() => null);
  if (registered?.status !== 204) {
    server.close();
    throw new Error(
      `The gateway at ${upstream.origin} did not take the runs stand-in (${registered?.status ?? "no answer"}): restart it with --mock from this checkout.`,
    );
  }

  return {
    origin: `http://localhost:${port}`,
    ...state,
    configure(options) {
      if (options.run) {
        run = options.run;
        progress.clear();
        investigations.clear();
        asleepUntil = 0;
      }
      if (options.pacing) {
        pacing = options.pacing;
        dropped = false;
      }
      if (options.gone != null) gone = options.gone;
      if (options.browserReadDelay != null) browserReadDelay = options.browserReadDelay;
    },
    release() {
      pacing = { ...pacing, holdBefore: null };
      const pending = releases;
      releases = [];
      for (const r of pending) r();
    },
    sleep(ms) {
      asleepUntil = Date.now() + ms;
    },
    close: async () => {
      await fetch(`${upstream.origin}/__mock/runs-upstream`, { method: "DELETE" }).catch(
        () => null,
      );
      await new Promise<void>((resolve) => {
        for (const socket of sockets) socket.destroy();
        for (const r of releases) r();
        server.closeAllConnections();
        server.close(() => resolve());
      });
    },
  };
}

/** The gateway the Playwright config starts (or reuses). */
export const GATEWAY = `http://localhost:${process.env.E2E_PORT ?? 4300}`;
