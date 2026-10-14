import * as THREE from "three";

import { safelightTokenHex } from "@/lib/optics/safelight";
import { FILM, type ExposurePlan, type DieLayout } from "@/lib/wafer/geometry";

import {
  dieFragmentShader,
  dieVertexShader,
  fieldFragmentShader,
  fieldVertexShader,
  substrateFragmentShader,
  substrateVertexShader,
} from "./shaders";

const KEY_DIR = new THREE.Vector3(-0.35, 1, 0.55).normalize();

/** Wafer outline with a notch at the bottom (towards the viewer), radius 1. */
function waferGeometry(): THREE.ExtrudeGeometry {
  const shape = new THREE.Shape();
  const notch = 0.035;
  const start = Math.PI / 2 + notch;
  shape.absarc(0, 0, 1, start, start + Math.PI * 2 - notch * 2, false);
  shape.lineTo(0, 1 - notch * 1.2);
  shape.closePath();
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: 0.022,
    bevelEnabled: false,
    curveSegments: 160,
  });
  // Shape y points up the map; lay it flat with the notch towards +z (the viewer).
  geometry.rotateX(Math.PI / 2);
  return geometry;
}

function hexToLinear(hex: string): THREE.Color {
  return new THREE.Color(hex).convertSRGBToLinear();
}

/** One frame of the stepper: where the field is, how bright, and what has been revealed. */
export interface StepperFrame {
  progress: number;
  x: number;
  y: number;
  size: number;
  flash: number;
  on: number;
  reveal: number;
}

export interface WaferObjects {
  root: THREE.Group;
  apply(frame: StepperFrame): void;
  dispose(): void;
}

/**
 * Builds the wafer as plain three.js objects: the substrate disc, one instanced mesh of dies and
 * the exposure field. Kept outside React so the stepper can drive uniforms directly.
 */
export function buildWafer(
  layout: DieLayout,
  plan: ExposurePlan,
  options: { failColor: string; roomGain?: number; inspectGain?: number },
): WaferObjects {
  const shared = {
    uFilmCentre: { value: FILM.centreNm },
    uEdgeDrop: { value: FILM.edgeDrop },
    uRoomGain: { value: options.roomGain ?? 0.42 },
    uInspectGain: { value: options.inspectGain ?? 1.05 },
    uKeyDir: { value: KEY_DIR },
  };
  const field = new THREE.Vector4(0, 0, 0, 0);

  const dieMaterial = new THREE.ShaderMaterial({
    vertexShader: dieVertexShader,
    fragmentShader: dieFragmentShader,
    uniforms: {
      ...shared,
      uProgress: { value: 0 },
      uField: { value: field },
      uFieldOn: { value: 0 },
      uFail: { value: hexToLinear(options.failColor) },
    },
  });
  const substrateMaterial = new THREE.ShaderMaterial({
    vertexShader: substrateVertexShader,
    fragmentShader: substrateFragmentShader,
    uniforms: { ...shared, uReveal: { value: 0 }, uNativeOxide: { value: 2 } },
  });
  const fieldMaterial = new THREE.ShaderMaterial({
    vertexShader: fieldVertexShader,
    fragmentShader: fieldFragmentShader,
    uniforms: {
      uLamp: { value: hexToLinear(safelightTokenHex()) },
      uFlash: { value: 0 },
      uOpacity: { value: 0 },
    },
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });

  const substrate = new THREE.Mesh(waferGeometry(), substrateMaterial);
  substrate.position.set(0, 0.022, 0);

  const dieGeometry = new THREE.PlaneGeometry(1, 1);
  dieGeometry.rotateX(-Math.PI / 2);
  const attr = new Float32Array(layout.dies.length * 2);
  layout.dies.forEach((die, i) => {
    attr[i * 2] = die.failed ? 2 : 1;
    attr[i * 2 + 1] = plan.dieField[i]!;
  });
  dieGeometry.setAttribute("aDie", new THREE.InstancedBufferAttribute(attr, 2));
  const dies = new THREE.InstancedMesh(dieGeometry, dieMaterial, layout.dies.length);
  const m = new THREE.Matrix4();
  const size = layout.pitch * 0.9;
  layout.dies.forEach((die, i) => {
    m.makeScale(size, 1, size);
    m.setPosition(die.x, 0.0235, die.y);
    dies.setMatrixAt(i, m);
  });
  dies.instanceMatrix.needsUpdate = true;
  dies.frustumCulled = false;

  const fieldGeometry = new THREE.PlaneGeometry(1, 1);
  fieldGeometry.rotateX(-Math.PI / 2);
  const fieldMesh = new THREE.Mesh(fieldGeometry, fieldMaterial);
  fieldMesh.renderOrder = 2;

  const root = new THREE.Group();
  root.add(substrate, dies, fieldMesh);

  return {
    root,
    apply(frame) {
      dieMaterial.uniforms.uProgress!.value = frame.progress;
      field.set(frame.x, frame.y, frame.size, frame.flash);
      dieMaterial.uniforms.uFieldOn!.value = frame.on;
      substrateMaterial.uniforms.uReveal!.value = frame.reveal;
      fieldMaterial.uniforms.uFlash!.value = frame.flash;
      fieldMaterial.uniforms.uOpacity!.value = frame.on;
      fieldMesh.position.set(frame.x, 0.03, frame.y);
      fieldMesh.scale.set(frame.size, 1, frame.size);
    },
    dispose() {
      substrate.geometry.dispose();
      dieGeometry.dispose();
      fieldGeometry.dispose();
      dies.dispose();
      dieMaterial.dispose();
      substrateMaterial.dispose();
      fieldMaterial.dispose();
    },
  };
}
