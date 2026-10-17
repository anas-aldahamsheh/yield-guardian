"use client";

import type { CatalogModel, RoleAssignment } from "@yield-guardian/contracts";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAssignRole } from "@/lib/api/llm";
import { ROLE_JOBS, ROLE_NAMES } from "@/lib/labels";

const DEFAULT_EFFORT = "__default";

/** The catalog kinds a role can use: OCR reads documents, vision reads images, the rest are text models. */
export function kindsFor(role: RoleAssignment["role"]): CatalogModel["kind"][] {
  if (role === "ocr") return ["ocr", "vlm"];
  if (role === "vision") return ["vlm"];
  return ["llm", "vlm"];
}

export function RoleDialog({
  assignment,
  catalog,
  open,
  onOpenChange,
}: {
  assignment: RoleAssignment;
  catalog: CatalogModel[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const assign = useAssignRole();
  const [modelId, setModelId] = useState(assignment.model_id);
  const [effort, setEffort] = useState<string>(assignment.reasoning_effort ?? DEFAULT_EFFORT);
  const [fallbacks, setFallbacks] = useState<string[]>(assignment.fallbacks);

  const kinds = kindsFor(assignment.role);
  const choices = catalog.filter((m) => kinds.includes(m.kind));
  const model = catalog.find((m) => m.model_id === modelId);
  const efforts = model?.reasoning_efforts ?? [];
  const effortValue =
    effort !== DEFAULT_EFFORT && !efforts.includes(effort as never) ? DEFAULT_EFFORT : effort;
  const addable = choices.filter((m) => m.model_id !== modelId && !fallbacks.includes(m.model_id));

  const save = () => {
    assign.mutate(
      {
        role: assignment.role,
        body: {
          model_id: modelId,
          reasoning_effort:
            effortValue === DEFAULT_EFFORT
              ? null
              : (effortValue as RoleAssignment["reasoning_effort"]),
          fallbacks: fallbacks.filter((f) => f !== modelId),
        },
      },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{ROLE_NAMES[assignment.role] ?? assignment.role}</DialogTitle>
          <DialogDescription>
            {ROLE_JOBS[assignment.role]}. The change applies from the next call and is recorded in
            the audit log.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
          <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
            <Label htmlFor="role-model">Model</Label>
            <Select value={modelId} onValueChange={setModelId}>
              <SelectTrigger id="role-model" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {choices.map((m) => (
                  <SelectItem key={m.model_id} value={m.model_id} disabled={!m.available}>
                    {m.model_id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {model ? (
              <p className="text-[12px] leading-4 text-ink-3">
                {model.json_schema ? "Strict JSON output" : "No strict JSON output"},{" "}
                {model.tools ? "tool calls" : "no tool calls"}
                {model.profile === "catalog_only"
                  ? ". Capabilities not documented: the profile comes from the catalog only."
                  : "."}
              </p>
            ) : null}
          </div>
          <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
            <Label htmlFor="role-effort">Reasoning effort</Label>
            <Select value={effortValue} onValueChange={setEffort} disabled={efforts.length === 0}>
              <SelectTrigger id="role-effort" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DEFAULT_EFFORT}>The model&rsquo;s default</SelectItem>
                {efforts.map((e) => (
                  <SelectItem key={e} value={e}>
                    {e}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {efforts.length === 0 ? (
              <p className="text-[12px] leading-4 text-ink-3">
                This model takes no reasoning effort.
              </p>
            ) : null}
          </div>
          <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
            <p className="text-[14px] leading-5 font-[560] text-ink">Fallbacks, tried in order</p>
            {fallbacks.length ? (
              <ol className="grid grid-cols-[minmax(0,1fr)] gap-1">
                {fallbacks.map((f, i) => (
                  <li
                    key={f}
                    className="flex items-center justify-between gap-2 rounded-[12px] bg-surface-2 py-1 pr-1 pl-3 text-[13px] shadow-[inset_0_0_0_1px_var(--hairline)]"
                  >
                    <span className="tnum">
                      <span className="text-ink-3">{i + 1}.</span> {f}
                    </span>
                    <span className="flex gap-1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={i === 0}
                        aria-label={`Move ${f} up`}
                        onClick={() =>
                          setFallbacks((list) =>
                            list.map((x, j) => (j === i - 1 ? f : j === i ? list[i - 1]! : x)),
                          )
                        }
                      >
                        Up
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        aria-label={`Remove ${f}`}
                        onClick={() => setFallbacks((list) => list.filter((x) => x !== f))}
                      >
                        Remove
                      </Button>
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-[13px] text-ink-3">
                No fallback: if the model is unavailable, the call fails.
              </p>
            )}
            {addable.length ? (
              <Select value="" onValueChange={(v) => v && setFallbacks((list) => [...list, v])}>
                <SelectTrigger size="sm" className="w-full" aria-label="Add a fallback">
                  <SelectValue placeholder="Add a fallback" />
                </SelectTrigger>
                <SelectContent>
                  {addable.map((m) => (
                    <SelectItem key={m.model_id} value={m.model_id}>
                      {m.model_id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={save} disabled={assign.isPending}>
            {assign.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
