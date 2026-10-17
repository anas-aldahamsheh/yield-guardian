"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { LlmProviderState } from "@yield-guardian/contracts";
import { useEffect, useState } from "react";

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
import { useSetProvider } from "@/lib/api/llm";
import { MODEL_FAILED, type ModelFailure } from "@/lib/model-failure";

/** Shown when a model call fails on AMD: switch the site to Claude and run the action again. */
export function ModelFailureDialog() {
  const client = useQueryClient();
  const set = useSetProvider();
  const [failure, setFailure] = useState<(ModelFailure & { model: string }) | null>(null);

  useEffect(() => {
    const onFailed = (e: Event) => {
      const detail = (e as CustomEvent<ModelFailure>).detail;
      const state = client.getQueryData<LlmProviderState>(["llm", "provider"]);
      if (state?.provider !== "amd") return;
      setFailure({ ...detail, model: state.model_id });
    };
    window.addEventListener(MODEL_FAILED, onFailed);
    return () => window.removeEventListener(MODEL_FAILED, onFailed);
  }, [client]);

  const switchAndRetry = async () => {
    const f = failure;
    setFailure(null);
    if (!f) return;
    try {
      await set.mutateAsync("claude");
    } catch {
      return;
    }
    f.retry();
  };

  return (
    <AlertDialog open={failure !== null} onOpenChange={(open) => !open && setFailure(null)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>AMD model failed</AlertDialogTitle>
          <AlertDialogDescription>
            {failure?.model} returned: {failure?.reason}. Switch to Claude to continue.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Close</AlertDialogCancel>
          <AlertDialogAction onClick={() => void switchAndRetry()}>
            Switch to Claude &amp; retry
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
