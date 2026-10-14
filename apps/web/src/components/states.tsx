"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { describeError } from "@/lib/api/errors";
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
