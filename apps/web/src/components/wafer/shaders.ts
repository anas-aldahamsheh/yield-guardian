import { thinFilmGlsl } from "@/lib/optics/glsl";

/**
 * Shaders of the 3D wafer. Every die's colour is the reflectance of its oxide film (Airy
 * summation over 16 wavelengths, s and p averaged) for the actual viewing angle of that
 * fragment, under the yellow-room lamp before the exposure field passes and under white
 * inspection light after it. The physics chunk is generated from the unit-tested TypeScript.
 *
 * Lighting: a diffuse room term, plus the reflection of one long overhead lamp (a polished wafer
 * is a mirror, so the lamp shows as a bright band that moves as the wafer tilts). The reflected
 * band is the film's own reflectance colour, so it is physically the same colour family.
 */

const THIN_FILM = thinFilmGlsl();

const SHARED_UNIFORMS = /* glsl */ `
uniform float uFilmCentre;   // oxide thickness at the wafer centre, nm
uniform float uEdgeDrop;     // fractional thinning at the edge
uniform float uRoomGain;     // brightness of the yellow-room lamp
uniform float uInspectGain;  // brightness of the inspection light
uniform vec3 uKeyDir;        // direction to the overhead lamp (world)
uniform vec3 uKeyAxis;       // long axis of the overhead lamp (world)
`;

const SHADE = /* glsl */ `
vec3 shadeFilm(float thickness, vec3 N, vec3 V, float revealed, out vec3 lamp) {
  float cosI = clamp(dot(N, V), 0.02, 1.0);
  vec3 white;
  vec3 safe;
  thinFilm(thickness, cosI, white, safe);
  lamp = safe;
  vec3 room = safe * uRoomGain;
  vec3 inspected = white * uInspectGain;
  vec3 colour = mix(room, inspected, revealed);

  // The overhead lamp seen in the mirror of the wafer: a long soft-edged band.
  vec3 R = reflect(-V, N);
  vec3 side = normalize(cross(uKeyDir, uKeyAxis));
  float along = dot(R, uKeyAxis);
  float across = dot(R, side);
  float facing = smoothstep(0.55, 0.8, dot(R, uKeyDir));
  float band = (1.0 - smoothstep(0.015, 0.075, abs(across))) * (1.0 - smoothstep(0.22, 0.5, abs(along))) * facing;
  vec3 tint = mix(safe * 1.1, white, revealed);
  colour += band * tint * 1.1;

  // A broad sheen keeps the surface reading as polished away from the band.
  vec3 H = normalize(uKeyDir + V);
  colour += pow(max(dot(N, H), 0.0), 8.0) * 0.06 * tint;
  return colour;
}
`;

export const dieVertexShader = /* glsl */ `
attribute vec2 aDie;          // x: 1 pass, 2 fail; y: exposure order of the die's field
varying vec2 vUv;
varying vec2 vDie;
varying vec3 vWorld;
varying vec3 vNormal;
varying vec2 vLocal;          // position on the unit wafer (x, map row direction)
varying vec2 vCentre;         // centre of this die on the unit wafer
void main() {
  vUv = uv;
  vDie = aDie;
  mat4 model = modelMatrix * instanceMatrix;
  vec4 world = model * vec4(position, 1.0);
  vWorld = world.xyz;
  vNormal = normalize(mat3(model) * normal);
  vLocal = (instanceMatrix * vec4(position, 1.0)).xz;
  vCentre = (instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xz;
  gl_Position = projectionMatrix * viewMatrix * world;
}
`;

export const dieFragmentShader = /* glsl */ `
${SHARED_UNIFORMS}
uniform float uProgress;      // stepper progress in fields (field i is exposed during [i, i + 1))
uniform vec4 uField;          // exposure field: centre x, centre y, size, flash (0 to 1)
uniform float uFieldOn;
uniform float uScan;          // position of the scanner slit down the current field, 0 to 1
uniform vec3 uFail;           // ink colour of a failed die (linear)
uniform vec3 uLampColour;     // the safelight itself (linear)
uniform vec3 uHover;          // centre of the die under the pointer (x, y) and whether one is
varying vec2 vUv;
varying vec2 vDie;
varying vec3 vWorld;
varying vec3 vNormal;
varying vec2 vLocal;
varying vec2 vCentre;
${THIN_FILM}
${SHADE}
void main() {
  float order = vDie.y;
  float current = floor(uProgress);
  // Step and scan: fields before the current one are done; in the current field a die is
  // revealed once the slit has passed its centre.
  float rel = clamp((vCentre.y - (uField.y - uField.z * 0.5)) / max(uField.z, 1e-4), 0.0, 1.0);
  float revealed = order < current - 0.5 ? 1.0 : (order > current + 0.5 ? 0.0 : smoothstep(rel - 0.04, rel + 0.04, uScan));

  float r2 = min(1.0, dot(vLocal, vLocal));
  float thickness = uFilmCentre * (1.0 - uEdgeDrop * r2);
  vec3 N = normalize(vNormal);
  vec3 V = normalize(cameraPosition - vWorld);
  vec3 lamp;
  vec3 colour = shadeFilm(thickness, N, V, revealed, lamp);

  // Die edge: the saw street catches less light.
  vec2 e = min(vUv, 1.0 - vUv);
  float edge = smoothstep(0.0, 0.08, min(e.x, e.y));
  colour *= mix(0.6, 1.0, edge);

  // Under the exposure field the die is lit by the field's light; the slit is brightest.
  vec2 d = abs(vLocal - uField.xy) - vec2(uField.z * 0.5);
  float inField = 1.0 - smoothstep(-0.004, 0.004, max(d.x, d.y));
  float slitRel = (vLocal.y - (uField.y - uField.z * 0.5)) / max(uField.z, 1e-4);
  float slit = (1.0 - smoothstep(0.0, 0.07, abs(slitRel - uScan))) * step(0.001, uScan) * step(uScan, 0.999);
  colour += uLampColour * inField * uFieldOn * (0.18 + 0.5 * uField.w + 1.6 * slit);

  // Light spilling from the field onto the dies around it.
  float dist = length(vLocal - uField.xy) / max(uField.z, 1e-4);
  colour += uLampColour * exp(-dist * dist * 1.4) * 0.08 * uFieldOn;

  // A failed die carries an ink dot once its result is revealed (as at wafer sort).
  if (vDie.x > 1.5) {
    float dd = length(vUv - 0.5);
    float aa = fwidth(dd) * 1.2;
    float ink = 1.0 - smoothstep(0.27 - aa, 0.27 + aa, dd);
    colour = mix(colour, uFail * (0.8 + 0.3 * revealed), ink * revealed);
  }

  // The die under the pointer: outlined in safelight.
  float hovered = uHover.z * (1.0 - step(1e-4, distance(vCentre, uHover.xy)));
  float outline = 1.0 - smoothstep(0.05, 0.11, min(e.x, e.y));
  colour = mix(colour, uLampColour * 1.4, outline * hovered);
  colour *= 1.0 + 0.25 * hovered;

  gl_FragColor = vec4(colour, 1.0);
  #include <colorspace_fragment>
}
`;

