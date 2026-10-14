import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Reads the two colour palettes from globals.css for tests. The light palette sits on
 * `:root, [data-theme="light"]`; the yellow room on `[data-theme="dark"]` and again inside the
 * prefers-color-scheme media query. Throws if the two dark copies differ.
 */
export const globalsCss = readFileSync(
  path.join(import.meta.dirname, "../app/globals.css"),
  "utf8",
);

export type Theme = "light" | "dark";

function block(selector: string): Map<string, string> {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s*");
  const match = globalsCss.match(new RegExp(`(?:^|\\n)\\s*${escaped}\\s*\\{([^}]*)\\}`));
  if (!match) throw new Error(`No block for ${selector} in globals.css`);
  const tokens = new Map<string, string>();
  for (const m of match[1]!.matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)) {
    tokens.set(m[1]!, m[2]!.trim());
  }
  return tokens;
}

export const palettes: Record<Theme, Map<string, string>> = {
  light: block(':root,\n[data-theme="light"]'),
  dark: block('[data-theme="dark"]'),
};

export const systemDarkPalette = block(':root:not([data-theme="light"])');

/** A palette token as a hex colour, failing loudly if it is not one. */
export function paletteHex(name: string, theme: Theme): string {
  const value = palettes[theme].get(name);
  if (!value || !/^#[0-9a-f]{6}$/.test(value)) {
    throw new Error(`Token --${name} in the ${theme} palette is not a hex colour: ${value}`);
  }
  return value;
}
