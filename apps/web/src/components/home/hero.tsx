"use client";

import { decodeWaferCells, type WaferHero } from "@yield-guardian/contracts";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo } from "react";

import { Placeholder, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { HeroWafer } from "@/components/wafer/hero-wafer";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { useSession, useStartGuestSession } from "@/lib/api/session";
import { formatInt, formatPValue, formatProbability } from "@/lib/format";
import { patternName } from "@/lib/labels";
import { FILM, layoutDies } from "@/lib/wafer/geometry";

export function Hero() {
  const api = useApi();
  const hero = useQuery(q.heroWafer(api));
  const { canAct } = useSession();
  const guest = useStartGuestSession();

  return (
    <section data-theme="dark" className="bg-room text-ink" aria-labelledby="hero-title">
      <div className="mx-auto grid max-w-[1600px] gap-x-12 gap-y-10 px-gutter pt-12 pb-14 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:pt-16 lg:pb-16">
        <div className="flex flex-col justify-center lg:pb-16">
          <h1
            id="hero-title"
            className="max-w-[14ch] text-[40px] leading-[44px] font-semibold tracking-[-0.025em] sm:text-display sm:leading-[54px] xl:text-display-lg xl:leading-[72px]"
          >
            Catch failing units before final test does.
          </h1>
          <p className="mt-6 max-w-[54ch] text-[17px] leading-7 text-ink-2">
            Yield Guardian replays a real semiconductor line. It scores every unit for failure
            risk, charts the sensors against their control limits and reads wafer maps for
            failure patterns. When something is off, an investigator gathers the evidence and
            writes a report in which every number is checked. An engineer decides what happens
            next.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg" className="bg-ink text-room hover:bg-ink/90">
              <Link href="/line">Open the live line</Link>
            </Button>
            {canAct ? (
              <Button asChild size="lg" variant="outline" className="border-hairline-strong bg-transparent">
                <Link href="/investigations">See the investigations</Link>
              </Button>
            ) : (
              <Button
                size="lg"
                variant="outline"
                className="border-hairline-strong bg-transparent"
                onClick={() => guest.mutate()}
                disabled={guest.isPending}
              >
                {guest.isPending ? "Starting session…" : "Try as engineer"}
              </Button>
            )}
          </div>
        </div>

        <div className="min-w-0">
          {hero.isPending ? (
            <Placeholder className="mx-auto aspect-square w-full max-w-[760px] rounded-full bg-die" label="Loading the wafer" />
          ) : hero.isError || !hero.data ? (
            <div className="flex aspect-[4/3] items-center">
              <ErrorState error={hero.error} onRetry={() => void hero.refetch()} className="w-full" />
            </div>
          ) : (
            <HeroFigure hero={hero.data} />
          )}
        </div>
      </div>
    </section>
  );
}

function HeroFigure({ hero }: { hero: WaferHero }) {
  const grid = useMemo(
    () => ({ height: hero.map.height, width: hero.map.width, cells: decodeWaferCells(hero.map) }),
    [hero.map],
  );
  const counts = useMemo(() => layoutDies(grid), [grid]);
  const { wafer, prediction, spatial } = hero;
  const label = `Wafer ${wafer.wafer_index} of lot ${wafer.lot}: ${formatInt(counts.pass + counts.fail)} dies, ${formatInt(counts.fail)} failed at wafer test, recorded pattern ${patternName(wafer.label)}.`;

  return (
    <div className="mx-auto max-w-[760px]">
      <HeroWafer grid={grid} label={label} className="pb-8" />
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border-t border-hairline pt-4 text-sm sm:grid-cols-4">
        <Fact label="Wafer" value={`${wafer.lot}, wafer ${wafer.wafer_index}`} />
        <Fact label="Dies" value={formatInt(counts.pass + counts.fail)} detail={`${formatInt(counts.fail)} failed`} />
        <Fact label="Recorded pattern" value={patternName(wafer.label)} />
        <Fact
          label="Model reading"
          value={
            prediction
              ? prediction.unknown.is_unknown
                ? "Unknown pattern"
                : patternName(prediction.top_label)
              : "Not predicted"
          }
          detail={prediction && !prediction.unknown.is_unknown ? formatProbability(prediction.top_probability) : undefined}
        />
        {spatial ? (
          <Fact
            label="Failed dies cluster"
            value={spatial.clustered ? "Yes" : "No"}
            detail={`join count, p ${formatPValue(spatial.p_value)}`}
          />
        ) : null}
      </dl>
      <div className="mt-4 grid gap-1.5 text-[13px] leading-5 text-ink-3">
        <p>
          <span className="mr-1.5 inline-block size-2 translate-y-[-1px] rounded-full bg-fail align-middle" aria-hidden="true" />
          A red dot marks a die that failed at wafer test. Die colours are the interference colours
          of a silicon-oxide film, computed from its optics for an assumed {FILM.centreNm} nm film
          (the dataset records only pass and fail).
        </p>
        <p>{hero.selection}</p>
        <p>{hero.attribution}</p>
      </div>
    </div>
  );
}

function Fact({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[13px] leading-5 text-ink-3">{label}</dt>
      <dd className="tnum truncate text-[15px] leading-6 text-ink">
        {value}
        {detail ? <span className="ml-1.5 text-[13px] text-ink-3">{detail}</span> : null}
      </dd>
    </div>
  );
}
