import React, { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { EffectComposer, Bloom, ToneMapping } from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";
import * as THREE from "three";

export interface JarvisNeuralCore3DProps {
  listening: boolean;
  speaking: boolean;
  thinking: boolean;
  audioLevel?: number; // Static fallback; live callers should provide audioLevelRef.
  audioLevelRef?: RefObject<number>;
  statusLabel?: string;
  optimizing?: boolean;
  awaitingApproval?: boolean;
  error?: boolean;
}

type CoreVisualMode =
  | "IDLE"
  | "SPEAKING"
  | "LISTENING"
  | "THINKING"
  | "AWAITING_APPROVAL"
  | "ERROR";

interface CorePalette {
  primary: string;
  ember: string;
  gold: string;
  hotCore: string;
  arcBright: string;
  nodeColor: string;
  hudBorder: string;
  dotClass: string;
}

const PALETTES: Record<CoreVisualMode, CorePalette> = {
  IDLE: {
    primary: "#ff8c1a",
    ember: "#ff5500",
    gold: "#ffb84d",
    hotCore: "#fff2cc",
    arcBright: "#ffae33",
    nodeColor: "#ff9924",
    hudBorder: "rgba(255, 148, 36, 0.35)",
    dotClass: "bg-[#ff8c1a]",
  },
  SPEAKING: {
    primary: "#ff7a00",
    ember: "#ff5500",
    gold: "#ffb84d",
    hotCore: "#fff6dc",
    arcBright: "#ffc15e",
    nodeColor: "#ffb84d",
    hudBorder: "rgba(255, 165, 56, 0.48)",
    dotClass: "bg-[#ffb84d] animate-pulse",
  },
  LISTENING: {
    primary: "#ffbe3b",
    ember: "#ff8c1a",
    gold: "#ffd97d",
    hotCore: "#fff8e1",
    arcBright: "#ffe08a",
    nodeColor: "#ffcf5c",
    hudBorder: "rgba(255, 190, 59, 0.50)",
    dotClass: "bg-[#ffbe3b] animate-ping",
  },
  THINKING: {
    primary: "#ff9f1c",
    ember: "#ff6d00",
    gold: "#ffd166",
    hotCore: "#fffaf0",
    arcBright: "#ffdf91",
    nodeColor: "#ffb703",
    hudBorder: "rgba(255, 159, 28, 0.45)",
    dotClass: "bg-[#ff9f1c] animate-pulse",
  },
  AWAITING_APPROVAL: {
    primary: "#ff6b00",
    ember: "#e63900",
    gold: "#ffa347",
    hotCore: "#ffe8c2",
    arcBright: "#ff8524",
    nodeColor: "#ff7714",
    hudBorder: "rgba(255, 107, 0, 0.50)",
    dotClass: "bg-[#ff6b00] animate-pulse",
  },
  ERROR: {
    primary: "#ff3b1f",
    ember: "#b81d00",
    gold: "#ff7849",
    hotCore: "#ffd6cc",
    arcBright: "#ff5733",
    nodeColor: "#ff4d2e",
    hudBorder: "rgba(255, 59, 31, 0.48)",
    dotClass: "bg-[#ff3b1f] animate-ping",
  },
};

function seededRand(seed: number): () => number {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function sphericalToCartesian(
  r: number,
  theta: number,
  phi: number
): [number, number, number] {
  const sinPhi = Math.sin(phi);
  return [
    r * sinPhi * Math.cos(theta),
    r * Math.cos(phi),
    r * sinPhi * Math.sin(theta),
  ];
}

/**
 * Generates stepped, PCB/neural-style jagged circuit filament segments distributed
 * across a spherical shell (optionally with radial outward spurs like JARVIS halo).
 */
function buildCircuitShellGeometry(
  radius: number,
  traceCount: number,
  stepsPerTrace: number,
  seed: number,
  phiMin = 0.08,
  phiMax = Math.PI - 0.08,
  spurChance = 0.22
): THREE.BufferGeometry {
  const rand = seededRand(seed);
  const positions: number[] = [];

  for (let t = 0; t < traceCount; t++) {
    let theta = rand() * Math.PI * 2;
    let phi = phiMin + rand() * (phiMax - phiMin);
    let r = radius + (rand() - 0.5) * 0.06;
    const stepLen = 0.05 + rand() * 0.045;

    for (let s = 0; s < stepsPerTrace; s++) {
      const p0 = sphericalToCartesian(r, theta, phi);
      const dir = Math.floor(rand() * 6);
      if (dir === 0) theta += stepLen;
      else if (dir === 1) theta -= stepLen;
      else if (dir === 2) phi = Math.min(phiMax, phi + stepLen * 0.72);
      else if (dir === 3) phi = Math.max(phiMin, phi - stepLen * 0.72);
      else if (dir === 4) {
        theta += stepLen * 0.7;
        phi = Math.min(phiMax, phi + stepLen * 0.5);
      } else {
        theta -= stepLen * 0.7;
        phi = Math.max(phiMin, phi - stepLen * 0.5);
      }
      const p1 = sphericalToCartesian(r, theta, phi);
      positions.push(p0[0], p0[1], p0[2], p1[0], p1[1], p1[2]);

      // Occasional radial circuit spur extending outward/inward for volumetric depth
      if (rand() < spurChance) {
        const spurR = r + (rand() > 0.35 ? 0.09 + rand() * 0.14 : -0.07);
        const pSpur = sphericalToCartesian(spurR, theta, phi);
        positions.push(p1[0], p1[1], p1[2], pSpur[0], pSpur[1], pSpur[2]);
      }
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return geo;
}

/** Generates a dense multi-layered circuit ring with organic jagged neural spurs. */
function buildCircuitRingGeometry(
  radius: number,
  width: number,
  count: number,
  seed: number
): THREE.BufferGeometry {
  const rand = seededRand(seed);
  const positions: number[] = [];

  for (let i = 0; i < count; i++) {
    let a = rand() * Math.PI * 2;
    let r = radius + (rand() - 0.5) * width;
    let y = (rand() - 0.5) * (width * 0.35);

    for (let s = 0; s < 10; s++) {
      const x0 = Math.cos(a) * r;
      const z0 = Math.sin(a) * r;
      const y0 = y;

      if (rand() < 0.72) {
        a += 0.045 + rand() * 0.032;
      } else {
        r += (rand() - 0.5) * width * 0.36;
        y += (rand() - 0.5) * width * 0.25;
      }

      const x1 = Math.cos(a) * r;
      const z1 = Math.sin(a) * r;
      positions.push(x0, y0, z0, x1, y, z1);
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return geo;
}

/** Generates pulsing radial energy filaments connecting inner plasma core to outer circuit shell. */
function buildRadialFilamentsGeometry(
  innerR: number,
  outerR: number,
  count: number,
  seed: number
): THREE.BufferGeometry {
  const rand = seededRand(seed);
  const positions: number[] = [];

  for (let i = 0; i < count; i++) {
    const theta = rand() * Math.PI * 2;
    const phi = Math.acos(2 * rand() - 1);
    const segments = 5;
    let prev = sphericalToCartesian(innerR, theta, phi);
    for (let s = 1; s <= segments; s++) {
      const frac = s / segments;
      const r = innerR + (outerR - innerR) * frac;
      const jitterTheta = theta + (rand() - 0.5) * 0.14 * frac;
      const jitterPhi = Math.max(0.1, Math.min(Math.PI - 0.1, phi + (rand() - 0.5) * 0.14 * frac));
      const next = sphericalToCartesian(r, jitterTheta, jitterPhi);
      positions.push(prev[0], prev[1], prev[2], next[0], next[1], next[2]);
      prev = next;
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return geo;
}

interface OrbitNodeSeed {
  radius: number;
  tiltX: number;
  tiltZ: number;
  speed: number;
  phase: number;
  size: number;
  isHot: boolean;
}

const ORBIT_NODE_COUNT = 180;

interface NeuralCoreMeshProps extends JarvisNeuralCore3DProps {
  mode: CoreVisualMode;
  palette: CorePalette;
  reducedMotion: boolean;
}

const NeuralCoreMesh: React.FC<NeuralCoreMeshProps> = ({
  listening,
  speaking,
  thinking,
  optimizing,
  awaitingApproval,
  audioLevel,
  audioLevelRef,
  palette,
  reducedMotion,
}) => {
  // Multi-layer refs (all animated in useFrame, zero React setState)
  const plasmaCoreRef = useRef<THREE.Mesh>(null);
  const plasmaHaloRef = useRef<THREE.Mesh>(null);
  const innerIcosaRef = useRef<THREE.Mesh>(null);
  const coreLightRef = useRef<THREE.PointLight>(null);

  const shell1Ref = useRef<THREE.Group>(null);
  const shell2Ref = useRef<THREE.Group>(null);
  const shell3Ref = useRef<THREE.Group>(null);

  const arcRing1Ref = useRef<THREE.Group>(null);
  const arcRing2Ref = useRef<THREE.Group>(null);
  const arcRing3Ref = useRef<THREE.Group>(null);

  const radialFilamentsRef = useRef<THREE.LineSegments>(null);
  const radialMatRef = useRef<THREE.LineBasicMaterial>(null);

  const instancedNodesRef = useRef<THREE.InstancedMesh>(null);
  const sparkPointsRef = useRef<THREE.Points>(null);

  const dummyObj = useMemo(() => new THREE.Object3D(), []);

  const geometries = useMemo(() => {
    const innerCore1 = buildCircuitShellGeometry(0.84, 155, 11, 101, 0.08, Math.PI - 0.08, 0.25);
    const innerCore2 = buildCircuitShellGeometry(1.12, 140, 11, 202, 0.1, Math.PI - 0.1, 0.22);
    const midShell = buildCircuitShellGeometry(1.58, 165, 12, 303, 0.08, Math.PI - 0.08, 0.28);
    const outerShellTop = buildCircuitShellGeometry(1.98, 95, 11, 404, 0.16, 1.15, 0.34);
    const outerShellBot = buildCircuitShellGeometry(
      1.98,
      90,
      11,
      505,
      Math.PI - 1.15,
      Math.PI - 0.16,
      0.34
    );
    const eqRing = buildCircuitRingGeometry(2.1, 0.28, 165, 606);
    const diagRing1 = buildCircuitRingGeometry(1.88, 0.16, 140, 707);
    const diagRing2 = buildCircuitRingGeometry(1.42, 0.12, 115, 808);
    const radialFilaments = buildRadialFilamentsGeometry(0.45, 2.02, 72, 909);

    // Dense glowing molten-orange micro-sparks distributed through the volumetric halo
    const rand = seededRand(1010);
    const pts = new Float32Array(900 * 3);
    for (let i = 0; i < 900; i++) {
      const r = i < 380 ? 0.55 + rand() * 0.65 : 1.35 + rand() * 0.85;
      const th = rand() * Math.PI * 2;
      const ph = Math.acos(2 * rand() - 1);
      const [x, y, z] = sphericalToCartesian(r, th, ph);
      pts[i * 3] = x;
      pts[i * 3 + 1] = y;
      pts[i * 3 + 2] = z;
    }
    const sparks = new THREE.BufferGeometry();
    sparks.setAttribute("position", new THREE.BufferAttribute(pts, 3));

    return {
      innerCore1,
      innerCore2,
      midShell,
      outerShellTop,
      outerShellBot,
      eqRing,
      diagRing1,
      diagRing2,
      radialFilaments,
      sparks,
    };
  }, []);

  const orbitNodes = useMemo<OrbitNodeSeed[]>(() => {
    const rand = seededRand(2026);
    const list: OrbitNodeSeed[] = [];
    for (let i = 0; i < ORBIT_NODE_COUNT; i++) {
      const band = i % 3;
      const radius =
        band === 0
          ? 0.92 + rand() * 0.32
          : band === 1
          ? 1.48 + rand() * 0.34
          : 1.92 + rand() * 0.36;
      list.push({
        radius,
        tiltX: (rand() - 0.5) * Math.PI * 1.4,
        tiltZ: (rand() - 0.5) * Math.PI * 1.4,
        speed: (0.28 + rand() * 0.72) * (rand() > 0.5 ? 1 : -1),
        phase: rand() * Math.PI * 2,
        size: 0.02 + rand() * 0.028,
        isHot: rand() > 0.68,
      });
    }
    return list;
  }, []);

  // Colorize instanced orbiting data nodes when palette changes
  useEffect(() => {
    const mesh = instancedNodesRef.current;
    if (!mesh) return;
    const cHot = new THREE.Color(palette.hotCore);
    const cMain = new THREE.Color(palette.nodeColor);
    const cEmber = new THREE.Color(palette.ember);
    for (let i = 0; i < ORBIT_NODE_COUNT; i++) {
      const node = orbitNodes[i];
      const col = node.isHot ? cHot : i % 3 === 0 ? cEmber : cMain;
      mesh.setColorAt(i, col);
    }
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [palette, orbitNodes]);

  useEffect(() => {
    return () => {
      Object.values(geometries).forEach((g) => g.dispose());
    };
  }, [geometries]);

  const smoothEnergyRef = useRef(0.14);

  useFrame((state, delta) => {
    const dt = Number.isFinite(delta) ? Math.min(Math.max(delta, 0), 0.05) : 0.016;
    const t = state.clock.elapsedTime;
    const motionScale = reducedMotion ? 0.18 : 1.0;
    const currentAudioLevel = audioLevelRef?.current ?? audioLevel ?? 0;
    const safeAudioLevel = Number.isFinite(currentAudioLevel) ? Math.max(0, Math.min(1, currentAudioLevel)) : 0;

    const synthWave = speaking
      ? 0.42 + Math.abs(Math.sin(t * 9.8)) * 0.45 + Math.abs(Math.cos(t * 5.3)) * 0.13
      : 0;
    const alertWave = awaitingApproval ? 0.28 + (Math.sin(t * 5.2) * 0.5 + 0.5) * 0.32 : 0;
    const targetEnergy = Math.min(
      1,
      Math.max(safeAudioLevel, synthWave, alertWave, thinking || optimizing ? 0.52 : 0.14)
    );

    // Frame-rate-independent damping
    smoothEnergyRef.current = THREE.MathUtils.damp(smoothEnergyRef.current, targetEnergy, 7.5, dt);
    const energy = smoothEnergyRef.current;

    const speedMult =
      (thinking || optimizing
        ? 2.35
        : listening || speaking
        ? 1.55 + energy * 1.45
        : awaitingApproval
        ? 1.4
        : 1.0) * motionScale;

    // 1. Breathing White-Hot / Molten Inner Core
    const coreBreath = 1.0 + Math.sin(t * 2.4) * 0.05 + energy * 0.24;
    if (plasmaCoreRef.current) {
      plasmaCoreRef.current.scale.set(coreBreath, coreBreath, coreBreath);
      plasmaCoreRef.current.rotation.y += dt * 0.45 * speedMult;
      plasmaCoreRef.current.rotation.x -= dt * 0.22 * speedMult;
    }
    if (plasmaHaloRef.current) {
      const haloScale = 1.0 + Math.sin(t * 1.9 + 0.8) * 0.08 + energy * 0.32;
      plasmaHaloRef.current.scale.set(haloScale, haloScale, haloScale);
    }
    if (innerIcosaRef.current) {
      innerIcosaRef.current.rotation.y -= dt * 0.62 * speedMult;
      innerIcosaRef.current.rotation.z += dt * 0.38 * speedMult;
      const icoScale = 1.0 + energy * 0.18 + Math.sin(t * 3.1) * 0.03;
      innerIcosaRef.current.scale.set(icoScale, icoScale, icoScale);
    }
    if (coreLightRef.current) {
      coreLightRef.current.intensity = 2.8 + energy * 3.4 + Math.sin(t * 3.5) * 0.4;
    }

    // 2. 3 Counter-Rotating Holographic Circuit Shells
    if (shell1Ref.current) {
      shell1Ref.current.rotation.y += dt * 0.24 * speedMult;
      shell1Ref.current.rotation.x += dt * 0.09 * speedMult;
      const s1 = 1.0 + energy * 0.1 + Math.sin(t * 2.2) * 0.015;
      shell1Ref.current.scale.set(s1, s1, s1);
    }
    if (shell2Ref.current) {
      shell2Ref.current.rotation.y -= dt * 0.14 * speedMult;
      shell2Ref.current.rotation.z += dt * 0.06 * speedMult;
    }
    if (shell3Ref.current) {
      shell3Ref.current.rotation.y += dt * 0.08 * speedMult;
      shell3Ref.current.rotation.x -= dt * 0.035 * speedMult;
    }

    // 3. Intersecting Stark HUD Luminous Arcs & Circuit Rings
    if (arcRing1Ref.current) {
      arcRing1Ref.current.rotation.y += dt * 0.22 * speedMult;
      const ar1 = 1.0 + energy * 0.06;
      arcRing1Ref.current.scale.set(ar1, ar1, ar1);
    }
    if (arcRing2Ref.current) {
      arcRing2Ref.current.rotation.z -= dt * 0.3 * speedMult;
      arcRing2Ref.current.rotation.x += dt * 0.05 * speedMult;
    }
    if (arcRing3Ref.current) {
      arcRing3Ref.current.rotation.y -= dt * 0.38 * speedMult;
      arcRing3Ref.current.rotation.z += dt * 0.14 * speedMult;
    }

    // 4. Pulsing Radial Energy Filaments
    if (radialFilamentsRef.current) {
      radialFilamentsRef.current.rotation.y += dt * 0.12 * speedMult;
      radialFilamentsRef.current.rotation.z -= dt * 0.07 * speedMult;
    }
    if (radialMatRef.current) {
      radialMatRef.current.opacity = 0.24 + (Math.sin(t * 3.4) * 0.5 + 0.5) * 0.34 + energy * 0.28;
    }

    // 5. Instanced Orbiting Amber-Orange Data Nodes
    if (instancedNodesRef.current) {
      const mesh = instancedNodesRef.current;
      for (let i = 0; i < ORBIT_NODE_COUNT; i++) {
        const n = orbitNodes[i];
        const angle = n.phase + t * n.speed * (0.65 + speedMult * 0.45);
        const rPulse = n.radius * (1.0 + Math.sin(t * 2.6 + n.phase) * 0.03 + energy * 0.07);
        // Point on equatorial circle, then apply spherical tilt
        const cx = Math.cos(angle) * rPulse;
        const cz = Math.sin(angle) * rPulse;
        const cosX = Math.cos(n.tiltX);
        const sinX = Math.sin(n.tiltX);
        const y1 = -cz * sinX;
        const z1 = cz * cosX;
        const cosZ = Math.cos(n.tiltZ);
        const sinZ = Math.sin(n.tiltZ);
        const fx = cx * cosZ - y1 * sinZ;
        const fy = cx * sinZ + y1 * cosZ;

        const nodeScale = n.size * (0.85 + Math.sin(t * 5.0 + n.phase) * 0.35 + energy * 0.45);
        dummyObj.position.set(fx, fy, z1);
        dummyObj.scale.set(nodeScale, nodeScale, nodeScale);
        dummyObj.updateMatrix();
        mesh.setMatrixAt(i, dummyObj.matrix);
      }
      if (mesh.instanceMatrix) mesh.instanceMatrix.needsUpdate = true;
    }

    if (sparkPointsRef.current) {
      sparkPointsRef.current.rotation.y += dt * 0.1 * speedMult;
      sparkPointsRef.current.rotation.x += dt * 0.03 * speedMult;
    }
  });

  return (
    <group>
      {/* Dynamic Inner Core Point Light */}
      <pointLight ref={coreLightRef} color={palette.primary} intensity={3.2} distance={8} />

      {/* 1. Glowing White-Hot / Molten Inner Plasma Core + Wireframe Icosahedron */}
      <group>
        <mesh ref={plasmaCoreRef}>
          <sphereGeometry args={[0.34, 24, 24]} />
          <meshBasicMaterial
            color={palette.hotCore}
            transparent
            opacity={0.96}
            toneMapped={false}
          />
        </mesh>
        <mesh ref={plasmaHaloRef}>
          <sphereGeometry args={[0.56, 24, 24]} />
          <meshBasicMaterial
            color={palette.primary}
            transparent
            opacity={0.34}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
        <mesh ref={innerIcosaRef}>
          <icosahedronGeometry args={[0.66, 1]} />
          <meshBasicMaterial
            color={palette.gold}
            wireframe
            transparent
            opacity={0.72}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      </group>

      {/* 2. Counter-Rotating Holographic Circuit Shell 1 (Inner Dense Molten Core) */}
      <group ref={shell1Ref}>
        <lineSegments geometry={geometries.innerCore1}>
          <lineBasicMaterial
            color={palette.gold}
            transparent
            opacity={0.94}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </lineSegments>
        <lineSegments geometry={geometries.innerCore2}>
          <lineBasicMaterial
            color={palette.primary}
            transparent
            opacity={0.86}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </lineSegments>
      </group>

      {/* 3. Counter-Rotating Holographic Circuit Shell 2 (Mid Neural Lattice) */}
      <group ref={shell2Ref}>
        <lineSegments geometry={geometries.midShell}>
          <lineBasicMaterial
            color={palette.primary}
            transparent
            opacity={0.72}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </lineSegments>
      </group>

      {/* 4. Counter-Rotating Holographic Circuit Shell 3 (Outer Fragmented Halo) */}
      <group ref={shell3Ref}>
        <lineSegments geometry={geometries.outerShellTop}>
          <lineBasicMaterial
            color={palette.ember}
            transparent
            opacity={0.84}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </lineSegments>
        <lineSegments geometry={geometries.outerShellBot}>
          <lineBasicMaterial
            color={palette.primary}
            transparent
            opacity={0.8}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </lineSegments>
      </group>

      {/* 5. Swirling Concentric Data Arcs & Luminous Torus/Ring Bands at Stark HUD Angles */}
      <group ref={arcRing1Ref} rotation={[0.18, 0, -0.12]}>
        <lineSegments geometry={geometries.eqRing}>
          <lineBasicMaterial
            color={palette.arcBright}
            transparent
            opacity={0.88}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </lineSegments>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[2.06, 0.014, 8, 96, Math.PI * 1.45]} />
          <meshBasicMaterial
            color={palette.gold}
            transparent
            opacity={0.78}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      </group>

      <group ref={arcRing2Ref} rotation={[1.32, 0.52, 0.34]}>
        <lineSegments geometry={geometries.diagRing1}>
          <lineBasicMaterial
            color={palette.hotCore}
            transparent
            opacity={0.92}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </lineSegments>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[1.64, 0.022, 10, 96, Math.PI * 1.25]} />
          <meshBasicMaterial
            color={palette.hotCore}
            transparent
            opacity={0.88}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
        <mesh rotation={[Math.PI / 2, 0, Math.PI * 0.4]}>
          <ringGeometry args={[1.22, 1.38, 64, 1, 0, Math.PI * 1.15]} />
          <meshBasicMaterial
            color={palette.primary}
            transparent
            opacity={0.22}
            side={THREE.DoubleSide}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      </group>

      <group ref={arcRing3Ref} rotation={[-1.08, -0.44, 0.62]}>
        <lineSegments geometry={geometries.diagRing2}>
          <lineBasicMaterial
            color={palette.ember}
            transparent
            opacity={0.85}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </lineSegments>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[1.18, 0.018, 8, 80, Math.PI * 1.6]} />
          <meshBasicMaterial
            color={palette.arcBright}
            transparent
            opacity={0.82}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      </group>

      {/* 6. Pulsing Radial Energy Filaments */}
      <lineSegments ref={radialFilamentsRef} geometry={geometries.radialFilaments}>
        <lineBasicMaterial
          ref={radialMatRef}
          color={palette.gold}
          transparent
          opacity={0.45}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </lineSegments>

      {/* 7. Instanced Orbiting Molten-Orange Data Nodes & Sparks */}
      <instancedMesh
        ref={instancedNodesRef}
        args={[undefined, undefined, ORBIT_NODE_COUNT]}
        frustumCulled={false}
      >
        <octahedronGeometry args={[1, 0]} />
        <meshBasicMaterial
          color="#ffffff"
          transparent
          opacity={0.95}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </instancedMesh>

      {/* Volumetric Synaptic Glow Dust */}
      <points ref={sparkPointsRef} geometry={geometries.sparks}>
        <pointsMaterial
          color={palette.gold}
          size={0.032}
          transparent
          opacity={0.85}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </points>

      <OrbitControls enablePan={false} minDistance={3.2} maxDistance={7.8} enableDamping dampingFactor={0.07} />
    </group>
  );
};

export const JarvisNeuralCore3D: React.FC<JarvisNeuralCore3DProps> = (props) => {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState<boolean>(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  });

  const isLowQuality = useMemo(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("quality") === "low";
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = (e: MediaQueryListEvent) => setPrefersReducedMotion(e.matches);
    setPrefersReducedMotion(mq.matches);
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);

  const mode: CoreVisualMode = props.error
    ? "ERROR"
    : props.listening
    ? "LISTENING"
    : props.thinking || props.optimizing
    ? "THINKING"
    : props.awaitingApproval
    ? "AWAITING_APPROVAL"
    : props.speaking
    ? "SPEAKING"
    : "IDLE";

  const palette = PALETTES[mode];
  const enablePostProcessing = !prefersReducedMotion && !isLowQuality;

  return (
    <div className="w-full h-full bg-[#030201] relative overflow-hidden">
      {/* Subtle radial molten aura behind canvas */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at 50% 48%, rgba(255, 140, 26, 0.14) 0%, rgba(255, 85, 0, 0.05) 36%, rgba(3, 2, 1, 0) 68%)",
        }}
      />

      <Canvas
        dpr={isLowQuality ? 1 : [1, 2]}
        camera={{ position: [0, 0.28, 5.15], fov: 44 }}
        gl={{
          antialias: !isLowQuality,
          powerPreference: "high-performance",
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.18,
        }}
      >
        <color attach="background" args={["#030201"]} />
        <NeuralCoreMesh
          {...props}
          mode={mode}
          palette={palette}
          reducedMotion={prefersReducedMotion}
        />
        {enablePostProcessing && (
          <EffectComposer multisampling={0}>
            <Bloom
              intensity={1.45}
              luminanceThreshold={0.14}
              luminanceSmoothing={0.85}
              mipmapBlur
            />
            <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
          </EffectComposer>
        )}
      </Canvas>

      {/* Stark Holographic HUD Frame Overlay (amber-orange technical lines, scan bar, rotating corner reticle) */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        {/* Top Amber Technical Scan Bar */}
        <div className="absolute top-4 left-6 right-16 max-w-xl h-5 flex flex-col gap-1">
          <div
            className="h-3 w-full border flex items-center justify-between px-1.5"
            style={{
              borderColor: palette.hudBorder,
              background:
                "linear-gradient(90deg, rgba(255,140,26,0.22) 0%, rgba(255,140,26,0.06) 68%, rgba(255,140,26,0.28) 100%)",
            }}
          >
            <span className="h-1 w-24 bg-[#ffae33]/70" />
            <span className="flex items-center gap-1">
              <span className="w-3 h-1.5 bg-[#ff8c1a]/75" />
              <span className="w-1.5 h-1.5 bg-[#ffb84d]/80" />
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-[2px] w-28 bg-[#ffae33]/65" />
            <div className="h-[1px] flex-1 bg-[#ff8c1a]/25" />
          </div>
        </div>

        {/* Fine Corner Framing Lines */}
        <div
          className="absolute inset-5 border"
          style={{
            borderColor: "rgba(255, 148, 36, 0.14)",
            maskImage:
              "linear-gradient(135deg, black 12%, transparent 25%, transparent 75%, black 88%)",
          }}
        />
        {/* Right-Side Vertical Stark Telemetry Ticks */}
        <div className="absolute right-4 top-12 bottom-24 w-3 flex flex-col items-end justify-between opacity-65">
          <div className="w-[2px] h-16 bg-[#ff8c1a]/50" />
          <div className="w-[1px] h-28 bg-[#ffb84d]/35" />
          <div className="w-[2px] h-12 bg-[#ff8c1a]/55" />
          <div className="w-[1px] h-20 bg-[#ff5500]/40" />
        </div>

        {/* Subtle Left Horizontal Alignment Marker */}
        <div className="hidden sm:flex absolute left-0 top-[34%] items-center gap-1.5 opacity-60">
          <div className="h-[3px] w-16 bg-gradient-to-r from-[#ff8c1a]/80 to-[#ffb84d]/20" />
          <div className="h-[1px] w-10 bg-[#ff8c1a]/40" />
        </div>

        {/* Bottom-Right Rotating Miniature Stark Corner Reticle SVG */}
        <div className="absolute bottom-14 right-5 w-16 h-16 flex items-center justify-center opacity-85">
          <svg
            viewBox="0 0 100 100"
            className="w-full h-full"
            style={{
              animation: prefersReducedMotion ? "none" : "spin 18s linear infinite",
            }}
          >
            <circle
              cx="50"
              cy="50"
              r="44"
              fill="none"
              stroke="rgba(255, 148, 36, 0.35)"
              strokeWidth="1.5"
              strokeDasharray="18 8 6 8"
            />
            <circle
              cx="50"
              cy="50"
              r="32"
              fill="none"
              stroke="rgba(255, 184, 77, 0.55)"
              strokeWidth="2"
              strokeDasharray="28 14"
            />
            <circle
              cx="50"
              cy="50"
              r="16"
              fill="none"
              stroke="#ffae33"
              strokeWidth="2.5"
            />
            <circle cx="50" cy="50" r="6" fill="#fff2cc" opacity="0.9" />
            <line x1="50" y1="6" x2="50" y2="20" stroke="#ff8c1a" strokeWidth="1.5" />
            <line x1="50" y1="80" x2="50" y2="94" stroke="#ff8c1a" strokeWidth="1.5" />
            <line x1="6" y1="50" x2="20" y2="50" stroke="#ff8c1a" strokeWidth="1.5" />
            <line x1="80" y1="50" x2="94" y2="50" stroke="#ff8c1a" strokeWidth="1.5" />
          </svg>
        </div>
      </div>

      {/* Crisp Status Overlay */}
      <div
        className="absolute bottom-14 sm:bottom-4 left-4 px-2.5 py-1 rounded bg-black/80 text-[10px] font-mono text-[#ffd89b] tracking-wider flex items-center gap-2 backdrop-blur-sm"
        style={{ border: `1px solid ${palette.hudBorder}` }}
      >
        <span className={`w-2 h-2 rounded-full ${palette.dotClass}`} />
        <span>
          {props.statusLabel ||
            (props.error
              ? "NEURAL CORE · FAULT DETECTED"
              : props.listening
              ? "LISTENING · LIVE MIC"
              : props.speaking
              ? "SPEAKING · VOICE SYNTH"
              : props.thinking || props.optimizing
              ? "OPTIMIZING · PROCESSING TOOLS"
              : props.awaitingApproval
              ? "AWAITING OPERATOR APPROVAL"
              : "JARVIS NEURAL CORE · STANDBY")}
        </span>
      </div>
    </div>
  );
};
