"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import { ThemeButton, useThemeMounted } from "./theme-menu";

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

/** The theme menu itself, loaded when someone first presses the button; it opens at once. */
export default function ThemeMenuFull() {
  const { theme, setTheme } = useTheme();
  const mounted = useThemeMounted();

  return (
    <DropdownMenu defaultOpen>
      <DropdownMenuTrigger asChild>
        <ThemeButton />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={mounted ? (theme ?? "system") : "system"}
          onValueChange={(value) => switchTheme(setTheme, value)}
        >
          <DropdownMenuRadioItem value="system">
            <Monitor strokeWidth={1.75} aria-hidden="true" />
            Match the system
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="light">
            <Sun strokeWidth={1.75} aria-hidden="true" />
            Light
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <Moon strokeWidth={1.75} aria-hidden="true" />
            Dark
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
