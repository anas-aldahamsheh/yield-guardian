"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

import { NAV_ITEMS, isActive } from "./nav-items";
import { PlantClockLink } from "./plant-clock";
import { SessionControl } from "./session-control";
import { ThemeMenu } from "./theme-menu";
import { Wordmark } from "./wordmark";

export function TopBar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-hairline bg-room">
      <div className="mx-auto flex h-bar max-w-[1600px] items-stretch gap-6 px-gutter">
        <Wordmark className="self-center" />

        <nav aria-label="Main" className="hidden items-stretch xl:flex">
          <ul className="flex items-stretch">
            {NAV_ITEMS.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href} className="flex">
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "relative flex items-center px-3 text-sm no-underline transition-colors duration-[var(--dur-micro)]",
                      active ? "font-medium text-ink" : "text-ink-2 hover:text-ink",
                      "after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full after:content-['']",
                      active ? "after:bg-safelight" : "after:bg-transparent",
                    )}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <PlantClockLink className="hidden sm:flex" />
          <span className="mx-1 hidden h-5 w-px bg-hairline sm:block" aria-hidden="true" />
          <ThemeMenu />
          <SessionControl className="hidden md:flex" />
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon-sm" className="xl:hidden" aria-label="Open the menu">
                <Menu className="size-4" aria-hidden="true" />
              </Button>
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
                            active ? "border-safelight bg-safelight-wash text-ink" : "border-transparent text-ink hover:bg-accent",
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
              <div className="mt-auto grid gap-3 border-t border-hairline px-5 py-4">
                <PlantClockLink className="sm:hidden" />
                <SessionControl stacked className="md:hidden" />
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
