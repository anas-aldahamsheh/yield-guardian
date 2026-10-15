"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import dynamic from "next/dynamic";
import { type ComponentProps, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";

const subscribe = () => () => {};
export const useThemeMounted = () =>
  useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );

/** The theme button; its icon shows the theme in use. */
export function ThemeButton(props: ComponentProps<typeof Button>) {
  const { resolvedTheme } = useTheme();
  const mounted = useThemeMounted();
  const Icon = !mounted ? Monitor : resolvedTheme === "dark" ? Moon : Sun;
  return (
    <Button variant="ghost" size="icon-sm" aria-label="Choose the colour theme" {...props}>
      <Icon className="size-4" aria-hidden="true" />
    </Button>
  );
}

const load = () => import("./theme-menu-full");
const ThemeMenuFull = dynamic(load, {
  ssr: false,
  loading: () => <ThemeButton aria-haspopup="menu" disabled />,
});

/**
 * Dark is the yellow room; light is the same bay under white inspection light. The menu (Radix
 * and its positioning code) is fetched when someone points at or focuses the button and mounts,
 * already open, when they press it: no page loads it for its first paint.
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
