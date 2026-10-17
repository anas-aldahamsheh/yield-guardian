import type { CSSProperties, ReactNode } from "react";

import { STATIONS, type StationName } from "@/lib/routes";
import { cn } from "@/lib/utils";

/*
 * The plain-language part of How it works: what the product does, the five stations and where
 * the data comes from, as short points.
 */

const STATION_TEXT: Record<StationName, { name: string; does: string }> = {
  manufacturing: {
    name: "Manufacturing",
    does: "Reads and checks your input: counts, missing readings and time order.",
  },
  monitoring: {
    name: "Monitoring",
    does: "Watches each unit's sensors: risk score, control charts, drift and sensor health.",
  },
  wafer_test: {
    name: "Wafer test",
    does: "Classifies the defect pattern on each wafer, finds the most similar real wafers and tests the lot.",
  },
  investigation: {
    name: "Investigation",
    does: "On an alarm, if you ask, the investigator gathers the evidence and writes a report.",
  },
  decision: {
    name: "Decision",
    does: "The engineer approves and a work order opens, or rejects. Nothing happens without approval.",
  },
};

/** Stations that run only when someone asks: their mark and rule are dashed. */
const ON_DEMAND = new Set<StationName>(["investigation", "decision"]);

const WHAT: { title: string; text: string }[] = [
  {
    title: "Four ways in",
    text: "A real sample, a case you pick, a defect you draw on a wafer, or a file from your fab.",
  },
  {
    title: "Computed live",
    text: "Your input runs down a five-station line and each result is computed as it arrives. Nothing recorded is replayed.",
  },
  {
    title: "Investigation on request",
    text: "On an alarm, the investigator gathers evidence with tools that compute every number and writes a report that links each number to its evidence.",
  },
  {
    title: "The engineer decides",
    text: "Approving opens a work order; rejecting keeps the report on file. Language models write and explain; the numbers come from the tools.",
  },
];

const SECTION =
  "scroll-mt-[calc(var(--bar-height)+72px)] border-t border-hairline pt-12 pb-16 sm:pt-16 sm:pb-20";
const H2 = "text-[28px] leading-[1.3] font-[640] text-ink sm:text-[34px]";

