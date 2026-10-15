"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import type {
  LotSummary,
  PickRunCreate,
  RunCase,
  UnitSummary,
  WaferSummary,
} from "@yield-guardian/contracts";
import { type ReactNode, useState } from "react";

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
  return (
    <section aria-labelledby="cases-title" className="min-w-0">
      <h3 id="cases-title" className="text-[15px] leading-6 font-semibold text-ink">
        Real situations
      </h3>
      <p className="mb-3 text-[13px] leading-5 text-ink-3">
        Each is found in the data by the rule shown with it.
      </p>
      {finding ? (
        <p
          role="status"
          className="flex items-start gap-2 rounded-[2px] border border-hairline px-3 py-2.5 text-[14px] leading-5 text-ink-2"
        >
          <span
            aria-hidden="true"
            className="mt-1.5 size-1.5 shrink-0 rounded-full bg-safelight-lamp"
          />
          Finding real cases in the data. The service looks for them each time it starts, which
          takes up to half a minute; the list appears here when it is ready.
        </p>
      ) : cases.isPending ? (
        <Placeholder className="h-40" />
      ) : cases.isError ? (
        <ErrorState error={cases.error} onRetry={() => void cases.refetch()} compact />
      ) : (
        <ul className="grid grid-cols-[minmax(0,1fr)] gap-2">
          {cases.data.items.map((c) => (
            <li key={c.case_id}>
              <CaseRow
                item={c}
                disabled={starting}
                onRun={() => void onStart({ source: "case", case_id: c.case_id })}
              />
            </li>
          ))}
        </ul>
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
    <div className="rounded-[2px] border border-hairline px-3 py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-[15px] leading-6 font-medium text-ink">{item.title}</p>
        <button
          type="button"
          onClick={onRun}
          disabled={disabled}
          aria-label={`Run: ${item.title}`}
          className="rounded-[4px] border border-hairline-strong px-2.5 py-0.5 text-[13px] leading-5 text-ink hover:bg-die-2 disabled:opacity-50"
        >
          Run
        </button>
      </div>
      <p className="text-[14px] leading-5 text-ink-2">{item.description}</p>
      <p className="mt-1 text-[12px] leading-4 text-ink-3">
        {counts.join(" and ")} from {item.datasets.map((d) => DATASET[d] ?? d).join(" and ")}.{" "}
        {item.rule}
      </p>
    </div>
  );
}

type Tab = "units" | "wafers" | "lots";

/** Browse real units, wafers and lots, tick some, run them. */
function Browsers({ onStart, starting }: { onStart: StartRun; starting: boolean }) {
  const [tab, setTab] = useState<Tab>("units");
  const [units, setUnits] = useState<number[]>([]);
  const [wafers, setWafers] = useState<string[]>([]);
  const [lot, setLot] = useState<string | null>(null);
  const toggle = <T,>(list: T[], value: T) =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  const parts = [
    units.length ? plural(units.length, "unit") : null,
    wafers.length ? plural(wafers.length, "wafer") : null,
    lot ? `lot ${lot}` : null,
  ].filter(Boolean);
  const body: PickRunCreate = { source: "pick", unit_ids: units, wafer_ids: wafers, lot };

  return (
    <section aria-labelledby="browse-title" className="min-w-0">
      <h3 id="browse-title" className="text-[15px] leading-6 font-semibold text-ink">
        Choose real items
      </h3>
      <p className="mb-3 text-[13px] leading-5 text-ink-3">
        SECOM units and WM-811K wafers and lots as recorded. Tick any mix and run them together.
      </p>
      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
        <TabsList variant="line" className="h-9 gap-4 border-b border-hairline p-0">
          <TabsTrigger value="units" className="flex-none px-0 text-[14px]">
            Units{units.length ? ` (${units.length})` : ""}
          </TabsTrigger>
          <TabsTrigger value="wafers" className="flex-none px-0 text-[14px]">
            Wafers{wafers.length ? ` (${wafers.length})` : ""}
          </TabsTrigger>
          <TabsTrigger value="lots" className="flex-none px-0 text-[14px]">
            Lots{lot ? " (1)" : ""}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="units">
          <UnitList chosen={units} onToggle={(id) => setUnits((l) => toggle(l, id))} />
        </TabsContent>
        <TabsContent value="wafers">
          <WaferList chosen={wafers} onToggle={(id) => setWafers((l) => toggle(l, id))} />
        </TabsContent>
        <TabsContent value="lots">
          <LotList chosen={lot} onChoose={(name) => setLot((l) => (l === name ? null : name))} />
        </TabsContent>
      </Tabs>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!parts.length || starting}
          onClick={() => void onStart(body)}
          className="inline-flex h-10 items-center rounded-[4px] bg-ink px-4 text-[14px] font-semibold text-room hover:bg-ink/90 disabled:opacity-50"
        >
          {parts.length ? `Run ${parts.join(", ")}` : "Tick items to run them"}
        </button>
        {parts.length ? (
          <button
            type="button"
            onClick={() => {
              setUnits([]);
              setWafers([]);
              setLot(null);
            }}
            className="text-[13px] text-ink-2 underline-offset-2 hover:text-ink hover:underline"
          >
            Clear the choice
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
  if (query.isPending) return <Placeholder className="mt-2 h-56" />;
  if (query.isError)
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} compact />;
  const items = query.data.pages.flatMap((p) => p.items);
  const total = query.data.pages[0]?.total ?? items.length;
  return (
    <div>
      <ul aria-label={label} className="mt-1 max-h-[300px] overflow-y-auto overscroll-contain">
        {items.map(render)}
      </ul>
      <div className="mt-2 flex items-center justify-between gap-3 text-[12px] leading-4 text-ink-3">
        <span className="tnum">{`${formatInt(items.length)} of ${formatInt(total)} shown`}</span>
        {query.hasNextPage ? (
          <button
            type="button"
            onClick={() => void query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
            className="rounded-[4px] border border-hairline-strong px-2 py-0.5 text-[13px] text-ink hover:bg-die-2"
          >
            {query.isFetchingNextPage ? "Loading" : "Show more"}
          </button>
        ) : null}
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
          "flex cursor-pointer items-start gap-3 border-b border-hairline px-1 py-2 hover:bg-die-2",
          checked && "bg-safelight-wash",
        )}
      >
        <input
          type={name ? "radio" : "checkbox"}
          name={name}
          checked={checked}
          onChange={onChange}
          onClick={name && checked ? onChange : undefined}
          className="mt-1 size-4 shrink-0 accent-[var(--safelight)]"
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
