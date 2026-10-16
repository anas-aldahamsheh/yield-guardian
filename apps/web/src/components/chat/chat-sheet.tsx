"use client";

import type { ChatContext, ChatMessage, Evidence } from "@yield-guardian/contracts";
import { ArrowRightIcon, ArrowUpIcon, ChevronRightIcon, SquareIcon } from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { type FormEvent, type KeyboardEvent, useRef, useState } from "react";

import { UnverifiedMark } from "@/components/investigation/report";
import { WaferMark } from "@/components/shell/wordmark";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { describeError } from "@/lib/api/errors";
import { NOT_CONFIGURED, useFeatures } from "@/lib/api/features";
import { useStartInvestigation } from "@/lib/api/investigations";
import { useSession, useStartGuestSession } from "@/lib/api/session";
import {
  applyChatEvent,
  type ChatAnswer,
  type ChatSuggestion,
  contextFromLocation,
  describeContext,
  emptyAnswer,
  extractVisiblePageContent,
  segmentAnswer,
  streamChat,
  type TextPart,
} from "@/lib/chat/chat";
import { formatDuration, formatNumber, formatReported } from "@/lib/format";
import { TOOL_NAME } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { AskButton } from "./ask-button";

type Turn = {
  id: number;
  question: string;
  context: ChatContext | null;
  answer: ChatAnswer;
  failed: string | null;
  streaming: boolean;
};

