"use client";

import { useState, useSyncExternalStore } from "react";

const noSubscribe = () => () => {};

/**
 * Whether the part that calls this appeared while the person is on the page: a run they
 * started, a panel they opened, a result that has just come in. Then it may enter (fade, rise,
 * grow). A part that was in the page the server sent, or came back with a reload, is drawn at
 * rest: false. Decided once, when the part mounts, so nothing starts an entrance later.
 */
export function useEntrance(): boolean {
  // The server's answer while hydrating, the browser's for a part mounted afterwards.
  const late = useSyncExternalStore(
    noSubscribe,
    () => true,
    () => false,
  );
  const [entrance] = useState(late);
  return entrance;
}
