import * as THREE from "three";

import { signalTokenHex } from "@/lib/optics/oxide";
import { FILM, type ExposurePlan, type DieLayout } from "@/lib/wafer/geometry";

import {
  dieFragmentShader,
  dieVertexShader,
  fieldFragmentShader,
  fieldVertexShader,
  stageFragmentShader,
  stageVertexShader,
  substrateFragmentShader,
  substrateVertexShader,
} from "./shaders";

/** The overhead lamp: above and behind the wafer, a long tube running left to right, placed so its mirror image crosses the wafer from the default view. */
const KEY_DIR = new THREE.Vector3(0.1, 0.8, -0.55).normalize();
const KEY_AXIS = new THREE.Vector3(1, 0, 0.18).normalize();

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
  /** Scanner slit position down the current field, 0 to 1 (0 when not scanning). */
  scan: number;
}

export interface WaferObjects {
  root: THREE.Group;
  apply(frame: StepperFrame): void;
  /** Outline the die centred at (x, y) on the unit wafer, or none. */
  setHover(centre: { x: number; y: number } | null): void;
  dispose(): void;
}

/**
 * Builds the wafer as plain three.js objects: the substrate disc, one instanced mesh of dies and
 * the exposure field. Kept outside React so the stepper can drive uniforms directly.
 */
export function buildWafer(
  layout: DieLayout,
  plan: ExposurePlan,
  options: { failColor: string; lampColor?: string; roomGain?: number; inspectGain?: number },
): WaferObjects {
  const shared = {
    uFilmCentre: { value: FILM.centreNm },
    uEdgeDrop: { value: FILM.edgeDrop },
    uRoomGain: { value: options.roomGain ?? 0.3 },
    uInspectGain: { value: options.inspectGain ?? 0.95 },
    uKeyDir: { value: KEY_DIR },
    uKeyAxis: { value: KEY_AXIS },
  };
  const field = new THREE.Vector4(0, 0, 0, 0);
  const hover = new THREE.Vector3(0, 0, 0);
  // The probe light is the signal of the instrument screens (dark glass in both themes).
  const lamp = hexToLinear(options.lampColor ?? signalTokenHex("dark"));

  const dieMaterial = new THREE.ShaderMaterial({
    vertexShader: dieVertexShader,
    fragmentShader: dieFragmentShader,
    uniforms: {
      ...shared,
      uProgress: { value: 0 },
      uField: { value: field },
      uFieldOn: { value: 0 },
      uScan: { value: 0 },
      uFail: { value: hexToLinear(options.failColor) },
      uLampColour: { value: lamp },
      uHover: { value: hover },
    },
  });
  const substrateMaterial = new THREE.ShaderMaterial({
    vertexShader: substrateVertexShader,
    fragmentShader: substrateFragmentShader,
    uniforms: {
      ...shared,
      uReveal: { value: 0 },
      uNativeOxide: { value: 2 },
      uLampColour: { value: lamp },
    },
  });
  const stageMaterial = new THREE.ShaderMaterial({
    vertexShader: stageVertexShader,
    fragmentShader: stageFragmentShader,
    uniforms: {
      uLamp: { value: lamp },
      uField: { value: field },
      uFieldOn: { value: 0 },
      uReveal: { value: 0 },
    },
    transparent: true,
    depthWrite: false,
  });
  const fieldMaterial = new THREE.ShaderMaterial({
    vertexShader: fieldVertexShader,
    fragmentShader: fieldFragmentShader,
    uniforms: {
      uLamp: { value: lamp },
      uFlash: { value: 0 },
      uOpacity: { value: 0 },
      uScan: { value: 0 },
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

  const stageGeometry = new THREE.CircleGeometry(1.34, 128);
  stageGeometry.rotateX(-Math.PI / 2);
  const stage = new THREE.Mesh(stageGeometry, stageMaterial);
  stage.position.y = -0.002;
  stage.renderOrder = -1;

  const root = new THREE.Group();
  root.add(stage, substrate, dies, fieldMesh);

  return {
    root,
    apply(frame) {
      dieMaterial.uniforms.uProgress!.value = frame.progress;
      field.set(frame.x, frame.y, frame.size, frame.flash);
      dieMaterial.uniforms.uFieldOn!.value = frame.on;
      dieMaterial.uniforms.uScan!.value = frame.scan;
      substrateMaterial.uniforms.uReveal!.value = frame.reveal;
      stageMaterial.uniforms.uFieldOn!.value = frame.on;
      stageMaterial.uniforms.uReveal!.value = frame.reveal;
      fieldMaterial.uniforms.uFlash!.value = frame.flash;
      fieldMaterial.uniforms.uOpacity!.value = frame.on;
      fieldMaterial.uniforms.uScan!.value = frame.scan;
      fieldMesh.position.set(frame.x, 0.03, frame.y);
      fieldMesh.scale.set(frame.size, 1, frame.size);
    },
    setHover(centre) {
      if (centre) hover.set(centre.x, centre.y, 1);
      else hover.setZ(0);
    },
    dispose() {
      stageGeometry.dispose();
      stageMaterial.dispose();
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
