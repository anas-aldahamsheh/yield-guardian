"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { CircleAlertIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, describeError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

/** What failed and what to do next. Errors do not apologise and are never vague. */
export function ErrorState({
  error,
  onRetry,
  className,
  compact = false,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
  compact?: boolean;
}) {
  const copy = describeError(error);
  // The API answers 503 not_ready while a service is loading or not installed. That is a state
  // of the plant, not a fault: it is drawn as an unexposed field, without the fail colour.
  if (error instanceof ApiError && error.code === "not_ready") {
    return (
      <PendingState
        title="Not ready yet"
        className={className}
        compact={compact}
        action={
          onRetry ? (
            <Button size="sm" variant="outline" onClick={onRetry}>
              Check again
            </Button>
          ) : undefined
        }
      >
        {copy.detail}
      </PendingState>
    );
  }
  return (
    <div
      role="alert"
      className={cn(
        "swap-in flex flex-wrap items-start gap-x-3 gap-y-3 rounded-[14px] bg-fail-wash px-4 shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--fail)_32%,transparent)]",
        compact ? "py-3" : "py-4",
        className,
      )}
    >
      <CircleAlertIcon className="mt-0.5 size-5 shrink-0 text-fail" strokeWidth={1.9} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-[15px] leading-6 font-[600] text-ink">{copy.title}</p>
        <p className="mt-0.5 text-[14px] leading-[22px] text-ink-2">{copy.detail}</p>
      </div>
      {onRetry ? (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

/** Nothing to show yet: say why, and what to do. */
export function EmptyState({
  title,
  children,
  action,
  className,
}: {
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-[14px] border border-dashed border-hairline-strong px-5 py-6 sm:px-6",
        className,
      )}
    >
      <p className="text-[16px] leading-6 font-[600] text-ink">{title}</p>
      {children ? (
        <div className="mt-1 max-w-[64ch] text-[14px] leading-[22px] text-ink-2">{children}</div>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

/**
 * A value or a service that does not exist yet: not measured, not ready, waiting for a result.
 * Drawn as an unexposed field of dies, with plain words for why and what happens next.
 */
export function PendingState({
  title,
  children,
  action,
  className,
  compact = false,
}: {
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div
      role="status"
      className={cn(
        "unexposed flex flex-wrap items-start gap-x-3.5 gap-y-3 rounded-[14px] bg-surface px-4 shadow-[inset_0_0_0_1px_var(--hairline-strong)]",
        compact ? "py-3" : "min-h-28 py-4",
        className,
      )}
    >
      <PendingMark className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-[15px] leading-6 font-[600] text-ink">{title}</p>
        {children ? (
          <div className="mt-0.5 max-w-[60ch] text-[14px] leading-[22px] text-ink-2">
            {children}
          </div>
        ) : null}
      </div>
      {action}
    </div>
  );
}

/** Four dies, one outlined and unfilled: the die that has not been measured. */
export function PendingMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" className={cn("size-5", className)} aria-hidden="true">
      <rect x="1.5" y="1.5" width="7.5" height="7.5" rx="2" fill="var(--hairline-strong)" />
      <rect x="11" y="1.5" width="7.5" height="7.5" rx="2" fill="var(--hairline-strong)" />
      <rect x="1.5" y="11" width="7.5" height="7.5" rx="2" fill="var(--hairline-strong)" />
      <rect
        x="11.5"
        y="11.5"
        width="6.5"
        height="6.5"
        rx="1.5"
        fill="none"
        stroke="var(--ink-3)"
        strokeDasharray="2 1.6"
      />
    </svg>
  );
}

/** A loading placeholder shaped like what will arrive. */
export function Placeholder({
  className,
  label = "Loading",
}: {
  className?: string;
  label?: string;
}) {
  return (
    <div
      role="status"
      aria-label={label}
      className={cn("shimmer rounded-[14px] bg-surface-2", className)}
    />
  );
}

/** Renders a query's three states the same way everywhere. */
export function QueryView<T>({
  query,
  loading,
  children,
  compactError = false,
  errorClassName,
}: {
  query: Pick<UseQueryResult<T>, "data" | "error" | "isPending" | "isError" | "refetch">;
  loading?: ReactNode;
  children: (data: T) => ReactNode;
  compactError?: boolean;
  /** Where the error sits, for a panel whose body runs edge to edge (a table's). */
  errorClassName?: string;
}) {
  if (query.isPending) return <>{loading ?? <Placeholder className="h-40" />}</>;
  if (query.isError || query.data === undefined) {
    return (
      <ErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
        compact={compactError}
        className={errorClassName}
      />
    );
  }
  return <>{children(query.data)}</>;
}
