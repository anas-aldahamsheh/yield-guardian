"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import type {
  LotSummary,
  PickRunCreate,
  RunCase,
  UnitSummary,
  WaferSummary,
} from "@yield-guardian/contracts";
import { type ReactNode, useRef, useState } from "react";

import { ErrorState, Placeholder } from "@/components/states";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { unwrap } from "@/lib/api/client";
import { useApi } from "@/lib/api/context";
import { formatInt, formatPlantTime, formatPValue, plural } from "@/lib/format";
import { BAND_NAME, patternName } from "@/lib/labels";
import { NotReadyYet, getRunCases } from "@/lib/live/api";
import { cn } from "@/lib/utils";

import type { StartRun } from "./input-bar";

const PAGE = 50;
const DATASET: Record<string, string> = { secom: "SECOM", wm811k: "WM-811K", user: "your data" };

/**
 * Pick a case: real situations found in the data by a fixed rule (the catalog), or real units,
 * wafers and lots chosen by hand from the dataset browsers.
 */
export function CasePicker({ onStart, starting }: { onStart: StartRun; starting: boolean }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <Catalog onStart={onStart} starting={starting} />
      <Browsers onStart={onStart} starting={starting} />
    </div>
  );
}

function Catalog({ onStart, starting }: { onStart: StartRun; starting: boolean }) {
  const cases = useQuery({
    queryKey: ["runs", "cases"],
    queryFn: ({ signal }) => getRunCases({ signal }),
    staleTime: 10 * 60_000,
  });
  const finding = cases.isPending && cases.failureReason instanceof NotReadyYet;
  const items = cases.data?.items ?? [];
  const sensorCases = items.filter((c) => c.datasets.includes("secom"));
  const waferCases = items.filter((c) => c.datasets.includes("wm811k"));

  return (
    <section aria-labelledby="cases-title" className="min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="cases-title" className="text-[15px] leading-6 font-[620] text-ink">
          Pre-Engineered Scenarios
        </h3>
      </div>
      <p className="mt-1 mb-4 text-[13px] leading-5 text-ink-3">
        Verified historical cases with deterministic detection rules. Select a scenario to test how that station reacts in-line.
      </p>
      {finding ? (
        <p
          role="status"
          className="flex items-start gap-2 rounded-[14px] px-3 py-2.5 text-[14px] leading-5 text-ink-2 shadow-[inset_0_0_0_1px_var(--hairline)]"
        >
          <span aria-hidden="true" className="mt-1.5 size-1.5 shrink-0 rounded-full bg-signal" />
          Finding real cases in the data. The service looks for them each time it starts, which
          takes up to half a minute; the list appears here when it is ready.
        </p>
      ) : cases.isPending ? (
        <Placeholder className="h-40" />
      ) : cases.isError ? (
        <ErrorState error={cases.error} onRetry={() => void cases.refetch()} compact />
      ) : (
        <div className="space-y-4">
          {sensorCases.length ? (
            <div>
              <div className="mb-2 flex items-center justify-between gap-2 border-b border-hairline pb-1.5">
                <span className="text-[12.5px] font-[600] uppercase tracking-wider text-ink">
                  Chamber Sensors (SECOM)
                </span>
                <span className="text-[12px] font-medium text-ink-3">
                  Station 2 active
                </span>
              </div>
              <ul className="grid grid-cols-[minmax(0,1fr)] gap-2">
                {sensorCases.map((c) => (
                  <li key={c.case_id}>
                    <CaseRow
                      item={c}
                      disabled={starting}
                      onRun={() => void onStart({ source: "case", case_id: c.case_id })}
                    />
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {waferCases.length ? (
            <div>
              <div className="mb-2 flex items-center justify-between gap-2 border-b border-hairline pb-1.5">
                <span className="text-[12.5px] font-[600] uppercase tracking-wider text-ink">
                  Optical Wafer Maps (WM-811K)
                </span>
                <span className="text-[12px] font-medium text-ink-3">
                  Station 3 active
                </span>
              </div>
              <ul className="grid grid-cols-[minmax(0,1fr)] gap-2">
                {waferCases.map((c) => (
                  <li key={c.case_id}>
                    <CaseRow
                      item={c}
                      disabled={starting}
                      onRun={() => void onStart({ source: "case", case_id: c.case_id })}
                    />
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

function CaseRow({
  item,
  disabled,
  onRun,
}: {
  item: RunCase;
  disabled: boolean;
  onRun: () => void;
}) {
  const counts = [
    item.units ? plural(item.units, "unit") : null,
    item.wafers ? plural(item.wafers, "wafer") : null,
  ].filter(Boolean);

  return (
    <div className="rounded-[14px] border border-hairline bg-surface p-3 transition-colors hover:border-hairline-strong hover:bg-surface-2/40 shadow-2xs">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <p className="text-[14.5px] leading-5 font-[600] text-ink">{item.title}</p>
        <button
          type="button"
          onClick={onRun}
          disabled={disabled}
          aria-label={`Run: ${item.title}`}
          className="press cursor-pointer inline-flex h-7 items-center justify-center rounded-full px-3.5 text-[12.5px] leading-none font-[560] text-ink shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface-2 hover:shadow-[inset_0_0_0_1px_var(--edge)] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Run
        </button>
      </div>
      <p className="mt-1 text-[13.5px] leading-snug text-ink-2">{item.description}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11.5px] leading-4 text-ink-3">
        <span className="font-semibold text-ink">
          {counts.join(" and ")} ({item.datasets.map((d) => DATASET[d] ?? d).join(" & ")})
        </span>
        <span aria-hidden="true">&bull;</span>
        <span className="line-clamp-1">{item.rule}</span>
      </div>
    </div>
  );
}

type StreamTab = "sensors" | "wafers";

/** Browse real units, wafers and lots, tick some, run them. */
function Browsers({ onStart, starting }: { onStart: StartRun; starting: boolean }) {
  const [tab, setTab] = useState<StreamTab>("sensors");
  const [waferSubMode, setWaferSubMode] = useState<"wafers" | "lots">("wafers");
  const [units, setUnits] = useState<number[]>([]);
  const [wafers, setWafers] = useState<string[]>([]);
  const [lot, setLot] = useState<string | null>(null);
  const toggle = <T,>(list: T[], value: T) =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  const hasSensors = units.length > 0;
  const hasWafers = wafers.length > 0 || Boolean(lot);
  const isDualStream = hasSensors && hasWafers;

  const parts = [
    units.length ? plural(units.length, "sensor unit") : null,
    wafers.length ? plural(wafers.length, "wafer map") : null,
    lot ? `lot ${lot}` : null,
  ].filter(Boolean);

  const body: PickRunCreate = { source: "pick", unit_ids: units, wafer_ids: wafers, lot };

  let runButtonLabel = "Tick items above to run";
  if (isDualStream) {
    runButtonLabel = `Run Dual-Stream (${plural(units.length, "unit")} + ${lot ? `lot ${lot}` : plural(wafers.length, "wafer")}) · Stations 2 & 3`;
  } else if (hasSensors) {
    runButtonLabel = `Run ${plural(units.length, "Chamber Unit")} · Tests Station 2`;
  } else if (hasWafers) {
    runButtonLabel = `Run ${lot ? `Lot ${lot}` : plural(wafers.length, "Wafer Map")} · Tests Station 3`;
  }

  return (
    <section aria-labelledby="browse-title" className="min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="browse-title" className="text-[15px] leading-6 font-[620] text-ink">
          Custom Selection (Browse Real Data)
        </h3>
      </div>
      <p className="mt-1 mb-3 text-[13px] leading-5 text-ink-3">
        Select from either stream to run that station, or tick both to test a combined dual-stream pipeline.
      </p>
      <Tabs value={tab} onValueChange={(v) => setTab(v as StreamTab)}>
        <TabsList variant="line" className="h-9 gap-6 border-b border-hairline p-0">
          <TabsTrigger value="sensors" className="cursor-pointer flex-none px-0 text-[14px]">
            Chamber Sensors (SECOM){units.length ? ` (${units.length})` : ""}
          </TabsTrigger>
          <TabsTrigger value="wafers" className="cursor-pointer flex-none px-0 text-[14px]">
            Wafer Maps (WM-811K){wafers.length || lot ? ` (${wafers.length ? plural(wafers.length, "wafer") : "1 lot"})` : ""}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="sensors" className="mt-2.5">
          <div className="mb-2 rounded-[10px] bg-surface-2/60 px-3 py-1.5 text-[12px] text-ink-2">
            <strong className="text-ink">Stream 1: Chamber Sensors</strong> &bull; 590 telemetry channels per unit. Feeds Station 1 &amp; Station 2 (Chamber Monitoring &amp; SPC).
          </div>
          <UnitList chosen={units} onToggle={(id) => setUnits((l) => toggle(l, id))} />
        </TabsContent>

        <TabsContent value="wafers" className="mt-2.5">
          <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2 border-b border-hairline pb-2">
            <span className="text-[12px] text-ink-2">
              <strong className="text-ink">Stream 2: Wafer Maps</strong> &bull; Optical inspection prober data. Feeds Station 1 &amp; Station 3.
            </span>
            <div className="flex items-center gap-1 rounded-lg border border-hairline bg-surface-2 p-0.5">
              <button
                type="button"
                onClick={() => setWaferSubMode("wafers")}
                className={cn(
                  "cursor-pointer rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors",
                  waferSubMode === "wafers"
                    ? "bg-surface text-ink shadow-2xs font-semibold"
                    : "text-ink-2 hover:text-ink",
                )}
              >
                Single Wafers{wafers.length ? ` (${wafers.length})` : ""}
              </button>
              <button
                type="button"
                onClick={() => setWaferSubMode("lots")}
                className={cn(
                  "cursor-pointer rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors",
                  waferSubMode === "lots"
                    ? "bg-surface text-ink shadow-2xs font-semibold"
                    : "text-ink-2 hover:text-ink",
                )}
              >
                Full Lots (25 Wafers){lot ? " (1)" : ""}
              </button>
            </div>
          </div>

          {waferSubMode === "wafers" ? (
            <WaferList chosen={wafers} onToggle={(id) => setWafers((l) => toggle(l, id))} />
          ) : (
            <LotList chosen={lot} onChoose={(name) => setLot((l) => (l === name ? null : name))} />
          )}
        </TabsContent>
      </Tabs>
      <div className="mt-3.5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!parts.length || starting}
          onClick={() => void onStart(body)}
          className="press lift sheen-hover cursor-pointer inline-flex h-10 items-center justify-center rounded-full bg-ink px-5 text-[13.5px] font-[600] text-canvas shadow-[0_1px_2px_rgb(0_0_0/0.12),inset_0_1px_0_rgb(255_255_255/0.12)] hover:bg-ink/92 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {runButtonLabel}
        </button>
        {parts.length ? (
          <button
            type="button"
            onClick={() => {
              setUnits([]);
              setWafers([]);
              setLot(null);
            }}
            className="cursor-pointer text-[13px] text-ink-2 underline-offset-2 hover:text-ink hover:underline"
          >
            Clear selection
          </button>
        ) : null}
      </div>
    </section>
  );
}

function usePaged<T>(
  key: unknown[],
  fetchPage: (
    cursor: string | null,
    signal: AbortSignal,
  ) => Promise<{ items: T[]; next_cursor?: string | null; total: number }>,
) {
  return useInfiniteQuery({
    queryKey: key,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => fetchPage(pageParam, signal),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    staleTime: 10 * 60_000,
  });
}

function PagedList<T>({
  query,
  label,
  render,
}: {
  query: ReturnType<typeof usePaged<T>>;
  label: string;
  render: (item: T) => ReactNode;
}) {
  const scrollRef = useRef<HTMLUListElement>(null);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el || !query.hasNextPage || query.isFetchingNextPage) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 60) {
      void query.fetchNextPage();
    }
  };

  if (query.isPending) return <Placeholder className="mt-2 h-56" />;
  if (query.isError)
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} compact />;
  const items = query.data.pages.flatMap((p) => p.items);
  const total = query.data.pages[0]?.total ?? items.length;
  return (
    <div>
      <ul
        ref={scrollRef}
        onScroll={handleScroll}
        aria-label={label}
        className="mt-1 max-h-[300px] overflow-y-auto overscroll-contain"
      >
        {items.map(render)}
        {query.isFetchingNextPage ? (
          <li className="p-2 text-center text-[12px] text-ink-3">Loading more...</li>
        ) : null}
      </ul>
      <div className="mt-2 flex items-center justify-between gap-3 text-[12px] leading-4 text-ink-3">
        <span className="tnum">{`${formatInt(items.length)} of ${formatInt(total)} loaded`}</span>
      </div>
    </div>
  );
}

function Tick({
  checked,
  onChange,
  label,
  detail,
  name,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  detail: string;
  name?: string;
}) {
  return (
    <li>
      <label
        className={cn(
          "flex cursor-pointer items-start gap-3 border-b border-hairline px-1 py-2 hover:bg-surface-2",
          checked && "bg-signal-wash",
        )}
      >
        <input
          type={name ? "radio" : "checkbox"}
          name={name}
          checked={checked}
          onChange={onChange}
          onClick={name && checked ? onChange : undefined}
          className="mt-1 size-4 shrink-0 accent-[var(--signal)]"
        />
        <span className="min-w-0">
          <span className="tnum block text-[14px] leading-5 text-ink">{label}</span>
          <span className="tnum block text-[12px] leading-4 text-ink-3">{detail}</span>
        </span>
      </label>
    </li>
  );
}

function UnitList({ chosen, onToggle }: { chosen: number[]; onToggle: (id: number) => void }) {
  const api = useApi();
  const query = usePaged<UnitSummary>(["runs", "browse", "units"], (cursor, signal) =>
    unwrap(api.GET("/api/v1/units", { params: { query: { cursor, limit: PAGE } }, signal })),
  );
  return (
    <PagedList
      query={query}
      label="SECOM units"
      render={(u) => (
        <Tick
          key={u.unit_id}
          checked={chosen.includes(u.unit_id)}
          onChange={() => onToggle(u.unit_id)}
          label={`Unit ${u.unit_id}`}
          detail={[
            formatPlantTime(u.timestamp),
            u.final_test ? `final test ${u.final_test}` : "no final test result",
            u.risk_band ? `${(BAND_NAME[u.risk_band] ?? u.risk_band).toLowerCase()} risk` : null,
            u.fdc_alarm === "alarm" ? "beyond the control limits" : null,
          ]
            .filter(Boolean)
            .join(", ")}
        />
      )}
    />
  );
}

function WaferList({ chosen, onToggle }: { chosen: string[]; onToggle: (id: string) => void }) {
  const api = useApi();
  const query = usePaged<WaferSummary>(["runs", "browse", "wafers"], (cursor, signal) =>
    unwrap(api.GET("/api/v1/wafers", { params: { query: { cursor, limit: PAGE } }, signal })),
  );
  return (
    <PagedList
      query={query}
      label="WM-811K wafers"
      render={(w) => (
        <Tick
          key={w.wafer_id}
          checked={chosen.includes(w.wafer_id)}
          onChange={() => onToggle(w.wafer_id)}
          label={w.wafer_id}
          detail={[
            `${formatInt(w.height)} by ${formatInt(w.width)} map`,
            w.label ? `recorded ${patternName(w.label)}` : "no recorded pattern",
          ].join(", ")}
        />
      )}
    />
  );
}

function LotList({ chosen, onChoose }: { chosen: string | null; onChoose: (lot: string) => void }) {
  const api = useApi();
  const query = usePaged<LotSummary>(["runs", "browse", "lots"], (cursor, signal) =>
    unwrap(api.GET("/api/v1/lots", { params: { query: { cursor, limit: PAGE } }, signal })),
  );
  return (
    <PagedList
      query={query}
      label="WM-811K lots"
      render={(l) => (
        <Tick
          key={l.lot}
          name="pick-lot"
          checked={chosen === l.lot}
          onChange={() => onChoose(l.lot)}
          label={l.lot}
          detail={[
            plural(l.wafers, "wafer"),
            l.flagged_labels.length
              ? `${l.flagged_labels.map((x) => patternName(x)).join(" and ")} repeats` +
              (l.min_q_value != null ? ` (q ${formatPValue(l.min_q_value)})` : "")
              : "no pattern repeats",
          ].join(", ")}
        />
      )}
    />
  );
}
