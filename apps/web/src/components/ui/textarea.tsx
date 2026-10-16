import * as React from "react";
import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full rounded-[14px] border border-edge bg-surface px-3.5 py-2.5 text-[16px] text-ink outline-offset-2 transition-[border-color,box-shadow] duration-[var(--dur-2)] ease-out placeholder:text-ink-3 hover:border-ink-3 focus-visible:border-signal disabled:cursor-not-allowed disabled:opacity-45 aria-invalid:border-fail md:text-[14px]",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
