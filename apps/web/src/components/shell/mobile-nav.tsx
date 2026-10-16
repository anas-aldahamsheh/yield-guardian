"use client";

import Link from "next/link";
import { useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

import { NAV_ITEMS, isActive } from "./nav-items";
import { SessionControl } from "./session-control";
import { MenuButton } from "./top-bar";

/**
 * The narrow-screen menu, loaded when it is first opened; it mounts open. A full-height sheet: the
 * pages in large type rise in one after another as it slides in, the current one marked by the
 * film's light at its start.
 */
export default function MobileNavSheet({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState(true);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <MenuButton />
      </SheetTrigger>
      <SheetContent side="right" className="gap-0 p-0 sm:max-w-[400px]">
        <SheetHeader className="px-6 pt-5 pb-2">
          <SheetTitle className="text-[13px] leading-5 font-[560] tracking-normal text-ink-3 [font-stretch:100%]">
            Menu
          </SheetTitle>
          <SheetDescription className="sr-only">Pages of Yield Guardian</SheetDescription>
        </SheetHeader>
        <nav aria-label="Main" className="overflow-y-auto">
          <ul className="px-3 py-2">
            {NAV_ITEMS.map((item, i) => {
              const active = isActive(pathname, item.href);
              return (
                <li
                  key={item.href}
                  className="rise-in"
                  style={{ "--i": i, "--d": "120ms" } as React.CSSProperties}
                >
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "press relative block rounded-[14px] px-4 py-3.5 no-underline",
                      active ? "bg-surface-2" : "hover:bg-surface-2",
                    )}
                  >
                    {active ? (
                      <span
                        aria-hidden
                        className="film-light absolute top-4 bottom-4 left-0 w-[3px] rounded-full"
                      />
                    ) : null}
                    <span
                      className={cn(
                        "block text-[28px] leading-9 font-[640] tracking-[-0.03em] [font-stretch:112%]",
                        active ? "text-ink" : "text-ink-2",
                      )}
                    >
                      {item.label}
                    </span>
                    <span className="mt-0.5 block text-[14px] leading-5 text-ink-3">
                      {item.hint}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div
          className="rise-in mt-auto grid grid-cols-[minmax(0,1fr)] gap-3 border-t border-hairline px-6 py-5"
          style={{ "--i": NAV_ITEMS.length, "--d": "120ms" } as React.CSSProperties}
        >
          <SessionControl stacked className="md:hidden" />
        </div>
      </SheetContent>
    </Sheet>
  );
}
