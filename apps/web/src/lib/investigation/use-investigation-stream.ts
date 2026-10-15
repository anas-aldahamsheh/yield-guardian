"use client";

import { useQueryClient } from "@tanstack/react-query";
import { API_PREFIX, type Investigation, type InvestigationEvent } from "@yield-guardian/contracts";
import { useCallback, useEffect, useState } from "react";

import {
  INVESTIGATION_EVENT_TYPES,
  LIVE_STATUSES,
  applyInvestigationEvent,
  emptyRun,
} from "./events";

export type StreamState = "idle" | "streaming" | "reconnecting" | "ended";

function eventsUrl(id: string) {
  return `${API_PREFIX}/investigations/${encodeURIComponent(id)}/events`;
}

function parse(data: unknown): InvestigationEvent | null {
  if (typeof data !== "string") return null;
  try {
    const value = JSON.parse(data) as InvestigationEvent;
    return value && typeof value === "object" && "type" in value ? value : null;
  } catch {
    return null;
  }
}

/**
 * Follows an investigation's events (SSE). While the run is queued or running, events update the
 * cached investigation; the browser's EventSource reconnects with Last-Event-ID by itself.
 * `startReplay` replays a finished run from its first event into a separate copy, so the
 * stored record stays as it is.
 */
export function useInvestigationStream(investigation: Investigation | undefined) {
  const client = useQueryClient();
  const [replay, setReplay] = useState<Investigation | null>(null);
  const [replayKey, setReplayKey] = useState(0);
  const [state, setState] = useState<StreamState>("idle");
  const id = investigation?.investigation_id;
  const live = investigation ? LIVE_STATUSES.has(investigation.status) : false;
  const replaying = replayKey > 0;

  useEffect(() => {
    if (!id || !investigation || (!live && !replaying)) return;
    const key = ["investigations", id];
    const source = new EventSource(eventsUrl(id), { withCredentials: true });

    const onEvent = (message: MessageEvent) => {
      const event = parse(message.data);
      if (!event) return;
      if (replaying) {
        setReplay((current) => (current ? applyInvestigationEvent(current, event) : current));
      } else {
        client.setQueryData<Investigation>(key, (current) =>
          current ? applyInvestigationEvent(current, event) : current,
        );
      }
      if (event.type === "end") {
        source.close();
        setState("ended");
        // A finished replay hands back to the stored record, with its decision.
        if (replaying) setTimeout(() => setReplayKey(0), 1200);
        else void client.invalidateQueries({ queryKey: ["investigations"] });
      }
    };
    for (const type of INVESTIGATION_EVENT_TYPES) source.addEventListener(type, onEvent);
    source.onerror = () => {
      setState(source.readyState === EventSource.CLOSED ? "ended" : "reconnecting");
    };
    source.onopen = () => setState("streaming");

    return () => {
      for (const type of INVESTIGATION_EVENT_TYPES) source.removeEventListener(type, onEvent);
      source.close();
    };
    // The stream restarts only for a new run, a status that becomes live, or a new replay.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, live, replayKey, client]);

  const startReplay = useCallback(() => {
    if (!investigation) return;
    setReplay(emptyRun(investigation));
    setState("streaming");
    setReplayKey((k) => k + 1);
  }, [investigation]);

  return { replay: replaying ? replay : null, state, startReplay };
}
