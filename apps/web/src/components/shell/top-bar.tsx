"use client";

import { History, Menu } from "lucide-react";
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
import { ModelFailureDialog } from "./model-failure-dialog";
import { ProviderSwitch } from "./provider-switch";
import { ThemeToggle } from "./theme-toggle";
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

const HistorySheet = dynamic(
  () => import("@/components/workspace/history-sheet").then((m) => m.HistorySheet),
  { ssr: false },
);

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
 * The bar lifts once the page scrolls under it: a hairline and a soft shadow appear under the
 * opaque canvas (no blurred backdrop: nearly opaque, it showed nothing, and it cost every frame
 * the page drew). The scroll position is written as an attribute, so scrolling renders nothing
 * in React.
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
  const [historyOpen, setHistoryOpen] = useState(false);

  // Fixed, with a spacer of the bar's height in the page's flow.
  return (
    <>
      <div aria-hidden="true" className="h-bar shrink-0" />
      <header
        ref={ref}
        className={cn(
          "group/bar fixed inset-x-0 top-0 z-40 bg-canvas transition-shadow duration-(--dur-3) ease-out",
          "data-[scrolled]:shadow-[0_1px_0_var(--hairline),0_12px_32px_-24px_rgb(0_0_0/0.35)]",
        )}
      >
        <div className="mx-auto flex h-bar max-w-[1600px] items-center justify-between px-gutter">
          <div className="flex items-center shrink-0">
            <Wordmark />
          </div>

          <div className="hidden md:flex flex-1 justify-center px-4">
            <DesktopNav pathname={pathname} />
          </div>

          <div className="flex items-center justify-end gap-2.5 shrink-0">
            <ProviderSwitch className="hidden sm:inline-flex" />
            <button
              type="button"
              onClick={() => setHistoryOpen(true)}
              className="press group inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-full border border-hairline bg-surface-2 px-3 text-[12px] font-[580] text-ink shadow-2xs hover:border-hairline-strong hover:bg-surface-3 transition-colors"
              aria-label="Open Run History"
            >
              <History className="size-3.5 text-ink-2 group-hover:text-ink transition-colors" />
              <span>History</span>
            </button>
            <ThemeToggle />
            <MobileNav pathname={pathname} />
          </div>
        </div>
      </header>
      <HistorySheet open={historyOpen} onOpenChange={setHistoryOpen} />
      <ModelFailureDialog />
    </>
  );
}

/**
 * The main navigation on wide screens. The current page sits on a raised pill;
 * on navigation the pill slides to the next page.
 */
function DesktopNav({ pathname }: { pathname: string }) {
  const activeHref = NAV_ITEMS.find((item) => isActive(pathname, item.href))?.href ?? null;
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <nav aria-label="Main" className="hidden md:flex">
      <LayoutGroup id="main-nav">
        <ul className="flex items-center gap-1 rounded-full border border-hairline/80 bg-surface/80 p-1 shadow-2xs backdrop-blur-xs" onPointerLeave={() => setHovered(null)}>
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
                    className="absolute inset-0 rounded-full bg-surface-2 shadow-[inset_0_0_0_1px_var(--hairline-strong),0_1px_2px_rgb(0_0_0/0.05)] dark:bg-surface-3"
                  />
                ) : null}
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  onPointerEnter={() => setHovered(item.href)}
                  className={cn(
                    "relative flex h-8 items-center rounded-full px-3.5 text-[13.5px] leading-none whitespace-nowrap transition-colors duration-(--dur-1) cursor-pointer",
                    active ? "font-[600] text-ink" : "font-[500] text-ink-2 hover:text-ink",
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
