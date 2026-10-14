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
import { PlantClockLink } from "./plant-clock";
import { SessionControl } from "./session-control";
import { MenuButton } from "./top-bar";

/** The narrow-screen menu, loaded when it is first opened; it mounts open. */
export default function MobileNavSheet({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState(true);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <MenuButton />
      </SheetTrigger>
      <SheetContent side="right" className="w-[min(360px,100vw)] gap-0 border-hairline bg-die p-0">
        <SheetHeader className="border-b border-hairline px-5 py-4">
          <SheetTitle className="text-base">Menu</SheetTitle>
          <SheetDescription className="sr-only">Pages of Yield Guardian</SheetDescription>
        </SheetHeader>
        <nav aria-label="Main" className="overflow-y-auto">
          <ul className="py-2">
            {NAV_ITEMS.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "block border-l-2 px-5 py-2.5 no-underline",
                      active
                        ? "border-safelight bg-safelight-wash text-ink"
                        : "border-transparent text-ink hover:bg-accent",
                    )}
                  >
                    <span className="block text-[15px] font-medium">{item.label}</span>
                    <span className="block text-[13px] text-ink-3">{item.hint}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="mt-auto grid grid-cols-[minmax(0,1fr)] gap-3 border-t border-hairline px-5 py-4">
          <PlantClockLink className="sm:hidden" />
          <SessionControl stacked className="md:hidden" />
        </div>
      </SheetContent>
    </Sheet>
  );
}
