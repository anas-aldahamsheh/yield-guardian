"use client";

import { Menu } from "lucide-react";
import { AnimatePresence, LayoutGroup } from "framer-motion";
import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ComponentProps, useEffect, useRef, useState } from "react";

import { Indicator } from "@/components/motion/indicator";
import { SPRING } from "@/components/motion/springs";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { NAV_ITEMS, isActive } from "./nav-items";
import { SessionControl } from "./session-control";
import { ThemeMenu } from "./theme-menu";
import { Wordmark } from "./wordmark";

/** The narrow-screen menu button. */
export function MenuButton({ className, ...props }: ComponentProps<typeof Button>) {
  return (
    <Button
      variant="ghost"
      size="icon"
      className={cn("md:hidden", className)}
      aria-label="Open the menu"
      {...props}
    >
      <Menu className="size-5" strokeWidth={1.75} aria-hidden="true" />
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

/**
 * The bar floats once the page scrolls under it: the canvas turns to frosted glass (blurred and
 * nearly opaque, so nothing reads through) and a hairline appears. The scroll position is written
 * as an attribute, so scrolling renders nothing in React.
 */
function useScrolledAttribute() {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      el.toggleAttribute("data-scrolled", window.scrollY > 4);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);
  return ref;
}

export function TopBar() {
  const pathname = usePathname();
  const ref = useScrolledAttribute();

  // Fixed rather than sticky (Chromium does not blur the backdrop of this sticky bar), with a
  // spacer of the bar's height in the page's flow.
  return (
    <>
      <div aria-hidden="true" className="h-bar shrink-0" />
      <header
        ref={ref}
        className={cn(
          "group/bar fixed inset-x-0 top-0 z-40 bg-canvas transition-[background-color,box-shadow] duration-(--dur-3) ease-out",
          "data-[scrolled]:bg-canvas/95 data-[scrolled]:shadow-[0_1px_0_var(--hairline),0_12px_32px_-24px_rgb(0_0_0/0.35)] data-[scrolled]:backdrop-blur-2xl data-[scrolled]:backdrop-saturate-[1.8]",
        )}
      >
        <div className="mx-auto flex h-bar max-w-[1600px] items-center gap-4 px-gutter md:gap-8">
          <Wordmark />
          <DesktopNav pathname={pathname} />

          <div className="ml-auto flex items-center gap-1.5">
            <ThemeMenu />
            <SessionControl className="hidden md:flex" />
            <MobileNav pathname={pathname} />
          </div>
        </div>
      </header>
    </>
  );
}

/**
 * The main navigation on wide screens. The current page sits on a raised pill with the film's
 * light along its foot; on navigation the pill slides to the next page (shared layout). A paler
 * pill follows the pointer over the other pages. Nothing moves on the first paint.
 */
function DesktopNav({ pathname }: { pathname: string }) {
  const activeHref = NAV_ITEMS.find((item) => isActive(pathname, item.href))?.href ?? null;
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <nav aria-label="Main" className="hidden md:flex">
      <LayoutGroup id="main-nav">
        <ul className="flex items-center gap-0.5" onPointerLeave={() => setHovered(null)}>
          {NAV_ITEMS.map((item) => {
            const active = item.href === activeHref;
            return (
              <li key={item.href} className="relative flex">
                <AnimatePresence>
                  {hovered === item.href && !active ? (
                    <Indicator
                      key="hover"
                      layoutId="nav-hover"
                      fade
                      transition={SPRING.hover}
                      className="absolute inset-0 rounded-full bg-surface-2"
                    />
                  ) : null}
                </AnimatePresence>
                {active ? (
                  <Indicator
                    layoutId="nav-current"
                    className="absolute inset-0 rounded-full bg-surface shadow-[inset_0_0_0_1px_var(--hairline),0_1px_2px_rgb(0_0_0/0.06)] dark:bg-surface-2"
                  >
                    <span className="film-light absolute inset-x-3.5 bottom-[3px] h-[2px] rounded-full" />
                  </Indicator>
                ) : null}
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  onPointerEnter={() => setHovered(item.href)}
                  className={cn(
                    "relative flex h-9 items-center rounded-full px-4 text-[14px] leading-5 font-[540] no-underline transition-colors duration-(--dur-1)",
                    active ? "text-ink" : "text-ink-2 hover:text-ink",
                  )}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </LayoutGroup>
    </nav>
  );
}
