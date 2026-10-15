import type { CallUsage, ChatContext, ChatEvent, ChatMessage, Evidence, Problem } from "@yield-guardian/contracts";

import { ApiError, isProblem } from "@/lib/api/errors";
import { UNVERIFIED_MARK } from "@/lib/investigation/events";
import { type Pick, parsePick, STATIONS, type StationName, type StationNumber } from "@/lib/routes";

/** One answer as it streams in, built only from the API's chat events. */
export interface ChatAnswer {
  route: { route: "deterministic" | "model"; intent: string; model_id: string | null } | null;
  tools: { tool: string; arguments: Record<string, unknown> }[];
  citations: Evidence[];
  text: string;
  refusal: string | null;
  done: { usage: CallUsage | null; numbers_checked: number; numbers_unverified: string[] } | null;
  error: Problem | null;
}

export const emptyAnswer = (): ChatAnswer => ({ route: null, tools: [], citations: [], text: "", refusal: null, done: null, error: null });

/** Applies one chat event; unknown event types are ignored so a newer API does not break the page. */
export function applyChatEvent(answer: ChatAnswer, event: ChatEvent): ChatAnswer {
  switch (event.type) {
    case "route":
      return { ...answer, route: { route: event.route, intent: event.intent, model_id: event.model_id ?? null } };
    case "tool":
      return { ...answer, tools: [...answer.tools, { tool: event.tool, arguments: event.arguments }] };
    case "citation":
      return answer.citations.some((c) => c.evidence_id === event.evidence.evidence_id)
        ? answer
        : { ...answer, citations: [...answer.citations, event.evidence] };
    case "token":
      return { ...answer, text: answer.text + event.text };
    case "refusal":
      return { ...answer, refusal: event.reason };
    case "done":
      return { ...answer, done: { usage: event.usage ?? null, numbers_checked: event.numbers_checked, numbers_unverified: event.numbers_unverified } };
    case "error":
      return { ...answer, error: event.problem };
    default:
      return answer;
  }
}

/** Parses a server-sent event stream into `{ event, data }` frames. */
export async function* parseSse(stream: ReadableStream<Uint8Array>): AsyncGenerator<{ event: string; data: string }> {
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
    const n = numbers.find((x) => text.startsWith(x, i) && !/\d/.test(text[i - 1] ?? "") && !/\d/.test(text[i + x.length] ?? ""));
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
 * The Line page's address, `/?run=<id>&station=<n>&unit=<index>|wafer=<index>|lot=<name>`, plus
 * the real item a v1 link picked (`pick=unit:<id>`, see lib/routes.ts) and a SECOM sensor. Each
 * value is kept only when it is well formed; the item is the first of unit, wafer, lot.
 */
export interface LineLocation {
  runId: string | null;
  station: StationNumber | null;
  item: { kind: "unit"; index: number } | { kind: "wafer"; index: number } | { kind: "lot"; lot: string } | null;
  pick: Pick | null;
  sensor: string | null;
}

const RUN_ID = /^run_[0-9a-z]{8,40}$/;
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
  return {
    runId: RUN_ID.test(run) ? run : null,
    station: Number.isInteger(station) && station >= 1 && station <= STATIONS.length ? (station as StationNumber) : null,
    item: INDEX.test(unit)
      ? { kind: "unit", index: Number(unit) }
      : INDEX.test(wafer)
        ? { kind: "wafer", index: Number(wafer) }
        : LOT_LABEL.test(lot)
          ? { kind: "lot", lot }
          : null,
    pick: parsePick(params.get("pick")),
    sensor: /^S\d{3}$/.test(sensor) ? sensor : null,
  };
}

/**
 * The run fields the AI worker adds to ChatContext (V6). They are not in the contract on main
 * yet, and the API rejects unknown context fields, so they are only sent once
 * SEND_RUN_CONTEXT is switched on.
 */
export interface RunChatContext {
  run_id: string;
  station: StationName | null;
  run_unit: number | null;
  run_wafer: number | null;
  run_lot: string | null;
}

/** Switch on at merge, once ChatContext carries the run fields (then drop the casts below). */
export const SEND_RUN_CONTEXT = false;

/** The run part of the Line's address as chat context, or null without a run. */
export function runChatContext(line: LineLocation): RunChatContext | null {
  if (!line.runId) return null;
  return {
    run_id: line.runId,
    station: line.station ? STATIONS[line.station - 1]! : null,
    run_unit: line.item?.kind === "unit" ? line.item.index : null,
    run_wafer: line.item?.kind === "wafer" ? line.item.index : null,
    run_lot: line.item?.kind === "lot" ? line.item.lot : null,
  };
}

/** Chat context of the Line page: the run (once the contract has it), else the real item. */
export function lineChatContext(line: LineLocation, sendRun = SEND_RUN_CONTEXT): ChatContext | null {
  const run = sendRun ? runChatContext(line) : null;
  if (run) return run as unknown as ChatContext;
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
  const run = c as ChatContext & Partial<RunChatContext>;
  if (run.run_id) {
    const item =
      run.run_unit != null
        ? `, unit ${run.run_unit + 1}`
        : run.run_wafer != null
          ? `, wafer ${run.run_wafer + 1}`
          : run.run_lot
            ? `, lot ${run.run_lot}`
            : "";
    return `This run${run.station ? `, ${STATION_LABEL[run.station]}` : ""}${item}`;
  }
  if (c.unit_id != null) return `Unit ${c.unit_id}`;
  if (c.sensor) return `Sensor ${c.sensor}`;
  if (c.wafer_id) return `Wafer ${c.wafer_id}`;
  if (c.lot) return `Lot ${c.lot}`;
  if (c.investigation_id) return `Investigation ${c.investigation_id}`;
  return "This page";
}
