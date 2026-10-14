"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import * as THREE from "three";

import { type DieGrid, layoutDies } from "@/lib/wafer/geometry";

/**
 * The lot as a stack of wafers in a cassette, slot 1 at the bottom. Failed dies are drawn in the
 * fail colour on every wafer, so a pattern repeated through the lot lines up vertically. The
 * chosen wafer slides out of the stack.
 */
export interface StackWafer {
  slot: number;
  grid: DieGrid | null;
}

const GAP = 0.085;

function readColour(name: string, fallback: string) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return new THREE.Color(/^#[0-9a-f]{6}$/i.test(v) ? v : fallback);
}

function buildStack(wafers: StackWafer[]) {
  const root = new THREE.Group();
  const fail = readColour("--fail", "#eb556e");
  const passTone = readColour("--ink-3", "#96948a");
  const disc = new THREE.CylinderGeometry(1, 1, 0.012, 96);
  const die = new THREE.BoxGeometry(1, 0.004, 1);
  const discMaterial = new THREE.MeshBasicMaterial({ color: readColour("--die-2", "#24221b"), transparent: true, opacity: 0.92 });
  const edgeMaterial = new THREE.LineBasicMaterial({ color: readColour("--hairline-strong", "#4f4c43") });
  const failMaterial = new THREE.MeshBasicMaterial({ color: fail });
  const passMaterial = new THREE.MeshBasicMaterial({ color: passTone, transparent: true, opacity: 0.18 });
  const ring = new THREE.EdgesGeometry(new THREE.CylinderGeometry(1, 1, 0.012, 96), 30);
  const slots: THREE.Group[] = [];
  const m = new THREE.Matrix4();
  const disposables: { dispose(): void }[] = [disc, die, discMaterial, edgeMaterial, failMaterial, passMaterial, ring];

  for (const w of wafers) {
    const g = new THREE.Group();
    g.position.y = (w.slot - 1) * GAP;
    g.userData.slot = w.slot;
    const body = new THREE.Mesh(disc, discMaterial);
    body.userData.slot = w.slot;
    g.add(body, new THREE.LineSegments(ring, edgeMaterial));
    if (w.grid) {
      const layout = layoutDies(w.grid);
      const failed = layout.dies.filter((d) => d.failed);
      const passed = layout.dies.filter((d) => !d.failed);
      const s = layout.pitch * 0.86;
      for (const [list, material] of [
        [failed, failMaterial],
        [passed, passMaterial],
      ] as const) {
        if (!list.length) continue;
        const mesh = new THREE.InstancedMesh(die, material, list.length);
        list.forEach((d, i) => {
          m.makeScale(s, 1, s);
          m.setPosition(d.x, 0.009, d.y);
          mesh.setMatrixAt(i, m);
        });
        mesh.instanceMatrix.needsUpdate = true;
        mesh.raycast = () => {};
        g.add(mesh);
        disposables.push(mesh);
      }
    }
    slots.push(g);
    root.add(g);
  }
  root.position.y = -((wafers.length - 1) * GAP) / 2;
  /** Move every slot one frame towards its place; returns true while any is still moving. */
  const step = (target: number | null, immediate: boolean) => {
    let moving = false;
    for (const g of slots) {
      const out = g.userData.slot === target ? 1.35 : 0;
      const next = immediate ? out : g.position.x + (out - g.position.x) * 0.14;
      const settled = Math.abs(out - next) <= 1e-3;
      if (!settled) moving = true;
      g.position.x = settled ? out : next;
    }
    return moving;
  };
  return { root, step, dispose: () => disposables.forEach((d) => d.dispose()) };
}

function Stack({
  wafers,
  selected,
  onSelect,
  reducedMotion,
}: {
  wafers: StackWafer[];
  selected: number | null;
  onSelect: (slot: number) => void;
  reducedMotion: boolean;
}) {
  const invalidate = useThree((s) => s.invalidate);
  const parent = useRef<THREE.Group>(null);
  const built = useRef<ReturnType<typeof buildStack> | null>(null);
  const target = useRef<number | null>(selected);

  useEffect(() => {
    const p = parent.current;
    if (!p) return;
    const b = buildStack(wafers);
    p.add(b.root);
    built.current = b;
    invalidate();
    return () => {
      p.remove(b.root);
      b.dispose();
      built.current = null;
    };
  }, [wafers, invalidate]);

  useEffect(() => {
    target.current = selected;
    invalidate();
  }, [selected, invalidate]);

  useFrame(() => {
    if (built.current?.step(target.current, reducedMotion)) invalidate();
  });

  return (
    <group
      ref={parent}
      rotation={[0, -0.5, 0]}
      onClick={(e) => {
        e.stopPropagation();
        const slot = e.object.userData.slot as number | undefined;
        if (slot != null) onSelect(slot);
      }}
    />
  );
}

export default function LotStackScene(props: {
  wafers: StackWafer[];
  selected: number | null;
  onSelect: (slot: number) => void;
  reducedMotion: boolean;
}) {
  return (
    <Canvas
      flat
      dpr={[1, 2]}
      frameloop="demand"
      camera={{ position: [0, 2.3, 6.2], fov: 30, near: 0.1, far: 30 }}
      gl={{ antialias: true, alpha: true }}
      onCreated={({ camera }) => camera.lookAt(0.35, 0, 0)}
      aria-hidden="true"
    >
      <Stack {...props} />
    </Canvas>
  );
}
