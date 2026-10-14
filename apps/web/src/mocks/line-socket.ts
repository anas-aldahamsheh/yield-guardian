/**
 * Replays the /ws/line fixture on a WebSocket: hello first, then a unit, an alarm and a
 * final-test result, then heartbeats. Development only.
 */
import type { LineEvent } from "@yield-guardian/contracts";

import { fixture } from "./fixtures";

interface SocketLike {
  send(data: string): void;
  close(): void;
  on(event: "close", listener: () => void): void;
  readyState: number;
}

export function replayLineSocket(socket: SocketLike, { intervalMs = 6000 } = {}) {
  const events = fixture<LineEvent[]>("line_socket");
  const hello = events.find((e) => e.type === "hello");
  const live = events.filter((e) => e.type === "unit" || e.type === "alarm" || e.type === "final_test");
  const heartbeat = events.find((e) => e.type === "heartbeat");
  const timers: ReturnType<typeof setTimeout>[] = [];
  const send = (event: LineEvent | undefined) => {
    if (event && socket.readyState === 1) socket.send(JSON.stringify(event));
  };

  send(hello);
  live.forEach((event, i) => timers.push(setTimeout(() => send(event), 2500 + i * 900)));
  const beat = setInterval(() => send(heartbeat), intervalMs);
  socket.on("close", () => {
    timers.forEach(clearTimeout);
    clearInterval(beat);
  });
}
