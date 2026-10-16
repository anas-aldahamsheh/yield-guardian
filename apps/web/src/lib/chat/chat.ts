import type {
  CallUsage,
  ChatContext,
  ChatEvent,
  ChatMessage,
  ChatSuggestionEvent,
  Evidence,
  Problem,
} from "@yield-guardian/contracts";

import { ApiError, isProblem } from "@/lib/api/errors";
import { UNVERIFIED_MARK } from "@/lib/investigation/events";
import { type Pick, parsePick, STATIONS, type StationName, type StationNumber } from "@/lib/routes";

/** An investigation the chat offers to start, checked by code: the trigger and its title. */
export interface ChatSuggestion {
  trigger: ChatSuggestionEvent["trigger"];
  title: string;
}

/** One answer as it streams in, built only from the API's chat events. */
export interface ChatAnswer {
  route: { route: "deterministic" | "model"; intent: string; model_id: string | null } | null;
  tools: { tool: string; arguments: Record<string, unknown> }[];
  citations: Evidence[];
  /** Investigations the answer offers to start; only the engineer's click starts one. */
  offers: ChatSuggestion[];
  text: string;
  refusal: string | null;
  done: { usage: CallUsage | null; numbers_checked: number; numbers_unverified: string[] } | null;
  error: Problem | null;
}

export const emptyAnswer = (): ChatAnswer => ({
  route: null,
  tools: [],
  citations: [],
  offers: [],
  text: "",
  refusal: null,
  done: null,
  error: null,
});

/** Applies one chat event; unknown event types are ignored so a newer API does not break the page. */
export function applyChatEvent(answer: ChatAnswer, event: ChatEvent): ChatAnswer {
  switch (event.type) {
    case "route":
      return {
        ...answer,
        route: { route: event.route, intent: event.intent, model_id: event.model_id ?? null },
      };
    case "tool":
      return {
        ...answer,
        tools: [...answer.tools, { tool: event.tool, arguments: event.arguments }],
      };
    case "citation":
      return answer.citations.some((c) => c.evidence_id === event.evidence.evidence_id)
        ? answer
        : { ...answer, citations: [...answer.citations, event.evidence] };
    case "suggestion":
      return answer.offers.some(
        (o) => o.trigger.kind === event.trigger.kind && o.trigger.ref === event.trigger.ref,
      )
        ? answer
        : { ...answer, offers: [...answer.offers, { trigger: event.trigger, title: event.title }] };
    case "token":
      return { ...answer, text: answer.text + event.text };
    case "refusal":
      return { ...answer, refusal: event.reason };
    case "done":
      return {
        ...answer,
        done: {
          usage: event.usage ?? null,
          numbers_checked: event.numbers_checked,
          numbers_unverified: event.numbers_unverified,
        },
      };
    case "error":
      return { ...answer, error: event.problem };
    default:
      return answer;
  }
}

/** Parses a server-sent event stream into `{ event, data }` frames. */
export async function* parseSse(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<{ event: string; data: string }> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.search(/\r?\n\r?\n/)) >= 0) {
      const raw = buffer.slice(0, cut);
      buffer = buffer.slice(cut).replace(/^\r?\n\r?\n/, "");
      let event = "message";
      const data: string[] = [];
      for (const line of raw.split(/\r?\n/)) {
        if (line.startsWith(":")) continue;
        const i = line.indexOf(":");
        const field = i < 0 ? line : line.slice(0, i);
        const v = i < 0 ? "" : line.slice(i + 1).replace(/^ /, "");
        if (field === "event") event = v;
        else if (field === "data") data.push(v);
      }
      if (data.length) yield { event, data: data.join("\n") };
    }
    if (done) return;
  }
}

/** Asks the API and calls `onEvent` for each chat event. Throws an ApiError when the API refuses. */
export async function streamChat({
  messages,
  context,
  headers,
  signal,
  onEvent,
}: {
  messages: ChatMessage[];
  context: ChatContext | null;
  headers: Record<string, string>;
  signal: AbortSignal;
  onEvent: (event: ChatEvent) => void;
}): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...headers },
      body: JSON.stringify({ messages: messages.slice(-20), context }),
      credentials: "same-origin",
      signal,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new ApiError(0, null, "The API could not be reached.");
  }
  if (!response.ok || !response.body) {
    const body: unknown = await response.json().catch(() => null);
    throw new ApiError(response.status, isProblem(body) ? body : null);
  }
  for await (const frame of parseSse(response.body)) {
    try {
      onEvent(JSON.parse(frame.data) as ChatEvent);
    } catch {
      // A frame that is not JSON is not a chat event.
    }
  }
}

