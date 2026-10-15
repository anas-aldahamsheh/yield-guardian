"use client";

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
        <DropdownMenuLabel className="text-xs font-normal text-ink-3">Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={mounted ? (theme ?? "system") : "system"}
          onValueChange={setTheme}
        >
          <DropdownMenuRadioItem value="system">Match the system</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">Dark: the yellow room</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="light">Light: inspection light</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
