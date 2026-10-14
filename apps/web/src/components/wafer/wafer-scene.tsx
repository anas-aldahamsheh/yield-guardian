"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import gsap from "gsap";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { type DieGrid, layoutDies, planExposure } from "@/lib/wafer/geometry";

import { buildWafer, type WaferObjects } from "./wafer-build";

/** A die the pointer is over, in map coordinates, with where the pointer is on the page. */
export interface DieHover {
  index: number;
  row: number;
  col: number;
  failed: boolean;
  field: number;
  clientX: number;
  clientY: number;
}

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
  /** Called each time the stepper moves to a new field (index), and with the field count at the end. */
  onField?: (field: number) => void;
  /** Called with the die under the pointer once the wafer is inspected, or null. */
  onHover?: (die: DieHover | null) => void;
  /** Ink colour of failed dies, hex. */
  failColor?: string;
}

const STAGE_EASE = gsap.parseEase("power2.inOut");
/** The wafer sits turned a little on the stage, so the serpentine path reads in depth. */
const BASE_YAW = -0.42;
const DIE_TOP = 0.0235;

function Wafer({
  grid,
  playKey,
  reducedMotion,
  duration = 5.2,
  onSequenceEnd,
  onReady,
  onField,
  onHover,
  failColor = "#eb556e",
}: WaferSceneProps) {
  const invalidate = useThree((s) => s.invalidate);
  const camera = useThree((s) => s.camera);
  const group = useRef<THREE.Group>(null);
  const objects = useRef<WaferObjects | null>(null);
  const tilt = useRef({ x: 0, y: 0, tx: 0, ty: 0 });
  const inspected = useRef(false);

  const { layout, plan, byCell } = useMemo(() => {
    const l = layoutDies(grid);
    const byCell = new Map(l.dies.map((d, i) => [d.index, i]));
    return { layout: l, plan: planExposure(grid, l, 6), byCell };
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

  // The scanner: the stage moves the wafer so the next field sits under the lens (stage move),
  // then a slit of light scans down the field and the results under it are revealed, field by
  // field in a serpentine path.
  useEffect(() => {
    const built = objects.current;
    if (!built) return;
    const n = plan.fields.length;
    let lastField = -1;
    const apply = (p: number) => {
      const i = Math.min(n - 1, Math.max(0, Math.floor(p)));
      const frac = Math.min(1, Math.max(0, p - i));
      const from = plan.fields[Math.max(0, i - 1)]!;
      const to = plan.fields[i]!;
      const move = STAGE_EASE(Math.min(1, frac / 0.38));
      const scanning = p < n && frac > 0.42 && frac < 0.92;
      built.apply({
        progress: p,
        x: from.x + (to.x - from.x) * move,
        y: from.y + (to.y - from.y) * move,
        size: to.size,
        flash: scanning ? Math.sin(((frac - 0.42) / 0.5) * Math.PI) : 0,
        scan: p >= n ? 1 : frac <= 0.42 ? 0 : Math.min(1, (frac - 0.42) / 0.5),
        on: p < n + 0.2 ? Math.min(1, p * 4, (n + 0.2 - p) * 5) : 0,
        reveal: Math.min(1, p / n),
      });
      const field = p >= n ? n : i;
      if (field !== lastField && (p >= n || frac > 0.5)) {
        lastField = field;
        onField?.(field);
      }
      invalidate();
    };

    inspected.current = false;
    if (reducedMotion) {
      apply(n + 1);
      inspected.current = true;
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
      delay: 0.5,
      onUpdate: () => apply(state.p),
      onComplete: () => {
        inspected.current = true;
        onSequenceEnd?.();
      },
    });
    return () => {
      tween.kill();
    };
    // playKey restarts the sequence; the callbacks are stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan, layout, playKey, reducedMotion, duration, failColor]);

  // The pointer: tilts the wafer a little (the film colours shift with the viewing angle) and,
  // once the wafer is inspected, outlines the die under it and reports that die's real result.
  const pointer = useThree((s) => s.pointer);
  const canvas = useThree((s) => s.gl.domElement);
  useEffect(() => {
    const raycaster = new THREE.Raycaster();
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -DIE_TOP);
    const hit = new THREE.Vector3();
    const inverse = new THREE.Matrix4();
    const ndc = new THREE.Vector2();
    let current = -1;

    const clear = () => {
      if (current !== -1) {
        current = -1;
        objects.current?.setHover(null);
        onHover?.(null);
      }
      invalidate();
    };
    const move = (event: PointerEvent) => {
      invalidate();
      if (!inspected.current || !group.current || event.pointerType === "touch") return;
      const box = canvas.getBoundingClientRect();
      ndc.set(((event.clientX - box.left) / box.width) * 2 - 1, -((event.clientY - box.top) / box.height) * 2 + 1);
      raycaster.setFromCamera(ndc, camera);
      inverse.copy(group.current.matrixWorld).invert();
      raycaster.ray.applyMatrix4(inverse);
      if (!raycaster.ray.intersectPlane(plane, hit)) return clear();
      const col = Math.floor(hit.x / layout.pitch + grid.width / 2);
      const row = Math.floor(hit.z / layout.pitch + grid.height / 2);
      const at = row >= 0 && row < grid.height && col >= 0 && col < grid.width ? byCell.get(row * grid.width + col) : undefined;
      if (at === undefined) return clear();
      const die = layout.dies[at]!;
      current = at;
      objects.current?.setHover({ x: die.x, y: die.y });
      onHover?.({
        index: die.index,
        row: die.row,
        col: die.col,
        failed: die.failed,
        field: plan.dieField[at]!,
        clientX: event.clientX,
        clientY: event.clientY,
      });
    };
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerleave", clear);
    return () => {
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerleave", clear);
    };
  }, [canvas, camera, invalidate, layout, plan, grid, byCell, onHover]);

  useFrame(() => {
    if (!group.current) return;
    if (reducedMotion) {
      group.current.rotation.set(0, BASE_YAW, 0);
      return;
    }
    const t = tilt.current;
    t.tx = pointer.y * 0.07;
    t.ty = pointer.x * 0.1;
    t.x += (t.tx - t.x) * 0.08;
    t.y += (t.ty - t.y) * 0.08;
    group.current.rotation.x = t.x;
    group.current.rotation.z = -t.y * 0.45;
    group.current.rotation.y = BASE_YAW + t.y * 0.35;
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
      camera={{ position: [0, 3.05, 3.1], fov: 30, near: 0.1, far: 20 }}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      onCreated={({ camera }) => camera.lookAt(0, -0.12, 0.02)}
      aria-hidden="true"
    >
      <Wafer {...props} />
    </Canvas>
  );
}
