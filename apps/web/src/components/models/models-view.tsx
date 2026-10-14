"use client";

import { useQuery } from "@tanstack/react-query";
import type { CatalogModel, EvaluationResult, Evaluations, RoleAssignment, Usage, UsageReport } from "@yield-guardian/contracts";
import { Fragment, useState } from "react";

import { EstimateText, IntervalMark } from "@/components/charts/interval";
import { PageFrame, PageHeader, Panel, Reading } from "@/components/page";
import { EmptyState, Placeholder, QueryView } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { useSession } from "@/lib/api/session";
import { formatCompact, formatDateTime, formatDuration, formatInt, formatNumber, formatPercent, formatReported } from "@/lib/format";
import { ROLE_JOBS, ROLE_NAMES } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { RoleDialog } from "./role-dialog";
import { ScrollRegion } from "@/components/scroll-region";

export function ModelsView() {
  const api = useApi();
  const roles = useQuery(q.llmRoles(api));
  const catalog = useQuery(q.llmCatalog(api));
  const evaluations = useQuery(q.llmEvaluations(api));
  const usage = useQuery(q.llmUsage(api));

  return (
    <PageFrame>
      <PageHeader
        title="Models"
        description="Which model does each job in investigations and chat, how the candidates were evaluated, and what today's calls used. The models run on AMD Token Factory."
      />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-street">
        <Panel title="Roles" description="One model per job, with the fallbacks tried when it is unavailable." bodyClassName="px-0 sm:px-0">
          <QueryView query={roles} loading={<Placeholder className="mx-4 h-56 sm:mx-5" label="Loading roles" />}>
            {(r) => <RolesTable roles={r} catalog={catalog.data ?? []} evaluations={evaluations.data} />}
          </QueryView>
        </Panel>
        <div className="grid grid-cols-[minmax(0,1fr)] gap-street xl:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
          <Panel title="Evaluations" description="Each candidate on the same task set for its role." bodyClassName="px-0 sm:px-0">
            <QueryView query={evaluations} loading={<Placeholder className="mx-4 h-56 sm:mx-5" label="Loading evaluations" />}>
              {(e) => <EvaluationsTable data={e} roles={roles.data ?? []} />}
            </QueryView>
          </Panel>
          <Panel title="Usage today" description="For information only: the product never limits calls.">
            <QueryView query={usage} loading={<Placeholder className="h-56" label="Loading usage" />}>
              {(u) => <UsagePanel report={u} />}
            </QueryView>
          </Panel>
        </div>
        <Panel title="Catalog" description="Models the product can assign, with the capability profile requests are built from." bodyClassName="px-0 sm:px-0">
          <QueryView query={catalog} loading={<Placeholder className="mx-4 h-56 sm:mx-5" label="Loading the catalog" />}>
            {(c) => <CatalogTable models={c} roles={roles.data ?? []} />}
          </QueryView>
        </Panel>
      </div>
    </PageFrame>
  );
}

