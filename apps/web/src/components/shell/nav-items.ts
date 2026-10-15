export interface NavItem {
  href: string;
  label: string;
  /** What the page is for, shown in the mobile menu. */
  hint: string;
}

/** The three pages. Everything else opens inside them, or redirects to them (lib/routes.ts). */
export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Line", hint: "Run your own data through the line, station by station" },
  {
    href: "/investigations",
    label: "Investigations",
    hint: "Reports with evidence, decisions and work orders",
  },
  { href: "/how", label: "How it works", hint: "Plain words, the measured results and the guide" },
];

export function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
