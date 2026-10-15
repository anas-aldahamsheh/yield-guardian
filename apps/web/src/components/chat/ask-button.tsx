import { MessageSquareText } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/**
 * The floating "Ask" button, on every page in the bottom corner. Its place is fixed, so the
 * button that loads the chat and the sheet's own trigger sit exactly on top of each other. The
 * footer keeps 96 px free at the bottom of every page (site-footer.tsx), so at the end of a page
 * the button covers nothing, down to 360 px.
 */
export function AskButton({ className, ...props }: ComponentProps<"button">) {
  return (
    <button
      type="button"
      aria-haspopup="dialog"
      className={cn(
        "fixed right-gutter bottom-[max(16px,env(safe-area-inset-bottom))] z-30 inline-flex h-12 cursor-pointer items-center gap-2 rounded-full bg-ink pr-5 pl-4 text-[15px] font-medium text-room",
        "shadow-[0_0_0_1px_var(--room),0_6px_20px_-6px_color-mix(in_oklab,var(--ink)_45%,transparent)]",
        "transition-transform duration-[var(--dur-micro)] ease-[var(--ease-arrive)] hover:-translate-y-px active:translate-y-px disabled:cursor-default disabled:opacity-70",
        "print:hidden",
        className,
      )}
      {...props}
    >
      <MessageSquareText className="size-[18px]" aria-hidden="true" />
      Ask
    </button>
  );
}
