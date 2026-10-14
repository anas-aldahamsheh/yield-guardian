"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import gsap from "gsap";
import { useEffect, useMemo, useRef } from "react";
import type * as THREE from "three";

import { type DieGrid, layoutDies, planExposure } from "@/lib/wafer/geometry";

import { buildWafer, type WaferObjects } from "./wafer-build";

export interface WaferSceneProps {
  grid: DieGrid;
  /** Change to replay the exposure sequence. */
  playKey: number;
  /** Show the wafer fully inspected and still. */
  reducedMotion: boolean;
  /** Sequence length in seconds. */
  duration?: number;
  onSequenceEnd?: () => void;
  onReady?: () => void;
  /** Ink colour of failed dies, hex. */
  failColor?: string;
}

const STAGE_EASE = gsap.parseEase("power2.inOut");

function Wafer({
  grid,
  playKey,
  reducedMotion,
  duration = 4.6,
  onSequenceEnd,
  onReady,
  failColor = "#eb556e",
}: WaferSceneProps) {
  const invalidate = useThree((s) => s.invalidate);
  const group = useRef<THREE.Group>(null);
  const objects = useRef<WaferObjects | null>(null);
  const tilt = useRef({ x: 0, y: 0, tx: 0, ty: 0 });

  const { layout, plan } = useMemo(() => {
    const l = layoutDies(grid);
    return { layout: l, plan: planExposure(grid, l, 6) };
  }, [grid]);

  // Build the GPU objects outside React's render, and free them when the wafer changes.
  useEffect(() => {
    const parent = group.current;
    if (!parent) return;
    const built = buildWafer(layout, plan, { failColor });
    parent.add(built.root);
    objects.current = built;
    invalidate();
    return () => {
      parent.remove(built.root);
      built.dispose();
      objects.current = null;
    };
  }, [layout, plan, failColor, invalidate]);

  // The stepper: the field moves to each site (stage move), exposes it (flash) and reveals the
  // results under it, field by field in a serpentine path.
  useEffect(() => {
    const built = objects.current;
    if (!built) return;
    const n = plan.fields.length;
    const apply = (p: number) => {
      const i = Math.min(n - 1, Math.max(0, Math.floor(p)));
      const frac = Math.min(1, Math.max(0, p - i));
      const from = plan.fields[Math.max(0, i - 1)]!;
      const to = plan.fields[i]!;
      const move = STAGE_EASE(Math.min(1, frac / 0.4));
      built.apply({
        progress: p,
        x: from.x + (to.x - from.x) * move,
        y: from.y + (to.y - from.y) * move,
        size: to.size,
        flash: frac > 0.45 && frac < 0.85 ? Math.sin(((frac - 0.45) / 0.4) * Math.PI) : 0,
        on: p < n + 0.2 ? Math.min(1, p * 4, (n + 0.2 - p) * 5) : 0,
        reveal: Math.min(1, p / n),
      });
      invalidate();
    };

    if (reducedMotion) {
      apply(n + 1);
      onReady?.();
      return;
    }
    const state = { p: 0 };
    apply(0);
    onReady?.();
    const tween = gsap.to(state, {
      p: n + 0.25,
      duration,
      ease: "none",
      delay: 0.35,
      onUpdate: () => apply(state.p),
      onComplete: () => onSequenceEnd?.(),
    });
    return () => {
      tween.kill();
    };
    // playKey restarts the sequence; the callbacks are stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan, layout, playKey, reducedMotion, duration, failColor]);

  // A small tilt that follows the pointer: the film colours shift with the viewing angle.
  const pointer = useThree((s) => s.pointer);
  const canvas = useThree((s) => s.gl.domElement);
  useEffect(() => {
    if (reducedMotion) return;
    const wake = () => invalidate();
    canvas.addEventListener("pointermove", wake);
    canvas.addEventListener("pointerleave", wake);
    return () => {
      canvas.removeEventListener("pointermove", wake);
      canvas.removeEventListener("pointerleave", wake);
    };
  }, [canvas, invalidate, reducedMotion]);
  useFrame(() => {
    if (reducedMotion || !group.current) return;
    const t = tilt.current;
    t.tx = pointer.y * 0.06;
    t.ty = pointer.x * 0.08;
    t.x += (t.tx - t.x) * 0.08;
    t.y += (t.ty - t.y) * 0.08;
    group.current.rotation.x = t.x;
    group.current.rotation.z = -t.y * 0.5;
    group.current.rotation.y = t.y * 0.35;
    if (Math.abs(t.tx - t.x) > 1e-4 || Math.abs(t.ty - t.y) > 1e-4) invalidate();
  });

  return <group ref={group} />;
}

export default function WaferScene(props: WaferSceneProps) {
  return (
    <Canvas
      flat
      dpr={[1, 2]}
      frameloop="demand"
      camera={{ position: [0, 3.5, 2.45], fov: 30, near: 0.1, far: 20 }}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      onCreated={({ camera }) => camera.lookAt(0, -0.05, 0.08)}
      aria-hidden="true"
    >
      <Wafer {...props} />
    </Canvas>
  );
}
