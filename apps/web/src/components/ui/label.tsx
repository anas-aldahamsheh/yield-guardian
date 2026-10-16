"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Label as LabelPrimitive } from "radix-ui";

function Label({ className, ...props }: React.ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(
        "flex items-center gap-2 text-[13px] leading-4 font-[560] text-ink-2 select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-45 peer-disabled:cursor-not-allowed peer-disabled:opacity-45",
        className,
      )}
      {...props}
    />
  );
}

export { Label };
