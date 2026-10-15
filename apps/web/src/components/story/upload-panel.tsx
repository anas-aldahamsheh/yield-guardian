"use client";

import { useMutation } from "@tanstack/react-query";
import type { UploadSummary } from "@yield-guardian/contracts";
import { type DragEvent, useId, useState } from "react";

import { LocalDateTime } from "@/components/local-date-time";
import { describeError } from "@/lib/api/errors";
import { useSession } from "@/lib/api/session";
import { formatInt } from "@/lib/format";
import {
  exampleUrl,
  templateUrl,
  uploadFile,
  type UploadFormat,
  type UploadKind,
} from "@/lib/live/api";
import { cn } from "@/lib/utils";

import type { StartRun } from "./input-bar";
import { UPLOAD_ACCEPT, checkFile, issuePlace, uploadView } from "./upload-view";

const FORMATS: UploadFormat[] = ["csv", "xlsx"];

const KINDS: { kind: UploadKind; name: string; format: string }[] = [
  {
    kind: "sensors",
    name: "Sensor units",
    format:
      "One row per unit: unit_id, timestamp, S001 to S590 and, if you have it, result (pass or fail). Timestamps are ISO 8601 without a zone, such as 2008-07-19T11:55:00. An empty cell is a missing reading.",
  },
  {
    kind: "wafers",
    name: "Wafer maps",
    format:
      "One row per die: lot, wafer, x, y, result (pass or fail). x is the column and y the row, both counted from 0 at the top left of the map.",
  },
];

/**
 * Upload a file: CSV or XLSX in the SECOM layout (sensor units) or die by die (wafer maps). The
 * API reads and checks it; the page shows what it read and every problem by row and column, and
 * runs it when nothing blocks it.
 */
export function UploadPanel({ onStart, starting }: { onStart: StartRun; starting: boolean }) {
  const { csrf } = useSession();
  const inputId = useId();
  const [refused, setRefused] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const upload = useMutation({ mutationFn: (file: File) => uploadFile(file, csrf) });

  const send = (file: File | undefined) => {
    if (!file) return;
    const problem = checkFile(file);
    setRefused(problem);
    if (problem) {
      upload.reset();
      return;
    }
    upload.mutate(file);
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setOver(false);
    send(event.dataTransfer.files[0]);
  };

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
      <div className="min-w-0">
        <label
          htmlFor={inputId}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
          className={cn(
            "flex min-h-[132px] cursor-pointer flex-col items-center justify-center gap-1 rounded-[2px] border border-dashed border-hairline-strong px-4 py-6 text-center hover:bg-die-2 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring",
            over && "lit",
          )}
        >
          <span className="text-[15px] leading-6 font-medium text-ink">
            {upload.isPending ? "Reading the file" : "Choose a CSV or XLSX file, or drop it here"}
          </span>
          <span className="text-[13px] leading-5 text-ink-3">Up to 32 MB per file.</span>
          <input
            id={inputId}
            type="file"
            accept={UPLOAD_ACCEPT}
            className="sr-only"
            onChange={(e) => {
              send(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </label>
        {refused ? (
          <p
            role="alert"
            className="mt-3 rounded-[2px] bg-fail-wash px-3 py-2 text-[14px] leading-5 text-ink"
          >
            {refused}
          </p>
        ) : null}
        {upload.isError ? (
          <p
            role="alert"
            className="mt-3 rounded-[2px] bg-fail-wash px-3 py-2 text-[14px] leading-5 text-ink"
          >
            {`${describeError(upload.error).title}. ${describeError(upload.error).detail}`}
          </p>
        ) : null}
        {upload.data && !refused ? (
          <UploadResult
            summary={upload.data}
            starting={starting}
            onRun={() => void onStart({ source: "upload", upload_id: upload.data.upload_id })}
          />
        ) : null}
      </div>
      <Formats />
    </div>
  );
}

function UploadResult({
  summary,
  starting,
  onRun,
}: {
  summary: UploadSummary;
  starting: boolean;
  onRun: () => void;
}) {
  const view = uploadView(summary);
  return (
    <section aria-label="What the file holds" className="mt-4" aria-live="polite">
      <p className="text-[14px] leading-5 text-ink-2">{view.read}</p>
      <p
        className={cn(
          "mt-1 text-[15px] leading-6 font-medium",
          view.ready ? "text-ink" : "text-fail",
        )}
      >
        {view.headline}
      </p>
      {view.shown.length ? (
        <ul className="mt-2 grid grid-cols-[minmax(0,1fr)] border-t border-hairline">
          {view.shown.map((issue, k) => (
            <li
              key={k}
              className="grid grid-cols-[72px_minmax(0,1fr)] gap-x-3 border-b border-hairline py-1.5 text-[14px] leading-5"
            >
              <span
                className={cn(
                  "text-[13px]",
                  issue.severity === "error" ? "text-fail" : "text-ink-3",
                )}
              >
                {issue.severity === "error" ? "Error" : "Warning"}
              </span>
              <span className="min-w-0 text-ink">
                <span className="tnum font-medium">{issuePlace(issue)}: </span>
                {issue.message}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {view.more ? (
        <p className="tnum mt-1.5 text-[13px] text-ink-3">{`and ${formatInt(view.more)} more of the same kinds`}</p>
      ) : null}
      {view.ready ? (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={onRun}
            disabled={starting}
            className="inline-flex h-10 items-center rounded-[4px] bg-ink px-4 text-[14px] font-semibold text-room hover:bg-ink/90 disabled:opacity-50"
          >
            {`Run ${summary.filename}`}
          </button>
          <span className="text-[12px] leading-4 text-ink-3">
            Kept until <LocalDateTime iso={summary.expires_at} />
          </span>
        </div>
      ) : null}
    </section>
  );
}

function Formats() {
  return (
    <section aria-labelledby="formats-title" className="min-w-0">
      <h3 id="formats-title" className="text-[15px] leading-6 font-semibold text-ink">
        What a file holds
      </h3>
      <dl className="mt-1 grid grid-cols-[minmax(0,1fr)] gap-3">
        {KINDS.map((k) => (
          <div key={k.kind} className="border-t border-hairline pt-2">
            <dt className="text-[14px] leading-5 font-medium text-ink">{k.name}</dt>
            <dd className="mt-0.5 text-[13px] leading-5 text-ink-2">{k.format}</dd>
            <dd className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[13px] leading-5">
              <span className="text-ink-3">
                Empty template:{" "}
                {FORMATS.map((f, i) => (
                  <span key={f}>
                    {i ? ", " : ""}
                    <a
                      href={templateUrl(k.kind, f)}
                      download
                      className="text-ink underline underline-offset-2 hover:text-safelight"
                    >
                      {f.toUpperCase()}
                    </a>
                  </span>
                ))}
              </span>
              <span className="text-ink-3">
                Real example:{" "}
                {FORMATS.map((f, i) => (
                  <span key={f}>
                    {i ? ", " : ""}
                    <a
                      href={exampleUrl(k.kind, f)}
                      download
                      className="text-ink underline underline-offset-2 hover:text-safelight"
                    >
                      {f.toUpperCase()}
                    </a>
                  </span>
                ))}
              </span>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
