"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { LineState } from "@yield-guardian/contracts";
import { useEffect, useRef, useState } from "react";

import { lineSocketUrl } from "@/lib/api/config";
import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";

import { applyLineEvent, parseLineEvent, reconnectDelay } from "./line-state";

export type LineConnection = "connecting" | "live" | "reconnecting" | "offline";

/**
 * The line as it runs: GET /line/state for the first paint, then /ws/line events applied in
 * place. Reconnects with backoff; every new connection starts with a hello that carries the full
 * state, so nothing is lost while the socket is down.
 */
export function useLiveLine(window: number) {
  const api = useApi();
  const client = useQueryClient();
  const query = useQuery(q.lineState(api, window));
  const queryKey = q.lineState(api, window).queryKey;
  const [connection, setConnection] = useState<LineConnection>("connecting");
  const [lastUnitAt, setLastUnitAt] = useState<number | null>(null);
  const windowRef = useRef(window);

  useEffect(() => {
    windowRef.current = window;
  }, [window]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const refetch = () => void client.invalidateQueries({ queryKey: ["line", "state"] });

    const connect = () => {
      if (stopped) return;
      clearTimeout(timer);
      if (!navigator.onLine) {
        setConnection("offline");
        return;
      }
      socket = new WebSocket(lineSocketUrl(globalThis.location));
      socket.onopen = () => {
        attempt = 0;
        setConnection("live");
      };
      socket.onmessage = (message) => {
        const event = parseLineEvent(message.data);
        if (!event) return;
        let followUp = "none" as "none" | "refetch";
        client.setQueryData<LineState>(queryKey, (current) => {
          if (!current) {
            return event.type === "hello" ? event.state : current;
          }
          const result = applyLineEvent(current, event, windowRef.current);
          followUp = result.followUp;
          return result.state;
        });
        if (event.type === "unit") setLastUnitAt(Date.now());
        if (followUp === "refetch") refetch();
      };
      socket.onclose = () => {
        socket = null;
        if (stopped) return;
        setConnection(navigator.onLine ? "reconnecting" : "offline");
        timer = setTimeout(connect, reconnectDelay(attempt));
        attempt += 1;
      };
      socket.onerror = () => socket?.close();
    };

    const online = () => {
      attempt = 0;
      if (!socket) connect();
    };
    const offline = () => setConnection("offline");
    globalThis.addEventListener("online", online);
    globalThis.addEventListener("offline", offline);
    connect();

    return () => {
      stopped = true;
      clearTimeout(timer);
      globalThis.removeEventListener("online", online);
      globalThis.removeEventListener("offline", offline);
      socket?.close();
    };
    // queryKey is derived from window, which is a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, window]);

  return { query, connection, lastUnitAt };
}
