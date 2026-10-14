import { thinFilmGlsl } from "@/lib/optics/glsl";

/**
 * Shaders of the 3D wafer. Every die's colour is the reflectance of its oxide film (Airy
 * summation over 16 wavelengths, s and p averaged) for the actual viewing angle of that
 * fragment, under the yellow-room lamp before the exposure field passes and under white
 * inspection light after it. The physics chunk is generated from the unit-tested TypeScript.
 */

const THIN_FILM = thinFilmGlsl();

const SHARED_UNIFORMS = /* glsl */ `
uniform float uFilmCentre;   // oxide thickness at the wafer centre, nm
uniform float uEdgeDrop;     // fractional thinning at the edge
uniform float uRoomGain;     // brightness of the yellow-room lamp
uniform float uInspectGain;  // brightness of the inspection light
uniform vec3 uKeyDir;        // direction to the key light (world)
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
  // A polished surface: a broad highlight of the key light, coloured by the film.
  vec3 H = normalize(uKeyDir + V);
  float sheen = pow(max(dot(N, H), 0.0), 36.0) * 0.55 + pow(max(dot(N, H), 0.0), 6.0) * 0.08;
  colour += sheen * mix(safe, white, revealed) * 1.4;
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
void main() {
  vUv = uv;
  vDie = aDie;
  mat4 model = modelMatrix * instanceMatrix;
  vec4 world = model * vec4(position, 1.0);
  vWorld = world.xyz;
  vNormal = normalize(mat3(model) * normal);
  vLocal = (instanceMatrix * vec4(position, 1.0)).xz;
  gl_Position = projectionMatrix * viewMatrix * world;
}
`;

export const dieFragmentShader = /* glsl */ `
${SHARED_UNIFORMS}
uniform float uProgress;      // stepper progress in fields (field i is exposed during [i, i + 1))
uniform vec4 uField;          // exposure field: centre x, centre y, size, flash (0 to 1)
uniform float uFieldOn;
uniform vec3 uFail;           // ink colour of a failed die (linear)
varying vec2 vUv;
varying vec2 vDie;
varying vec3 vWorld;
varying vec3 vNormal;
varying vec2 vLocal;
${THIN_FILM}
${SHADE}
void main() {
  float order = vDie.y;
  float revealed = smoothstep(order + 0.55, order + 0.9, uProgress);
  float r2 = min(1.0, dot(vLocal, vLocal));
  float thickness = uFilmCentre * (1.0 - uEdgeDrop * r2);
  vec3 N = normalize(vNormal);
  vec3 V = normalize(cameraPosition - vWorld);
  vec3 lamp;
  vec3 colour = shadeFilm(thickness, N, V, revealed, lamp);

  // Die edge: the saw street catches less light.
  vec2 e = min(vUv, 1.0 - vUv);
  float edge = smoothstep(0.0, 0.08, min(e.x, e.y));
  colour *= mix(0.72, 1.0, edge);

  // Under the exposure field the die is lit by the field's light.
  vec2 d = abs(vLocal - uField.xy) - vec2(uField.z * 0.5);
  float inField = 1.0 - smoothstep(-0.004, 0.004, max(d.x, d.y));
  colour += lamp * inField * uFieldOn * (0.35 + 1.4 * uField.w);

  // A failed die carries an ink dot once its result is revealed (as at wafer sort).
  if (vDie.x > 1.5) {
    float dist = length(vUv - 0.5);
    float aa = fwidth(dist) * 1.2;
    float ink = 1.0 - smoothstep(0.27 - aa, 0.27 + aa, dist);
    colour = mix(colour, uFail * (0.85 + 0.25 * revealed), ink * revealed);
  }
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
  // Side walls of the wafer read darker.
  colour *= mix(0.45, 1.0, step(0.5, N.y));
  gl_FragColor = vec4(colour * 0.82, 1.0);
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

/** The exposure field: a lit rectangle with crisp edges and corner ticks. */
export const fieldFragmentShader = /* glsl */ `
uniform vec3 uLamp;
uniform float uFlash;
uniform float uOpacity;
varying vec2 vUv;
void main() {
  vec2 e = min(vUv, 1.0 - vUv);
  float w = fwidth(vUv.x) * 1.5;
  float border = 1.0 - smoothstep(w, w * 2.0, min(e.x, e.y));
  vec2 c = step(vec2(0.82), max(vUv, 1.0 - vUv));
  float corner = c.x * c.y * (1.0 - smoothstep(w * 2.0, w * 3.5, min(e.x, e.y)));
  float fill = 0.06 + 0.22 * uFlash;
  float a = max(border * 0.95, max(corner, fill));
  gl_FragColor = vec4(uLamp * (1.0 + uFlash), a * uOpacity);
  #include <colorspace_fragment>
}
`;
