import { MessageSquareText } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/**
 * The floating "Ask" button, on every page in the bottom corner. Its place is fixed, so the
 * button that loads the chat and the sheet's own trigger sit exactly on top of each other. The
 * footer keeps 112 px free at the bottom of every page (site-footer.tsx), so at the end of a page
 * the button covers nothing, down to 360 px. An ink pill that lifts on hover, catches the film's
 * light, and goes down under a press.
 */
export function AskButton({ className, ...props }: ComponentProps<"button">) {
  return (
    <button
      type="button"
      aria-haspopup="dialog"
      className={cn(
        "press lift sheen-hover magnetic fixed right-gutter bottom-[max(16px,env(safe-area-inset-bottom))] z-30 inline-flex h-12 cursor-pointer items-center gap-2 rounded-full bg-ink pr-5 pl-4 text-[15px] leading-5 font-[600] text-canvas",
        "shadow-[0_0_0_1px_var(--canvas),0_10px_28px_-10px_color-mix(in_oklab,var(--ink)_55%,transparent),inset_0_1px_0_rgb(255_255_255/0.14)]",
        "disabled:cursor-default disabled:opacity-70",
        "print:hidden",
        className,
      )}
      {...props}
    >
      <MessageSquareText className="size-[18px]" strokeWidth={1.9} aria-hidden="true" />
      Ask
    </button>
  );
}
