"use client";

import { useQuery } from "@tanstack/react-query";
import type { MeasuredResults, MethodsOverview } from "@yield-guardian/contracts";
import { type ReactNode, useState } from "react";

import { EstimateText } from "@/components/charts/interval";
import { Markdown } from "@/components/markdown";
import { PageFrame, PageHeader, Panel } from "@/components/page";
import { EmptyState, Placeholder, QueryView } from "@/components/states";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { formatCompact, formatDateTime, formatInt } from "@/lib/format";

import { Limitations, SecomMethods } from "./secom-methods";
import { WaferMethods } from "./wafer-methods";

const SECTIONS = [
  { id: "results", label: "Measured results" },
  { id: "secom", label: "SECOM: control charts and failure risk" },
  { id: "wafermap", label: "Wafer maps" },
  { id: "provenance", label: "Data and provenance" },
] as const;

export function MethodsView() {
  const api = useApi();
  const results = useQuery(q.results(api));
  const overview = useQuery(q.methods(api));
  return (
    <PageFrame>
      <PageHeader
        title="Methods"
        description="Every number the product reports, with its confidence interval, the data it was measured on and where it comes from. Findings are associations in historical data, not causes."
      />
      <nav aria-label="On this page" className="mb-6 flex flex-wrap gap-x-5 gap-y-2 border-y border-hairline py-2.5 text-[13px]">
        {SECTIONS.map((s) => (
          <a key={s.id} href={`#${s.id}`} className="text-ink-2 underline decoration-hairline-strong underline-offset-4 hover:text-ink">
            {s.label}
          </a>
        ))}
      </nav>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-12">
        <Section id="results" title="Measured results" lede="The headline numbers. A row reads “Not measured yet” until it has been measured on held-out data.">
          <Panel bodyClassName="px-0 sm:px-0 pt-0">
            <QueryView query={results} loading={<Placeholder className="mx-4 h-48 sm:mx-5" label="Loading results" />}>
              {(r) => <ResultsTable data={r} />}
            </QueryView>
          </Panel>
        </Section>
        <Section
          id="secom"
          title="SECOM: control charts and failure risk"
          lede="The line screen leads with multivariate control charts; the failure-risk score beside them is experimental. Here is how both were measured."
        >
          <SecomMethods />
        </Section>
        <Section id="wafermap" title="Wafer maps" lede="The pattern classifier, the unknown-pattern check and similar-wafer retrieval on WM-811K.">
          <WaferMethods />
        </Section>
        <Section id="provenance" title="Data and provenance" lede="The datasets with their checksums, the artifact bundles the API loaded, and the model cards.">
          <QueryView query={overview} loading={<Placeholder className="h-64" label="Loading provenance" />}>
            {(o) => <Provenance data={o} />}
          </QueryView>
        </Section>
      </div>
    </PageFrame>
  );
}

function Section({ id, title, lede, children }: { id: string; title: string; lede: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-20">
      <h2 id={`${id}-title`} className="text-[22px] leading-8 font-semibold tracking-[-0.01em] text-ink">
        {title}
      </h2>
      <p className="mt-1 mb-4 max-w-[80ch] text-[15px] leading-6 text-ink-2">{lede}</p>
      {children}
    </section>
  );
}

function ResultsTable({ data }: { data: MeasuredResults }) {
  if (data.results.length === 0) return <EmptyState className="mx-4 mt-4 sm:mx-5" title="Not measured yet">No result has been recorded.</EmptyState>;
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-[14px] leading-5">
          <caption className="sr-only">Measured results</caption>
          <thead>
            <tr className="border-b border-hairline text-[12px] text-ink-3">
              <th scope="col" className="px-4 py-2 font-normal sm:px-5">Quantity</th>
              <th scope="col" className="px-3 py-2 font-normal">Value</th>
              <th scope="col" className="px-4 py-2 font-normal sm:px-5">Measured on</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((r) => (
              <tr key={r.id} className="border-b border-hairline last:border-b-0 align-top">
                <th scope="row" className="px-4 py-2.5 font-normal text-ink sm:px-5">{r.label}</th>
                <td className="px-3 py-2.5 text-[13px]">
                  {r.estimate ? <EstimateText estimate={r.estimate} format={r.format} showN /> : <span className="text-ink-3">Not measured yet</span>}
                </td>
                <td className="px-4 py-2.5 text-[13px] text-ink-2 sm:px-5">
                  {r.data}
                  <span className="tnum block text-[12px] break-all text-ink-3">{r.source}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.updated_at ? (
        <p className="mx-4 mt-3 text-[12px] text-ink-3 sm:mx-5">
          Updated <time dateTime={data.updated_at} suppressHydrationWarning>{formatDateTime(data.updated_at)}</time>.
        </p>
      ) : null}
    </>
  );
}

