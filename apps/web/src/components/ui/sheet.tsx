"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { XIcon } from "lucide-react";
import { Dialog as SheetPrimitive } from "radix-ui";

import { closeControl, scrim } from "./styles";

function Sheet({ ...props }: React.ComponentProps<typeof SheetPrimitive.Root>) {
  return <SheetPrimitive.Root data-slot="sheet" {...props} />;
}

function SheetTrigger({ ...props }: React.ComponentProps<typeof SheetPrimitive.Trigger>) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />;
}

function SheetClose({ ...props }: React.ComponentProps<typeof SheetPrimitive.Close>) {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />;
}

function SheetPortal({ ...props }: React.ComponentProps<typeof SheetPrimitive.Portal>) {
  return <SheetPrimitive.Portal data-slot="sheet-portal" {...props} />;
}

function SheetOverlay({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Overlay>) {
  return (
    <SheetPrimitive.Overlay data-slot="sheet-overlay" className={cn(scrim, className)} {...props} />
  );
}

/*
 * A sheet slides in on the soft spring and leaves quickly. From the small breakpoint up it floats
 * a few pixels off the edge as its own rounded plane; on a phone it fills the edge.
 */
const SIDE = {
  right:
    "inset-y-0 right-0 h-full w-full sm:inset-y-2 sm:right-2 sm:h-[calc(100%-16px)] sm:max-w-sm sm:rounded-[20px] data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right",
  left: "inset-y-0 left-0 h-full w-full sm:inset-y-2 sm:left-2 sm:h-[calc(100%-16px)] sm:max-w-sm sm:rounded-[20px] data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left",
  top: "inset-x-0 top-0 h-auto rounded-b-[20px] data-[state=open]:slide-in-from-top data-[state=closed]:slide-out-to-top",
  bottom:
    "inset-x-0 bottom-0 h-auto rounded-t-[20px] data-[state=open]:slide-in-from-bottom data-[state=closed]:slide-out-to-bottom",
} as const;

function SheetContent({
  className,
  children,
  side = "right",
  showCloseButton = true,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content> & {
  side?: "top" | "right" | "bottom" | "left";
  showCloseButton?: boolean;
}) {
  return (
    <SheetPortal>
      <SheetOverlay />
      <SheetPrimitive.Content
        data-slot="sheet-content"
        className={cn(
          "fixed z-50 flex flex-col gap-4 bg-surface text-ink shadow-overlay ring-1 ring-hairline outline-none",
          "data-[state=open]:animate-in data-[state=open]:duration-[560ms] data-[state=open]:ease-spring-soft",
          "data-[state=closed]:animate-out data-[state=closed]:duration-[220ms] data-[state=closed]:ease-in",
          SIDE[side],
          className,
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <SheetPrimitive.Close className={cn(closeControl, "top-3 right-3")}>
            <XIcon />
            <span className="sr-only">Close</span>
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Content>
    </SheetPortal>
  );
}

function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-header"
      className={cn("flex flex-col gap-1.5 p-5 pr-14", className)}
      {...props}
    />
  );
}

function SheetFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-footer"
      className={cn("mt-auto flex flex-col gap-2 p-5", className)}
      {...props}
    />
  );
}

function SheetTitle({ className, ...props }: React.ComponentProps<typeof SheetPrimitive.Title>) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cn(
        "text-[18px] leading-6 font-[640] tracking-[-0.01em] text-ink [font-stretch:106%]",
        className,
      )}
      {...props}
    />
  );
}

function SheetDescription({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Description>) {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cn("text-[13.5px] leading-5 text-ink-2", className)}
      {...props}
    />
  );
}

export {
  Sheet,
  SheetTrigger,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
};
