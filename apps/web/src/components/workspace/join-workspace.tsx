"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleAlertIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { PageFrame, PageHeader, Panel } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApi } from "@/lib/api/context";
import { ApiError, describeError } from "@/lib/api/errors";
import { useSession } from "@/lib/api/session";
import { codeFromHash, useJoinWorkspace, wq } from "@/lib/api/workspace";
import { plural } from "@/lib/format";
import { toast } from "@/lib/toast";

/**
 * Continue on this device: type the code another device made (or arrive with it in the link)
 * and press Join. Joining always waits for that press, and says first what comes along.
 */
export function JoinWorkspace() {
  const api = useApi();
  const router = useRouter();
  const { session } = useSession();
  const join = useJoinWorkspace();
  const [code, setCode] = useState("");

  // The code arrives after `#` (the server never sees it, so it cannot be rendered there); it is
  // read once after hydration and leaves the address bar and the history at once.
  useEffect(() => {
    const fromLink = codeFromHash(window.location.hash);
    if (fromLink == null) return;
    window.history.replaceState(window.history.state, "", window.location.pathname);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read once from the address
    setCode(fromLink);
  }, []);

  const summary = useQuery({ ...wq.summary(api), enabled: session.workspace != null });
  const here = summary.data;
  const held = here
    ? [
        here.runs ? plural(here.runs, "run") : null,
        here.uploads ? plural(here.uploads, "upload") : null,
        here.investigations ? plural(here.investigations, "investigation") : null,
      ].filter(Boolean)
    : [];
  const shared = here ? here.devices.length > 1 : false;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    join.mutate(code, {
      onSuccess: () => {
        setCode("");
        toast.success("This device is in the workspace", {
          description: "Its runs, uploads and investigations are here now.",
        });
        router.push("/");
      },
    });
  };
  // The API says what is wrong with a code (unknown, used up, ended) in its own words.
  const failure = join.error;
  const message = !failure
    ? null
    : failure instanceof ApiError && failure.status === 422
      ? "That is not a code: type its 12 letters and digits, for example 7K2M-QX9D-4HRT."
      : failure instanceof ApiError && failure.problem?.detail
        ? failure.problem.detail
        : `${describeError(failure).title}. ${describeError(failure).detail}`;

  return (
    <PageFrame className="max-w-[720px]">
      <PageHeader
        title="Continue on this device"
        description="Type the code your other device shows under Your work, Continue on another device. This device then sees that workspace: its runs, uploads and investigations, as they are there."
      />
      <Panel>
        <form onSubmit={submit} className="grid grid-cols-[minmax(0,1fr)] gap-4">
          <div className="grid grid-cols-[minmax(0,1fr)] gap-1.5">
            <Label htmlFor="join-code">Code</Label>
            <Input
              id="join-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="XXXX-XXXX-XXXX"
              autoComplete="one-time-code"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={24}
              required
              aria-describedby={message ? "join-help join-error" : "join-help"}
              aria-invalid={message ? true : undefined}
              className="tnum h-14 rounded-[16px] px-4 text-[22px] font-[600] tracking-[0.12em] uppercase [font-stretch:104%] placeholder:tracking-[0.12em] placeholder:text-ink-3/70"
            />
            <p id="join-help" className="text-[13px] leading-5 text-ink-2">
              12 letters and digits; dashes, spaces and case do not matter. A code works once
              {here ? `, for ${plural(here.handoff_minutes, "minute")}` : null}.
            </p>
          </div>
          <p className="rounded-[14px] bg-surface-2 px-4 py-3 text-[14px] leading-[22px] text-ink-2">
            {!here
              ? "What this device made so far comes along with it."
              : shared
                ? "Another device shares this device's workspace now, so what is in it stays there for that device."
                : held.length
                  ? `This device's ${held.join(", ")} come along into the workspace you join.`
                  : "This device has made nothing yet."}{" "}
            Join only with a code you made yourself: everyone in that workspace sees what you do
            here.
          </p>
          {message ? (
            <p
              id="join-error"
              role="alert"
              className="swap-in flex items-start gap-2.5 rounded-[14px] bg-fail-wash px-4 py-3 text-[14px] leading-5 text-ink shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--fail)_30%,transparent)]"
            >
              <CircleAlertIcon aria-hidden="true" className="mt-px size-4 shrink-0 text-fail" />
              {message}
            </p>
          ) : null}
          <div>
            <Button type="submit" size="lg" disabled={join.isPending || !code.trim()}>
              {join.isPending ? "Joining" : "Join the workspace"}
            </Button>
          </div>
        </form>
      </Panel>
    </PageFrame>
  );
}
