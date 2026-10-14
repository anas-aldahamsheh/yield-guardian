import { useMemo } from "react";

import { linearSrgbToHex } from "@/lib/optics/oklab";
import { sampledFilmColor, spectralSamples } from "@/lib/optics/spectral-samples";
import { type DieGrid, filmThicknessAt, layoutDies } from "@/lib/wafer/geometry";
import { cn } from "@/lib/utils";

const RINGS = 10;
let samples: ReturnType<typeof spectralSamples> | null = null;

/** Film colour of a ring of the wafer under white light, seen from `angleDeg`. */
function ringColour(ring: number, angleDeg: number): string {
  samples ??= spectralSamples();
  const r = (ring + 0.5) / RINGS;
  const rgb = sampledFilmColor(samples, filmThicknessAt(r, 0), angleDeg).map((c) => c * 1.05) as [
    number,
    number,
    number,
  ];
  return linearSrgbToHex(rgb);
}

/** Bare silicon with its native oxide, dimmed like the substrate in the 3D view. */
function bareSilicon(angleDeg: number): string {
  samples ??= spectralSamples();
  return linearSrgbToHex(sampledFilmColor(samples, 2, angleDeg).map((c) => c * 0.82) as [number, number, number]);
}

/** The hero is always the dark bay, so the poster carries that theme's --fail. */
const FAIL_DARK = "#eb556e";

/** An SVG as a data URI. Only the characters a URI cannot carry are escaped, to keep it small. */
function svgDataUri(svg: string): string {
  return `data:image/svg+xml,${svg.replace(/"/g, "'").replace(/%/g, "%25").replace(/#/g, "%23").replace(/</g, "%3C").replace(/>/g, "%3E")}`;
}

/**
 * The wafer drawn flat in SVG with the same physics as the 3D view: the first paint of the home
 * page, the fallback without WebGL, and the still image for reduced motion. Dies are grouped
 * into rings of equal film thickness so the markup stays small.
 *
 * It is an <img> of that SVG rather than inline SVG: an image is a Largest Contentful Paint
 * candidate and inline SVG is not, and as a data URI it paints with the first frame, with no
 * request. One attribute also hydrates faster than a tree of paths.
 */
export function WaferPoster({
  grid,
  className,
  angleDeg = 30,
}: {
  grid: DieGrid;
  className?: string;
  angleDeg?: number;
}) {
  const src = useMemo(() => {
    const layout = layoutDies(grid);
    const rings = Array.from({ length: RINGS }, () => [] as string[]);
    const inks: string[] = [];
    const s = layout.pitch * 0.9;
    const k = (v: number) => Math.round(v * 1e4) / 1e4;
    for (const die of layout.dies) {
      const ring = Math.min(RINGS - 1, Math.floor(Math.hypot(die.x, die.y) * RINGS));
      rings[ring]!.push(`M${k(die.x - s / 2)} ${k(die.y - s / 2)}h${k(s)}v${k(s)}h${k(-s)}z`);
      if (die.failed) inks.push(`M${k(die.x)} ${k(die.y)}m${k(-s * 0.27)} 0a${k(s * 0.27)} ${k(s * 0.27)} 0 1 0 ${k(s * 0.54)} 0a${k(s * 0.27)} ${k(s * 0.27)} 0 1 0 ${k(-s * 0.54)} 0`);
    }
    const paths = [
      `<path d="M-0.035 -0.999A1 1 0 1 0 0.035 -0.999L0 -0.958Z" transform="rotate(180)" fill="${bareSilicon(angleDeg)}"/>`,
      ...rings.map((d, i) => (d.length ? `<path d="${d.join("")}" fill="${ringColour(i, angleDeg)}"/>` : "")),
      inks.length ? `<path d="${inks.join("")}" fill="${FAIL_DARK}"/>` : "",
    ];
    return svgDataUri(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1.04 -1.04 2.08 2.08" width="780" height="780">${paths.join("")}</svg>`,
    );
  }, [grid, angleDeg]);

  // A data URI: next/image would add nothing. Decorative, as the figure around it is labelled.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt="" width={780} height={780} decoding="sync" fetchPriority="high" className={cn("block size-full", className)} />;
}
