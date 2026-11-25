import React, { useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import * as THREE from "three";

export type JarvisState = "IDLE" | "LISTENING" | "THINKING" | "EXECUTING" | "SPEAKING" | "VERIFIED" | "ALERT";

interface Jarvis3DCoreProps {
  state: JarvisState;
  speechPulse?: number;
  voiceListening?: boolean;
}

const STATE_PALETTES: Record<JarvisState, { hot: string; gold: string; amber: string; deep: string }> = {
  IDLE:      { hot: "#fff9db", gold: "#ffbe3b", amber: "#e86a17", deep: "#7c2d12" },
  LISTENING: { hot: "#ffffff", gold: "#ffd166", amber: "#fb923c", deep: "#9a3412" },
  THINKING:  { hot: "#ffffff", gold: "#ffbe0b", amber: "#fb8500", deep: "#9a3412" },
  EXECUTING: { hot: "#fffbeb", gold: "#ffa62b", amber: "#ea580c", deep: "#7c2d12" },
  SPEAKING:  { hot: "#ffffff", gold: "#ffc83d", amber: "#f97316", deep: "#9a3412" },
  VERIFIED:  { hot: "#ecfdf5", gold: "#34d399", amber: "#10b981", deep: "#065f46" },
  ALERT:     { hot: "#fef2f2", gold: "#f87171", amber: "#ef4444", deep: "#991b1b" },
};

// 8,000 GPU GLSL flowing golden-fire plasma particles streaming through the globe & surging with voice
const FLOW_VERT = `
attribute float aPhi;
attribute float aTheta;
attribute float aRadius;
attribute float aSpeed;
attribute float aPhase;
attribute float aSize;
attribute float aMix;

uniform float uTime;
uniform float uVoice;
uniform float uFlowSpeed;

varying float vMix;
varying float vSpark;

void main() {
  float t = uTime * aSpeed * uFlowSpeed;
  float theta = aTheta + t;
  float phi = aPhi + sin(t * 0.72 + aPhase) * (0.24 + uVoice * 0.38);

  // Fiery organic lacy wave distortion + voice-reactive radial pulse
  float w1 = sin(phi * 9.0 + theta * 4.0 - uTime * 4.1 + aPhase);
  float w2 = cos(theta * 7.0 - phi * 6.0 + uTime * 3.1);
  float voiceWave = (0.55 + 0.45 * sin(phi * 12.0 - uTime * 10.5 + aPhase)) * uVoice;

  float radialFlow = sin(uTime * (1.35 * abs(aSpeed)) + aPhase) * 0.22;
  float r = aRadius + radialFlow + (w1 * 0.13 + w2 * 0.08) + voiceWave * (0.52 + aRadius * 0.16);

  vec3 pos = vec3(
    sin(phi) * cos(theta) * r,
    cos(phi) * r,
    sin(phi) * sin(theta) * r
  );

  vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
  gl_Position = projectionMatrix * mvPos;

  float flicker = 0.72 + 0.28 * sin(uTime * 12.0 + aPhase * 3.7);
  gl_PointSize = clamp((aSize * (1.0 + uVoice * 1.05) * flicker) * (245.0 / max(1.0, -mvPos.z)), 1.4, 24.0);
  vMix = aMix;
  vSpark = clamp(0.68 + voiceWave * 0.95 + flicker * 0.25, 0.4, 2.4);
}
`;

const FLOW_FRAG = `
uniform vec3 uHotColor;
uniform vec3 uGoldColor;
uniform vec3 uAmberColor;

varying float vMix;
varying float vSpark;

void main() {
  vec2 uv = gl_PointCoord - 0.5;
  float d = length(uv);
  if (d > 0.5) discard;

  float core = exp(-d * d * 28.0);
  float halo = exp(-d * d * 6.2) * 0.68;
  float alpha = clamp(core + halo, 0.0, 1.0);

  vec3 baseCol = vMix > 0.68 ? uHotColor : (vMix > 0.26 ? uGoldColor : uAmberColor);
  vec3 col = mix(baseCol, uHotColor, core * 0.78) * (1.28 * vSpark);
  gl_FragColor = vec4(col, alpha * 0.94);
}
`;

/** Bottom-left & perimeter protruding radial circuit-ladder fins matching reference image */
function buildCircuitLadderArc(
  innerR: number,
  outerR: number,
  arcStart: number,
  arcSpan: number,
  tracks: number,
  radialTicks: number,
  seed: number
): THREE.BufferGeometry {
  const verts: number[] = [];
  const segs = 54;
  for (let t = 0; t < tracks; t++) {
    const frac = tracks === 1 ? 0.5 : t / (tracks - 1);
    const r = innerR + frac * (outerR - innerR);
    for (let s = 0; s < segs; s++) {
      if ((s + t * 5 + seed) % 11 === 0) continue;
      const a0 = arcStart + (s / segs) * arcSpan;
      const a1 = arcStart + ((s + 1) / segs) * arcSpan;
      verts.push(Math.cos(a0) * r, Math.sin(a0) * r, 0, Math.cos(a1) * r, Math.sin(a1) * r, 0);
    }
  }
  for (let i = 0; i <= radialTicks; i++) {
    const a = arcStart + (i / radialTicks) * arcSpan;
    const ca = Math.cos(a), sa = Math.sin(a);
    const extraOut = ((i * 17 + seed) % 5 === 0) ? 0.52 : ((i * 11 + seed) % 3 === 0 ? 0.22 : 0.0);
    const r0 = innerR - ((i % 4 === 0) ? 0.1 : 0.0);
    const r1 = outerR + extraOut;
    verts.push(ca * r0, sa * r0, 0, ca * r1, sa * r1, 0);
    if (extraOut > 0.28) {
      const aNext = a + 0.05;
      verts.push(ca * r1, sa * r1, 0, Math.cos(aNext) * r1, Math.sin(aNext) * r1, 0);
      const rMid = outerR + extraOut * 0.55;
      verts.push(ca * rMid, sa * rMid, 0, Math.cos(aNext) * rMid, Math.sin(aNext) * rMid, 0);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
  return geo;
}

const OriginalJarvisScene: React.FC<{
  state: JarvisState;
  speechEnergyRef: React.MutableRefObject<number>;
  micEnergyRef: React.MutableRefObject<number>;
  mouseRef: React.MutableRefObject<{ x: number; y: number }>;
}> = ({ state, speechEnergyRef, micEnergyRef, mouseRef }) => {
  const rootRef = useRef<THREE.Group>(null);
  const coreGroupRef = useRef<THREE.Group>(null);
  const crescentRibbonRef = useRef<THREE.Group>(null);
  const sectorRefs = useRef<Array<THREE.Group | null>>([]);
  const webRef = useRef<THREE.LineSegments>(null);
  const shockRef = useRef<THREE.Mesh>(null);

  const pal = STATE_PALETTES[state];
  const hotCol = useMemo(() => new THREE.Color(pal.hot), [pal.hot]);
  const goldCol = useMemo(() => new THREE.Color(pal.gold), [pal.gold]);
  const amberCol = useMemo(() => new THREE.Color(pal.amber), [pal.amber]);

  // 8,000 GPU flowing plasma particles
  const { flowGeo, flowMat } = useMemo(() => {
    const COUNT = 8000;
    const positions = new Float32Array(COUNT * 3);
    const aPhi = new Float32Array(COUNT);
    const aTheta = new Float32Array(COUNT);
    const aRadius = new Float32Array(COUNT);
    const aSpeed = new Float32Array(COUNT);
    const aPhase = new Float32Array(COUNT);
    const aSize = new Float32Array(COUNT);
    const aMix = new Float32Array(COUNT);

    for (let i = 0; i < COUNT; i++) {
      const h1 = Math.sin(i * 12.9898 + 78.233) * 43758.5453;
      const r1 = h1 - Math.floor(h1);
      const h2 = Math.sin(i * 93.989 + 67.345) * 28461.1234;
      const r2 = h2 - Math.floor(h2);
      const h3 = Math.sin(i * 45.164 + 19.721) * 19532.8765;
      const r3 = h3 - Math.floor(h3);

      const band = i % 10;
      const radius =
        band < 2
          ? 0.35 + r1 * 0.75    // Hot molten inner streams
          : band < 4
          ? 1.12 + r1 * 0.85    // Mid volumetric streams
          : band < 9
          ? 1.98 + r1 * 0.56    // Dense fiery outer corona (signature look)
          : 2.52 + r1 * 0.45;   // Outer floating sparks

      const phi = Math.acos(1 - 2 * r2);
      const theta = r3 * Math.PI * 2.0;

      positions[i * 3] = Math.sin(phi) * Math.cos(theta) * radius;
      positions[i * 3 + 1] = Math.cos(phi) * radius;
      positions[i * 3 + 2] = Math.sin(phi) * Math.sin(theta) * radius;

      aPhi[i] = phi;
      aTheta[i] = theta;
      aRadius[i] = radius;
      aSpeed[i] = (i % 2 === 0 ? 1.0 : -1.0) * (0.26 + r1 * 0.96);
      aPhase[i] = r3 * Math.PI * 2.0;
      aSize[i] = band < 2 ? 0.14 + r2 * 0.14 : band < 9 ? 0.085 + r2 * 0.14 : 0.06 + r2 * 0.08;
      aMix[i] = band < 2 ? 0.88 : r1;
    }

    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    g.setAttribute("aPhi", new THREE.BufferAttribute(aPhi, 1));
    g.setAttribute("aTheta", new THREE.BufferAttribute(aTheta, 1));
    g.setAttribute("aRadius", new THREE.BufferAttribute(aRadius, 1));
    g.setAttribute("aSpeed", new THREE.BufferAttribute(aSpeed, 1));
    g.setAttribute("aPhase", new THREE.BufferAttribute(aPhase, 1));
    g.setAttribute("aSize", new THREE.BufferAttribute(aSize, 1));
    g.setAttribute("aMix", new THREE.BufferAttribute(aMix, 1));

    const m = new THREE.ShaderMaterial({
      vertexShader: FLOW_VERT,
      fragmentShader: FLOW_FRAG,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTime: { value: 0 },
        uVoice: { value: 0 },
        uFlowSpeed: { value: 1.0 },
        uHotColor: { value: new THREE.Color(pal.hot) },
        uGoldColor: { value: new THREE.Color(pal.gold) },
        uAmberColor: { value: new THREE.Color(pal.amber) },
      },
    });
    return { flowGeo: g, flowMat: m };
  }, []);

  useEffect(() => {
    flowMat.uniforms.uHotColor.value.set(pal.hot);
    flowMat.uniforms.uGoldColor.value.set(pal.gold);
    flowMat.uniforms.uAmberColor.value.set(pal.amber);
  }, [pal.hot, pal.gold, pal.amber, flowMat]);

  // Iconic sweeping molten-gold C-ribbon & horizontal right-hand core energy bridge from reference image
  const { cRibbonGeo, coreBridgeGeo, innerRibbons } = useMemo(() => {
    const cPts = Array.from({ length: 28 }, (_, k) => {
      const u = k / 27;
      const ang = Math.PI * 0.42 + u * Math.PI * 1.12;
      const r = 1.24 + Math.sin(u * Math.PI) * 0.12;
      return new THREE.Vector3(Math.cos(ang) * r, Math.sin(ang) * r, Math.sin(u * Math.PI * 2) * 0.25);
    });
    const cGeo = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(cPts), 48, 0.042, 8, false);

    const bPts = [
      new THREE.Vector3(0.05, 0.02, 0.1),
      new THREE.Vector3(0.65, 0.04, 0.18),
      new THREE.Vector3(1.38, -0.02, 0.05),
      new THREE.Vector3(2.05, -0.04, -0.1),
    ];
    const bGeo = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(bPts), 24, 0.032, 8, false);

    const ribs: THREE.TubeGeometry[] = [];
    for (let i = 0; i < 6; i++) {
      const a0 = (i / 6) * Math.PI * 2;
      const pts = Array.from({ length: 18 }, (_, k) => {
        const u = k / 17;
        const ang = a0 + u * Math.PI * 1.45;
        const r = 0.25 + Math.sin(u * Math.PI) * (0.48 + (i % 3) * 0.2);
        const z = Math.cos(u * Math.PI * 2 + i) * 0.34;
        return new THREE.Vector3(Math.cos(ang) * r, Math.sin(ang) * r, z);
      });
      ribs.push(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 32, 0.018, 6, false));
    }
    return { cRibbonGeo: cGeo, coreBridgeGeo: bGeo, innerRibbons: ribs };
  }, []);

  // Curved circuit-ladder fins (heaviest along bottom-left 7-to-10 o'clock matching reference image)
  const sectorLayers = useMemo(
    () => [
      { geo: buildCircuitLadderArc(2.08, 2.68, Math.PI * 0.92, Math.PI * 0.65, 5, 42, 2), rot: [0.1, 0.14, 0.0], sp: 0.16, col: "gold" },
      { geo: buildCircuitLadderArc(1.86, 2.42, Math.PI * 0.15, Math.PI * 1.15, 5, 56, 5), rot: [-0.35, 0.48, 0.25], sp: -0.26, col: "amber" },
      { geo: buildCircuitLadderArc(1.22, 1.72, 0.6, Math.PI * 1.5, 4, 44, 9), rot: [-0.68, -0.4, 0.1], sp: -0.42, col: "hot" },
      { geo: buildCircuitLadderArc(2.2, 2.75, Math.PI * 1.55, Math.PI * 0.85, 4, 48, 13), rot: [0.55, -0.35, 0.4], sp: 0.22, col: "gold" },
      { geo: buildCircuitLadderArc(0.84, 1.24, 0.0, Math.PI * 1.75, 3, 36, 17), rot: [0.9, 0.18, 0.65], sp: 0.56, col: "hot" },
    ],
    []
  );

  const webGeo = useMemo(() => {
    const fVerts: number[] = [];
    const n = 760;
    const pts: Array<[number, number, number]> = [];
    for (let i = 0; i < n; i++) {
      const phi = Math.acos(1 - (2 * (i + 0.5)) / n);
      const theta = Math.PI * (1 + Math.sqrt(5)) * (i + 5);
      const r = 2.18 + Math.sin(phi * 9 + theta * 3) * 0.18;
      pts.push([Math.sin(phi) * Math.cos(theta) * r, Math.cos(phi) * r, Math.sin(phi) * Math.sin(theta) * r]);
    }
    for (let i = 0; i < n; i += 2) {
      const [ax, ay, az] = pts[i];
      for (let j = i + 1; j < Math.min(n, i + 20); j++) {
        const [bx, by, bz] = pts[j];
        if (Math.hypot(ax - bx, ay - by, az - bz) < 0.5) fVerts.push(ax, ay, az, bx, by, bz);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(fVerts, 3));
    return g;
  }, []);

  const smoothVoiceRef = useRef(0);

  useFrame(({ clock, camera }, delta) => {
    const t = clock.getElapsedTime();
    speechEnergyRef.current = Math.max(0, speechEnergyRef.current - delta * 2.5);

    const targetVoice =
      state === "SPEAKING"
        ? 0.36 +
          Math.abs(Math.sin(t * 15.2)) * 0.34 +
          Math.abs(Math.sin(t * 24.8)) * 0.22 +
          speechEnergyRef.current * 0.58
        : state === "LISTENING"
        ? 0.28 + Math.abs(Math.sin(t * 11.0)) * 0.22 + speechEnergyRef.current * 0.65 + micEnergyRef.current * 0.75
        : state === "EXECUTING"
        ? 0.44 + Math.sin(t * 12.0) * 0.18
        : state === "THINKING"
        ? 0.26 + Math.sin(t * 8.0) * 0.12
        : 0.04 + Math.sin(t * 1.8) * 0.03;

    smoothVoiceRef.current = THREE.MathUtils.lerp(smoothVoiceRef.current, targetVoice, Math.min(1, delta * 13));
    const vocal = smoothVoiceRef.current;

    const speed =
      state === "EXECUTING" ? 2.5 : state === "SPEAKING" ? 2.0 : state === "THINKING" ? 2.2 : state === "LISTENING" ? 1.75 : 0.78;

    flowMat.uniforms.uTime.value = t;
    flowMat.uniforms.uVoice.value = vocal;
    flowMat.uniforms.uFlowSpeed.value = speed;

    camera.position.x = THREE.MathUtils.lerp(camera.position.x, Math.sin(t * 0.26) * 0.36 + mouseRef.current.x * 0.65, 0.045);
    camera.position.y = THREE.MathUtils.lerp(camera.position.y, Math.cos(t * 0.22) * 0.22 - mouseRef.current.y * 0.42, 0.045);
    camera.lookAt(0, 0, 0);

    if (rootRef.current) {
      rootRef.current.position.y = Math.sin(t * 1.2) * 0.08;
      rootRef.current.rotation.y += delta * 0.11 * speed;
      rootRef.current.rotation.x = THREE.MathUtils.lerp(rootRef.current.rotation.x, mouseRef.current.y * 0.26, 0.05);
      rootRef.current.rotation.z = THREE.MathUtils.lerp(rootRef.current.rotation.z, -mouseRef.current.x * 0.18, 0.05);
    }

    if (coreGroupRef.current) {
      coreGroupRef.current.rotation.z -= delta * 0.92 * speed;
      coreGroupRef.current.rotation.x += delta * 0.52 * speed;
      coreGroupRef.current.scale.setScalar(0.94 + vocal * 0.55);
    }

    if (crescentRibbonRef.current) {
      crescentRibbonRef.current.rotation.z = Math.sin(t * 0.35) * 0.18;
      crescentRibbonRef.current.rotation.y = Math.cos(t * 0.28) * 0.25;
      crescentRibbonRef.current.scale.setScalar(1.0 + vocal * 0.22);
    }

    sectorLayers.forEach((lay, idx) => {
      const grp = sectorRefs.current[idx];
      if (!grp) return;
      grp.rotation.z += delta * lay.sp * speed;
      grp.rotation.x = lay.rot[0] + Math.sin(t * 0.45 + idx) * 0.12;
      grp.rotation.y = lay.rot[1] + Math.cos(t * 0.4 + idx) * 0.12;
      grp.scale.setScalar(1.0 + vocal * (0.12 + (idx % 3) * 0.05));
    });

    if (webRef.current) {
      webRef.current.rotation.y -= delta * 0.22 * speed;
      webRef.current.scale.setScalar(1.0 + vocal * 0.28);
    }

    if (shockRef.current) {
      const show = state === "SPEAKING" || state === "EXECUTING" || state === "LISTENING" || state === "VERIFIED" || state === "ALERT";
      if (!show) {
        shockRef.current.visible = false;
      } else {
        const cyc = (t * 1.45) % 1.0;
        shockRef.current.visible = true;
        shockRef.current.scale.setScalar(0.92 + cyc * 2.55);
        (shockRef.current.material as THREE.MeshBasicMaterial).opacity = (1.0 - cyc) * 0.46;
      }
    }
  });

  return (
    <group ref={rootRef}>
      {/* 8,000 FLOWING GOLDEN-FIRE PARTICLES REACTING TO VOICE & LISTENING */}
      <points geometry={flowGeo} material={flowMat} frustumCulled={false} />

      {/* MOLTEN INNER RING-KNOT CORE */}
      <group ref={coreGroupRef}>
        <mesh>
          <torusGeometry args={[0.32, 0.04, 14, 64]} />
          <meshBasicMaterial color={hotCol} toneMapped={false} />
        </mesh>
        <mesh rotation={[Math.PI / 2.4, 0.4, 0]}>
          <torusGeometry args={[0.46, 0.028, 12, 64, Math.PI * 1.65]} />
          <meshBasicMaterial color={goldCol} toneMapped={false} />
        </mesh>
        <mesh rotation={[-Math.PI / 3, 1.1, 0.5]}>
          <torusGeometry args={[0.64, 0.02, 12, 64, Math.PI * 1.4]} />
          <meshBasicMaterial color={amberCol} toneMapped={false} />
        </mesh>
        {innerRibbons.map((geo, i) => (
          <mesh key={i} geometry={geo}>
            <meshBasicMaterial color={i % 2 === 0 ? hotCol : goldCol} transparent opacity={0.88} toneMapped={false} blending={THREE.AdditiveBlending} depthWrite={false} />
          </mesh>
        ))}
      </group>

      {/* SIGNATURE SWEEPING INNER C-RIBBON & RIGHT HORIZONTAL CORE BRIDGE */}
      <group ref={crescentRibbonRef}>
        <mesh geometry={cRibbonGeo}>
          <meshBasicMaterial color={goldCol} transparent opacity={0.82} toneMapped={false} blending={THREE.AdditiveBlending} depthWrite={false} />
        </mesh>
        <mesh geometry={coreBridgeGeo}>
          <meshBasicMaterial color={hotCol} transparent opacity={0.78} toneMapped={false} blending={THREE.AdditiveBlending} depthWrite={false} />
        </mesh>
      </group>

      {/* PROTRUDING CIRCUIT-LADDER SECTOR FINS */}
      {sectorLayers.map((lay, idx) => (
        <group key={idx} ref={(el) => { sectorRefs.current[idx] = el; }} rotation={lay.rot as [number, number, number]}>
          <lineSegments geometry={lay.geo}>
            <lineBasicMaterial
              color={lay.col === "hot" ? hotCol : lay.col === "gold" ? goldCol : amberCol}
              transparent
              opacity={idx < 2 ? 0.78 : 0.56}
              blending={THREE.AdditiveBlending}
              depthWrite={false}
              toneMapped={false}
            />
          </lineSegments>
        </group>
      ))}

      {/* OUTER NEURAL FILAMENT WEB */}
      <lineSegments ref={webRef} geometry={webGeo}>
        <lineBasicMaterial color={amberCol} transparent opacity={0.28} blending={THREE.AdditiveBlending} depthWrite={false} />
      </lineSegments>

      {/* DUAL SMOKY BRONZE BACKDROP CRESCENTS (top-left & bottom-right from reference image) */}
      <mesh position={[0, 0, -0.5]}>
        <ringGeometry args={[2.35, 3.05, 64, 1, Math.PI * 0.52, Math.PI * 0.55]} />
        <meshBasicMaterial color="#6b5235" transparent opacity={0.22} side={THREE.DoubleSide} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh position={[0, 0, -0.5]}>
        <ringGeometry args={[2.3, 3.02, 64, 1, -Math.PI * 0.58, Math.PI * 0.52]} />
        <meshBasicMaterial color="#5c4730" transparent opacity={0.2} side={THREE.DoubleSide} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>

      {/* EXPANDING VOICE SHOCKWAVE RING */}
      <mesh ref={shockRef} visible={false}>
        <ringGeometry args={[1.45, 1.5, 72]} />
        <meshBasicMaterial color={hotCol} transparent opacity={0.45} side={THREE.DoubleSide} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
    </group>
  );
};

