"use client";

import { useQuery } from "@tanstack/react-query";
import type { RunComparison, RunSide, WorkRun } from "@yield-guardian/contracts";
import { CopyIcon, LaptopMinimalIcon, LinkIcon, SmartphoneIcon } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import { LocalDateTime } from "@/components/local-date-time";
import { ScrollRegion } from "@/components/scroll-region";
import { Placeholder, QueryView } from "@/components/states";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/lib/api/context";
import { describeError } from "@/lib/api/errors";
import {
  useCreateHandoff,
  useDeleteWorkRun,
  useFreshWorkspace,
  useUpdateWorkRun,
  wq,
} from "@/lib/api/workspace";
import { formatDateTime, formatInt, formatRelative, plural } from "@/lib/format";
import { ACTOR_ROLE, RUN_STAGE, RUN_STATUS, STAGE_STATUS, patternName } from "@/lib/labels";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

import { alarmCount, runName } from "./work-model";

// -- rename or note ------------------------------------------------------------------------------

/** A name and a note for a run; only this workspace sees them. */
export function RenameDialog({
  run,
  open,
  onOpenChange,
}: {
  run: WorkRun;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const update = useUpdateWorkRun({ quiet: true });
  const [label, setLabel] = useState(run.label ?? "");
  const [note, setNote] = useState(run.note ?? "");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    update.mutate(
      { runId: run.run_id, body: { label: label.trim() || null, note: note.trim() || null } },
      {
        onSuccess: () => {
          onOpenChange(false);
          toast.success("Saved", { description: "The run's name and note are kept with it." });
        },
      },
    );
  };
  const error = update.error ? describeError(update.error) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="grid grid-cols-[minmax(0,1fr)] gap-4">
          <DialogHeader>
            <DialogTitle>Rename or note this run</DialogTitle>
            <DialogDescription>
              {run.title}. Only the devices of this workspace see the name and the note.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
            <Label htmlFor="work-run-label">Name</Label>
            <Input
              id="work-run-label"
              value={label}
              maxLength={80}
              placeholder={run.title}
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
            <Label htmlFor="work-run-note">Note</Label>
            <Textarea
              id="work-run-note"
              value={note}
              maxLength={2000}
              rows={4}
              onChange={(e) => setNote(e.target.value)}
            />
            <p className="text-[12.5px] leading-4 text-ink-3">
              Leave a field empty to remove it. Up to 2,000 characters.
            </p>
          </div>
          {error ? (
            <p role="alert" className="text-[13.5px] leading-5 text-fail">
              {`${error.title}. ${error.detail}`}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Saving" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// -- delete --------------------------------------------------------------------------------------

/** Deletes a run for good, on every device of the workspace, once the person confirms. */
export function DeleteRunDialog({
  run,
  open,
  onOpenChange,
  onDeleted,
}: {
  run: WorkRun;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted: (run: WorkRun) => void;
}) {
  const remove = useDeleteWorkRun();
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this run?</AlertDialogTitle>
          <AlertDialogDescription>
            Its results, alarms and the investigations started from it are removed on every device
            in this workspace. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {remove.isError ? (
          <p role="alert" className="text-[13.5px] leading-5 text-fail">
            {`${describeError(remove.error).title}. ${describeError(remove.error).detail}`}
          </p>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={remove.isPending}
            onClick={(event) => {
              event.preventDefault();
              remove.mutate(run.run_id, {
                onSuccess: () => {
                  onOpenChange(false);
                  onDeleted(run);
                  toast.success("Run deleted");
                },
              });
            }}
          >
            {remove.isPending ? "Deleting" : "Delete run"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// -- compare -------------------------------------------------------------------------------------

/** Two runs side by side, from what each computed (GET /runs/{a}/compare/{b}). */
export function CompareDialog({
  run,
  runs,
  open,
  onOpenChange,
}: {
  run: WorkRun;
  runs: WorkRun[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const api = useApi();
  const others = runs.filter((r) => r.run_id !== run.run_id);
  const [other, setOther] = useState(
    () => (others.find((r) => r.run_id === run.again_of) ?? others[0])?.run_id ?? "",
  );
  const comparison = useQuery({ ...wq.compare(api, run.run_id, other), enabled: other !== "" });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Compare two runs</DialogTitle>
          <DialogDescription>
            {`What each run computed, side by side. A is “${runName(run)}”.`}
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
          <Label htmlFor="work-compare-with">Compare it with</Label>
          <Select value={other} onValueChange={setOther}>
            <SelectTrigger id="work-compare-with" className="w-full">
              <SelectValue placeholder="Choose a run" />
            </SelectTrigger>
            <SelectContent>
              {others.map((r) => (
                <SelectItem key={r.run_id} value={r.run_id}>
                  {`${runName(r)}, ${formatDateTime(r.created_at)}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {other ? (
          <QueryView
            query={comparison}
            loading={<Placeholder className="h-64" label="Comparing the runs" />}
          >
            {(c) => <Comparison comparison={c} runs={runs} />}
          </QueryView>
        ) : (
          <p className="text-[14px] leading-5 text-ink-2">
            This workspace has no other run to compare with.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}

const ROWS: { label: string; value: (side: RunSide) => string }[] = [
  { label: "Status", value: (s) => RUN_STATUS[s.status] ?? s.status },
  { label: "Units", value: (s) => formatInt(s.units) },
  { label: "Units with a risk result", value: (s) => formatInt(s.units_scored) },
  { label: "Units above the risk threshold", value: (s) => formatInt(s.units_flagged) },
  { label: "Units at the T² or SPE alarm level", value: (s) => formatInt(s.units_chart_alarm) },
  { label: "Units at the warning level", value: (s) => formatInt(s.units_chart_warning) },
  { label: "Wafers", value: (s) => formatInt(s.wafers) },
  { label: "Wafers classified", value: (s) => formatInt(s.wafers_classified) },
  { label: "Wafers accepted automatically", value: (s) => formatInt(s.wafers_auto_accepted) },
  { label: "Wafers left as unknown", value: (s) => formatInt(s.wafers_unknown) },
  {
    label: "Wafer patterns",
    value: (s) =>
      Object.entries(s.patterns)
        .filter(([, n]) => n)
        .map(([label, n]) => `${patternName(label as never)} ${formatInt(n)}`)
        .join(", ") || "None",
  },
  { label: "Lots", value: (s) => formatInt(s.lots) },
  { label: "Lots flagged", value: (s) => formatInt(s.lots_flagged) },
  // Counted as the alarms rail counts them; past a run's cap, the rest are counted, not listed.
  { label: "Alarms", value: (s) => formatInt(s.alarms) },
  { label: "Warnings", value: (s) => formatInt(s.warnings) },
  { label: "More, not listed", value: (s) => formatInt(s.alarms_not_listed) },
  { label: "Final test", value: (s) => s.final_test ?? "Did not run" },
];

function Comparison({ comparison, runs }: { comparison: RunComparison; runs: WorkRun[] }) {
  const { a, b } = comparison;
  // Each run by the name it has here (the one given to it, else how its input was chosen).
  const named = (side: RunSide) => {
    const listed = runs.find((r) => r.run_id === side.run_id);
    return listed ? runName(listed) : side.title;
  };
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      <div className="rounded-[16px] bg-surface-2 px-4 py-3.5 text-[14px] leading-5 text-ink-2">
        <p className="font-[600] text-ink">
          {comparison.same_input
            ? "Both runs computed exactly the same input."
            : "The runs computed different inputs, so their numbers are not of the same items."}
        </p>
        {comparison.changes.length ? (
          <ul className="mt-1.5 grid list-disc gap-0.5 pl-5 marker:text-ink-3">
            {comparison.changes.map((change) => (
              <li key={change}>{change}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1">Nothing differs: every count and stage status is the same.</p>
        )}
      </div>
      <ScrollRegion
        label="The two runs side by side"
        className="rounded-[16px] shadow-[inset_0_0_0_1px_var(--hairline)]"
      >
        <table className="w-full min-w-[520px] border-collapse text-left text-[13.5px] leading-5">
          <caption className="sr-only">The two runs side by side</caption>
          <thead>
            <tr className="border-b border-hairline text-[12.5px] leading-4 text-ink-3">
              <th scope="col" className="py-3 pr-3 pl-4 font-[520]">
                <span className="sr-only">Result</span>
              </th>
              {[a, b].map((side, i) => (
                <th key={side.run_id} scope="col" className="px-3 py-3 font-[520] last:pr-4">
                  <span className="block text-[13.5px] leading-5 font-[600] text-ink">{`${i ? "B" : "A"}: ${named(side)}`}</span>
                  <LocalDateTime iso={side.created_at} className="tnum" />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => {
              const [va, vb] = [row.value(a), row.value(b)];
              const differs = va !== vb;
              return (
                <tr key={row.label} className="border-b border-hairline last:border-b-0">
                  <th scope="row" className="py-2 pr-3 pl-4 align-top font-[420] text-ink-2">
                    {row.label}
                  </th>
                  <td className="tnum px-3 py-2 align-top text-ink">{va}</td>
                  <td
                    className={cn(
                      "tnum py-2 pr-4 pl-3 align-top text-ink",
                      differs && "bg-signal-wash font-[600]",
                    )}
                  >
                    {vb}
                    {differs ? <span className="sr-only"> (differs)</span> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </ScrollRegion>
      <ScrollRegion
        label="The stages of the two runs"
        className="rounded-[16px] shadow-[inset_0_0_0_1px_var(--hairline)]"
      >
        <table className="w-full min-w-[520px] border-collapse text-left text-[13.5px] leading-5">
          <caption className="sr-only">The stages of the two runs</caption>
          <thead>
            <tr className="border-b border-hairline text-[12.5px] leading-4 text-ink-3">
              <th scope="col" className="py-3 pr-3 pl-4 font-[520]">
                Stage
              </th>
              <th scope="col" className="px-3 py-3 font-[520]">
                A
              </th>
              <th scope="col" className="py-3 pr-4 pl-3 font-[520]">
                B
              </th>
            </tr>
          </thead>
          <tbody>
            {comparison.stages.map((stage) => (
              <tr key={stage.stage} className="border-b border-hairline last:border-b-0">
                <th scope="row" className="py-2 pr-3 pl-4 align-top font-[420] text-ink-2">
                  {RUN_STAGE[stage.stage] ?? stage.stage}
                </th>
                {(
                  [
                    [stage.a_status, stage.a_alarms, stage.a_warnings],
                    [stage.b_status, stage.b_alarms, stage.b_warnings],
                  ] as const
                ).map(([status, alarms, warnings], i) => (
                  <td key={i} className="tnum px-3 py-2 align-top text-ink last:pr-4">
                    {STAGE_STATUS[status] ?? status}
                    {alarms || warnings ? `, ${alarmCount({ alarms, warnings })}` : null}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollRegion>
    </div>
  );
}

// -- continue on another device -------------------------------------------------------------

/**
 * A single-use code and its link for another device. Made when the dialog opens; the devices
 * list follows, so the person sees the other device arrive.
 */
export function HandoffDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const api = useApi();
  const create = useCreateHandoff();
  const make = create.mutate;
  useEffect(() => make(), [make]);
  const summary = useQuery({ ...wq.summary(api), refetchInterval: 3_000 });
  const devices = summary.data?.devices ?? [];
  const [before, setBefore] = useState<number | null>(null);
  if (before === null && summary.data) setBefore(summary.data.devices.length);
  const joined = before !== null && devices.length > before;

  const handoff = create.data ?? null;
  const [ended, setEnded] = useState<string | null>(null);
  useEffect(() => {
    if (!handoff) return;
    const left = new Date(handoff.expires_at).getTime() - Date.now();
    const timer = window.setTimeout(() => setEnded(handoff.code), Math.max(0, left));
    return () => window.clearTimeout(timer);
  }, [handoff]);
  const expired = handoff != null && ended === handoff.code;
  const link = handoff ? `${window.location.origin}${handoff.join_path}` : "";
  const [copied, setCopied] = useState<string | null>(null);
  const copy = (text: string, what: string) => {
    navigator.clipboard
      ?.writeText(text)
      .then(() => setCopied(what))
      .catch(() => setCopied("none"));
    if (!navigator.clipboard) setCopied("none");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Continue on another device</DialogTitle>
          <DialogDescription>
            Open the link on your phone or another computer, or open {window.location.host}/join
            there and type the code. That device then sees this workspace&apos;s runs, uploads and
            investigations, and what it does is added here.
          </DialogDescription>
        </DialogHeader>
        {create.isError ? (
          <p role="alert" className="text-[13.5px] leading-5 text-fail">
            {`${describeError(create.error).title}. ${describeError(create.error).detail}`}
          </p>
        ) : !handoff ? (
          <Placeholder className="h-[13.5rem] rounded-[16px]" label="Making a code" />
        ) : (
          <div className="grid grid-cols-[minmax(0,1fr)] gap-4">
            <div className="rounded-[16px] bg-surface-2 px-4 pt-3 pb-3.5 text-center shadow-[inset_0_0_0_1px_var(--hairline)]">
              <p className="text-[12.5px] leading-4 font-[520] text-ink-3">Code</p>
              <p
                className="tnum mt-1 text-[30px] leading-10 font-[640] tracking-[0.14em] text-ink [font-stretch:104%]"
                data-handoff-code=""
              >
                <span aria-hidden="true">{handoff.code}</span>
                <span className="sr-only">{handoff.code.split("").join(" ")}</span>
              </p>
            </div>
            <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
              <Label htmlFor="work-handoff-link">Link</Label>
              <Input
                id="work-handoff-link"
                readOnly
                value={link}
                onFocus={(e) => e.currentTarget.select()}
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => copy(link, "link")}>
                <LinkIcon aria-hidden="true" strokeWidth={1.9} />
                Copy the link
              </Button>
              <Button size="sm" variant="outline" onClick={() => copy(handoff.code, "code")}>
                <CopyIcon aria-hidden="true" strokeWidth={1.9} />
                Copy the code
              </Button>
            </div>
            <p className="text-[13.5px] leading-5 text-ink-2" role="status">
              {expired ? (
                "This code has ended. Make a new one."
              ) : copied === "none" ? (
                "This browser does not allow copying here: select the link and copy it."
              ) : copied ? (
                `The ${copied} is copied.`
              ) : (
                <>
                  {"It works once, until "}
                  <LocalDateTime iso={handoff.expires_at} timeOnly />
                  {`. A new code ends this one. Use it only on your own device: whoever opens it sees everything here.`}
                </>
              )}
            </p>
          </div>
        )}
        <div className="grid grid-cols-[minmax(0,1fr)] gap-2 border-t border-hairline pt-4">
          <h3 className="text-[14px] leading-5 font-[600] text-ink">Devices in this workspace</h3>
          {joined ? (
            <p
              role="status"
              className="swap-in flex items-center gap-2 rounded-[12px] bg-pass-wash px-3 py-2 text-[13.5px] leading-5 text-ink"
            >
              <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-pass" />
              Another device joined: it sees this workspace now.
            </p>
          ) : null}
          <ul className="grid grid-cols-[minmax(0,1fr)] gap-1 text-[13.5px] leading-5 text-ink-2">
            {devices.map((device, i) => (
              <li
                key={`${device.created_at}-${i}`}
                className="flex flex-wrap items-center gap-x-2.5 rounded-[12px] bg-surface-2 px-3 py-2"
              >
                {device.current ? (
                  <LaptopMinimalIcon
                    aria-hidden="true"
                    className="size-4 shrink-0 text-ink-3"
                    strokeWidth={1.8}
                  />
                ) : (
                  <SmartphoneIcon
                    aria-hidden="true"
                    className="size-4 shrink-0 text-ink-3"
                    strokeWidth={1.8}
                  />
                )}
                <span className="font-[560] text-ink">
                  {device.current ? "This device" : "Another device"}
                </span>
                <span>{ACTOR_ROLE[device.role] ?? device.role}</span>
                <span className="text-ink-3">{`last used ${formatRelative(device.last_seen_at)}`}</span>
              </li>
            ))}
          </ul>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            disabled={create.isPending}
            onClick={() => {
              setCopied(null);
              make();
            }}
          >
            Make a new code
          </Button>
          <Button onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// -- start fresh ---------------------------------------------------------------------------------

/**
 * Moves this device to a new, empty workspace. Says first what happens to this one: other
 * devices keep it; with none, it is deleted at the next cleanup.
 */
export function FreshDialog({
  open,
  onOpenChange,
  onMoved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onMoved: () => void;
}) {
  const api = useApi();
  const summary = useQuery(wq.summary(api));
  const fresh = useFreshWorkspace();
  const s = summary.data;
  const others = s ? s.devices.filter((d) => !d.current).length : 0;
  const held = s
    ? [
        s.runs ? plural(s.runs, "run") : null,
        s.uploads ? plural(s.uploads, "upload") : null,
        s.investigations ? plural(s.investigations, "investigation") : null,
      ].filter(Boolean)
    : [];
  const losing = s != null && others === 0 && held.length > 0;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Start a fresh workspace on this device?</AlertDialogTitle>
          <AlertDialogDescription>
            {!s
              ? "Reading what this workspace holds."
              : others > 0
                ? `This device moves to a new, empty workspace and no longer sees this one. The ${plural(others, "other device")} ${others === 1 ? "keeps" : "keep"} it, with everything in it.`
                : losing
                  ? `No other device uses this workspace, so its ${held.join(", ")} are deleted within minutes. To keep them, continue on another device first.`
                  : "This device moves to a new, empty workspace. This one holds nothing yet."}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {fresh.isError ? (
          <p role="alert" className="text-[13.5px] leading-5 text-fail">
            {describeError(fresh.error).detail}
          </p>
        ) : null}
        <AlertDialogFooter>
          <AlertDialogCancel>Keep this workspace</AlertDialogCancel>
          <AlertDialogAction
            variant={losing ? "destructive" : "default"}
            disabled={!s || fresh.isPending}
            onClick={(event) => {
              event.preventDefault();
              fresh.mutate(undefined, {
                onSuccess: () => {
                  onOpenChange(false);
                  onMoved();
                  toast.success("A fresh workspace", {
                    description: "This device starts with an empty workspace.",
                  });
                },
              });
            }}
          >
            {fresh.isPending ? "Moving" : losing ? "Delete it and start fresh" : "Start fresh"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
