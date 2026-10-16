"use client";

import * as React from "react";
import { type VariantProps } from "class-variance-authority";
import { LayoutGroup } from "framer-motion";
import { cn } from "@/lib/utils";
import { ToggleGroup as ToggleGroupPrimitive } from "radix-ui";

import { Indicator } from "@/components/motion/indicator";
import { toggleVariants } from "@/components/ui/toggle";

/*
 * A single-choice group is a segmented control: the words sit in one recessed track and the chosen
 * one carries a raised thumb that slides to it (shared layout). Multiple-choice groups and groups
 * with spacing keep separate toggles.
 */
const ToggleGroupContext = React.createContext<
  VariantProps<typeof toggleVariants> & {
    spacing?: number;
    selected?: string;
  }
>({
  size: "default",
  variant: "default",
  spacing: 0,
});

function ToggleGroup({
  className,
  variant,
  size,
  spacing = 0,
  children,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Root> &
  VariantProps<typeof toggleVariants> & {
    spacing?: number;
  }) {
  const id = React.useId();
  const selected =
    props.type === "single" && typeof props.value === "string" ? props.value : undefined;
  const segmented = spacing === 0;
  return (
    <ToggleGroupPrimitive.Root
      data-slot="toggle-group"
      data-variant={variant}
      data-size={size}
      data-spacing={spacing}
      style={{ "--gap": spacing } as React.CSSProperties}
      className={cn(
        "group/toggle-group flex w-fit max-w-full flex-wrap items-center gap-[--spacing(var(--gap))]",
        segmented &&
          "gap-0.5 rounded-full bg-surface-2 p-1 shadow-[inset_0_0_0_1px_var(--hairline)]",
        className,
      )}
      {...props}
    >
      <LayoutGroup id={id}>
        <ToggleGroupContext.Provider value={{ variant, size, spacing, selected }}>
          {children}
        </ToggleGroupContext.Provider>
      </LayoutGroup>
    </ToggleGroupPrimitive.Root>
  );
}

function ToggleGroupItem({
  className,
  children,
  variant,
  size,
  value,
  ...props
}: React.ComponentProps<typeof ToggleGroupPrimitive.Item> & VariantProps<typeof toggleVariants>) {
  const context = React.useContext(ToggleGroupContext);
  const segmented = context.spacing === 0;
  const sliding = segmented && context.selected !== undefined;
  const on = sliding && context.selected === value;

  return (
    <ToggleGroupPrimitive.Item
      data-slot="toggle-group-item"
      data-variant={context.variant || variant}
      data-size={context.size || size}
      data-spacing={context.spacing}
      value={value}
      className={cn(
        toggleVariants({
          variant: segmented ? "default" : context.variant || variant,
          size: context.size || size,
        }),
        "relative w-auto min-w-0 shrink-0 px-3 focus:z-10 focus-visible:z-10",
        segmented && "hover:bg-transparent data-[state=on]:bg-transparent",
        segmented &&
          !sliding &&
          "data-[state=on]:bg-surface data-[state=on]:shadow-[0_1px_2px_rgb(0_0_0/0.08),inset_0_0_0_1px_var(--hairline)] dark:data-[state=on]:bg-surface-3",
        className,
      )}
      {...props}
    >
      {on ? (
        <Indicator
          layoutId="toggle-thumb"
          className="absolute inset-0 rounded-full bg-surface shadow-[0_1px_2px_rgb(0_0_0/0.08),inset_0_0_0_1px_var(--hairline)] dark:bg-surface-3"
        />
      ) : null}
      <span className="relative inline-flex items-center gap-2">{children}</span>
    </ToggleGroupPrimitive.Item>
  );
}

export { ToggleGroup, ToggleGroupItem };
