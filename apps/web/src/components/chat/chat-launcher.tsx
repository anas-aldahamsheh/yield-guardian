"use client";

import dynamic from "next/dynamic";
import { Suspense, useState } from "react";

import { AskButton } from "./ask-button";

/**
 * The floating "Ask" button on every page. The chat sheet (its dialog, Markdown and stream code)
 * is fetched when someone points at or focuses the button and mounts, already open, when they
 * press it, not with every page.
 */
const load = () => import("./chat-sheet");
const ChatSheet = dynamic(() => load().then((m) => m.ChatSheet), {
  ssr: false,
  loading: () => <AskButton disabled />,
});

export function ChatLauncher() {
  const [opened, setOpened] = useState(false);
  if (!opened) {
    return (
      <AskButton
        aria-expanded={false}
        onClick={() => setOpened(true)}
        onPointerEnter={() => void load()}
        onFocus={() => void load()}
      />
    );
  }
  return (
    <Suspense fallback={<AskButton disabled />}>
      <ChatSheet defaultOpen />
    </Suspense>
  );
}
