/**
 * Local gateway: one origin for the web app and the API, like the reverse proxy of every
 * deployment. Browsers call /api/v1/... on the page's own origin; this routes it to the API (or
 * to the development fixtures with --mock) and everything else to Next.js.
 *
 *   tsx scripts/gateway.ts --mode dev            next dev behind the gateway, real API
 *   tsx scripts/gateway.ts --mode dev --mock     next dev, fixture API (development data)
 *   tsx scripts/gateway.ts --mode start --mock   next start (a production build), fixture API
 *
 * Options: --port (default 3000), --next-port (default 3001), --api (default API_INTERNAL_URL or
 * http://localhost:8000). Development only: this file is never part of the build.
 */
import { spawn } from "node:child_process";
import http, { type IncomingMessage, type ServerResponse } from "node:http";
import https from "node:https";
import net from "node:net";
import { Readable } from "node:stream";
import { parseArgs } from "node:util";

import { getResponse } from "msw";

import { createHandlers } from "../src/mocks/handlers";

// Load local env files if present so API_INTERNAL_URL is respected
for (const envPath of [".env.local", ".env", "../../.env"]) {
  try {
    process.loadEnvFile(envPath);
  } catch {
    // ignore missing files
  }
}

const { values } = parseArgs({
  options: {
    mode: { type: "string", default: "dev" },
    mock: { type: "boolean", default: false },
    port: { type: "string", default: process.env.PORT ?? "3000" },
    "next-port": { type: "string", default: "3001" },
    api: { type: "string", default: process.env.API_INTERNAL_URL ?? "http://localhost:8000" },
    "stream-delay": { type: "string", default: "420" },
  },
});

const port = Number(values.port);
const nextPort = Number(values["next-port"]);
const api = new URL(values.api!);
const isApiPath = (url = "") => url.startsWith("/api/");

// Next.js, started as a child process on its own port.
const next = spawn(
  "pnpm",
  ["exec", "next", values.mode === "start" ? "start" : "dev", "--port", String(nextPort)],
  {
    stdio: "inherit",
    shell: process.platform === "win32",
    env: {
      ...process.env,
      API_INTERNAL_URL: values.mock ? `http://127.0.0.1:${port}` : api.origin,
    },
  },
);
const stop = () => {
  next.kill("SIGTERM");
  process.exit(0);
};
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
next.on("exit", (code) => process.exit(code ?? 0));

const handlers = values.mock
  ? createHandlers({ streamDelayMs: Number(values["stream-delay"]) })
  : [];

async function answerFromFixtures(req: IncomingMessage, res: ServerResponse) {
  const body =
    req.method === "GET" || req.method === "HEAD"
      ? undefined
      : (Readable.toWeb(req) as unknown as ReadableStream<Uint8Array>);
  const request = new Request(`http://${req.headers.host}${req.url}`, {
    method: req.method,
    headers: req.headers as Record<string, string>,
    body,
    duplex: "half",
  } as RequestInit);
  const response = await getResponse(handlers, request);
  if (!response) {
    res.writeHead(404, { "Content-Type": "application/problem+json" });
    res.end(
      JSON.stringify({
        title: "Not found",
        status: 404,
        code: "not_found",
        detail: `${req.method} ${req.url} has no development fixture.`,
      }),
    );
    return;
  }
  const headers: Record<string, string | string[]> = {};
  response.headers.forEach((value, key) => {
    headers[key] = key === "set-cookie" ? response.headers.getSetCookie() : value;
  });
  res.writeHead(response.status, headers);
  if (!response.body) return void res.end();
  for await (const chunk of response.body as unknown as AsyncIterable<Uint8Array>) res.write(chunk);
  res.end();
}