export function HowIntro() {
  return (
    <div id="intro" className="mx-auto max-w-[1040px] scroll-mt-[calc(var(--bar-height)+72px)]">
      <header className="pb-14 sm:pb-20">
        <h1
          id="how-title"
          className="hero-line text-[40px] leading-[1.15] font-[640] text-ink sm:text-[60px] sm:leading-[1.1]"
        >
          <span>How Yield Guardian works</span>
        </h1>
        <p
          className="settle-in mt-6 max-w-[58ch] text-[18px] leading-8 text-ink-2 sm:text-[20px] sm:leading-9"
          style={{ "--d": "120ms" } as CSSProperties}
        >
          Software for quality and yield engineers in silicon wafer fabs: it helps them spot a
          problem early and narrow down where to look.
        </p>
      </header>

      <section id="what" aria-labelledby="what-title" className={SECTION}>
        <h2 id="what-title" className={H2}>
          What it does
        </h2>
        <ul className="mt-6 grid max-w-[72ch] gap-4 text-[17px] leading-7 text-ink">
          {WHAT.map((w) => (
            <Point key={w.title} title={w.title}>
              {w.text}
            </Point>
          ))}
        </ul>
        {/* The line itself: five stations on one track, in the order a unit or wafer meets them.
            The film's light runs along the track as the reader scrolls past it (globals.css,
            .how-line); the way into an on-demand station stays dashed and unlit. */}
        <ol
          className="how-line mt-12 grid grid-cols-[minmax(0,1fr)] rounded-[28px] bg-surface p-6 shadow-[inset_0_0_0_1px_var(--hairline),var(--highlight)] sm:p-8 md:grid-cols-5"
          aria-label="The five stations in order"
        >
          {STATIONS.map((s, i) => {
            const next = STATIONS[i + 1];
            const dashed = next != null && ON_DEMAND.has(next);
            const lit = !ON_DEMAND.has(s);
            const style = {
              "--i": i,
              "--seg-a": `var(--film-${i + 1})`,
              "--seg-b": `var(--film-${i + 2})`,
            } as CSSProperties;
            return (
              <li
                key={s}
                style={style}
                className="relative grid content-start gap-1.5 ps-12 pb-9 last:pb-0 md:ps-0 md:pe-6 md:pt-14 md:pb-0"
              >
                {next ? (
                  <>
                    {/* The track to the next station: down the start edge on a phone, along the top from md. */}
                    <span
                      aria-hidden="true"
                      className={cn(
                        "absolute start-[15px] top-10 bottom-1 w-0 border-s-2 border-hairline-strong md:hidden",
                        dashed && "border-dashed",
                      )}
                    />
                    <span
                      aria-hidden="true"
                      className={cn(
                        "absolute start-11 end-1 top-[15px] hidden h-0 border-t-2 border-hairline-strong md:block",
                        dashed && "border-dashed",
                      )}
                    />
                    {!dashed ? (
                      <>
                        <span
                          aria-hidden="true"
                          className="how-fill-y absolute start-[15px] top-10 bottom-1 w-[2px] rounded-full bg-[linear-gradient(180deg,var(--seg-a),var(--seg-b))] md:hidden"
                        />
                        <span
                          aria-hidden="true"
                          className="how-fill-x absolute start-11 end-1 top-[15px] hidden h-[2px] rounded-full bg-[linear-gradient(90deg,var(--seg-a),var(--seg-b))] md:block"
                        />
                      </>
                    ) : null}
                  </>
                ) : null}
                <span
                  aria-hidden="true"
                  className={cn(
                    "tnum absolute start-0 top-0 grid size-8 place-items-center rounded-full bg-surface text-[14px] leading-none font-[620] text-ink shadow-[inset_0_0_0_2px_var(--hairline-strong)]",
                    !lit && "border-2 border-dashed border-hairline-strong shadow-none",
                  )}
                >
                  {lit ? (
                    <span className="how-node absolute inset-0 rounded-full shadow-[inset_0_0_0_2px_var(--seg-a),0_0_0_4px_color-mix(in_oklab,var(--seg-a)_20%,transparent)]" />
                  ) : null}
                  <span className="relative">{i + 1}</span>
                </span>
                <span className="justify-self-start text-[17px] leading-7 font-[630] text-ink">
                  {STATION_TEXT[s].name}
                </span>
                <span className="text-[15px] leading-7 text-ink-2">{STATION_TEXT[s].does}</span>
              </li>
            );
          })}
        </ol>
      </section>

      <section id="inputs" aria-labelledby="inputs-title" className={SECTION}>
        <h2 id="inputs-title" className={H2}>
          Two kinds of input
        </h2>
        <p className="mt-4 max-w-[66ch] text-[17px] leading-7 text-ink-2">
          Everything the line reads is one of two kinds. Each kind has its own data, its own models
          and its own file layout, and both run down the same five stations.
        </p>
        <div className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-2">
          <div className="glow panel p-6">
            <SourceGlyph kind="sensors" />
            <h3 className="mt-5 text-[20px] leading-7 font-[630] text-ink">Sensor units</h3>
            <p className="mt-1 text-[16px] leading-7 text-ink-2">
              A unit is one product as it passes through the process, with up to 590 sensor
              readings taken along the way and the time it was made.
            </p>
            <ul className="mt-4 grid gap-3 text-[16px] leading-7 text-ink">
              <Point title="What it tells you">
                The risk that the unit fails its final test, which sensors drifted or went out of
                their control limits, and which sensors look unhealthy.
              </Point>
              <Point title="Trained on">SECOM, real units from a semiconductor fab.</Point>
              <Point title="Your file">
                One row per unit: unit_id, timestamp, S001 to S590, and the result (pass or fail) if
                you have it.
              </Point>
            </ul>
          </div>
          <div className="glow panel p-6">
            <SourceGlyph kind="wafers" />
            <h3 className="mt-5 text-[20px] leading-7 font-[630] text-ink">Wafer maps</h3>
            <p className="mt-1 text-[16px] leading-7 text-ink-2">
              A wafer map is the test result of every die on one wafer, good or failed, laid out in
              its place on the wafer. The shape the failed dies make points to the cause.
            </p>
            <ul className="mt-4 grid gap-3 text-[16px] leading-7 text-ink">
              <Point title="What it tells you">
                The defect pattern, such as an edge ring, a scratch or a centre cluster, whether the
                pattern is one the model has not seen, and the most similar real wafers.
              </Point>
              <Point title="Trained on">WM-811K, real wafer maps from real fabs.</Point>
              <Point title="Your file">
                One row per die: lot, wafer, x, y and the result (pass or fail). You can also draw a
                defect on a wafer yourself.
              </Point>
            </ul>
          </div>
        </div>
      </section>

      <section id="sources" aria-labelledby="sources-title" className={SECTION}>
        <h2 id="sources-title" className={H2}>
          Where the data comes from
        </h2>
        <dl className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-3 text-[16px] leading-7 md:grid-cols-3">
          <div className="glow panel p-6">
            <SourceGlyph kind="sensors" />
            <dt className="mt-5 text-[18px] leading-7 font-[620] text-ink">SECOM: sensors</dt>
            <dd className="mt-1 text-ink-2">
              Real production units from a semiconductor fab, each with anonymous sensor readings,
              its final test result (pass or fail) and its production time.
            </dd>
          </div>
          <div className="glow panel p-6">
            <SourceGlyph kind="wafers" />
            <dt className="mt-5 text-[18px] leading-7 font-[620] text-ink">WM-811K: wafer maps</dt>
            <dd className="mt-1 text-ink-2">
              Real wafer maps from real fabs: each die is good or failed, and part of the maps carry
              an engineer&apos;s defect pattern, such as an edge ring or a scratch.
            </dd>
          </div>
          <div className="glow panel p-6">
            <SourceGlyph kind="file" />
            <dt className="mt-5 text-[18px] leading-7 font-[620] text-ink">Your own data</dt>
            <dd className="mt-1 text-ink-2">
              A file from your fab (Excel or CSV) or a drawing, processed by the same code as the
              samples. Runs are kept for a while, then deleted unless an investigation uses them.
            </dd>
          </div>
        </dl>
        <p className="mt-8 max-w-[66ch] text-[17px] leading-7 text-ink">
          Both sources are public; their origin, licence and file checksums are under For experts.
          No data is synthetic: every number is computed now from your input or measured on real
          data the model did not see in training.
        </p>
      </section>
    </div>
  );
}

