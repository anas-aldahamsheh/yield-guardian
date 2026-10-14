import type { CallUsage, ChatContext, ChatEvent, ChatMessage, Evidence, Problem } from "@yield-guardian/contracts";

import { ApiError, isProblem } from "@/lib/api/errors";
import { UNVERIFIED_MARK } from "@/lib/investigation/events";

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

/** What the engineer is looking at, read from the page address. */
export function contextFromLocation(pathname: string, params: URLSearchParams): ChatContext | null {
  const unit = /^\/units\/(\d+)/.exec(pathname);
  if (unit) return { unit_id: Number(unit[1]) };
  const lot = /^\/lots\/([A-Za-z0-9_.]+)/.exec(pathname);
  if (lot) return { lot: decodeURIComponent(lot[1]!) };
  const inv = /^\/investigations\/(inv_[0-9a-z]+)/.exec(pathname);
  if (inv) return { investigation_id: inv[1]! };
  if (pathname.startsWith("/sensors") && /^S\d{3}$/.test(params.get("sensor") ?? "")) return { sensor: params.get("sensor")! };
  if (pathname.startsWith("/wafers") && params.get("wafer")) return { wafer_id: params.get("wafer")! };
  return null;
}

export function describeContext(c: ChatContext): string {
  if (c.unit_id != null) return `Unit ${c.unit_id}`;
  if (c.sensor) return `Sensor ${c.sensor}`;
  if (c.wafer_id) return `Wafer ${c.wafer_id}`;
  if (c.lot) return `Lot ${c.lot}`;
  if (c.investigation_id) return `Investigation ${c.investigation_id}`;
  return "This page";
}
