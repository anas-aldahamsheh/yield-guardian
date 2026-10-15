"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Placeholder, QueryView } from "@/components/states";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";

/** Where the data and the models come from, with checksums and citations. */
export function Provenance() {
  const api = useApi();
  const methods = useQuery(q.methods(api));

  return (
    <section aria-labelledby="provenance-title" className="mx-auto max-w-[1600px] px-gutter py-16">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-x-12 gap-y-6 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)]">
        <div>
          <h2 id="provenance-title" className="text-h2 font-semibold tracking-[-0.01em]">
            Where the data comes from
          </h2>
          <p className="mt-3 max-w-[46ch] text-[15px] leading-6 text-ink-2">
            Two public datasets, downloaded with checksums. Trained models ship as versioned bundles
            whose files are verified when the API starts.
          </p>
          <p className="mt-4">
            <Link
              href="/methods"
              className="text-[15px] text-ink underline decoration-hairline-strong hover:decoration-ink"
            >
              Methods, metrics and limitations
            </Link>
          </p>
        </div>
        <QueryView
          query={methods}
          loading={<Placeholder className="h-64" label="Loading data sources" />}
        >
          {(data) => (
            <div className="grid grid-cols-[minmax(0,1fr)] gap-street md:grid-cols-2">
              {data.datasets.map((d) => (
                <article key={d.name} className="panel p-5">
                  <h3 className="text-h4 font-semibold">{d.name}</h3>
                  <p className="mt-2 text-[15px] leading-6 text-ink-2">{d.description}</p>
                  <p className="mt-3 text-[13px] leading-5 text-ink-3">{d.citation}</p>
                  <dl className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-1 text-[13px] leading-5">
                    <div className="flex gap-2">
                      <dt className="text-ink-3">Licence</dt>
                      <dd className="text-ink-2">{d.licence}</dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="text-ink-3">Retrieved</dt>
                      <dd className="tnum text-ink-2">
                        <LocalDateTime iso={d.retrieved_at} />
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="text-ink-3">Files</dt>
                      <dd className="text-ink-2">{d.files.length} with SHA-256 checksums</dd>
                    </div>
                  </dl>
                  <a
                    href={d.source_url}
                    className="mt-4 inline-block text-[13px] text-ink underline decoration-hairline-strong hover:decoration-ink"
                    rel="noreferrer"
                  >
                    Source
                  </a>
                </article>
              ))}
            </div>
          )}
        </QueryView>
      </div>
    </section>
  );
}