export const substrateVertexShader = /* glsl */ `
varying vec3 vWorld;
varying vec3 vNormal;
varying vec2 vLocal;
void main() {
  vec4 world = modelMatrix * vec4(position, 1.0);
  vWorld = world.xyz;
  vNormal = normalize(mat3(modelMatrix) * normal);
  vLocal = position.xz;
  gl_Position = projectionMatrix * viewMatrix * world;
}
`;

export const substrateFragmentShader = /* glsl */ `
${SHARED_UNIFORMS}
uniform float uReveal;        // share of the wafer already inspected
uniform float uNativeOxide;   // nm
uniform vec3 uLampColour;
varying vec3 vWorld;
varying vec3 vNormal;
varying vec2 vLocal;
${THIN_FILM}
${SHADE}
void main() {
  vec3 N = normalize(vNormal);
  vec3 V = normalize(cameraPosition - vWorld);
  vec3 lamp;
  // Bare silicon with its native oxide, between dies and in the edge exclusion.
  vec3 colour = shadeFilm(uNativeOxide, N, V, uReveal, lamp);
  float top = step(0.5, N.y);
  // Side walls of the wafer read darker; the bevelled top edge catches a line of light.
  colour *= mix(0.3, 0.62, top);
  float r = length(vLocal);
  colour += top * smoothstep(0.988, 0.999, r) * mix(uLampColour * 0.5, vec3(0.6), uReveal);
  gl_FragColor = vec4(colour, 1.0);
  #include <colorspace_fragment>
}
`;

export const fieldVertexShader = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

/** The exposure field: a lit rectangle with crisp edges, corner ticks and the scanner slit. */
export const fieldFragmentShader = /* glsl */ `
uniform vec3 uLamp;
uniform float uFlash;
uniform float uOpacity;
uniform float uScan;
varying vec2 vUv;
void main() {
  vec2 e = min(vUv, 1.0 - vUv);
  float w = fwidth(vUv.x) * 1.5;
  float border = 1.0 - smoothstep(w, w * 2.0, min(e.x, e.y));
  vec2 c = step(vec2(0.82), max(vUv, 1.0 - vUv));
  float corner = c.x * c.y * (1.0 - smoothstep(w * 2.0, w * 3.5, min(e.x, e.y)));
  float fill = 0.04 + 0.12 * uFlash;
  float scanning = step(0.001, uScan) * step(uScan, 0.999);
  float slit = (1.0 - smoothstep(0.0, 0.05, abs((1.0 - vUv.y) - uScan))) * scanning;
  float a = max(border * 0.95, max(corner, max(fill, slit * 0.9)));
  gl_FragColor = vec4(uLamp * (1.0 + uFlash + slit), a * uOpacity);
  #include <colorspace_fragment>
}
`;

export const stageVertexShader = /* glsl */ `
varying vec2 vLocal;
void main() {
  vLocal = position.xz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

/**
 * The wafer stage under the wafer: a dark vacuum chuck with concentric grooves, lit only by what
 * spills from the exposure field, fading into the page at its edge.
 */
export const stageFragmentShader = /* glsl */ `
uniform vec3 uLamp;
uniform vec4 uField;
uniform float uFieldOn;
uniform float uReveal;
varying vec2 vLocal;
void main() {
  float r = length(vLocal);
  float groove = smoothstep(0.93, 0.985, abs(fract(r * 9.0) - 0.5) * 2.0);
  float dist = length(vLocal - uField.xy);
  float spill = exp(-dist * dist * 3.0) * uFieldOn;
  vec3 base = vec3(0.012, 0.011, 0.007);
  vec3 colour = base * (1.0 + 0.6 * groove) + uLamp * spill * 0.05 + uLamp * 0.015 * (1.0 - uReveal) * exp(-r * r * 2.0);
  float alpha = 1.0 - smoothstep(1.0, 1.22, r);
  gl_FragColor = vec4(colour, alpha);
  #include <colorspace_fragment>
}
`;
