"use client";

import { useQuery } from "@tanstack/react-query";
import type { LlmProviderState } from "@yield-guardian/contracts";
import { useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useApi } from "@/lib/api/context";
import { useSetProvider } from "@/lib/api/llm";
import { q } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

type Provider = LlmProviderState["provider"];

const OPTIONS: { value: Provider; label: string; model: string }[] = [
  { value: "amd", label: "AMD Infra", model: "DeepSeek-V4.1-Flash" },
  { value: "claude", label: "Claude", model: "Claude Haiku" },
];

/** Which provider runs every model call, for every visitor. Switching asks first. */
export function ProviderSwitch({ className }: { className?: string }) {
  const api = useApi();
  const { data } = useQuery(q.llmProvider(api));
  const set = useSetProvider();
  const [pending, setPending] = useState<Provider | null>(null);
  const current = set.isPending && set.variables ? set.variables : data?.provider;
  const target = OPTIONS.find((o) => o.value === pending);

  return (
    <>
      <div
        role="radiogroup"
        aria-label="Model provider"
        className={cn(
          "inline-flex h-8 items-center gap-0.5 rounded-full border border-hairline bg-surface-2 p-0.5 shadow-2xs",
          className,
        )}
      >
        {OPTIONS.map((o) => {
          const active = current === o.value;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={!data || set.isPending}
              title={`${o.label}: ${o.model}`}
              onClick={() => !active && setPending(o.value)}
              className={cn(
                "inline-flex h-full cursor-pointer items-center rounded-full px-3 text-[12px] font-[580] whitespace-nowrap transition-colors duration-(--dur-1) disabled:cursor-default",
                active
                  ? "bg-surface text-ink shadow-[inset_0_0_0_1px_var(--hairline-strong),0_1px_2px_rgb(0_0_0/0.06)] dark:bg-surface-3"
                  : "text-ink-2 hover:text-ink",
              )}
            >
              {o.label}
            </button>
          );
        })}
      </div>
      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Switch to {target?.label}?</AlertDialogTitle>
            <AlertDialogDescription>
              Every investigation and chat answer, for everyone using the site, will run on{" "}
              {target?.model} from the next call.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pending) set.mutate(pending);
                setPending(null);
              }}
            >
              Switch
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