function Provenance({ data }: { data: MethodsOverview }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-street">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-street xl:grid-cols-2">
        {data.datasets.map((d) => (
          <Panel key={d.name} title={d.name} description={d.description}>
            <dl className="grid grid-cols-[minmax(0,1fr)] gap-2 text-[13px] leading-5">
              <div>
                <dt className="text-ink-3">Citation</dt>
                <dd className="text-ink">{d.citation}</dd>
              </div>
              <div>
                <dt className="text-ink-3">Source</dt>
                <dd>
                  <a href={d.source_url} target="_blank" rel="noopener noreferrer" className="break-all text-ink underline decoration-hairline-strong underline-offset-4">
                    {d.source_url}
                  </a>
                </dd>
              </div>
              <div>
                <dt className="text-ink-3">Licence</dt>
                <dd className="text-ink">{d.licence}</dd>
              </div>
              <div>
                <dt className="text-ink-3">Retrieved</dt>
                <dd className="tnum text-ink">
                  <time dateTime={d.retrieved_at} suppressHydrationWarning>{formatDateTime(d.retrieved_at)}</time>
                </dd>
              </div>
            </dl>
            <h3 className="mt-4 text-[12px] text-ink-3">Files (SHA-256)</h3>
            <ul className="mt-1 grid grid-cols-[minmax(0,1fr)] gap-1.5">
              {d.files.map((f) => (
                <li key={f.path} className="tnum text-[12px] leading-4">
                  <span className="text-ink">{f.path}</span> <span className="text-ink-3">{f.bytes ? `${formatCompact(f.bytes)} bytes` : ""}</span>
                  <code className="block break-all text-ink-3">{f.sha256}</code>
                </li>
              ))}
            </ul>
          </Panel>
        ))}
      </div>
      <Panel title="Artifact bundles" description="Every file is checked against the SHA-256 in its MANIFEST.json when the API loads it." bodyClassName="px-0 sm:px-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse text-left text-[13px] leading-5">
            <caption className="sr-only">Artifact bundles</caption>
            <thead>
              <tr className="border-y border-hairline text-[12px] text-ink-3">
                <th scope="col" className="px-4 py-2 font-normal sm:px-5">Bundle</th>
                <th scope="col" className="px-3 py-2 font-normal">Built</th>
                <th scope="col" className="px-3 py-2 font-normal">Commit</th>
                <th scope="col" className="px-3 py-2 text-right font-normal">Files</th>
                <th scope="col" className="px-4 py-2 font-normal sm:px-5">Checksums</th>
              </tr>
            </thead>
            <tbody>
              {data.bundles.map((b) => (
                <tr key={b.bundle.name} className="border-b border-hairline last:border-b-0">
                  <th scope="row" className="tnum px-4 py-2 font-normal text-ink sm:px-5">
                    {b.bundle.name} {b.bundle.version}
                  </th>
                  <td className="tnum px-3 py-2 text-ink-2">
                    <time dateTime={b.bundle.created_at} suppressHydrationWarning>{formatDateTime(b.bundle.created_at)}</time>
                  </td>
                  <td className="tnum px-3 py-2 text-ink-2">{b.bundle.git_commit.slice(0, 10)}</td>
                  <td className="tnum px-3 py-2 text-right text-ink-2">{formatInt(b.files)}</td>
                  <td className={b.verified ? "px-4 py-2 text-ink sm:px-5" : "px-4 py-2 text-fail sm:px-5"}>{b.verified ? "Verified" : "Mismatch"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      {data.model_cards.length ? <ModelCards cards={data.model_cards} /> : null}
      <Limitations items={data.limitations} title="Limitations of the product" />
    </div>
  );
}

function ModelCards({ cards }: { cards: MethodsOverview["model_cards"] }) {
  const api = useApi();
  const [name, setName] = useState(cards[0]!.name);
  const card = useQuery(q.modelCard(api, name));
  return (
    <Panel
      title="Model cards"
      description="Written by the training pipeline with the bundle."
      actions={
        cards.length > 1 ? (
          <ToggleGroup type="single" variant="outline" size="sm" value={name} onValueChange={(v) => v && setName(v as typeof name)} aria-label="Model card">
            {cards.map((c) => (
              <ToggleGroupItem key={c.name} value={c.name} className="h-auto min-h-8 shrink px-2.5 py-1 text-left whitespace-normal">
                {c.title}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        ) : null
      }
    >
      <QueryView query={card} loading={<Placeholder className="h-64" label="Loading the model card" />}>
        {(c) => <Markdown className="max-w-[80ch]">{c.markdown}</Markdown>}
      </QueryView>
    </Panel>
  );
}
