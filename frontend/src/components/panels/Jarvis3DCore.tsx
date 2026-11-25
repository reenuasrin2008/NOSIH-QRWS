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

const STATE_PALETTES: Record<JarvisState, { primary: string; core: string; accent: string; flare: string }> = {
  IDLE:      { primary: "#f59e0b", core: "#fff7cc", accent: "#d97706", flare: "#fbbf24" },
  LISTENING: { primary: "#fbbf24", core: "#ffffff", accent: "#f59e0b", flare: "#fde047" },
  THINKING:  { primary: "#fb923c", core: "#ffffff", accent: "#f59e0b", flare: "#fef08a" },
  EXECUTING: { primary: "#ea580c", core: "#fffbeb", accent: "#f97316", flare: "#fdba74" },
  SPEAKING:  { primary: "#f59e0b", core: "#ffffff", accent: "#fbbf24", flare: "#fef08a" },
  VERIFIED:  { primary: "#34d399", core: "#ecfdf5", accent: "#10b981", flare: "#6ee7b7" },
  ALERT:     { primary: "#ef4444", core: "#fef2f2", accent: "#dc2626", flare: "#fca5a5" },
};

const IronManJarvisMatrix: React.FC<{
  state: JarvisState;
  speechEnergyRef: React.MutableRefObject<number>;
  micEnergyRef: React.MutableRefObject<number>;
  mouseRef: React.MutableRefObject<{ x: number; y: number }>;
}> = ({ state, speechEnergyRef, micEnergyRef, mouseRef }) => {
  const rootRef = useRef<THREE.Group>(null);
  const coreRef = useRef<THREE.Mesh>(null);
  const coreHaloRef = useRef<THREE.Mesh>(null);
  const innerPointsRef = useRef<THREE.Points>(null);
  const midPointsRef = useRef<THREE.Points>(null);
  const outerPointsRef = useRef<THREE.Points>(null);
  const webLinesRef = useRef<THREE.LineSegments>(null);
  const spikeLinesRef = useRef<THREE.LineSegments>(null);
  const ringsGroupRef = useRef<THREE.Group>(null);
  const ringRefs = useRef<Array<THREE.Mesh | null>>([]);
  const shock1Ref = useRef<THREE.Mesh>(null);
  const shock2Ref = useRef<THREE.Mesh>(null);

  const pal = STATE_PALETTES[state];
  const primaryCol = useMemo(() => new THREE.Color(pal.primary), [pal.primary]);
  const coreCol = useMemo(() => new THREE.Color(pal.core), [pal.core]);
  const accentCol = useMemo(() => new THREE.Color(pal.accent), [pal.accent]);
  const flareCol = useMemo(() => new THREE.Color(pal.flare), [pal.flare]);

  // Build rich multi-shell Iron Man neural sphere + synaptic filaments + radial data protrusions
  const { innerGeo, midGeo, outerGeo, webGeo, spikeGeo } = useMemo(() => {
    const makeShell = (count: number, minR: number, maxR: number, seed: number) => {
      const pos = new Float32Array(count * 3);
      for (let i = 0; i < count; i++) {
        const phi = Math.acos(1 - (2 * (i + 0.5)) / count);
        const theta = Math.PI * (1 + Math.sqrt(5)) * (i + seed);
        const jitter = (((i * 47 + seed * 13) % 100) / 100);
        const r = minR + jitter * (maxR - minR);
        pos[i * 3] = Math.sin(phi) * Math.cos(theta) * r;
        pos[i * 3 + 1] = Math.cos(phi) * r;
        pos[i * 3 + 2] = Math.sin(phi) * Math.sin(theta) * r;
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      return { geo: g, pos };
    };

    const inner = makeShell(360, 0.72, 1.38, 3);
    const mid = makeShell(520, 1.4, 2.22, 19);
    const outer = makeShell(420, 2.15, 2.75, 41);

    // Synaptic neural web connecting inner + mid nodes
    const webVerts: number[] = [];
    const mPts = mid.pos;
    const mCount = mPts.length / 3;
    for (let i = 0; i < mCount; i += 2) {
      const ax = mPts[i * 3], ay = mPts[i * 3 + 1], az = mPts[i * 3 + 2];
      for (let j = i + 1; j < Math.min(mCount, i + 28); j++) {
        const bx = mPts[j * 3], by = mPts[j * 3 + 1], bz = mPts[j * 3 + 2];
        if (Math.hypot(ax - bx, ay - by, az - bz) < 0.72) {
          webVerts.push(ax, ay, az, bx, by, bz);
        }
      }
    }
    const wGeo = new THREE.BufferGeometry();
    wGeo.setAttribute("position", new THREE.Float32BufferAttribute(webVerts, 3));

    // Signature Iron Man movie jagged radial holographic data flares protruding around the sphere
    const spikeVerts: number[] = [];
    for (let i = 0; i < 160; i++) {
      const phi = Math.acos(1 - (2 * (i + 0.5)) / 160);
      const theta = Math.PI * (1 + Math.sqrt(5)) * (i + 7);
      const dirX = Math.sin(phi) * Math.cos(theta);
      const dirY = Math.cos(phi);
      const dirZ = Math.sin(phi) * Math.sin(theta);
      const r0 = 1.65 + ((i * 19) % 10) * 0.04;
      const r1 = r0 + (i % 5 === 0 ? 0.92 : 0.36 + ((i * 31) % 10) * 0.04);
      spikeVerts.push(dirX * r0, dirY * r0, dirZ * r0, dirX * r1, dirY * r1, dirZ * r1);
    }
    const sGeo = new THREE.BufferGeometry();
    sGeo.setAttribute("position", new THREE.Float32BufferAttribute(spikeVerts, 3));

    return { innerGeo: inner.geo, midGeo: mid.geo, outerGeo: outer.geo, webGeo: wGeo, spikeGeo: sGeo };
  }, []);

  const ringSpecs = useMemo(
    () => [
      { r: 1.48, tube: 0.022, arc: Math.PI * 1.65, rx: 0.4, ry: 0.2, sp: 0.85 },
      { r: 1.88, tube: 0.028, arc: Math.PI * 1.4,  rx: 1.1, ry: 0.6, sp: -1.1 },
      { r: 2.24, tube: 0.024, arc: Math.PI * 1.55, rx: 0.7, ry: 1.3, sp: 0.75 },
      { r: 2.52, tube: 0.018, arc: Math.PI * 1.25, rx: 1.4, ry: 0.3, sp: -0.65 },
      { r: 2.74, tube: 0.014, arc: Math.PI * 1.85, rx: 0.2, ry: 0.9, sp: 0.45 },
      { r: 1.15, tube: 0.018, arc: Math.PI * 1.5,  rx: 0.9, ry: 1.1, sp: -1.35 },
    ],
    []
  );

  useFrame(({ clock }, delta) => {
    const t = clock.getElapsedTime();
    speechEnergyRef.current = Math.max(0, speechEnergyRef.current - delta * 2.5);

    const vocal =
      state === "SPEAKING"
        ? 0.22 +
          Math.abs(Math.sin(t * 13.5)) * 0.24 +
          Math.abs(Math.sin(t * 21.7)) * 0.16 +
          speechEnergyRef.current * 0.42
        : state === "LISTENING"
        ? 0.12 + micEnergyRef.current * 0.55
        : state === "EXECUTING"
        ? 0.28 + Math.sin(t * 11.0) * 0.14
        : state === "THINKING"
        ? 0.18 + Math.sin(t * 7.5) * 0.09
        : 0.04 + Math.sin(t * 1.9) * 0.035;

    const speed =
      state === "EXECUTING"
        ? 2.7
        : state === "SPEAKING"
        ? 2.0
        : state === "THINKING"
        ? 2.3
        : state === "LISTENING"
        ? 1.7
        : 0.72;

    if (rootRef.current) {
      // Organic Stark-lab levitation + responsive cursor tracking
      rootRef.current.position.y = Math.sin(t * 1.3) * 0.12;
      rootRef.current.position.x = Math.cos(t * 0.75) * 0.06;
      rootRef.current.rotation.y += delta * 0.18 * speed;
      rootRef.current.rotation.x = THREE.MathUtils.lerp(rootRef.current.rotation.x, mouseRef.current.y * 0.34, 0.055);
      rootRef.current.rotation.z = THREE.MathUtils.lerp(rootRef.current.rotation.z, -mouseRef.current.x * 0.22, 0.055);
    }

    if (coreRef.current) {
      coreRef.current.scale.setScalar(0.64 + vocal * 0.46);
    }
    if (coreHaloRef.current) {
      coreHaloRef.current.scale.setScalar(0.95 + vocal * 0.52);
      coreHaloRef.current.rotation.y -= delta * 0.9 * speed;
    }

    if (innerPointsRef.current) {
      innerPointsRef.current.rotation.y -= delta * 0.52 * speed;
      innerPointsRef.current.rotation.x += delta * 0.22 * speed;
      innerPointsRef.current.scale.setScalar(1.0 + vocal * 0.26);
    }
    if (midPointsRef.current) {
      midPointsRef.current.rotation.y += delta * 0.34 * speed;
      midPointsRef.current.rotation.z -= delta * 0.18 * speed;
      midPointsRef.current.scale.setScalar(1.0 + vocal * 0.3);
    }
    if (outerPointsRef.current) {
      outerPointsRef.current.rotation.y -= delta * 0.2 * speed;
      outerPointsRef.current.rotation.x -= delta * 0.12 * speed;
      outerPointsRef.current.scale.setScalar(1.0 + vocal * 0.36);
    }
    if (webLinesRef.current) {
      webLinesRef.current.rotation.y += delta * 0.34 * speed;
      webLinesRef.current.rotation.z -= delta * 0.18 * speed;
      webLinesRef.current.scale.setScalar(1.0 + vocal * 0.3);
    }
    if (spikeLinesRef.current) {
      spikeLinesRef.current.rotation.y -= delta * 0.26 * speed;
      spikeLinesRef.current.rotation.x += delta * 0.14 * speed;
      spikeLinesRef.current.scale.setScalar(1.0 + vocal * 0.44);
    }

    ringSpecs.forEach((spec, idx) => {
      const m = ringRefs.current[idx];
      if (!m) return;
      m.rotation.z += delta * spec.sp * speed;
      m.rotation.x = spec.rx + Math.sin(t * 0.65 + idx) * 0.22;
      m.rotation.y = spec.ry + Math.cos(t * 0.55 + idx) * 0.22;
      m.scale.setScalar(1.0 + vocal * (0.14 + idx * 0.03));
    });

    const showWaves = state === "SPEAKING" || state === "EXECUTING" || state === "LISTENING" || state === "VERIFIED" || state === "ALERT";
    [shock1Ref.current, shock2Ref.current].forEach((sh, idx) => {
      if (!sh) return;
      if (!showWaves) {
        sh.visible = false;
        return;
      }
      const cyc = (t * 1.35 + idx * 0.5) % 1.0;
      sh.visible = true;
      sh.scale.setScalar(0.95 + cyc * 2.65);
      (sh.material as THREE.MeshBasicMaterial).opacity = (1.0 - cyc) * 0.48;
    });
  });

  return (
    <group ref={rootRef}>
      {/* Blazing Incandescent Nucleus */}
      <mesh ref={coreRef}>
        <icosahedronGeometry args={[0.68, 4]} />
        <meshStandardMaterial
          color={coreCol}
          emissive={primaryCol}
          emissiveIntensity={3.2}
          roughness={0.1}
          metalness={0.1}
          toneMapped={false}
        />
      </mesh>

      {/* Inner Holographic Faceted Energy Shell */}
      <mesh ref={coreHaloRef}>
        <icosahedronGeometry args={[1.08, 2]} />
        <meshBasicMaterial color={flareCol} wireframe transparent opacity={0.32} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>

      {/* 3 Volumetric Swirling Golden Particle Shells */}
      <points ref={innerPointsRef} geometry={innerGeo}>
        <pointsMaterial color={coreCol} size={0.072} transparent opacity={0.95} sizeAttenuation blending={THREE.AdditiveBlending} depthWrite={false} />
      </points>
      <points ref={midPointsRef} geometry={midGeo}>
        <pointsMaterial color={flareCol} size={0.062} transparent opacity={0.86} sizeAttenuation blending={THREE.AdditiveBlending} depthWrite={false} />
      </points>
      <points ref={outerPointsRef} geometry={outerGeo}>
        <pointsMaterial color={primaryCol} size={0.048} transparent opacity={0.68} sizeAttenuation blending={THREE.AdditiveBlending} depthWrite={false} />
      </points>

      {/* Glowing Neural Synaptic Filament Web */}
      <lineSegments ref={webLinesRef} geometry={webGeo}>
        <lineBasicMaterial color={accentCol} transparent opacity={0.38} blending={THREE.AdditiveBlending} depthWrite={false} />
      </lineSegments>

      {/* Radial Holographic Data Protrusions / Flares */}
      <lineSegments ref={spikeLinesRef} geometry={spikeGeo}>
        <lineBasicMaterial color={flareCol} transparent opacity={0.52} blending={THREE.AdditiveBlending} depthWrite={false} />
      </lineSegments>

      {/* 6 Counter-Rotating Gyroscopic Circuit Rings */}
      <group ref={ringsGroupRef}>
        {ringSpecs.map((spec, idx) => (
          <mesh key={idx} ref={(el) => { ringRefs.current[idx] = el; }}>
            <torusGeometry args={[spec.r, spec.tube, 12, 110, spec.arc]} />
            <meshBasicMaterial
              color={idx % 2 === 0 ? coreCol : primaryCol}
              transparent
              opacity={idx === 4 ? 0.35 : 0.82}
              wireframe={idx === 4}
              toneMapped={false}
              blending={THREE.AdditiveBlending}
              depthWrite={false}
            />
          </mesh>
        ))}
      </group>

      {/* Dual Expanding Voice/Execution Shockwave Rings */}
      <mesh ref={shock1Ref} visible={false}>
        <ringGeometry args={[1.38, 1.44, 72]} />
        <meshBasicMaterial color={coreCol} transparent opacity={0.45} side={THREE.DoubleSide} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh ref={shock2Ref} visible={false} rotation={[Math.PI / 3, Math.PI / 5, 0]}>
        <ringGeometry args={[1.38, 1.43, 72]} />
        <meshBasicMaterial color={flareCol} transparent opacity={0.4} side={THREE.DoubleSide} blending={THREE.AdditiveBlending} depthWrite={false} />
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
    if (speechPulse > 0) {
      speechEnergyRef.current = 1.0;
    }
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
          micEnergyRef.current = Math.min(1, avg / 80);
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
      className="absolute inset-0 w-full h-full bg-[radial-gradient(circle_at_center,#1d1204_0%,#06070a_52%,#010203_100%)]"
    >
      <Canvas
        camera={{ position: [0, 0, 7.2], fov: 44 }}
        gl={{ antialias: true, alpha: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.2 }}
      >
        <ambientLight intensity={0.4} />
        <pointLight position={[5, 5, 6]} intensity={2.8} color="#fbbf24" />
        <pointLight position={[-5, -4, -4]} intensity={1.4} color="#ea580c" />
        <IronManJarvisMatrix
          state={state}
          speechEnergyRef={speechEnergyRef}
          micEnergyRef={micEnergyRef}
          mouseRef={mouseRef}
        />
        <EffectComposer multisampling={2}>
          <Bloom luminanceThreshold={0.62} mipmapBlur intensity={1.35} radius={0.72} />
        </EffectComposer>
      </Canvas>
    </div>
  );
};