function RolesTable({ roles, catalog, evaluations }: { roles: RoleAssignment[]; catalog: CatalogModel[]; evaluations?: Evaluations }) {
  const { isAdmin } = useSession();
  const [editing, setEditing] = useState<RoleAssignment["role"] | null>(null);
  const current = roles.find((r) => r.role === editing);
  if (roles.length === 0) return <EmptyState className="mx-4 sm:mx-5" title="No roles">The API has no role assignments.</EmptyState>;
  return (
    <>
      <ScrollRegion label="Role assignments">
        <table className="w-full min-w-[760px] border-collapse text-left text-[14px] leading-5">
          <caption className="sr-only">Role assignments</caption>
          <thead>
            <tr className="border-y border-hairline text-[12px] text-ink-3">
              <th scope="col" className="px-4 py-2 font-normal sm:px-5">Role</th>
              <th scope="col" className="px-2 py-2 font-normal">Model</th>
              <th scope="col" className="px-2 py-2 font-normal">Effort</th>
              <th scope="col" className="px-2 py-2 font-normal">Fallbacks</th>
              <th scope="col" className="px-2 py-2 font-normal">Evaluated success</th>
              <th scope="col" className="px-4 py-2 text-right font-normal sm:px-5">{isAdmin ? "" : "Changed"}</th>
            </tr>
          </thead>
          <tbody>
            {roles.map((r) => {
              const evaluation = evaluations?.results.find((e) => e.role === r.role && e.model_id === r.model_id);
              const model = catalog.find((m) => m.model_id === r.model_id);
              return (
                <tr key={r.role} className="border-b border-hairline last:border-b-0">
                  <th scope="row" className="px-4 py-2.5 align-top font-normal sm:px-5">
                    <span className="font-medium text-ink">{ROLE_NAMES[r.role] ?? r.role}</span>
                    <span className="block text-[12px] text-ink-3">{ROLE_JOBS[r.role]}</span>
                  </th>
                  <td className="tnum px-2 py-2.5 align-top text-ink">
                    {r.model_id}
                    {model && !model.available ? <span className="block text-[12px] text-fail">Not in the live catalog</span> : null}
                  </td>
                  <td className="px-2 py-2.5 align-top text-ink-2">{r.reasoning_effort ?? <span className="text-ink-3">default</span>}</td>
                  <td className="tnum px-2 py-2.5 align-top text-[13px] text-ink-2">{r.fallbacks.length ? r.fallbacks.join(", ") : <span className="text-ink-3">None</span>}</td>
                  <td className="px-2 py-2.5 align-top text-[13px]">
                    {evaluation ? <EstimateText estimate={evaluation.success_rate} format="percent" /> : <span className="text-ink-3">Not evaluated</span>}
                  </td>
                  <td className="px-4 py-2.5 text-right align-top text-[12px] text-ink-3 sm:px-5">
                    {isAdmin ? (
                      <Button size="sm" variant="outline" onClick={() => setEditing(r.role)} disabled={catalog.length === 0}>
                        Change
                      </Button>
                    ) : r.updated_at ? (
                      <time dateTime={r.updated_at} suppressHydrationWarning>
                        {formatDateTime(r.updated_at)}
                        {r.updated_by ? ` by ${r.updated_by}` : ""}
                      </time>
                    ) : (
                      "Default"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </ScrollRegion>
      {!isAdmin ? <p className="mx-4 mt-3 text-[12px] leading-4 text-ink-3 sm:mx-5">Only an admin can change a role.</p> : null}
      {current ? <RoleDialog key={current.role} assignment={current} catalog={catalog} open onOpenChange={(o) => !o && setEditing(null)} /> : null}
    </>
  );
}

function EvaluationsTable({ data, roles }: { data: Evaluations; roles: RoleAssignment[] }) {
  if (data.results.length === 0) {
    return (
      <EmptyState className="mx-4 sm:mx-5" title="Not measured yet">
        No evaluation has been run. {data.note}
      </EmptyState>
    );
  }
  const groups = new Map<string, EvaluationResult[]>();
  for (const r of data.results) {
    const key = `${r.role}\u0000${r.task_set}`;
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  return (
    <>
      <ScrollRegion label="Model evaluations by role">
        <table className="w-full min-w-[620px] border-collapse text-left text-[13px] leading-5">
          <caption className="sr-only">Model evaluations by role</caption>
          <thead>
            <tr className="border-y border-hairline text-[12px] text-ink-3">
              <th scope="col" className="px-4 py-2 font-normal sm:px-5">Model</th>
              <th scope="col" className="w-[26%] px-2 py-2 font-normal">Success, 0 to 100%</th>
              <th scope="col" className="px-2 py-2 text-right font-normal">Violations</th>
              <th scope="col" className="px-2 py-2 text-right font-normal">Median latency</th>
              <th scope="col" className="px-4 py-2 text-right font-normal sm:px-5">Points</th>
            </tr>
          </thead>
          <tbody>
            {[...groups.values()].map((rows) => {
              const head = rows[0]!;
              const assigned = roles.find((r) => r.role === head.role)?.model_id;
              return (
                <Fragment key={`${head.role}-${head.task_set}`}>
                  <tr className="border-b border-hairline bg-die-2">
                    <th scope="colgroup" colSpan={5} className="px-4 py-1.5 text-[12px] font-normal text-ink-2 sm:px-5">
                      <span className="font-medium text-ink">{ROLE_NAMES[head.role] ?? head.role}</span>, task set <span className="tnum">{head.task_set}</span> ({formatInt(head.tasks)} tasks)
                    </th>
                  </tr>
                  {rows.map((r) => (
                    <tr key={r.model_id} className="border-b border-hairline">
                      <th scope="row" className="tnum px-4 py-2 align-top font-normal sm:px-5">
                        <span className={cn(r.model_id === assigned ? "font-medium text-ink" : "text-ink-2")}>{r.model_id}</span>
                        {r.model_id === assigned ? <span className="block text-[12px] text-ink-3">Assigned</span> : null}
                      </th>
                      <td className="px-2 py-2 align-top">
                        <IntervalMark estimate={r.success_rate} />
                        <span className="mt-0.5 block text-[12px]">
                          <EstimateText estimate={r.success_rate} format="percent" />
                        </span>
                      </td>
                      <td className="tnum px-2 py-2 text-right align-top text-ink-2">{formatInt(r.violations)}</td>
                      <td className="tnum px-2 py-2 text-right align-top text-ink-2">{r.latency_ms_p50 == null ? "not reported" : formatDuration(r.latency_ms_p50)}</td>
                      <td className="tnum px-4 py-2 text-right align-top text-ink-2 sm:px-5">{formatNumber(r.points, 4)}</td>
                    </tr>
                  ))}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </ScrollRegion>
      <p className="mx-4 mt-3 text-[12px] leading-4 text-ink-3 sm:mx-5">
        {data.results[0]?.success_rate.method ? `Intervals: ${data.results[0].success_rate.method}. ` : ""}
        {data.note}
      </p>
    </>
  );
}

function usageLine(u: Usage) {
  return `${formatCompact(u.tokens_in)} in, ${formatCompact(u.tokens_out)} out${u.tokens_reasoning ? `, ${formatCompact(u.tokens_reasoning)} reasoning` : ""}`;
}

function UsagePanel({ report }: { report: UsageReport }) {
  const t = report.total;
  const quota = report.quota;
  const share = quota.limit && quota.used != null ? quota.used / quota.limit : null;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      <p className="text-[13px] leading-5 text-ink-3">
        Since <time dateTime={report.since} suppressHydrationWarning>{formatDateTime(report.since)}</time>.
      </p>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        <Reading label="Model calls" value={formatInt(t.requests)} detail={t.cache_hits ? `${formatInt(t.cache_hits)} from cache` : undefined} />
        <Reading label="Tokens in" value={formatCompact(t.tokens_in)} />
        <Reading label="Tokens out" value={formatCompact(t.tokens_out)} detail={t.tokens_reasoning ? `${formatCompact(t.tokens_reasoning)} reasoning` : undefined} />
        <Reading label="Points" value={formatNumber(t.points, 4)} />
      </dl>
      {t.requests_without_usage > 0 ? (
        <p className="rounded-sm bg-die-2 px-3 py-2 text-[13px] leading-5 text-ink-2">
          {formatInt(t.requests_without_usage)} {t.requests_without_usage === 1 ? "call" : "calls"} did not report usage, so the sums leave {t.requests_without_usage === 1 ? "it" : "them"} out.
        </p>
      ) : null}

      <div>
        <h3 className="text-[13px] leading-5 font-medium text-ink">Quota</h3>
        {share != null ? (
          <div className="mt-1.5">
            <div className="h-2 rounded-[2px] bg-hairline" aria-hidden="true">
              <div className="h-2 rounded-[2px] bg-ink-2" style={{ width: `${Math.min(100, share * 100)}%` }} />
            </div>
            <p className="tnum mt-1 text-[12px] leading-4 text-ink-3">
              {formatNumber(quota.used, 4)} of {formatNumber(quota.limit, 4)} points used ({formatPercent(share)})
              {quota.resets_at ? (
                <>
                  , resets <time dateTime={quota.resets_at} suppressHydrationWarning>{formatDateTime(quota.resets_at)}</time>
                </>
              ) : null}
              {quota.rpm_limit != null ? `. ${formatInt(quota.rpm_limit)} requests per minute.` : "."}
            </p>
          </div>
        ) : (
          <p className="mt-1 text-[13px] text-ink-3">The endpoint has not reported a quota.</p>
        )}
      </div>

      <div>
        <h3 className="text-[13px] leading-5 font-medium text-ink">Chat answers</h3>
        <p className="tnum mt-0.5 text-[13px] leading-5 text-ink-2">
          {formatInt(report.deterministic_answers)} answered by rules without a model, {formatInt(report.model_answers)} by a model.
        </p>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 sm:grid-cols-2">
        <UsageList title="By role" rows={report.by_role.map((r) => ({ key: r.role, label: ROLE_NAMES[r.role] ?? r.role, usage: r.usage }))} />
        <UsageList title="By model" rows={report.by_model.map((r) => ({ key: r.model_id, label: r.model_id, usage: r.usage }))} />
      </div>

      <div>
        <h3 className="text-[13px] leading-5 font-medium text-ink">Recent calls</h3>
        {report.recent.length === 0 ? (
          <p className="mt-1 text-[13px] text-ink-3">No model call today.</p>
        ) : (
          <ol className="mt-1 divide-y divide-hairline border-y border-hairline">
            {report.recent.slice(0, 10).map((c, i) => (
              <li key={i} className="tnum grid grid-cols-[4.5rem_minmax(0,1fr)_auto] gap-x-3 py-1.5 text-[12px] leading-4">
                <time dateTime={c.at} suppressHydrationWarning className="text-ink-3">
                  {formatDateTime(c.at).slice(11)}
                </time>
                <span className="min-w-0">
                  <span className="text-ink">{ROLE_NAMES[c.role] ?? c.role}</span> <span className="text-ink-2">{c.model_id}</span>
                  <span className="block text-ink-3">
                    {c.status === "error" || c.status === "refused" ? (
                      <span className="text-fail">{c.status === "error" ? "Error" : "Refused"}{c.error ? `: ${c.error}` : ""}</span>
                    ) : c.status === "cached" ? (
                      "From cache"
                    ) : c.tokens_in == null && c.tokens_out == null ? (
                      "tokens not reported"
                    ) : (
                      `${formatReported(c.tokens_in)} in, ${formatReported(c.tokens_out)} out`
                    )}
                  </span>
                </span>
                <span className="text-right text-ink-2">
                  {c.points == null ? <span className="text-ink-3">not reported</span> : formatNumber(c.points, 5)}
                  <span className="block text-ink-3">{formatDuration(c.latency_ms)}</span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

function UsageList({ title, rows }: { title: string; rows: { key: string; label: string; usage: Usage }[] }) {
  const max = Math.max(1e-9, ...rows.map((r) => r.usage.points));
  return (
    <div className="min-w-0">
      <h3 className="text-[13px] leading-5 font-medium text-ink">{title}</h3>
      {rows.length === 0 ? (
        <p className="mt-1 text-[13px] text-ink-3">None today.</p>
      ) : (
        <ul className="mt-1 grid grid-cols-[minmax(0,1fr)] gap-2">
          {rows.map((r) => (
            <li key={r.key} className="min-w-0 text-[12px] leading-4">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-ink">{r.label}</span>
                <span className="tnum shrink-0 text-ink-2">{formatNumber(r.usage.points, 4)}</span>
              </div>
              <div className="mt-0.5 h-1.5 rounded-[2px] bg-hairline" aria-hidden="true">
                <div className="h-1.5 rounded-[2px] bg-ink-3" style={{ width: `${(r.usage.points / max) * 100}%` }} />
              </div>
              <span className="tnum text-ink-3">
                {formatInt(r.usage.requests)} {r.usage.requests === 1 ? "call" : "calls"}, {usageLine(r.usage)}
                {r.usage.requests_without_usage > 0 ? `, ${formatInt(r.usage.requests_without_usage)} without usage` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CatalogTable({ models, roles }: { models: CatalogModel[]; roles: RoleAssignment[] }) {
  if (models.length === 0) return <EmptyState className="mx-4 sm:mx-5" title="Empty catalog">The API reports no models.</EmptyState>;
  return (
    <ScrollRegion label="Model catalog">
      <table className="w-full min-w-[880px] border-collapse text-left text-[13px] leading-5">
        <caption className="sr-only">Model catalog</caption>
        <thead>
          <tr className="border-y border-hairline text-[12px] text-ink-3">
            <th scope="col" className="px-4 py-2 font-normal sm:px-5">Model</th>
            <th scope="col" className="px-2 py-2 font-normal">Kind</th>
            <th scope="col" className="px-2 py-2 text-right font-normal">Context</th>
            <th scope="col" className="px-2 py-2 font-normal">Inputs</th>
            <th scope="col" className="px-2 py-2 font-normal">Reasoning</th>
            <th scope="col" className="px-2 py-2 font-normal">JSON schema</th>
            <th scope="col" className="px-2 py-2 font-normal">Tools</th>
            <th scope="col" className="px-2 py-2 text-right font-normal">Price in / out</th>
            <th scope="col" className="px-4 py-2 font-normal sm:px-5">Used as</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m) => {
            const usedAs = roles.filter((r) => r.model_id === m.model_id).map((r) => ROLE_NAMES[r.role] ?? r.role);
            return (
              <tr key={m.model_id} className={cn("border-b border-hairline last:border-b-0", !m.available && "text-ink-3")}>
                <th scope="row" className="tnum px-4 py-2 align-top font-normal sm:px-5">
                  <span className={m.available ? "text-ink" : undefined}>{m.model_id}</span>
                  {!m.available ? <span className="block text-[12px]">Not in the live catalog</span> : null}
                  {m.profile === "catalog_only" ? <span className="block text-[12px] text-ink-3">Profile from the catalog only</span> : null}
                </th>
                <td className="px-2 py-2 align-top uppercase text-ink-2">{m.kind}</td>
                <td className="tnum px-2 py-2 text-right align-top text-ink-2">{m.context_length == null ? "–" : formatCompact(m.context_length)}</td>
                <td className="px-2 py-2 align-top text-ink-2">{m.inputs.join(", ")}</td>
                <td className="px-2 py-2 align-top text-ink-2">
                  {m.reasoning_efforts.length ? m.reasoning_efforts.join(", ") : <span className="text-ink-3">–</span>}
                  {m.thinks_by_default ? <span className="block text-[12px] text-ink-3">thinks by default</span> : null}
                </td>
                <td className="px-2 py-2 align-top text-ink-2">{m.json_schema ? "Strict" : "No"}</td>
                <td className="px-2 py-2 align-top text-ink-2">{m.tools ? "Yes" : "No"}</td>
                <td className="tnum px-2 py-2 text-right align-top text-ink-2">
                  {m.pricing ? `${formatNumber(m.pricing.input, 3)} / ${formatNumber(m.pricing.output, 3)}` : <span className="text-ink-3">not listed</span>}
                </td>
                <td className="px-4 py-2 align-top text-ink-2 sm:px-5">{usedAs.length ? usedAs.join(", ") : <span className="text-ink-3">–</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </ScrollRegion>
  );
}
