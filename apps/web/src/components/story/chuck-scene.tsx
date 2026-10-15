"use client";

import { Canvas, useThree } from "@react-three/fiber";
import type { WaferPatternItem } from "@yield-guardian/contracts";
import { useEffect, useMemo, useRef } from "react";
import type * as THREE from "three";

import { buildWafer, type WaferObjects } from "@/components/wafer/wafer-build";
import { layoutDies, planExposure } from "@/lib/wafer/geometry";

import { gridOf } from "./probe-order";
import type { SceneStore } from "./scene";

/**
 * The wafer on the prober chuck, in 3D: the real map on a thin-film wafer, probed die by die in
 * probe order (one die per field of the stepper plan, a serpentine by rows), each die's recorded
 * result revealed as the probe passes it. The camera looks down at the angle that puts the
 * overhead lamp's reflection across the wafer; the map is not turned, so it reads as the flat map
 * in the drawer does. Frames render on demand only, when the scene changes.
 */

/** Camera elevation (55 degrees, the overhead lamp's mirror angle) and distance. */
const ELEVATION = (55 * Math.PI) / 180;
const DISTANCE = 4.4;

/**
 * The canvas is small and a dense map has dies of a pixel or two, so it is drawn at twice the
 * screen's pixels (at most 3 device pixels per CSS pixel) and scaled down: the die grid does not
 * shimmer into moire.
 */
function supersample(): number {
  return Math.min(3, Math.max(2, (window.devicePixelRatio || 1) * 2));
}

function cssHex(el: Element, name: string, fallback: string) {
  const v = getComputedStyle(el).getPropertyValue(name).trim();
  return /^#[0-9a-f]{6}$/i.test(v) ? v : fallback;
}

function Chuck({
  store,
  wafers,
  onReady,
}: {
  store: SceneStore;
  wafers: WaferPatternItem[];
  onReady: () => void;
}) {
  const invalidate = useThree((s) => s.invalidate);
  const el = useThree((s) => s.gl.domElement);
  const holder = useRef<THREE.Group>(null);
  const failHex = useMemo(() => cssHex(el, "--fail", "#eb556e"), [el]);

  // The wafer follows the scene: rebuilt when the prober takes the next wafer, revealed die by
  // die as the dies count advances.
  useEffect(() => {
    const parent = holder.current;
    if (!parent) return;
    let objects: WaferObjects | null = null;
    let plan: { index: number; fields: { x: number; y: number; size: number }[] } | null = null;
    const show = () => {
      const scene = store.get();
      const index = scene.wafer;
      if (index == null) return;
      if (!plan || plan.index !== index) {
        const wafer = wafers.find((w) => w.index === index);
        if (!wafer) return;
        if (objects) {
          parent.remove(objects.root);
          objects.dispose();
        }
        const grid = gridOf(wafer.map);
        const layout = layoutDies(grid);
        const exposure = planExposure(grid, layout, Math.max(grid.height, grid.width));
        objects = buildWafer(layout, exposure, { failColor: failHex });
        parent.add(objects.root);
        plan = { index, fields: exposure.fields };
      }
      const fields = plan.fields;
      const n = fields.length;
      const p = Math.min(n + 0.25, scene.dies);
      const i = Math.min(n - 1, Math.max(0, Math.floor(p)));
      const f = fields[i]!;
      const probing = p < n;
      objects?.apply({
        progress: probing ? p : n + 1,
        x: f.x,
        y: f.y,
        size: f.size * 1.6,
        flash: probing ? 0.5 : 0,
        scan: probing ? p - Math.floor(p) : 1,
        on: probing ? 1 : 0,
        reveal: Math.min(1, p / n),
      });
      invalidate();
    };
    show();
    onReady();
    const stop = store.subscribe(show);
    return () => {
      stop();
      if (objects) {
        parent.remove(objects.root);
        objects.dispose();
      }
    };
  }, [store, wafers, failHex, invalidate, onReady]);

  return <group ref={holder} />;
}

export default function ChuckScene(props: {
  store: SceneStore;
  wafers: WaferPatternItem[];
  onReady: () => void;
}) {
  return (
    <Canvas
      flat
      dpr={supersample()}
      frameloop="demand"
      camera={{
        position: [0, DISTANCE * Math.sin(ELEVATION), DISTANCE * Math.cos(ELEVATION)],
        fov: 30,
        near: 0.1,
        far: 20,
      }}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      onCreated={({ camera }) => camera.lookAt(0, -0.04, 0.06)}
      aria-hidden="true"
      style={{ pointerEvents: "none" }}
    >
      <Chuck {...props} />
    </Canvas>
  );
}
