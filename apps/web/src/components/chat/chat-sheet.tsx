"use client";

import type { ChatContext, ChatMessage, Evidence } from "@yield-guardian/contracts";
import { MessageSquareText } from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { type FormEvent, type KeyboardEvent, useRef, useState } from "react";

import { UnverifiedMark } from "@/components/investigation/report";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { describeError } from "@/lib/api/errors";
import { NOT_CONFIGURED, useFeatures } from "@/lib/api/features";
import { useSession, useStartGuestSession } from "@/lib/api/session";
import { applyChatEvent, type ChatAnswer, contextFromLocation, describeContext, emptyAnswer, segmentAnswer, streamChat } from "@/lib/chat/chat";
import { formatDuration, formatNumber, formatReported } from "@/lib/format";
import { TOOL_NAME } from "@/lib/labels";
import { cn } from "@/lib/utils";

type Turn = { id: number; question: string; context: ChatContext | null; answer: ChatAnswer; failed: string | null; streaming: boolean };

/** Questions that only name the object on screen; the numbers come from the answer. */
function suggestions(context: ChatContext | null): string[] {
  if (context?.unit_id != null) return [`Why was unit ${context.unit_id} flagged?`, `Which sensors moved most on unit ${context.unit_id}?`];
  if (context?.sensor) return [`Is ${context.sensor} healthy?`, `Which group is ${context.sensor} in?`];
  if (context?.wafer_id) return [`What pattern is wafer ${context.wafer_id}?`, `Which wafers look like ${context.wafer_id}?`];
  if (context?.lot) return [`Which patterns are over-represented in lot ${context.lot}?`];
  return ["Which units are high risk right now?", "Which sensors need maintenance?", "What does an Edge-Ring pattern usually point to?"];
}

