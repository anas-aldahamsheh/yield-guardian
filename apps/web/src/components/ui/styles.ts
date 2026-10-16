/*
 * Class strings the floating layers share, so a menu, a select and a popover look and move alike.
 * Entrances spring in from the trigger's side (ease-spring, docs/DESIGN.md); exits are quick and
 * plain. Tailwind reads these literals, so every class must appear whole.
 */

/** The room behind a dialog or a sheet: dimmed, a little out of focus. */
export const scrim =
  "fixed inset-0 z-50 bg-(--scrim) backdrop-blur-[3px] " +
  "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:duration-(--dur-3) data-[state=open]:ease-out " +
  "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:duration-(--dur-2) data-[state=closed]:ease-in";

/** A floating plane of silicon: menus, selects and popovers. */
export const floating =
  "z-50 rounded-[14px] bg-surface text-ink shadow-overlay ring-1 ring-hairline outline-none " +
  "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=open]:duration-[380ms] data-[state=open]:ease-spring " +
  "data-[side=bottom]:slide-in-from-top-1 data-[side=left]:slide-in-from-right-1 data-[side=right]:slide-in-from-left-1 data-[side=top]:slide-in-from-bottom-1 " +
  "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-98 data-[state=closed]:duration-[120ms] data-[state=closed]:ease-in";

/** One row of a menu or a select. Pointer: a raised plane. Keyboard: the signal ring inside. */
export const menuItem =
  "relative flex min-h-9 cursor-default items-center gap-2.5 rounded-[9px] px-2.5 py-1.5 text-[14px] leading-5 text-ink outline-none select-none " +
  "transition-colors duration-(--dur-1) data-[highlighted]:bg-surface-2 " +
  "focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-signal " +
  "data-[disabled]:pointer-events-none data-[disabled]:opacity-45 " +
  "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 [&_svg:not([class*='text-'])]:text-ink-3";

/** A dialog's plane: centred, springs up from a little below and a little smaller. */
export const dialogPlane =
  "fixed top-1/2 left-1/2 z-50 grid w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 gap-5 rounded-[20px] bg-surface p-6 text-ink shadow-overlay ring-1 ring-hairline outline-none sm:p-7 " +
  "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-96 data-[state=open]:slide-in-from-bottom-3 data-[state=open]:duration-[460ms] data-[state=open]:ease-spring " +
  "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-98 data-[state=closed]:duration-[150ms] data-[state=closed]:ease-in";

/** The round close control in a dialog's or a sheet's corner. */
export const closeControl =
  "press absolute top-4 right-4 inline-flex size-9 items-center justify-center rounded-full text-ink-2 hover:bg-surface-2 hover:text-ink disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:size-[18px] [&_svg]:shrink-0";
