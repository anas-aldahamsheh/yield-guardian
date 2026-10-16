import type { Transition } from "framer-motion";

/**
 * The interface's springs (docs/DESIGN.md, "Motion"). Every Motion animation takes one of these,
 * so the whole interface moves with one physics.
 */
export const SPRING = {
  /** Buttons and rows going down under a press. */
  press: { type: "spring", stiffness: 700, damping: 40, mass: 0.6 },
  /** Lifts, the hover pill, the magnetic primary action. */
  hover: { type: "spring", stiffness: 420, damping: 32 },
  /** Layout changes, shared elements, the navigation indicator. */
  layout: { type: "spring", stiffness: 320, damping: 36 },
  /** A result arriving: numbers, chips, alarms (a slight overshoot). */
  arrive: { type: "spring", stiffness: 190, damping: 22 },
  /** The final-test stamp landing. */
  stamp: { type: "spring", stiffness: 260, damping: 15 },
} as const satisfies Record<string, Transition>;

/** Expo-out, for tweens that must end exactly (opacity, drawing a path). */
export const EASE_OUT = [0.22, 1, 0.36, 1] as const;
