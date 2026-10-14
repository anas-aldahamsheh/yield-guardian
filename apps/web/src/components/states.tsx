"use client";

import type { UseQueryResult } from "@tanstack/react-query";
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
            <Button size="sm" variant="outline" onClick={onRetry} className="border-hairline-strong bg-transparent">
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
        "flex flex-wrap items-start gap-x-4 gap-y-2 rounded-sm border-l-2 border-fail bg-fail-wash px-4",
        compact ? "py-2.5" : "py-4",
        className,
      )}
    >
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-medium text-ink">{copy.title}</p>
        <p className="mt-0.5 text-sm text-ink-2">{copy.detail}</p>
      </div>
      {onRetry ? (
        <Button size="sm" variant="outline" onClick={onRetry} className="border-hairline-strong">
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
    <div className={cn("rounded-sm border border-dashed border-hairline-strong px-5 py-6", className)}>
      <p className="text-[15px] font-medium text-ink">{title}</p>
      {children ? <div className="mt-1 max-w-[64ch] text-sm text-ink-2">{children}</div> : null}
      {action ? <div className="mt-3">{action}</div> : null}
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
        "unexposed flex flex-wrap items-start gap-x-4 gap-y-2 rounded-sm border border-hairline-strong bg-die px-4",
        compact ? "py-2.5" : "min-h-28 py-4",
        className,
      )}
    >
      <PendingMark className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-[15px] leading-6 font-medium text-ink">{title}</p>
        {children ? <div className="mt-0.5 max-w-[60ch] text-sm text-ink-2">{children}</div> : null}
      </div>
      {action}
    </div>
  );
}

/** Four dies, one outlined and unfilled: the die that has not been measured. */
export function PendingMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" className={cn("size-5", className)} aria-hidden="true">
      <rect x="1.5" y="1.5" width="7.5" height="7.5" rx="1" fill="var(--hairline-strong)" />
      <rect x="11" y="1.5" width="7.5" height="7.5" rx="1" fill="var(--hairline-strong)" />
      <rect x="1.5" y="11" width="7.5" height="7.5" rx="1" fill="var(--hairline-strong)" />
      <rect x="11.5" y="11.5" width="6.5" height="6.5" rx="0.75" fill="none" stroke="var(--ink-3)" strokeDasharray="2 1.6" />
    </svg>
  );
}

/** A loading placeholder shaped like what will arrive. */
export function Placeholder({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <div
      role="status"
      aria-label={label}
      className={cn("animate-pulse rounded-sm bg-die-2 motion-reduce:animate-none", className)}
    />
  );
}

/** Renders a query's three states the same way everywhere. */
export function QueryView<T>({
  query,
  loading,
  children,
  compactError = false,
}: {
  query: Pick<UseQueryResult<T>, "data" | "error" | "isPending" | "isError" | "refetch">;
  loading?: ReactNode;
  children: (data: T) => ReactNode;
  compactError?: boolean;
}) {
  if (query.isPending) return <>{loading ?? <Placeholder className="h-40" />}</>;
  if (query.isError || query.data === undefined) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} compact={compactError} />;
  }
  return <>{children(query.data)}</>;
}
