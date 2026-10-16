import type { ReactNode } from "react";

/**
 * Every navigation mounts a new template, so each page settles in once as it arrives: one
 * opacity and rise of the whole page (`.page-enter`, CSS, so it runs before hydration). Nothing
 * fades in section by section.
 */
export default function Template({ children }: { children: ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