export type TextPart = { text: string; cite?: string; unverified?: true; flagged?: true };

/**
 * Splits answer text at evidence references ("[E1]"), the verifier's "[unverified]" marker and
 * numbers the check could not find in the evidence.
 */
export function segmentAnswer(text: string, unverifiedNumbers: string[]): TextPart[] {
  const numbers = [...unverifiedNumbers].filter(Boolean).sort((a, b) => b.length - a.length);
  const parts: TextPart[] = [];
  let plain = "";
  let i = 0;
  const flush = () => {
    if (plain) parts.push({ text: plain });
    plain = "";
  };
  while (i < text.length) {
    const cite = /^\[(E\d+)\]/.exec(text.slice(i, i + 12));
    if (cite) {
      flush();
      parts.push({ text: cite[0], cite: cite[1] });
      i += cite[0].length;
      continue;
    }
    if (text.startsWith(UNVERIFIED_MARK, i)) {
      flush();
      parts.push({ text: UNVERIFIED_MARK, unverified: true });
      i += UNVERIFIED_MARK.length;
      continue;
    }
    const n = numbers.find(
      (x) =>
        text.startsWith(x, i) &&
        !/\d/.test(text[i - 1] ?? "") &&
        !/\d/.test(text[i + x.length] ?? ""),
    );
    if (n) {
      flush();
      parts.push({ text: n, flagged: true });
      i += n.length;
      continue;
    }
    plain += text[i];
    i += 1;
  }
  flush();
  return parts;
}

/**
 * The Line page's address, `/?run=<id>&station=<n>&unit=<index>|wafer=<index>|lot=<name>` and
 * `alarm=<RA-n>`, plus the real item a v1 link picked (`pick=unit:<id>`, see lib/routes.ts) and
 * a SECOM sensor. Each value is kept only when it is well formed (as the run contract defines
 * it); the item is the first of unit, wafer, lot.
 */
export interface LineLocation {
  runId: string | null;
  station: StationNumber | null;
  item:
    | { kind: "unit"; index: number }
    | { kind: "wafer"; index: number }
    | { kind: "lot"; lot: string }
    | null;
  alarm: string | null;
  pick: Pick | null;
  sensor: string | null;
}

const RUN_ID = /^run_[0-9a-z]{8,40}$/;
// The run contract's RunAlarmId.
const RUN_ALARM = /^RA-\d{1,6}$/;
const INDEX = /^\d{1,6}$/;
// The run contract's UserLabel: the lot name as the run's input wrote it.
const LOT_LABEL = /^[A-Za-z0-9_.:\- ]{1,64}$/;

export function parseLineLocation(params: URLSearchParams): LineLocation {
  const run = params.get("run") ?? "";
  const station = Number(params.get("station"));
  const unit = params.get("unit") ?? "";
  const wafer = params.get("wafer") ?? "";
  const lot = params.get("lot") ?? "";
  const sensor = params.get("sensor") ?? "";
  const alarm = params.get("alarm") ?? "";
  return {
    runId: RUN_ID.test(run) ? run : null,
    station:
      Number.isInteger(station) && station >= 1 && station <= STATIONS.length
        ? (station as StationNumber)
        : null,
    item: INDEX.test(unit)
      ? { kind: "unit", index: Number(unit) }
      : INDEX.test(wafer)
        ? { kind: "wafer", index: Number(wafer) }
        : LOT_LABEL.test(lot)
          ? { kind: "lot", lot }
          : null,
    alarm: RUN_ALARM.test(alarm) ? alarm : null,
    pick: parsePick(params.get("pick")),
    sensor: /^S\d{3}$/.test(sensor) ? sensor : null,
  };
}

/**
 * The run part of the Line's address as chat context, or null without a run: the chat may then
 * read that run with the run tools. The API refuses run fields without `run_id`.
 */
