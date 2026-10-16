"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { Toggle as TogglePrimitive } from "radix-ui";

const toggleVariants = cva(
  "press inline-flex items-center justify-center gap-2 rounded-full text-[14px] leading-5 font-[560] whitespace-nowrap text-ink-2 outline-offset-2 hover:text-ink disabled:pointer-events-none disabled:opacity-45 data-[state=on]:text-ink [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-transparent hover:bg-surface-2 data-[state=on]:bg-signal-wash",
        outline:
          "bg-transparent shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface-2 data-[state=on]:bg-surface data-[state=on]:shadow-[inset_0_0_0_1px_var(--edge)]",
      },
      size: {
        default: "h-9 min-w-9 px-3",
        sm: "h-8 min-w-8 px-3 text-[13px]",
        lg: "h-10 min-w-10 px-4",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function Toggle({
  className,
  variant,
  size,
  ...props
}: React.ComponentProps<typeof TogglePrimitive.Root> & VariantProps<typeof toggleVariants>) {
  return (
    <TogglePrimitive.Root
      data-slot="toggle"
      className={cn(toggleVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Toggle, toggleVariants };