function forward(req: IncomingMessage, res: ServerResponse, target: URL) {
  const isHttps = target.protocol === "https:";
  const client = isHttps ? https : http;
  const defaultPort = isHttps ? 443 : 80;
  const targetPort = target.port ? Number(target.port) : defaultPort;
  const headers = {
    ...req.headers,
    host: target.host,
    "x-forwarded-host": req.headers.host ?? "",
    "x-forwarded-proto": req.headers["x-forwarded-proto"] ?? (isHttps ? "https" : "http"),
  };

  const upstream = client.request(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: targetPort,
      method: req.method,
      path: req.url,
      headers,
    },
    (upstreamRes) => {
      const resHeaders = { ...upstreamRes.headers };
      if (resHeaders["set-cookie"]) {
        const rawCookies = resHeaders["set-cookie"];
        resHeaders["set-cookie"] = (Array.isArray(rawCookies) ? rawCookies : [rawCookies]).map(
          (c) => c.replace(/;\s*Secure/gi, ""),
        );
      }
      res.writeHead(upstreamRes.statusCode ?? 502, resHeaders);
      upstreamRes.pipe(res);
    },
  );
  upstream.on("error", (err) => {
    if (!res.headersSent) res.writeHead(502, { "Content-Type": "text/plain" });
    res.end(
      isApiPath(req.url)
        ? `The API at ${target.origin} did not answer: ${err.message}`
        : "Next.js is starting…",
    );
  });
  req.pipe(upstream);
}

const nextOrigin = new URL(`http://127.0.0.1:${nextPort}`);

/**
 * With --mock, browser tests put a stand-in for the runs API in front of the gateway
 * (e2e/story/stub.ts). It registers itself here (PUT /__mock/runs-upstream with its origin,
 * DELETE when it closes), so the pages Next.js renders read the same runs as the browser does.
 * Only a stand-in on this machine is accepted.
 */
let runsUpstream: URL | null = null;
const isRunsPath = (url = "") => url === "/api/v1/runs" || url.startsWith("/api/v1/runs/");

async function registerRuns(req: IncomingMessage, res: ServerResponse) {
  if (req.method === "DELETE") {
    runsUpstream = null;
    return void res.writeHead(204).end();
  }
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  let origin: URL | null = null;
  try {
    origin = new URL(Buffer.concat(chunks).toString("utf8").trim());
  } catch {
    origin = null;
  }
  if (
    req.method !== "PUT" ||
    !origin ||
    origin.protocol !== "http:" ||
    !["localhost", "127.0.0.1"].includes(origin.hostname)
  ) {
    return void res
      .writeHead(400, { "Content-Type": "text/plain" })
      .end("PUT http://127.0.0.1:<port>");
  }
  runsUpstream = new URL(origin.origin);
  res.writeHead(204).end();
}

const server = http.createServer((req, res) => {
  if (values.mock && req.url === "/__mock/runs-upstream") {
    registerRuns(req, res).catch(() => res.writeHead(500).end());
    return;
  }
  if (isApiPath(req.url)) {
    if (values.mock && runsUpstream && isRunsPath(req.url?.split("?")[0])) {
      forward(req, res, runsUpstream);
      return;
    }
    if (values.mock) {
      answerFromFixtures(req, res).catch((error: unknown) => {
        console.error(error);
        if (!res.headersSent) res.writeHead(500);
        res.end();
      });
    } else forward(req, res, api);
    return;
  }
  forward(req, res, nextOrigin);
});

// WebSockets: Next's hot reload in dev mode (the API has none).
server.on("upgrade", (req, socket, head) => {
  const target = isApiPath(req.url) ? api : nextOrigin;
  const upstream = net.connect(Number(target.port || 80), target.hostname, () => {
    const lines = [`${req.method} ${req.url} HTTP/${req.httpVersion}`];
    for (let i = 0; i < req.rawHeaders.length; i += 2)
      lines.push(`${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}`);
    upstream.write(`${lines.join("\r\n")}\r\n\r\n`);
    if (head.length) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  upstream.on("error", () => socket.destroy());
  socket.on("error", () => upstream.destroy());
});

server.listen(port, () => {
  const source = values.mock ? "development fixtures (not real results)" : api.origin;
  console.log(
    `Gateway on http://localhost:${port}: API from ${source}, pages from next ${values.mode} on :${nextPort}`,
  );
});
