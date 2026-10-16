"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { LayoutGroup } from "framer-motion";
import { cn } from "@/lib/utils";
import { Tabs as TabsPrimitive } from "radix-ui";

import { Indicator } from "@/components/motion/indicator";

/*
 * Tabs are a segmented control: ink-2 words, the chosen one ink on a pill that slides to it
 * (shared layout). The "line" variant slides an ink underline instead. The slide needs the value,
 * so it runs on controlled Tabs; uncontrolled ones mark the chosen tab without the slide.
 */
const TabsValue = React.createContext<string | undefined>(undefined);
const TabsVariant = React.createContext<"default" | "line">("default");

function Tabs({
  className,
  orientation = "horizontal",
  value,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  const id = React.useId();
  return (
    <TabsValue.Provider value={value}>
      <LayoutGroup id={id}>
        <TabsPrimitive.Root
          data-slot="tabs"
          data-orientation={orientation}
          orientation={orientation}
          value={value}
          className={cn("group/tabs flex gap-3 data-[orientation=horizontal]:flex-col", className)}
          {...props}
        />
      </LayoutGroup>
    </TabsValue.Provider>
  );
}

const tabsListVariants = cva(
  "group/tabs-list inline-flex w-fit items-center text-ink-2 group-data-[orientation=vertical]/tabs:h-fit group-data-[orientation=vertical]/tabs:flex-col",
  {
    variants: {
      variant: {
        default:
          "gap-0.5 rounded-full bg-surface-2 p-1 shadow-[inset_0_0_0_1px_var(--hairline)] group-data-[orientation=horizontal]/tabs:h-10",
        line: "gap-5 rounded-none bg-transparent shadow-[inset_0_-1px_0_var(--hairline)] group-data-[orientation=horizontal]/tabs:h-10",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

function TabsList({
  className,
  variant = "default",
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List> & VariantProps<typeof tabsListVariants>) {
  return (
    <TabsVariant.Provider value={variant ?? "default"}>
      <TabsPrimitive.List
        data-slot="tabs-list"
        data-variant={variant}
        className={cn(tabsListVariants({ variant }), className)}
        {...props}
      />
    </TabsVariant.Provider>
  );
}

function TabsTrigger({
  className,
  value,
  children,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  const current = React.useContext(TabsValue);
  const variant = React.useContext(TabsVariant);
  const sliding = current !== undefined;
  const active = sliding && current === value;
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      value={value}
      className={cn(
        "relative inline-flex h-full flex-1 items-center justify-center gap-1.5 text-[14px] leading-5 font-[560] whitespace-nowrap text-ink-2 outline-offset-2 transition-colors duration-(--dur-1) group-data-[orientation=vertical]/tabs:w-full group-data-[orientation=vertical]/tabs:justify-start hover:text-ink disabled:pointer-events-none disabled:opacity-45 data-[state=active]:text-ink [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        variant === "default" ? "rounded-full px-3.5" : "px-0",
        !sliding &&
          (variant === "default"
            ? "data-[state=active]:bg-surface data-[state=active]:shadow-[0_1px_2px_rgb(0_0_0/0.08),inset_0_0_0_1px_var(--hairline)] dark:data-[state=active]:bg-surface-3"
            : "data-[state=active]:shadow-[inset_0_-2px_0_var(--ink)]"),
        className,
      )}
      {...props}
    >
      {active ? (
        <Indicator
          layoutId="tab-indicator"
          className={
            variant === "default"
              ? "absolute inset-0 rounded-full bg-surface shadow-[0_1px_2px_rgb(0_0_0/0.08),inset_0_0_0_1px_var(--hairline)] dark:bg-surface-3"
              : "absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-ink"
          }
        />
      ) : null}
      <span className="relative inline-flex items-center gap-1.5">{children}</span>
    </TabsPrimitive.Trigger>
  );
}

function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn("swap-in flex-1 outline-none", className)}
      {...props}
    />
  );
}

export { Tabs, TabsList, TabsTrigger, TabsContent, tabsListVariants };