/** One point of the intro: a short bold title and a line or two after it. */
function Point({ title, children }: { title: string; children: ReactNode }) {
  return (
    <li className="relative ps-7">
      <span
        aria-hidden="true"
        className="absolute start-1 top-[11px] size-2 rounded-full shadow-[inset_0_0_0_1.5px_var(--ink-3)]"
      />
      <span className="font-[620]">{title}.</span> <span className="text-ink-2">{children}</span>
    </li>
  );
}

/** A small drawing of each source: a bank of sensor lamps, a wafer of dies, a file. */
function SourceGlyph({ kind }: { kind: "sensors" | "wafers" | "file" }) {
  return (
    <svg
      viewBox="0 0 48 48"
      aria-hidden="true"
      className="size-12 rounded-[14px] bg-screen p-2 text-film-4 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.06)]"
    >
      {kind === "sensors"
        ? Array.from({ length: 25 }, (_, k) => (
            <circle
              key={k}
              cx={8 + (k % 5) * 8}
              cy={8 + Math.floor(k / 5) * 8}
              r={1.9}
              fill="currentColor"
              opacity={0.7}
            />
          ))
        : null}
      {kind === "wafers" ? (
        <g>
          <circle cx={24} cy={24} r={19} fill="none" stroke="currentColor" strokeOpacity={0.6} />
          {Array.from({ length: 49 }, (_, k) => {
            const x = 9 + (k % 7) * 5;
            const y = 9 + Math.floor(k / 7) * 5;
            if ((x + 2 - 24) ** 2 + (y + 2 - 24) ** 2 > 15.5 ** 2) return null;
            return (
              <rect
                key={k}
                x={x}
                y={y}
                width={4}
                height={4}
                rx={0.8}
                fill="currentColor"
                opacity={0.55}
              />
            );
          })}
        </g>
      ) : null}
      {kind === "file" ? (
        <g fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinejoin="round">
          <path d="M14 6h14l8 8v28H14z" strokeOpacity={0.8} />
          <path d="M28 6v8h8" strokeOpacity={0.8} />
          <path d="M19 24h12M19 30h12M19 36h8" strokeOpacity={0.5} />
        </g>
      ) : null}
    </svg>
  );
}
