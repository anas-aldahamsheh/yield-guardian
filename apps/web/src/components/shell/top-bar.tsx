"use client";

import { Menu } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ComponentProps, useLayoutEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { NAV_ITEMS, isActive } from "./nav-items";
import { SessionControl } from "./session-control";
import { ThemeMenu } from "./theme-menu";
import { Wordmark } from "./wordmark";

/** The narrow-screen menu button. */
export function MenuButton(props: ComponentProps<typeof Button>) {
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      className="md:hidden"
      aria-label="Open the menu"
      {...props}
    >
      <Menu className="size-4" aria-hidden="true" />
    </Button>
  );
}

const loadNav = () => import("./mobile-nav");
const MobileNavSheet = dynamic(loadNav, {
  ssr: false,
  loading: () => <MenuButton aria-haspopup="dialog" disabled />,
});

/**
 * The menu on narrow screens. Its sheet (Radix Dialog, focus trap and scroll lock) is fetched
 * when someone points at or focuses the button and mounts, already open, when they press it.
 */
function MobileNav({ pathname }: { pathname: string }) {
  const [opened, setOpened] = useState(false);
  if (opened) return <MobileNavSheet pathname={pathname} />;
  return (
    <MenuButton
      aria-haspopup="dialog"
      aria-expanded={false}
      onClick={() => setOpened(true)}
      onPointerEnter={() => void loadNav()}
      onFocus={() => void loadNav()}
    />
  );
}

export function TopBar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-hairline bg-room">
      <div className="mx-auto flex h-bar max-w-[1600px] items-stretch gap-6 px-gutter">
        <Wordmark className="self-center" />
        <DesktopNav pathname={pathname} />

        <div className="ml-auto flex items-center gap-2">
          <ThemeMenu />
          <SessionControl className="hidden md:flex" />
          <MobileNav pathname={pathname} />
        </div>
      </div>
    </header>
  );
}

/**
 * The main navigation on wide screens. The safelight bar under the current page slides to the
 * next page when you navigate, so the move is visible; it does not animate on first paint.
 */
function DesktopNav({ pathname }: { pathname: string }) {
  const list = useRef<HTMLUListElement>(null);
  const [bar, setBar] = useState<{ left: number; width: number; animate: boolean } | null>(null);
  const activeHref = NAV_ITEMS.find((item) => isActive(pathname, item.href))?.href ?? null;

  useLayoutEffect(() => {
    const el = list.current;
    if (!el) return;
    const place = (animate: boolean) => {
      const link = activeHref ? el.querySelector<HTMLElement>(`a[href="${activeHref}"]`) : null;
      setBar((prev) => (link ? { ...underText(link), animate: animate && prev != null } : null));
    };
    place(true);
    const observer = new ResizeObserver(() => place(false));
    observer.observe(el);
    return () => observer.disconnect();
  }, [activeHref]);

  return (
    <nav aria-label="Main" className="hidden items-stretch md:flex">
      <ul ref={list} className="relative flex items-stretch">
        {NAV_ITEMS.map((item) => {
          const active = item.href === activeHref;
          return (
            <li key={item.href} className="flex">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex items-center px-3 text-sm no-underline transition-colors duration-[var(--dur-micro)]",
                  active ? "font-medium text-ink" : "text-ink-2 hover:text-ink",
                )}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
        {bar ? (
          <li
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute bottom-0 left-0 h-0.5 rounded-full bg-safelight",
              bar.animate &&
                "transition-[transform,width] duration-[var(--dur-panel)] ease-[var(--ease-arrive)]",
            )}
            style={{ width: bar.width, transform: `translateX(${bar.left}px)` }}
          />
        ) : null}
      </ul>
    </nav>
  );
}

/** The bar spans the link's text, inside its padding. */
function underText(link: HTMLElement): { left: number; width: number } {
  const pad = Number.parseFloat(getComputedStyle(link).paddingLeft) || 0;
  return { left: link.offsetLeft + pad, width: link.offsetWidth - 2 * pad };
}
