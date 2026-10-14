import Link from "next/link";

import { cn } from "@/lib/utils";

/** A wafer with its flat and a grid of dies, drawn in ink. */
export function WaferMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={cn("size-6", className)} fill="none">
      <defs>
        <clipPath id="yg-mark-clip">
          <path d="M12 2.5a9.5 9.5 0 0 1 7.6 15.2H4.4A9.5 9.5 0 0 1 12 2.5Z" />
        </clipPath>
      </defs>
      <path
        d="M4.4 17.7A9.5 9.5 0 1 1 19.6 17.7Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <g clipPath="url(#yg-mark-clip)" fill="currentColor">
        {[5.2, 9.4, 13.6].map((x) =>
          [5.2, 9.4, 13.6].map((y) => (
            <rect key={`${x}-${y}`} x={x} y={y} width="3.2" height="3.2" rx="0.4" opacity="0.9" />
          )),
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
        "flex items-center gap-2.5 rounded-sm text-[15px] font-semibold tracking-[-0.01em] text-ink no-underline",
        className,
      )}
    >
      <WaferMark />
      <span>Yield Guardian</span>
    </Link>
  );
}
