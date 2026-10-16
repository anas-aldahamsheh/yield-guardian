"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const subscribe = () => () => {};
const useThemeMounted = () =>
  useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );

/**
 * Switches the theme with transitions held until the new colours are on screen, so no control
 * fades on its own clock. Done here, on a reader's choice, rather than by next-themes, which
 * would restyle the whole page twice on every page load to do it.
 */
function switchTheme(setTheme: (theme: string) => void, theme: string) {
  const root = document.documentElement;
  root.classList.add("theme-switching");
  let done = false;
  const release = () => {
    if (done) return;
    done = true;
    observer.disconnect();
    window.clearTimeout(fallback);
    // The new colours are styled with transitions off, then transitions come back.
    void getComputedStyle(root).color;
    requestAnimationFrame(() => root.classList.remove("theme-switching"));
  };
  const observer = new MutationObserver(release);
  observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  const fallback = window.setTimeout(release, 400);
  setTheme(theme);
}

/**
 * Light is the cleanroom, dark is silicon; the line's instrument screens are dark glass in both.
 * One press switches to the other theme; the icon and label name that action. Until the reader
 * picks one, the theme follows the system. The icon the page arrives with is simply there; once
 * the reader switches, each new icon turns in.
 */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useThemeMounted();
  const shown = mounted && resolvedTheme ? resolvedTheme : null;
  const [first, setFirst] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);
  if (shown !== null && first === null) setFirst(shown);
  if (first !== null && shown !== first && !changed) setChanged(true);
  const next = shown === "dark" ? "light" : "dark";
  const Icon = shown === "dark" ? Sun : Moon;
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={shown ? `Switch to ${next} theme` : "Switch theme"}
      disabled={!shown}
      onClick={() => switchTheme(setTheme, next)}
    >
      <Icon
        key={shown ?? "unknown"}
        className={cn(
          "size-[18px]",
          !shown && "invisible",
          changed &&
            "animate-in duration-[480ms] ease-spring fade-in-0 zoom-in-75 spin-in-[-60deg]",
        )}
        strokeWidth={1.75}
        aria-hidden="true"
      />
    </Button>
  );
}
