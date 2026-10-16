import Link from "next/link";

import { cn } from "@/lib/utils";

const DIES = [6.9, 11.9, 16.9];

/**
 * The mark: a wafer with its notch, drawn in ink, its dies lit by the oxide film's colours (the
 * one place the film is a fill, because the mark is a picture of a filmed wafer).
 */
export function WaferMark({
  className,
  idPrefix = "yg-mark",
}: {
  className?: string;
  /** Each mark on a page names its own gradient and clip. */
  idPrefix?: string;
}) {
  return (
    <svg viewBox="0 0 28 28" aria-hidden="true" className={cn("size-7", className)} fill="none">
      <defs>
        <linearGradient
          id={`${idPrefix}-film`}
          x1="5"
          y1="5"
          x2="23"
          y2="23"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" style={{ stopColor: "var(--film-1)" }} />
          <stop offset="0.36" style={{ stopColor: "var(--film-2)" }} />
          <stop offset="0.64" style={{ stopColor: "var(--film-4)" }} />
          <stop offset="1" style={{ stopColor: "var(--film-6)" }} />
        </linearGradient>
        <clipPath id={`${idPrefix}-clip`}>
          <circle cx="14" cy="14" r="9.4" />
        </clipPath>
      </defs>
      <path
        d="M16.15 25.04A11.25 11.25 0 1 0 11.85 25.04A2.2 2.2 0 0 1 16.15 25.04Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <g clipPath={`url(#${idPrefix}-clip)`} fill={`url(#${idPrefix}-film)`}>
        {DIES.map((x) =>
          DIES.map((y) => <rect key={`${x}-${y}`} x={x} y={y} width="4.2" height="4.2" rx="1" />),
        )}
      </g>
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cn(
        "group/mark press flex shrink-0 items-center gap-2.5 rounded-full py-1 pr-2 text-[16px] leading-6 font-[660] tracking-[-0.02em] text-ink [font-stretch:112%] no-underline",
        className,
      )}
    >
      <WaferMark className="transition-transform duration-[900ms] ease-spring-soft group-hover/mark:-rotate-90" />
      <span>Yield Guardian</span>
    </Link>
  );
}
