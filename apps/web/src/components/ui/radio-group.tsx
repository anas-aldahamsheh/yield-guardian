"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { CircleIcon } from "lucide-react";
import { RadioGroup as RadioGroupPrimitive } from "radix-ui";

function RadioGroup({
  className,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Root>) {
  return (
    <RadioGroupPrimitive.Root
      data-slot="radio-group"
      className={cn("grid gap-3", className)}
      {...props}
    />
  );
}

function RadioGroupItem({
  className,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Item>) {
  return (
    <RadioGroupPrimitive.Item
      data-slot="radio-group-item"
      className={cn(
        "press aspect-square size-[18px] shrink-0 rounded-full border border-edge bg-surface text-signal outline-offset-2 hover:border-ink-3 disabled:cursor-not-allowed disabled:opacity-45 aria-invalid:border-fail data-[state=checked]:border-signal",
        className,
      )}
      {...props}
    >
      <RadioGroupPrimitive.Indicator
        data-slot="radio-group-indicator"
        className="relative flex items-center justify-center"
      >
        <CircleIcon className="absolute top-1/2 left-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 animate-in fill-signal stroke-none duration-[320ms] ease-spring zoom-in-0" />
      </RadioGroupPrimitive.Indicator>
    </RadioGroupPrimitive.Item>
  );
}

export { RadioGroup, RadioGroupItem };
