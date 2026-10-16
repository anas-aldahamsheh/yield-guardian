/**
 * Motion for the interface's sliding marks, in a chunk of their own: `m` components with the
 * full feature set (layout and shared-element transitions among them). MotionProvider fetches it
 * at the reader's first sign of activity, so Motion's renderer is not part of any page's first
 * load and never competes with the first paint.
 */
export { LazyMotion, domMax, m } from "framer-motion";
