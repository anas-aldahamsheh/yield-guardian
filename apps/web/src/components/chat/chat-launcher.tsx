"use client";

import { MessageSquareText } from "lucide-react";
import dynamic from "next/dynamic";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/button";

/**
 * The top bar's "Ask" button. The chat sheet (its dialog, Markdown and stream code) is fetched
 * when someone points at or focuses the button and mounts when they press it, not with every
 * page.
 */
const load = () => import("./chat-sheet");
const ChatSheet = dynamic(() => load().then((m) => m.ChatSheet), {
  ssr: false,
  loading: () => <AskButton disabled />,
});

function AskButton({ disabled, onPress, onWarm }: { disabled?: boolean; onPress?: () => void; onWarm?: () => void }) {
  return (
    <Button
      variant="outline"
      size="sm"
      className="gap-1.5"
      disabled={disabled}
      onClick={onPress}
      onPointerEnter={onWarm}
      onFocus={onWarm}
    >
      <MessageSquareText className="size-4" aria-hidden="true" />
      Ask
    </Button>
  );
}

export function ChatLauncher() {
  const [opened, setOpened] = useState(false);
  // Pointing or focusing fetches the code early; pressing mounts the sheet already open.
  if (!opened) return <AskButton onPress={() => setOpened(true)} onWarm={() => void load()} />;
  return (
    <Suspense fallback={<AskButton disabled />}>
      <ChatSheet defaultOpen />
    </Suspense>
  );
}
