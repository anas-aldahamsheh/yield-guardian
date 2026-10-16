"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Switch as SwitchPrimitive } from "radix-ui";

/*
 * Off: a recessed track with a 3:1 edge and an ink-2 thumb. On: the track fills with the signal and
 * the thumb slides over on the firm spring; pressed, the thumb widens a little toward its travel.
 */
function Switch({
  className,
  size = "default",
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root> & {
  size?: "sm" | "default";
}) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      data-size={size}
      className={cn(
        "peer group/switch relative inline-flex shrink-0 items-center rounded-full p-[3px] outline-offset-2 transition-[background-color,box-shadow] duration-(--dur-2) ease-out disabled:cursor-not-allowed disabled:opacity-45",
        "data-[size=default]:h-6 data-[size=default]:w-10 data-[size=sm]:h-5 data-[size=sm]:w-8",
        "data-[state=checked]:bg-signal data-[state=unchecked]:bg-surface-3 data-[state=unchecked]:shadow-[inset_0_0_0_1px_var(--edge)]",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className={cn(
          "pointer-events-none block origin-left rounded-full shadow-[0_1px_2px_rgb(0_0_0/0.2)] transition-[translate,scale,background-color] duration-[420ms] ease-spring-firm",
          "group-data-[size=default]/switch:size-[18px] group-data-[size=sm]/switch:size-[14px]",
          "data-[state=checked]:bg-canvas data-[state=unchecked]:translate-x-0 data-[state=unchecked]:bg-ink-2",
          "group-data-[size=default]/switch:data-[state=checked]:translate-x-4 group-data-[size=sm]/switch:data-[state=checked]:translate-x-3",
          "group-active/switch:scale-x-[1.18] data-[state=checked]:origin-right",
        )}
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
