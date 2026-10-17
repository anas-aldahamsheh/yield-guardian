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
import {
  DRAFT_KEYS,
  readDraft,
  readJsonDraft,
  writeDraft,
  writeJsonDraft,
} from "@/lib/live/drafts";
import { cn } from "@/lib/utils";

import type { StartRun } from "./input-bar";
import {
  UPLOAD_ACCEPT,
  checkFile,
  isUpload,
  issueLine,
  keptUpload,
  uploadView,
} from "./upload-view";

const FORMATS: UploadFormat[] = ["csv", "xlsx"];

const KINDS: {
  kind: UploadKind;
  name: string;
  badge: string;
  stations: string;
  format: string;
}[] = [
  {
    kind: "sensors",
    name: "Chamber Sensor Telemetry (SECOM)",
    badge: "Stations 1 & 2 Active",
    stations: "Feeds Station 1 (Intake) and Station 2 (Monitoring & SPC Control Charts). Station 3 is bypassed.",
    format:
      "One row per unit: unit_id, timestamp, S001 to S590 and, if you have it, result (pass or fail). Timestamps are ISO 8601 without a zone, such as 2008-07-19T11:55:00. An empty cell is a missing reading.",
  },
  {
    kind: "wafers",
    name: "Optical Wafer Maps (WM-811K)",
    badge: "Station 3 Active",
    stations: "Feeds Station 3 (Wafer Defect Pattern Recognition & Lot Signatures). Station 2 is bypassed.",
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
  const sensorInputId = useId();
  const waferInputId = useId();
  const [refused, setRefused] = useState<string | null>(null);
  const [over, setOver] = useState(false);

  // Keep uploaded files across tab switches / reloads
  const [kept] = useState(() => keptUpload(readJsonDraft(DRAFT_KEYS.upload, isUpload)));
  const [sensorSummary, setSensorSummary] = useState<UploadSummary | null>(() => {
    const s = keptUpload(readJsonDraft(DRAFT_KEYS.uploadSensors, isUpload));
    if (s) return s;
    return kept?.kind === "sensors" ? kept : null;
  });
  const [waferSummary, setWaferSummary] = useState<UploadSummary | null>(() => {
    const w = keptUpload(readJsonDraft(DRAFT_KEYS.uploadWafers, isUpload));
    if (w) return w;
    return kept?.kind === "wafers" ? kept : null;
  });

  const upload = useMutation({
    mutationFn: (file: File) => uploadFile(file, csrf),
    onSuccess: (summary) => {
      if (summary.kind === "sensors") {
        setSensorSummary(summary);
        writeJsonDraft(DRAFT_KEYS.uploadSensors, summary);
      } else {
        setWaferSummary(summary);
        writeJsonDraft(DRAFT_KEYS.uploadWafers, summary);
      }
      writeJsonDraft(DRAFT_KEYS.upload, summary);
    },
  });

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
    const files = Array.from(event.dataTransfer.files);
    if (files.length === 0) return;
    files.slice(0, 2).forEach((f) => send(f));
  };

  const hasSensors = Boolean(sensorSummary);
  const hasWafers = Boolean(waferSummary);
  const isDual = hasSensors && hasWafers;

  const handleRun = () => {
    if (isDual && sensorSummary && waferSummary) {
      void onStart({
        source: "upload",
        upload_id: sensorSummary.upload_id,
        wafer_upload_id: waferSummary.upload_id,
      });
    } else if (sensorSummary) {
      void onStart({
        source: "upload",
        upload_id: sensorSummary.upload_id,
      });
    } else if (waferSummary) {
      void onStart({
        source: "upload",
        upload_id: waferSummary.upload_id,
      });
    }
  };

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
      <div className="min-w-0 space-y-4">
        {/* Main dropzone */}
        <label
          htmlFor={inputId}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
          className={cn(
            "flex min-h-[110px] cursor-pointer flex-col items-center justify-center gap-1 rounded-[16px] border border-dashed border-hairline-strong px-4 py-5 text-center transition-colors hover:bg-surface-2 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring",
            over && "lit",
          )}
        >
          <span className="text-[14.5px] leading-6 font-[560] text-ink">
            {upload.isPending
              ? "Validating file..."
              : isDual
                ? "Upload or replace a file"
                : "Drop CSV or XLSX file here, or choose to upload"}
          </span>
          <span className="text-[12.5px] leading-4 text-ink-3">
            Supports both Chamber Sensors (SECOM) and Optical Wafer Maps (WM-811K) &bull; Up to 32 MB
          </span>
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
            className="rounded-[14px] bg-fail-wash px-4 py-3 text-[13.5px] leading-5 text-ink"
          >
            {refused}
          </p>
        ) : null}

        {upload.isError ? (
          <p
            role="alert"
            className="rounded-[14px] bg-fail-wash px-4 py-3 text-[13.5px] leading-5 text-ink"
          >
            {`${describeError(upload.error).title}. ${describeError(upload.error).detail}`}
          </p>
        ) : null}

        {/* Stream upload slots */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {/* Slot 1: Chamber Sensors */}
          <div className="rounded-[14px] border border-hairline bg-surface p-3.5 shadow-2xs">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[13px] font-[600] text-ink">1. Chamber Sensors</span>
              <span className="rounded-full border border-hairline bg-surface-2 px-2 py-0.5 text-[10.5px] font-medium text-ink-2">
                Station 2
              </span>
            </div>
            {sensorSummary ? (
              <div className="mt-2 text-[12.5px]">
                <p className="font-[600] text-ink truncate">{sensorSummary.filename}</p>
                <p className="text-ink-3 text-[11.5px] mt-0.5">
                  {formatInt(sensorSummary.units)} units &bull; 590 sensors &bull; {sensorSummary.runnable ? "Valid" : "Issues found"}
                </p>
                <div className="mt-2 flex items-center justify-between border-t border-hairline pt-1.5 text-[11.5px]">
                  <label htmlFor={sensorInputId} className="cursor-pointer text-ink font-medium hover:underline">
                    Replace
                    <input
                      id={sensorInputId}
                      type="file"
                      accept={UPLOAD_ACCEPT}
                      className="sr-only"
                      onChange={(e) => {
                        send(e.target.files?.[0]);
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setSensorSummary(null);
                      writeDraft(DRAFT_KEYS.uploadSensors, null);
                    }}
                    className="cursor-pointer text-ink-3 hover:text-fail"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-2.5">
                <p className="text-[12px] text-ink-3 mb-2">No sensor telemetry file loaded.</p>
                <label
                  htmlFor={sensorInputId}
                  className="press inline-flex h-7 cursor-pointer items-center justify-center rounded-full border border-hairline bg-surface-2 px-3 text-[12px] font-medium text-ink hover:bg-surface-3 shadow-2xs"
                >
                  Upload Sensors CSV
                  <input
                    id={sensorInputId}
                    type="file"
                    accept={UPLOAD_ACCEPT}
                    className="sr-only"
                    onChange={(e) => {
                      send(e.target.files?.[0]);
                      e.target.value = "";
                    }}
                  />
                </label>
              </div>
            )}
          </div>

          {/* Slot 2: Wafer Maps */}
          <div className="rounded-[14px] border border-hairline bg-surface p-3.5 shadow-2xs">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[13px] font-[600] text-ink">2. Optical Wafer Maps</span>
              <span className="rounded-full border border-hairline bg-surface-2 px-2 py-0.5 text-[10.5px] font-medium text-ink-2">
                Station 3
              </span>
            </div>
            {waferSummary ? (
              <div className="mt-2 text-[12.5px]">
                <p className="font-[600] text-ink truncate">{waferSummary.filename}</p>
                <p className="text-ink-3 text-[11.5px] mt-0.5">
                  {formatInt(waferSummary.wafers)} wafers &bull; {formatInt(waferSummary.lots)} lots &bull; {waferSummary.runnable ? "Valid" : "Issues found"}
                </p>
                <div className="mt-2 flex items-center justify-between border-t border-hairline pt-1.5 text-[11.5px]">
                  <label htmlFor={waferInputId} className="cursor-pointer text-ink font-medium hover:underline">
                    Replace
                    <input
                      id={waferInputId}
                      type="file"
                      accept={UPLOAD_ACCEPT}
                      className="sr-only"
                      onChange={(e) => {
                        send(e.target.files?.[0]);
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setWaferSummary(null);
                      writeDraft(DRAFT_KEYS.uploadWafers, null);
                    }}
                    className="cursor-pointer text-ink-3 hover:text-fail"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-2.5">
                <p className="text-[12px] text-ink-3 mb-2">No wafer maps file loaded.</p>
                <label
                  htmlFor={waferInputId}
                  className="press inline-flex h-7 cursor-pointer items-center justify-center rounded-full border border-hairline bg-surface-2 px-3 text-[12px] font-medium text-ink hover:bg-surface-3 shadow-2xs"
                >
                  Upload Wafer CSV
                  <input
                    id={waferInputId}
                    type="file"
                    accept={UPLOAD_ACCEPT}
                    className="sr-only"
                    onChange={(e) => {
                      send(e.target.files?.[0]);
                      e.target.value = "";
                    }}
                  />
                </label>
              </div>
            )}
          </div>
        </div>

        {/* Detailed file results */}
        {sensorSummary ? (
          <UploadResult
            summary={sensorSummary}
            isSecondary={Boolean(waferSummary)}
          />
        ) : null}

        {waferSummary ? (
          <UploadResult
            summary={waferSummary}
            isSecondary={Boolean(sensorSummary)}
          />
        ) : null}

        {/* Route status & Launch CTA */}
        {(hasSensors || hasWafers) ? (
          <div className="mt-4 rounded-[14px] border border-hairline bg-surface p-4 shadow-2xs">
            <div className="text-[13px] leading-relaxed text-ink-2">
              <strong className="text-ink">Pipeline Execution Route: </strong>
              {isDual ? (
                <span>
                  <strong className="text-ink">Full Dual-Stream Active!</strong> Station 1 (Intake), Station 2 (Chamber Monitoring), Station 3 (Wafer Inspection), and Station 4 (Decision).
                </span>
              ) : hasSensors ? (
                <span>
                  Runs <strong className="text-ink">Station 1 &amp; Station 2 (Chamber SPC)</strong>. Station 3 is bypassed. (Tip: Upload a wafer map file to run both!)
                </span>
              ) : (
                <span>
                  Runs <strong className="text-ink">Station 1 &amp; Station 3 (Wafer Inspection)</strong>. Station 2 is bypassed. (Tip: Upload a sensor telemetry file to run both!)
                </span>
              )}
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handleRun}
                disabled={Boolean(starting || (sensorSummary && !sensorSummary.runnable) || (waferSummary && !waferSummary.runnable))}
                className="press lift sheen-hover cursor-pointer inline-flex h-10 items-center justify-center rounded-full bg-ink px-6 text-[14px] font-[600] text-canvas shadow-[0_1px_2px_rgb(0_0_0/0.12),inset_0_1px_0_rgb(255_255_255/0.12)] hover:bg-ink/92 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isDual
                  ? `Run Dual-Stream (${sensorSummary?.filename} + ${waferSummary?.filename})`
                  : sensorSummary
                    ? `Run ${sensorSummary.filename} (Station 2)`
                    : `Run ${waferSummary?.filename} (Station 3)`}
              </button>
              {(sensorSummary || waferSummary) ? (
                <button
                  type="button"
                  onClick={() => {
                    setSensorSummary(null);
                    setWaferSummary(null);
                    writeDraft(DRAFT_KEYS.uploadSensors, null);
                    writeDraft(DRAFT_KEYS.uploadWafers, null);
                    writeDraft(DRAFT_KEYS.upload, null);
                  }}
                  className="cursor-pointer text-[13px] text-ink-2 hover:text-ink hover:underline"
                >
                  Clear all uploads
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
      <Formats />
    </div>
  );
}

function UploadResult({
  summary,
  isSecondary = false,
}: {
  summary: UploadSummary;
  isSecondary?: boolean;
}) {
  const view = uploadView(summary);
  return (
    <section aria-label={`Inspection results for ${summary.filename}`} className="rounded-[12px] border border-hairline bg-surface-2/30 p-3 text-[13px]" aria-live="polite">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-ink truncate">{summary.filename}</span>
        <span className={cn("text-[12px] font-medium", view.ready ? "text-ink-2" : "text-fail")}>
          {view.ready ? "Ready to run" : "Requires attention"}
        </span>
      </div>
      <p className="mt-1 text-ink-2">{view.read}</p>
      {view.shown.length ? (
        <ul className="mt-2 max-h-32 overflow-y-auto grid grid-cols-[minmax(0,1fr)] border-t border-hairline">
          {view.shown.map((issue, k) => (
            <li
              key={k}
              className="grid grid-cols-[68px_minmax(0,1fr)] gap-x-2 border-b border-hairline py-1 text-[12.5px] leading-4.5"
            >
              <span
                className={cn(
                  "text-[11.5px]",
                  issue.severity === "error" ? "text-fail" : "text-ink-3",
                )}
              >
                {issue.severity === "error" ? "Error" : "Warning"}
              </span>
              <span className="min-w-0 text-ink truncate">
                <span className="tnum font-[560]">{issueLine(issue).place}</span>
                {issueLine(issue).rest}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {view.more ? (
        <p className="tnum mt-1 text-[11.5px] text-ink-3">{`and ${formatInt(view.more)} more issues`}</p>
      ) : null}
    </section>
  );
}

function Formats() {
  return (
    <section aria-labelledby="formats-title" className="min-w-0">
      <div className="flex items-center justify-between gap-2">
        <h3 id="formats-title" className="text-[15px] leading-6 font-[620] text-ink">
          Supported Fab Data Streams
        </h3>
        <span className="rounded-full bg-surface-2 px-2.5 py-0.5 text-[11.5px] font-medium text-ink-2">
          Single or Dual Stream
        </span>
      </div>
      <p className="mt-1 text-[13px] leading-5 text-ink-2">
        In manufacturing, tool chamber sensors (FDC/SPC logs) and wafer defect probers (metrology scans) originate from separate systems. Yield Guardian lets you upload either stream or both together:
      </p>
      <div className="mt-3 grid grid-cols-[minmax(0,1fr)] gap-3">
        {KINDS.map((k) => (
          <div
            key={k.kind}
            className="rounded-[16px] border border-hairline bg-surface-2/40 p-3.5 shadow-2xs transition-colors hover:bg-surface-2/60"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[14px] leading-5 font-[620] text-ink">{k.name}</span>
              <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[11px] font-semibold text-ink-2">
                {k.badge}
              </span>
            </div>
            <p className="mt-1 text-[12.5px] font-medium text-signal">
              {k.stations}
            </p>
            <p className="mt-1 text-[12px] leading-4.5 text-ink-3">{k.format}</p>
            <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-hairline/60 pt-2 text-[12.5px] leading-5">
              <span className="text-ink-3">
                Empty template:{" "}
                {FORMATS.map((f, i) => (
                  <span key={f}>
                    {i ? ", " : ""}
                    <a
                      href={templateUrl(k.kind, f)}
                      download
                      className="font-medium text-ink underline underline-offset-2 hover:text-signal"
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
                      className="font-medium text-ink underline underline-offset-2 hover:text-signal"
                    >
                      {f.toUpperCase()}
                    </a>
                  </span>
                ))}
              </span>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 rounded-[12px] border border-hairline bg-surface-2/50 px-3.5 py-2 text-[12px] leading-4.5 text-ink-3">
        <strong className="text-ink-2">Dual-Stream Capability:</strong> You can upload both a chamber sensor log and an optical wafer map above to run the full semiconductor pipeline concurrently with your own fab data.
      </div>
    </section>
  );
}
