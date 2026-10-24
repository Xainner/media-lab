import { useEffect, useRef } from 'react'
import { motionAllowed } from './prefs'

// Fixed WebGL atmosphere: ember fbm nebula + two twinkling star layers. The tone follows the active
// section, the cursor adds a soft light, and `warp` (0..1) streaks the stars for transitions.
// Half resolution, 30 fps cap, paused while hidden; the CSS gradient on .nebula is the fallback.
const FRAG = `
precision mediump float;
uniform vec2 uRes;
uniform float uTime;
uniform vec2 uMouse;
uniform vec3 uTone;
uniform float uWarp;
uniform float uGlow;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  mat2 r = mat2(0.8, -0.6, 0.6, 0.8);
  for (int i = 0; i < 5; i++) { v += a * noise(p); p = r * p * 2.03 + 11.7; a *= 0.5; }
  return v;
}
float stars(vec2 uv, float scale, float t, float stretch) {
  vec2 c = uv - 0.5;
  c *= 1.0 - stretch * 0.35 * length(c);
  vec2 g = (c + 0.5) * scale;
  vec2 id = floor(g), f = fract(g) - 0.5;
  float h = hash(id);
  if (h < 0.93) return 0.0;
  vec2 o = vec2(hash(id + 3.1), hash(id + 7.7)) - 0.5;
  vec2 d2 = f - o * 0.7;
  d2.y *= 1.0 + stretch * 6.0 * abs(c.y);
  d2.x *= 1.0 + stretch * 6.0 * abs(c.x);
  float d = length(d2);
  float tw = 0.6 + 0.4 * sin(t * (1.0 + h * 3.0) + h * 40.0);
  return smoothstep(0.06, 0.0, d) * tw * (h - 0.93) * 14.0;
}
void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  vec2 p = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y;
  float t = uTime * 0.018;
  vec2 q = p * 1.35 * (1.0 - uWarp * 0.25);
  float n1 = fbm(q + vec2(t, -t * 0.6));
  float n2 = fbm(q * 1.8 + n1 * 1.6 - vec2(t * 0.7, t));
  float neb = smoothstep(0.35, 0.95, n2 * 0.9 + n1 * 0.35);
  float band = exp(-pow((p.y + p.x * 0.45 - 0.08) * 2.2, 2.0));
  vec3 deep = vec3(0.03, 0.03, 0.035);
  vec3 violet = vec3(0.5, 0.16, 0.05);
  vec3 indigo = vec3(0.12, 0.07, 0.05);
  vec3 col = deep;
  col += indigo * neb * 0.55;
  col += mix(violet, uTone, clamp(n1 * 1.25 - 0.25, 0.0, 1.0)) * neb * band * (0.42 + uGlow * 0.3);
  float m = exp(-length(p - uMouse) * 2.6);
  col += mix(violet, uTone, 0.5) * m * 0.09;
  float s = stars(uv, 90.0, uTime, uWarp) + stars(uv, 46.0, uTime * 1.3, uWarp) * 1.2;
  col += vec3(1.0, 0.92, 0.85) * s * (0.6 + uWarp * 1.4);
  col += uTone * uWarp * 0.12 * (1.0 - length(p));
  col *= 1.0 - 0.38 * length(uv - 0.5);
  gl_FragColor = vec4(col, 1.0);
}`
const VERT = `attribute vec2 a; void main() { gl_Position = vec4(a, 0.0, 1.0); }`

const TONES: Record<string, [number, number, number]> = {
  image: [1.0, 0.45, 0.18], edit: [1.0, 0.62, 0.4], video: [1.0, 0.38, 0.2], music: [0.36, 0.6, 0.85],
  director: [0.98, 0.62, 0.3], agent: [1.0, 0.5, 0.25], library: [0.8, 0.62, 0.5], account: [0.55, 0.55, 0.58], entry: [1.0, 0.4, 0.15],
}

type NebulaApi = { tone(name: string): void; warp(value: number): void; glow(value: number): void }
let api: NebulaApi | null = null
/** Imperative bridge so routes and timelines can steer the background without re-rendering it. */
export const nebula: NebulaApi = {
  tone: name => api?.tone(name),
  warp: value => api?.warp(value),
  glow: value => api?.glow(value),
}

export default function Nebula({ tone = 'entry' }: { tone?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => { nebula.tone(tone) }, [tone])
  useEffect(() => {
    const canvas = ref.current
    const gl = canvas?.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power' })
    if (!canvas || !gl) return
    const shader = (type: number, src: string) => { const s = gl.createShader(type)!; gl.shaderSource(s, src); gl.compileShader(s); return s }
    const prog = gl.createProgram()!
    gl.attachShader(prog, shader(gl.VERTEX_SHADER, VERT)); gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FRAG)); gl.linkProgram(prog)
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return
    gl.useProgram(prog)
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer())
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    const loc = gl.getAttribLocation(prog, 'a'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
    const U = (n: string) => gl.getUniformLocation(prog, n)
    const uRes = U('uRes'), uTime = U('uTime'), uMouse = U('uMouse'), uTone = U('uTone'), uWarp = U('uWarp'), uGlow = U('uGlow')
    let w = 0, h = 0
    const resize = () => {
      const scale = Math.min(1, 0.5 * (devicePixelRatio || 1))
      w = Math.max(1, Math.round(innerWidth * scale)); h = Math.max(1, Math.round(innerHeight * scale))
      canvas.width = w; canvas.height = h; gl.viewport(0, 0, w, h)
    }
    resize(); addEventListener('resize', resize)
    let mx = .3, my = .2, tmx = mx, tmy = my
    const move = (e: PointerEvent) => { tmx = (e.clientX - innerWidth / 2) / innerHeight; tmy = -(e.clientY - innerHeight / 2) / innerHeight }
    addEventListener('pointermove', move, { passive: true })
    let target = TONES.entry, current = [...target], warpT = 0, warp = 0, glowT = 0, glow = 0
    api = { tone: name => { target = TONES[name] || TONES.image }, warp: v => { warpT = v }, glow: v => { glowT = v } }
    const t0 = performance.now(); let last = 0, raf = 0
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame)
      if (document.hidden || now - last < 33) return
      last = now
      const moving = motionAllowed()
      mx += (tmx - mx) * .05; my += (tmy - my) * .05
      for (let i = 0; i < 3; i++) current[i] += (target[i] - current[i]) * .04
      warp += (warpT - warp) * .12; glow += (glowT - glow) * .06
      gl.uniform2f(uRes, w, h); gl.uniform1f(uTime, moving ? (now - t0) / 1000 : 0)
      gl.uniform2f(uMouse, mx, my); gl.uniform3f(uTone, current[0], current[1], current[2])
      gl.uniform1f(uWarp, moving ? warp : 0); gl.uniform1f(uGlow, glow)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
    }
    raf = requestAnimationFrame(frame)
    return () => { cancelAnimationFrame(raf); removeEventListener('resize', resize); removeEventListener('pointermove', move); api = null; gl.getExtension('WEBGL_lose_context')?.loseContext() }
  }, [])
  return <><canvas ref={ref} className="nebula" aria-hidden="true" /><div className="vignette" aria-hidden="true" /><div className="grain" aria-hidden="true" /></>
}
