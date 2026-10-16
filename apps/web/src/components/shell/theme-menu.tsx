"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import dynamic from "next/dynamic";
import { type ComponentProps, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const subscribe = () => () => {};
export const useThemeMounted = () =>
  useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );

/**
 * The theme button; its icon shows the theme in use. The icon the page arrives with is simply
 * there; once the reader picks another theme, each new icon turns in.
 */
export function ThemeButton(props: ComponentProps<typeof Button>) {
  const { resolvedTheme } = useTheme();
  const mounted = useThemeMounted();
  const shown = mounted ? (resolvedTheme ?? "system") : null;
  const [first, setFirst] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);
  if (shown !== null && first === null) setFirst(shown);
  if (first !== null && shown !== first && !changed) setChanged(true);
  const Icon = !mounted ? Monitor : resolvedTheme === "dark" ? Moon : Sun;
  return (
    <Button variant="ghost" size="icon" aria-label="Choose the colour theme" {...props}>
      <Icon
        key={shown ?? "system"}
        className={cn(
          "size-[18px]",
          changed &&
            "animate-in duration-[480ms] ease-spring fade-in-0 zoom-in-75 spin-in-[-60deg]",
        )}
        strokeWidth={1.75}
        aria-hidden="true"
      />
    </Button>
  );
}

const load = () => import("./theme-menu-full");
const ThemeMenuFull = dynamic(load, {
  ssr: false,
  loading: () => <ThemeButton aria-haspopup="menu" disabled />,
});

/**
 * Light is the cleanroom, dark is silicon; the line's instrument screens are dark glass in both.
 * The menu (Radix and its positioning code) is fetched when someone points at or focuses the
 * button and mounts, already open, when they press it: no page loads it for its first paint.
 */
export function ThemeMenu() {
  const [opened, setOpened] = useState(false);
  if (opened) return <ThemeMenuFull />;
  return (
    <ThemeButton
      aria-haspopup="menu"
      aria-expanded={false}
      onClick={() => setOpened(true)}
      onPointerEnter={() => void load()}
      onFocus={() => void load()}
    />
  );
}
