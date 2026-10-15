import type { FdcContributions } from "@yield-guardian/contracts";
import Link from "next/link";

import { formatPercent, formatReading } from "@/lib/format";
import { sensorHref } from "@/lib/routes";

/** Each sensor's share of a unit's T² or SPE, largest first, with the reading against the reference median. */
export function ContributionTable({ data }: { data: FdcContributions }) {
  const max = Math.max(...data.contributions.map((c) => c.share), data.other_share, 0.01);
  return (
    <>
      <p className="tnum mb-3 text-[13px] leading-5 text-ink-2">
        {data.statistic === "t2" ? "T²" : "SPE"} {formatReading(data.value)} against limits {formatReading(data.limit_99, 3)} (99%) and{" "}
        {formatReading(data.limit_999, 3)} (99.9%).
      </p>
      <table className="w-full border-collapse text-left text-[13px] leading-5">
        <caption className="sr-only">Contributions by sensor</caption>
        <thead>
          <tr className="text-[12px] text-ink-3">
            <th scope="col" className="py-1.5 pr-3 font-normal">Sensor</th>
            <th scope="col" className="w-[40%] py-1.5 pr-3 font-normal">Share</th>
            <th scope="col" className="py-1.5 pr-3 text-right font-normal">Reading</th>
            <th scope="col" className="py-1.5 text-right font-normal">Reference median</th>
          </tr>
        </thead>
        <tbody>
          {data.contributions.map((c) => (
            <tr key={c.sensor} className="border-t border-hairline">
              <th scope="row" className="tnum py-1.5 pr-3 font-normal">
                <Link href={sensorHref(c.sensor)} className="text-ink underline decoration-hairline-strong underline-offset-4">
                  {c.sensor}
                </Link>
              </th>
              <td className="py-1.5 pr-3">
                <span className="flex items-center gap-2">
                  <span className="h-2.5 rounded-[2px] bg-ink-2" style={{ width: `${(c.share / max) * 100}%`, minWidth: 2 }} aria-hidden="true" />
                  <span className="tnum shrink-0 text-ink-2">{formatPercent(c.share)}</span>
                </span>
              </td>
              <td className="tnum py-1.5 pr-3 text-right text-ink">{c.value == null ? <span className="text-ink-3">Not measured</span> : formatReading(c.value)}</td>
              <td className="tnum py-1.5 text-right text-ink-3">{formatReading(c.reference_median)}</td>
            </tr>
          ))}
          <tr className="border-t border-hairline">
            <th scope="row" className="py-1.5 pr-3 font-normal text-ink-3">Others</th>
            <td className="py-1.5 pr-3">
              <span className="flex items-center gap-2">
                <span className="h-2.5 rounded-[2px] bg-mark-muted" style={{ width: `${(data.other_share / max) * 100}%`, minWidth: 2 }} aria-hidden="true" />
                <span className="tnum shrink-0 text-ink-3">{formatPercent(data.other_share)}</span>
              </span>
            </td>
            <td />
            <td />
          </tr>
        </tbody>
      </table>
      <p className="mt-3 text-[12px] leading-4 text-ink-3">{data.method}.</p>
    </>
  );
}
