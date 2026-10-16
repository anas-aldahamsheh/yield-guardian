import { type ReactNode, ViewTransition } from "react";

/**
 * Transition types a link carries between a list and one of its items: deeper into the item, or
 * back up to the list. Pass them to `<Link transitionTypes>`.
 */
export const NAV_FORWARD = ["nav-forward"];
export const NAV_BACK = ["nav-back"];

const DIRECTIONS = { "nav-forward": "nav-forward", "nav-back": "nav-back", default: "none" };

/**
 * A page that slides the way the reader moves between a list and one of its items: forward, the
 * list leaves to the left and the item arrives from the right; back, the reverse. Only links
 * tagged with NAV_FORWARD or NAV_BACK move it, so every other navigation keeps the template's own
 * entrance. Browsers without view transitions swap the page at once.
 */
export function DirectionalPage({ children }: { children: ReactNode }) {
  return (
    <ViewTransition enter={DIRECTIONS} exit={DIRECTIONS} default="none">
      {children}
    </ViewTransition>
  );
}

/**
 * Something shown on both pages, such as an investigation's title in its list row and in its
 * page's heading: on the way between them it travels from one place to the other. Its child must
 * be a single element that is not split across lines (a block or an inline-block).
 */
export function Shared({ name, children }: { name: string; children: ReactNode }) {
  return (
    <ViewTransition name={name} share="morph" default="none">
      {children}
    </ViewTransition>
  );
}