export const Jarvis3DCore: React.FC<Jarvis3DCoreProps> = ({
  state,
  speechPulse = 0,
  voiceListening = false,
}) => {
  const speechEnergyRef = useRef(0);
  const micEnergyRef = useRef(0);
  const mouseRef = useRef({ x: 0, y: 0 });

  useEffect(() => {
    if (speechPulse > 0) speechEnergyRef.current = 1.0;
  }, [speechPulse]);

  useEffect(() => {
    if (!voiceListening || !navigator.mediaDevices?.getUserMedia) {
      micEnergyRef.current = 0;
      return;
    }
    let cancelled = false;
    let ctx: AudioContext | null = null;
    let stream: MediaStream | null = null;
    let raf = 0;

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((s) => {
        if (cancelled) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        stream = s;
        ctx = new AudioContext();
        const src = ctx.createMediaStreamSource(s);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 64;
        src.connect(analyser);
        const buf = new Uint8Array(analyser.frequencyBinCount);
        const tick = () => {
          if (cancelled) return;
          analyser.getByteFrequencyData(buf);
          const avg = buf.reduce((a, b) => a + b, 0) / Math.max(1, buf.length);
          micEnergyRef.current = Math.min(1, avg / 70);
          raf = requestAnimationFrame(tick);
        };
        tick();
      })
      .catch(() => {
        micEnergyRef.current = 0;
      });

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
      ctx?.close().catch(() => {});
    };
  }, [voiceListening]);

  return (
    <div
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        mouseRef.current = {
          x: ((e.clientX - r.left) / Math.max(1, r.width)) * 2 - 1,
          y: ((e.clientY - r.top) / Math.max(1, r.height)) * 2 - 1,
        };
      }}
      className="absolute inset-0 w-full h-full bg-[#000000] overflow-hidden"
    >
      {/* Exact Stark HUD Frame Hairlines & Spinning Bottom-Right Emblem matching reference image */}
      <svg className="pointer-events-none absolute inset-0 w-full h-full z-10 opacity-65" preserveAspectRatio="none" viewBox="0 0 1200 720">
        {/* Top segmented golden header bar */}
        <rect x="85" y="24" width="690" height="18" fill="#5c3a14" fillOpacity="0.28" stroke="#925c24" strokeWidth="1" />
        <rect x="85" y="42" width="155" height="4" fill="#d99b43" fillOpacity="0.85" />
        <rect x="640" y="26" width="58" height="14" fill="#b45309" fillOpacity="0.55" />
        <rect x="706" y="29" width="58" height="8" fill="#000000" stroke="#78350f" strokeWidth="1" />
        <rect x="748" y="31" width="10" height="4" fill="#fbbf24" />
        {/* Left-mid horizontal double accent bar */}
        <rect x="0" y="210" width="315" height="6" fill="#d99b43" fillOpacity="0.45" />
        <line x1="0" y1="220" x2="290" y2="220" stroke="#f59e0b" strokeWidth="1.2" strokeOpacity="0.55" />
        {/* Thin right & bottom-left framing brackets */}
        <polyline points="870,155 1095,155 1095,620" fill="none" stroke="#78491b" strokeWidth="1" />
        <polyline points="125,520 125,630 290,630" fill="none" stroke="#78491b" strokeWidth="1" />
        {/* Bottom segmented bronze bar */}
        <rect x="40" y="688" width="995" height="8" fill="#4a2e10" fillOpacity="0.35" stroke="#78491b" strokeWidth="0.8" />
        <rect x="720" y="688" width="315" height="8" fill="#b4732a" fillOpacity="0.48" />
        {/* Spinning bottom-right miniature Stark radial emblem */}
        <g transform="translate(1140, 672)">
          <circle r="30" fill="none" stroke="#b45309" strokeWidth="1.4" strokeDasharray="8 6">
            <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="14s" repeatCount="indefinite" />
          </circle>
          <circle r="19" fill="none" stroke="#f59e0b" strokeWidth="3.2" strokeDasharray="16 8">
            <animateTransform attributeName="transform" type="rotate" from="360" to="0" dur="9s" repeatCount="indefinite" />
          </circle>
          <circle r="8" fill="none" stroke="#fef08a" strokeWidth="1.8" />
          <circle r="3.5" fill="#fffbeb" />
        </g>
      </svg>

      <Canvas
        camera={{ position: [0, 0, 7.0], fov: 44 }}
        gl={{ antialias: true, alpha: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.32 }}
      >
        <ambientLight intensity={0.22} />
        <pointLight position={[0, 0, 4]} intensity={2.8} color="#ffb703" />
        <OriginalJarvisScene
          state={state}
          speechEnergyRef={speechEnergyRef}
          micEnergyRef={micEnergyRef}
          mouseRef={mouseRef}
        />
        <EffectComposer multisampling={2}>
          <Bloom luminanceThreshold={0.38} mipmapBlur intensity={1.9} radius={0.85} />
        </EffectComposer>
      </Canvas>
    </div>
  );
};