export function ChatSheet({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const pageContext = contextFromLocation(pathname, new URLSearchParams(params.toString()));
  const [open, setOpen] = useState(defaultOpen);
  const [useContext, setUseContext] = useState(true);
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const abort = useRef<AbortController | null>(null);
  const nextId = useRef(0);
  const scroller = useRef<HTMLDivElement>(null);
  const { canAct, csrf } = useSession();
  const guest = useStartGuestSession();
  const { chat: chatServed } = useFeatures();
  const streaming = turns.some((t) => t.streaming);
  const context = useContext ? pageContext : null;

  const update = (id: number, fn: (t: Turn) => Turn) => setTurns((all) => all.map((t) => (t.id === id ? fn(t) : t)));
  const follow = () => requestAnimationFrame(() => scroller.current?.scrollTo({ top: scroller.current.scrollHeight }));

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || streaming) return;
    nextId.current += 1;
    const id = nextId.current;
    const history: ChatMessage[] = turns
      .filter((t) => !t.failed && t.answer.text)
      .flatMap((t) => [
        { role: "user" as const, content: t.question },
        { role: "assistant" as const, content: t.answer.text.slice(0, 4000) },
      ]);
    setTurns((all) => [...all, { id, question: q, context, answer: emptyAnswer(), failed: null, streaming: true }]);
    setDraft("");
    follow();
    const controller = new AbortController();
    abort.current = controller;
    try {
      await streamChat({
        messages: [...history, { role: "user", content: q.slice(0, 4000) }],
        context,
        headers: csrf,
        signal: controller.signal,
        onEvent: (event) => {
          update(id, (t) => ({ ...t, answer: applyChatEvent(t.answer, event) }));
          follow();
        },
      });
    } catch (error) {
      if (!controller.signal.aborted) {
        const copy = describeError(error);
        update(id, (t) => ({ ...t, failed: [copy.title, copy.detail].filter(Boolean).join(". ") }));
      }
    } finally {
      update(id, (t) => ({ ...t, streaming: false }));
      abort.current = null;
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void ask(draft);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void ask(draft);
    }
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <MessageSquareText className="size-4" aria-hidden="true" />
          Ask
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="flex w-[min(520px,100vw)] flex-col gap-0 border-hairline bg-die p-0 sm:max-w-[520px]">
        <SheetHeader className="border-b border-hairline px-5 py-4">
          <SheetTitle className="text-base">Ask about the plant data</SheetTitle>
          <SheetDescription className="text-[13px] leading-5">
            Answers cite the evidence they used, and every number is checked against it. Associations in historical data, not causes.
          </SheetDescription>
        </SheetHeader>

        <div ref={scroller} className="min-h-0 grow overflow-y-auto px-5 py-4" aria-live="polite" aria-busy={streaming}>
          {chatServed === false && turns.length === 0 ? (
            <div role="note" className="rounded-md border border-hairline-strong px-4 py-3">
              <p className="text-[14px] font-medium leading-5 text-ink">{NOT_CONFIGURED.chat.title}</p>
              <p className="mt-1 text-[13px] leading-5 text-ink-2">{NOT_CONFIGURED.chat.detail}</p>
            </div>
          ) : turns.length === 0 ? (
            <div>
              <p className="text-[13px] leading-5 text-ink-3">Try</p>
              <ul className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-2">
                {suggestions(context).map((s) => (
                  <li key={s}>
                    <button
                      type="button"
                      disabled={!canAct}
                      onClick={() => void ask(s)}
                      className="w-full cursor-pointer rounded-sm border border-hairline px-3 py-2 text-left text-[14px] leading-5 text-ink hover:border-hairline-strong hover:bg-die-2 disabled:cursor-default disabled:text-ink-3"
                    >
                      {s}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <ol className="grid grid-cols-[minmax(0,1fr)] gap-6">
              {turns.map((t) => (
                <li key={t.id} className="grid grid-cols-[minmax(0,1fr)] gap-2">
                  <p className="ml-auto max-w-[85%] rounded-sm bg-die-2 px-3 py-2 text-[14px] leading-5 text-ink">
                    {t.question}
                    {t.context ? <span className="mt-0.5 block text-[11px] text-ink-3">About {describeContext(t.context)}</span> : null}
                  </p>
                  <AnswerView turn={t} />
                </li>
              ))}
            </ol>
          )}
        </div>

        <div className="border-t border-hairline px-5 py-3">
          {chatServed === false ? (
            <p className="text-[13px] leading-5 text-ink-2">Asking is off until the API has a language model key.</p>
          ) : !canAct ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[13px] leading-5 text-ink-2">Asking needs an engineer session.</p>
              <Button size="sm" variant="outline" onClick={() => guest.mutate()} disabled={guest.isPending}>
                {guest.isPending ? "Signing in…" : "Try as engineer"}
              </Button>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="grid grid-cols-[minmax(0,1fr)] gap-2">
              {pageContext ? (
                <label className="flex items-center gap-2 text-[12px] leading-4 text-ink-2">
                  <input type="checkbox" checked={useContext} onChange={(e) => setUseContext(e.target.checked)} className="size-3.5 accent-[var(--ink)]" />
                  About {describeContext(pageContext)}
                </label>
              ) : null}
              <div className="flex items-end gap-2">
                <Textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={onKeyDown}
                  maxLength={4000}
                  rows={2}
                  placeholder="Ask about a unit, sensor, wafer or lot"
                  aria-label="Question"
                  className="min-h-[44px] resize-none"
                />
                {streaming ? (
                  <Button type="button" variant="outline" onClick={() => abort.current?.abort()}>
                    Stop
                  </Button>
                ) : (
                  <Button type="submit" disabled={!draft.trim()}>
                    Ask
                  </Button>
                )}
              </div>
            </form>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function AnswerView({ turn }: { turn: Turn }) {
  const a = turn.answer;
  const [open, setOpen] = useState<string | null>(null);
  const cited = a.citations.find((c) => c.evidence_id === open);
  const parts = segmentAnswer(a.text, a.done?.numbers_unverified ?? []);

  return (
    <div className="min-w-0 text-[14px] leading-6">
      {a.route ? (
        <p className="text-[12px] leading-4 text-ink-3">
          {a.route.route === "deterministic" ? "Answered by rules, without a model" : `Answered by ${a.route.model_id ?? "a model"}`}
          {a.tools.length ? `, using ${a.tools.map((x) => TOOL_NAME[x.tool] ?? x.tool).join(", ")}` : ""}.
        </p>
      ) : turn.streaming ? (
        <p className="text-[12px] text-ink-3">Reading the question…</p>
      ) : null}

      {a.refusal ? <p className="mt-1 text-ink-2">{a.refusal}</p> : null}

      {a.text ? (
        <p className="mt-1 whitespace-pre-wrap text-ink">
          {parts.map((p, i) =>
            p.cite ? (
              <button
                key={i}
                type="button"
                onClick={() => setOpen(open === p.cite ? null : p.cite!)}
                aria-expanded={open === p.cite}
                className={cn(
                  "tnum mx-0.5 cursor-pointer rounded-[2px] border px-1 align-baseline text-[11px] leading-4",
                  open === p.cite ? "border-ink bg-ink text-die" : "border-hairline-strong text-ink-2 hover:border-ink",
                )}
              >
                {p.cite}
              </button>
            ) : p.unverified ? (
              <UnverifiedMark key={i} />
            ) : p.flagged ? (
              <Tooltip key={i}>
                <TooltipTrigger asChild>
                  <span tabIndex={0} className="tnum bg-fail-wash underline decoration-fail decoration-wavy underline-offset-[5px]">
                    {p.text}
                  </span>
                </TooltipTrigger>
                <TooltipContent className="max-w-[260px] font-sans">This number was not found in any cited evidence.</TooltipContent>
              </Tooltip>
            ) : (
              <span key={i}>{p.text}</span>
            ),
          )}
          {turn.streaming ? <span aria-hidden="true" className="ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-pulse bg-ink-3" /> : null}
        </p>
      ) : null}

      {cited ? <EvidenceCard evidence={cited} /> : null}

      {a.error ? <p className="mt-2 text-[13px] text-fail">{a.error.title}{a.error.detail ? `: ${a.error.detail}` : ""}</p> : null}
      {turn.failed ? <p className="mt-2 text-[13px] text-fail">{turn.failed}</p> : null}

      {a.done ? (
        <p className="tnum mt-2 text-[12px] leading-4 text-ink-3">
          {a.done.numbers_unverified.length
            ? `${a.done.numbers_unverified.length} of ${a.done.numbers_checked} numbers not found in the evidence.`
            : a.done.numbers_checked
              ? `${a.done.numbers_checked} ${a.done.numbers_checked === 1 ? "number" : "numbers"} checked against the evidence.`
              : "No numbers to check."}{" "}
          {a.done.usage
            ? `${a.done.usage.model_id}: ${a.done.usage.cached ? "from cache" : `${formatReported(a.done.usage.tokens_in)} in, ${formatReported(a.done.usage.tokens_out)} out, ${a.done.usage.points == null ? "points not reported" : `${formatNumber(a.done.usage.points, 5)} points`}`}, ${formatDuration(a.done.usage.latency_ms)}.`
            : a.route?.route === "model"
              ? "Usage not reported."
              : ""}
        </p>
      ) : !turn.streaming && !turn.failed && !a.refusal && !a.text ? (
        <p className="mt-1 text-[13px] text-ink-3">Stopped.</p>
      ) : null}
    </div>
  );
}

function EvidenceCard({ evidence }: { evidence: Evidence }) {
  return (
    <div className="mt-2 rounded-sm border border-hairline bg-die-2 px-3 py-2 text-[12px] leading-4">
      <p className="text-ink">
        <span className="tnum font-medium">{evidence.evidence_id}</span> {TOOL_NAME[evidence.tool] ?? evidence.tool}
      </p>
      <p className="mt-0.5 text-ink-2">{evidence.summary}</p>
      <details className="mt-1.5">
        <summary className="cursor-pointer text-ink-3">The data</summary>
        <pre className="tnum mt-1 max-h-56 overflow-auto text-[11px] leading-4 whitespace-pre-wrap text-ink-2">{JSON.stringify(evidence.data, null, 2)}</pre>
      </details>
      {evidence.source ? (
        <p className="tnum mt-1 text-ink-3">
          From {evidence.source.name} {evidence.source.version}
        </p>
      ) : null}
    </div>
  );
}
