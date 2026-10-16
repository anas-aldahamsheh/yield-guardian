import * as React from "react";
import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-10 w-full min-w-0 rounded-[10px] border border-edge bg-surface px-3.5 py-1 text-[16px] text-ink outline-offset-2 transition-[border-color,background-color,box-shadow] duration-[var(--dur-2)] ease-out selection:bg-signal-wash-strong file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-[13px] file:font-medium file:text-ink placeholder:text-ink-3 hover:border-ink-3 focus-visible:border-signal disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-45 md:text-[14px]",
        "aria-invalid:border-fail aria-invalid:shadow-[0_0_0_3px_var(--fail-wash)]",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