export function runChatContext(line: LineLocation): ChatContext | null {
  if (!line.runId) return null;
  return {
    run_id: line.runId,
    station: line.station ? STATIONS[line.station - 1]! : null,
    run_unit: line.item?.kind === "unit" ? line.item.index : null,
    run_wafer: line.item?.kind === "wafer" ? line.item.index : null,
    run_lot: line.item?.kind === "lot" ? line.item.lot : null,
    run_alarm: line.alarm,
  };
}

/** Chat context of the Line page: the run being looked at, else the real item a link picked. */
export function lineChatContext(line: LineLocation): ChatContext | null {
  const run = runChatContext(line);
  if (run) return run;
  if (line.pick?.kind === "unit") return { unit_id: line.pick.id };
  if (line.pick?.kind === "wafer") return { wafer_id: line.pick.id };
  if (line.pick?.kind === "lot") return { lot: line.pick.id };
  if (line.sensor) return { sensor: line.sensor };
  return null;
}

/** What the engineer is looking at, read from the page address. */
export function contextFromLocation(pathname: string, params: URLSearchParams): ChatContext | null {
  if (pathname === "/") return lineChatContext(parseLineLocation(params));
  const inv = /^\/investigations\/(inv_[0-9a-z]+)/.exec(pathname);
  if (inv) return { investigation_id: inv[1]! };
  return null;
}

const STATION_LABEL: Record<StationName, string> = {
  manufacturing: "Manufacturing",
  monitoring: "Monitoring",
  wafer_test: "Wafer test",
  investigation: "Investigation",
  decision: "Decision",
};

export function describeContext(c: ChatContext): string {
  if (c.run_id) {
    const item =
      c.run_unit != null
        ? `, unit ${c.run_unit + 1}`
        : c.run_wafer != null
          ? `, wafer ${c.run_wafer + 1}`
          : c.run_lot
            ? `, lot ${c.run_lot}`
            : "";
    const alarm = c.run_alarm ? `, alarm ${c.run_alarm}` : "";
    return `This run${c.station ? `, ${STATION_LABEL[c.station]}` : ""}${item}${alarm}`;
  }
  if (c.unit_id != null) return `Unit ${c.unit_id}`;
  if (c.sensor) return `Sensor ${c.sensor}`;
  if (c.wafer_id) return `Wafer ${c.wafer_id}`;
  if (c.lot) return `Lot ${c.lot}`;
  if (c.investigation_id) return `Investigation ${c.investigation_id}`;
  return "This page";
}

/**
 * Extracts a clean, structured text snapshot of what is currently visible on the screen.
 * It reads the main page container, cleanly formatting headings, tables, metrics, and text,
 * while omitting hidden elements, scripts, styles, SVGs, and the chat dialog itself.
 */
export function extractVisiblePageContent(root?: Element | null): string {
  if (typeof document === "undefined") return "";
  const container =
    root ??
    document.querySelector("main#main") ??
    document.querySelector("main") ??
    document.body;
  if (!container) return "";

  const lines: string[] = [];

  function processElement(el: Element) {
    const tag = el.tagName.toLowerCase();
    if (
      tag === "script" ||
      tag === "style" ||
      tag === "noscript" ||
      tag === "svg" ||
      tag === "path" ||
      el.getAttribute("aria-hidden") === "true" ||
      el.getAttribute("role") === "dialog" ||
      el.classList?.contains("print:hidden")
    ) {
      return;
    }

    if (/^h[1-6]$/.test(tag)) {
      const heading = (el as HTMLElement).innerText?.trim();
      if (heading) lines.push(`\n### ${heading}\n`);
      return;
    }

    if (tag === "table") {
      const rows = Array.from(el.querySelectorAll("tr"));
      for (const row of rows) {
        const cells = Array.from(row.querySelectorAll("th, td"))
          .map((c) => (c as HTMLElement).innerText?.trim())
          .filter(Boolean);
        if (cells.length > 0) {
          lines.push(cells.join(" | "));
        }
      }
      lines.push("");
      return;
    }

    for (const child of Array.from(el.childNodes)) {
      if (child.nodeType === Node.TEXT_NODE) {
        const text = (child.textContent ?? "").replace(/\s+/g, " ").trim();
        if (text) lines.push(text);
      } else if (child.nodeType === Node.ELEMENT_NODE) {
        processElement(child as Element);
      }
    }
  }

  processElement(container);

  const result = lines
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  return result.length > 6000 ? result.slice(0, 6000) + "\n[... content truncated]" : result;
}