/** Questions that only name the object on screen; the numbers come from the answer. */
function suggestions(context: ChatContext | null): string[] {
  if (context?.run_alarm)
    return [`Why was ${context.run_alarm} raised?`, "Which sensors moved most before this alarm?"];
  if (context?.run_id) return ["Summarise this run.", "What does this station's result mean?"];
  if (context?.unit_id != null)
    return [
      `Why was unit ${context.unit_id} flagged?`,
      `Which sensors moved most on unit ${context.unit_id}?`,
    ];
  if (context?.sensor)
    return [`Is ${context.sensor} healthy?`, `Which group is ${context.sensor} in?`];
  if (context?.wafer_id)
    return [
      `What pattern is wafer ${context.wafer_id}?`,
      `Which wafers look like ${context.wafer_id}?`,
    ];
  if (context?.lot) return [`Which patterns are over-represented in lot ${context.lot}?`];
  return [
    "What is shown on this page?",
    "Which units are high risk right now?",
    "Which sensors need maintenance?",
  ];
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

  const update = (id: number, fn: (t: Turn) => Turn) =>
    setTurns((all) => all.map((t) => (t.id === id ? fn(t) : t)));
  const follow = () =>
    requestAnimationFrame(() => scroller.current?.scrollTo({ top: scroller.current.scrollHeight }));

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || streaming) return;
    nextId.current += 1;
    const id = nextId.current;

    const visibleContent = useContext ? extractVisiblePageContent() : null;
    const effectiveContext: ChatContext | null = useContext
      ? {
          ...(pageContext ?? {}),
          ...(visibleContent ? { page_content: visibleContent } : {}),
        }
      : null;

    const history: ChatMessage[] = turns
      .filter((t) => !t.failed && t.answer.text)
      .flatMap((t) => [
        { role: "user" as const, content: t.question },
        { role: "assistant" as const, content: t.answer.text.slice(0, 4000) },
      ]);
    setTurns((all) => [
      ...all,
      { id, question: q, context: effectiveContext, answer: emptyAnswer(), failed: null, streaming: true },
    ]);
    setDraft("");
    follow();
    const controller = new AbortController();
    abort.current = controller;
    try {
      await streamChat({
        messages: [...history, { role: "user", content: q.slice(0, 4000) }],
        context: effectiveContext,
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
        <AskButton />
      </SheetTrigger>
      <SheetContent side="right" className="flex flex-col gap-0 p-0 sm:max-w-[520px]">
        <SheetHeader className="border-b border-hairline px-4 pt-5 pb-4 sm:px-6 sm:pt-6 sm:pb-5">
          <div className="flex items-center gap-2.5 pr-10">
            <WaferMark idPrefix="yg-chat-mark" className="size-6 shrink-0 text-ink" />
            <SheetTitle>Ask about the plant data</SheetTitle>
          </div>
          <SheetDescription>
            Answers cite the evidence they used, and every number is checked against it.
            Associations in historical data, not causes.
          </SheetDescription>
        </SheetHeader>

        <div
          ref={scroller}
          className="min-h-0 grow overflow-y-auto px-4 py-5 sm:px-6"
          aria-live="polite"
          aria-busy={streaming}
        >
          {chatServed === false && turns.length === 0 ? (
            <div
              role="note"
              className="unexposed rounded-[14px] px-4 py-3.5 shadow-[inset_0_0_0_1px_var(--hairline-strong)]"
            >
              <p className="text-[14px] leading-5 font-medium text-ink">
                {NOT_CONFIGURED.chat.title}
              </p>
              <p className="mt-1 text-[13px] leading-5 text-ink-2">{NOT_CONFIGURED.chat.detail}</p>
            </div>
          ) : turns.length === 0 ? (
            <div>
              <p className="text-[12.5px] leading-4 font-[560] text-ink-3">Try</p>
              <ul className="mt-3 grid grid-cols-[minmax(0,1fr)] gap-2">
                {suggestions(context).map((s, i) => (
                  <li
                    key={s}
                    className="rise-in"
                    style={{ "--i": i, "--d": "160ms" } as React.CSSProperties}
                  >
                    <button
                      type="button"
                      disabled={!canAct}
                      onClick={() => void ask(s)}
                      className="group/try press flex w-full cursor-pointer items-center justify-between gap-3 rounded-[14px] bg-surface-2 py-3 pr-3.5 pl-4 text-left text-[14px] leading-5 text-ink transition-colors duration-(--dur-2) hover:bg-surface-3 disabled:cursor-default disabled:text-ink-3"
                    >
                      <span className="min-w-0">{s}</span>
                      <ArrowRightIcon
                        aria-hidden="true"
                        strokeWidth={1.9}
                        className="size-4 shrink-0 text-ink-3 transition-[translate,color,opacity] duration-(--dur-3) ease-spring group-hover/try:translate-x-0.5 group-hover/try:text-ink group-disabled/try:opacity-0"
                      />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <ol className="grid grid-cols-[minmax(0,1fr)] gap-6">
              {turns.map((t) => (
                <li key={t.id} className="swap-in grid grid-cols-[minmax(0,1fr)] gap-3">
                  <p className="ml-auto max-w-[85%] rounded-[18px] rounded-br-[6px] bg-ink px-4 py-2.5 text-[14px] leading-5 text-canvas">
                    {t.question}
                    {t.context ? (
                      <span className="mt-0.5 block text-[12px] text-canvas/70">
                        About {describeContext(t.context)}
                      </span>
                    ) : null}
                  </p>
                  <AnswerView turn={t} onStarted={() => setOpen(false)} />
                </li>
              ))}
            </ol>
          )}
        </div>

        <div className="border-t border-hairline px-4 pt-4 pb-[max(16px,env(safe-area-inset-bottom))] sm:px-6">
          {chatServed === false ? (
            <p className="text-[13px] leading-5 text-ink-2">
              Asking is off until the API has a language model key.
            </p>
          ) : !canAct ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[13px] leading-5 text-ink-2">Asking needs an engineer session.</p>
              <Button
                size="sm"
                variant="outline"
                onClick={() => guest.mutate()}
                disabled={guest.isPending}
              >
                {guest.isPending ? "Signing in…" : "Try as engineer"}
              </Button>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="grid grid-cols-[minmax(0,1fr)] gap-2.5">
              <label className="flex w-fit cursor-pointer items-center gap-2 text-[12.5px] leading-4 text-ink-2">
                <input
                  type="checkbox"
                  checked={useContext}
                  onChange={(e) => setUseContext(e.target.checked)}
                  className="size-4 accent-[var(--signal)]"
                />
                About {describeContext(pageContext ?? {})}
              </label>
              {/* One field: the question and its button share a rounded plane that takes the focus ring. */}
              <div className="flex items-end gap-1.5 rounded-[22px] bg-surface p-1.5 shadow-[inset_0_0_0_1px_var(--edge)] transition-shadow duration-(--dur-2) hover:shadow-[inset_0_0_0_1px_var(--ink-3)] has-[textarea:focus-visible]:shadow-[inset_0_0_0_1.5px_var(--signal),0_0_0_4px_color-mix(in_oklab,var(--signal)_16%,transparent)]">
                <Textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={onKeyDown}
                  maxLength={4000}
                  rows={2}
                  placeholder="Ask about a run, unit, wafer or lot"
                  aria-label="Question"
                  className="max-h-40 min-h-10 resize-none rounded-[16px] border-0 bg-transparent px-3 py-2 hover:border-transparent focus-visible:outline-none"
                />
                {streaming ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={() => abort.current?.abort()}
                    className="shrink-0 rounded-full"
                  >
                    <SquareIcon aria-hidden="true" className="size-3.5 fill-current" />
                    <span className="sr-only">Stop</span>
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    size="icon"
                    disabled={!draft.trim()}
                    className="shrink-0 rounded-full"
                  >
                    <ArrowUpIcon aria-hidden="true" className="size-[18px]" strokeWidth={2.1} />
                    <span className="sr-only">Ask</span>
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

function AnswerView({ turn, onStarted }: { turn: Turn; onStarted: () => void }) {
  const a = turn.answer;
  const [open, setOpen] = useState<string | null>(null);
  const cited = a.citations.find((c) => c.evidence_id === open);
  const parts = keepCitationsInLine(segmentAnswer(a.text, a.done?.numbers_unverified ?? []));

  return (
    <div className="min-w-0 text-[14px] leading-6">
      {a.route ? (
        <p className="text-[12px] leading-4 text-ink-3">
          {a.route.route === "deterministic"
            ? "Answered by rules, without a model"
            : `Answered by ${a.route.model_id ?? "a model"}`}
          {a.tools.length
            ? `, using ${a.tools.map((x) => TOOL_NAME[x.tool] ?? x.tool).join(", ")}`
            : ""}
          .
        </p>
      ) : turn.streaming ? (
        <p className="text-[12px] text-ink-3">Reading the question…</p>
      ) : null}

      {a.refusal ? <p className="mt-1 text-ink-2">{a.refusal}</p> : null}

      {a.text ? (
        <p
          className={cn(
            "mt-1 whitespace-pre-wrap text-ink",
            // Model prose is set in the serif, as everywhere: check its evidence links.
            a.route?.route === "model" && "written text-[16px] leading-[26px]",
          )}
        >
          {parts.map((p, i) =>
            p.cite ? (
              <span key={i} className="whitespace-nowrap">
                {p.before}
                <button
                  type="button"
                  onClick={() => setOpen(open === p.cite ? null : p.cite!)}
                  aria-expanded={open === p.cite}
                  className={cn(
                    "tnum press mx-0.5 cursor-pointer rounded-full px-1.5 align-baseline text-[11px] leading-4 font-[560] transition-[background-color,color,box-shadow] duration-(--dur-2)",
                    open === p.cite
                      ? "bg-ink text-canvas"
                      : "bg-surface-2 text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:text-ink hover:shadow-[inset_0_0_0_1px_var(--edge)]",
                  )}
                >
                  {p.cite}
                </button>
                {p.after}
              </span>
            ) : p.unverified ? (
              <UnverifiedMark key={i} />
            ) : p.flagged ? (
              <Tooltip key={i}>
                <TooltipTrigger asChild>
                  <span
                    tabIndex={0}
                    className="tnum bg-fail-wash underline decoration-fail decoration-wavy underline-offset-[5px]"
                  >
                    {p.text}
                  </span>
                </TooltipTrigger>
                <TooltipContent className="max-w-[260px] font-sans">
                  This number was not found in any cited evidence.
                </TooltipContent>
              </Tooltip>
            ) : (
              <span key={i}>{p.text}</span>
            ),
          )}
          {turn.streaming ? (
            <span
              aria-hidden="true"
              className="ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-pulse rounded-full bg-signal"
            />
          ) : null}
        </p>
      ) : null}

      {cited ? <EvidenceCard evidence={cited} /> : null}

      {a.offers.map((offer) => (
        <OfferCard
          key={`${offer.trigger.kind}:${offer.trigger.ref}`}
          offer={offer}
          onStarted={onStarted}
        />
      ))}

      {a.error ? (
        <p className="mt-2 text-[13px] text-fail">
          {a.error.title}
          {a.error.detail ? `: ${a.error.detail}` : ""}
        </p>
      ) : null}
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

/**
 * An investigation the answer offers, checked by code against the run, the evidence or the
 * page. Nothing starts until the engineer clicks: then POST /investigations with its trigger.
 */
function OfferCard({ offer, onStarted }: { offer: ChatSuggestion; onStarted: () => void }) {
  const start = useStartInvestigation();
  const { liveInvestigations } = useFeatures();
  return (
    <div
      className="grow-in mt-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2 rounded-[14px] bg-signal-wash px-4 py-3 shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--signal)_40%,transparent)]"
      data-chat-offer
    >
      <p className="min-w-0 text-[13px] leading-5 text-ink">
        <span className="text-ink-2">Suggested investigation: </span>
        {offer.title}
      </p>
      <Button
        size="sm"
        onClick={() => start.mutate(offer.trigger, { onSuccess: onStarted })}
        disabled={start.isPending || liveInvestigations === false}
      >
        {start.isPending ? "Starting…" : "Start investigation"}
      </Button>
      {liveInvestigations === false ? (
        <p className="w-full text-[12px] leading-4 text-ink-3">
          {NOT_CONFIGURED.investigations.title}.
        </p>
      ) : null}
    </div>
  );
}

function EvidenceCard({ evidence }: { evidence: Evidence }) {
  return (
    <div className="grow-in mt-3 rounded-[14px] bg-surface-2 px-4 py-3 text-[12.5px] leading-[18px]">
      <p className="flex items-center gap-2 text-ink">
        <span className="tnum rounded-full bg-ink px-1.5 text-[11px] leading-4 font-[560] text-canvas">
          {evidence.evidence_id}
        </span>
        <span className="font-[560]">{TOOL_NAME[evidence.tool] ?? evidence.tool}</span>
      </p>
      <p className="mt-1.5 text-ink-2">{evidence.summary}</p>
      <details className="group/data mt-2">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-full text-ink-2 transition-colors duration-(--dur-1) hover:text-ink [&::-webkit-details-marker]:hidden">
          <ChevronRightIcon
            aria-hidden="true"
            strokeWidth={2}
            className="size-3.5 transition-transform duration-(--dur-2) ease-out group-open/data:rotate-90"
          />
          The data
        </summary>
        <pre className="tnum mt-2 max-h-56 overflow-auto rounded-[10px] bg-surface px-3 py-2 text-[11.5px] leading-4 whitespace-pre-wrap text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline)]">
          {JSON.stringify(evidence.data, null, 2)}
        </pre>
      </details>
      {evidence.source ? (
        <p className="tnum mt-2 text-ink-3">
          From {evidence.source.name} {evidence.source.version}
        </p>
      ) : null}
    </div>
  );
}

type Shown = TextPart & { before?: string; after?: string };

/**
 * A citation keeps the word before it and the punctuation after it on its line, so no line
 * starts with a lone "E1" or with ", above". Only how the parts are laid out changes: the text
 * reads the same.
 */
function keepCitationsInLine(parts: TextPart[]): Shown[] {
  const shown: Shown[] = parts.map((p) => ({ ...p }));
  const plain = (p: Shown | undefined) => p && !p.cite && !p.unverified && !p.flagged;
  shown.forEach((p, i) => {
    if (!p.cite) return;
    const prev = shown[i - 1];
    const next = shown[i + 1];
    if (prev && plain(prev)) {
      const word = /\S+[ \t]*$/.exec(prev.text)?.[0] ?? "";
      prev.text = prev.text.slice(0, prev.text.length - word.length);
      p.before = word;
    }
    if (next && plain(next)) {
      const mark = /^[,.;:!?)\]]+/.exec(next.text)?.[0] ?? "";
      next.text = next.text.slice(mark.length);
      p.after = mark;
    }
  });
  return shown;
}
