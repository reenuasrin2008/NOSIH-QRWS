import React, { useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import * as THREE from "three";

interface JarvisNeuralCore3DProps {
  listening: boolean;
  speaking: boolean;
  thinking: boolean;
  audioLevel: number; // 0.0 - 1.0 from real Web Audio API mic analyser or TTS cadence
  statusLabel?: string;
}

function seededRand(seed: number): () => number {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function sphericalToCartesian(r: number, theta: number, phi: number): [number, number, number] {
  const sinPhi = Math.sin(phi);
  return [r * sinPhi * Math.cos(theta), r * Math.cos(phi), r * sinPhi * Math.sin(theta)];
}

/**
 * Generates stepped, PCB/neural-style jagged circuit filament segments distributed
 * across a spherical shell (optionally clipped to partial polar/equatorial bands).
 */
function buildCircuitShellGeometry(
  radius: number,
  traceCount: number,
  stepsPerTrace: number,
  seed: number,
  phiMin = 0.08,
  phiMax = Math.PI - 0.08
): THREE.BufferGeometry {
  const rand = seededRand(seed);
  const positions: number[] = [];

  for (let t = 0; t < traceCount; t++) {
    let theta = rand() * Math.PI * 2;
    let phi = phiMin + rand() * (phiMax - phiMin);
    const stepLen = 0.055 + rand() * 0.04;

    for (let s = 0; s < stepsPerTrace; s++) {
      const p0 = sphericalToCartesian(radius, theta, phi);
      // Orthogonal / 45-degree circuit trace step on spherical surface
      const dir = Math.floor(rand() * 6);
      if (dir === 0) theta += stepLen;
      else if (dir === 1) theta -= stepLen;
      else if (dir === 2) phi = Math.min(phiMax, phi + stepLen * 0.7);
      else if (dir === 3) phi = Math.max(phiMin, phi - stepLen * 0.7);
      else if (dir === 4) {
        theta += stepLen * 0.7;
        phi = Math.min(phiMax, phi + stepLen * 0.5);
      } else {
        theta -= stepLen * 0.7;
        phi = Math.max(phiMin, phi - stepLen * 0.5);
      }
      const p1 = sphericalToCartesian(radius, theta, phi);
      positions.push(p0[0], p0[1], p0[2], p1[0], p1[1], p1[2]);
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return geo;
}

/** Generates a dense multi-layered circuit ring with organic jagged neural spurs. */
function buildCircuitRingGeometry(radius: number, width: number, count: number, seed: number): THREE.BufferGeometry {
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

      if (rand() < 0.7) {
        a += 0.045 + rand() * 0.03;
      } else {
        r += (rand() - 0.5) * width * 0.35;
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

const NeuralCoreMesh: React.FC<JarvisNeuralCore3DProps> = ({
  listening,
  speaking,
  thinking,
  audioLevel,
}) => {
  const innerCoreRef = useRef<THREE.Group>(null);
  const midShellRef = useRef<THREE.LineSegments>(null);
  const outerCapRef = useRef<THREE.LineSegments>(null);
  const eqRingRef = useRef<THREE.LineSegments>(null);
  const diagRingRef = useRef<THREE.LineSegments>(null);
  const sparkPointsRef = useRef<THREE.Points>(null);

  const geometries = useMemo(() => {
    const innerCore1 = buildCircuitShellGeometry(0.86, 150, 12, 101);
    const innerCore2 = buildCircuitShellGeometry(1.06, 130, 11, 202);
    const midShell = buildCircuitShellGeometry(1.62, 145, 13, 303);
    // Partial outer fragmented polar/arc bands matching reference silhouette
    const outerTopBand = buildCircuitShellGeometry(2.04, 65, 11, 404, 0.22, 0.75);
    const outerBotBand = buildCircuitShellGeometry(2.04, 55, 11, 505, Math.PI - 0.72, Math.PI - 0.22);
    const eqRing = buildCircuitRingGeometry(2.14, 0.24, 150, 606);
    const diagRing = buildCircuitRingGeometry(1.92, 0.14, 130, 707);

    // Synaptic glowing gold micro-nodes
    const rand = seededRand(808);
    const pts = new Float32Array(750 * 3);
    for (let i = 0; i < 750; i++) {
      const r = i < 350 ? 0.95 + rand() * 0.25 : 1.55 + rand() * 0.55;
      const th = rand() * Math.PI * 2;
      const ph = Math.acos(2 * rand() - 1);
      const [x, y, z] = sphericalToCartesian(r, th, ph);
      pts[i * 3] = x;
      pts[i * 3 + 1] = y;
      pts[i * 3 + 2] = z;
    }
    const sparks = new THREE.BufferGeometry();
    sparks.setAttribute("position", new THREE.BufferAttribute(pts, 3));

    return { innerCore1, innerCore2, midShell, outerTopBand, outerBotBand, eqRing, diagRing, sparks };
  }, []);

  useEffect(() => {
    return () => {
      Object.values(geometries).forEach((g) => g.dispose());
    };
  }, [geometries]);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const synthWave = speaking ? 0.35 + Math.abs(Math.sin(t * 9.5)) * 0.45 : 0;
    const energy = Math.min(1, Math.max(audioLevel, synthWave, thinking ? 0.38 : 0.08));
    const speedMult = thinking ? 2.4 : listening || speaking ? 1.65 + energy * 1.4 : 1.0;
    const pulse = 1.0 + energy * 0.14 + Math.sin(t * 2.2) * 0.015;

    if (innerCoreRef.current) {
      innerCoreRef.current.rotation.y += delta * 0.22 * speedMult;
      innerCoreRef.current.rotation.x += delta * 0.08 * speedMult;
      innerCoreRef.current.scale.setScalar(pulse);
    }
    if (midShellRef.current) {
      midShellRef.current.rotation.y -= delta * 0.11 * speedMult;
      midShellRef.current.rotation.z += delta * 0.04 * speedMult;
    }
    if (outerCapRef.current) {
      outerCapRef.current.rotation.y += delta * 0.07 * speedMult;
    }
    if (eqRingRef.current) {
      eqRingRef.current.rotation.y += delta * 0.18 * speedMult;
      eqRingRef.current.scale.setScalar(1.0 + energy * 0.06);
    }
    if (diagRingRef.current) {
      diagRingRef.current.rotation.z -= delta * 0.24 * speedMult;
    }
    if (sparkPointsRef.current) {
      sparkPointsRef.current.rotation.y += delta * 0.09 * speedMult;
    }
  });

  const coreColor = listening ? "#ffe08a" : speaking ? "#ffd06b" : "#ffae42";
  const ringColor = listening ? "#fff1c2" : "#ffba52";

  return (
    <group>
      {/* Dense Golden Neural Core */}
      <group ref={innerCoreRef}>
        <lineSegments geometry={geometries.innerCore1}>
          <lineBasicMaterial color={coreColor} transparent opacity={0.92} blending={THREE.AdditiveBlending} depthWrite={false} />
        </lineSegments>
        <lineSegments geometry={geometries.innerCore2}>
          <lineBasicMaterial color="#ff9d2e" transparent opacity={0.78} blending={THREE.AdditiveBlending} depthWrite={false} />
        </lineSegments>
      </group>

      {/* Mid Spherical Neural Lattice */}
      <lineSegments ref={midShellRef} geometry={geometries.midShell}>
        <lineBasicMaterial color="#f59e36" transparent opacity={0.58} blending={THREE.AdditiveBlending} depthWrite={false} />
      </lineSegments>

      {/* Outer Fragmented Polar Circuit Shells */}
      <group ref={outerCapRef}>
        <lineSegments geometry={geometries.outerTopBand}>
          <lineBasicMaterial color="#ffbe63" transparent opacity={0.68} blending={THREE.AdditiveBlending} depthWrite={false} />
        </lineSegments>
        <lineSegments geometry={geometries.outerBotBand}>
          <lineBasicMaterial color="#ffbe63" transparent opacity={0.62} blending={THREE.AdditiveBlending} depthWrite={false} />
        </lineSegments>
      </group>

      {/* Tilted Equatorial Circuit Ring */}
      <lineSegments ref={eqRingRef} geometry={geometries.eqRing} rotation={[0.14, 0, -0.08]}>
        <lineBasicMaterial color={ringColor} transparent opacity={0.86} blending={THREE.AdditiveBlending} depthWrite={false} />
      </lineSegments>

      {/* Steep Diagonal Energy Ring slicing through the core */}
      <lineSegments ref={diagRingRef} geometry={geometries.diagRing} rotation={[1.38, 0.56, 0.28]}>
        <lineBasicMaterial color="#ffe4a8" transparent opacity={0.92} blending={THREE.AdditiveBlending} depthWrite={false} />
      </lineSegments>

      {/* Glowing Synaptic Particles */}
      <points ref={sparkPointsRef} geometry={geometries.sparks}>
        <pointsMaterial color="#ffdf94" size={0.028} transparent opacity={0.82} blending={THREE.AdditiveBlending} depthWrite={false} />
      </points>

      <OrbitControls enablePan={false} minDistance={3.2} maxDistance={7.5} />
    </group>
  );
};

export const JarvisNeuralCore3D: React.FC<JarvisNeuralCore3DProps> = (props) => {
  return (
    <div className="w-full h-full bg-[#040302] relative overflow-hidden">
      <Canvas
        camera={{ position: [0, 0.35, 5.2], fov: 44 }}
        gl={{ antialias: true, powerPreference: "high-performance", toneMapping: THREE.ACESFilmicToneMapping }}
      >
        <color attach="background" args={["#040302"]} />
        <NeuralCoreMesh {...props} />
        <EffectComposer>
          <Bloom intensity={1.15} luminanceThreshold={0.15} luminanceSmoothing={0.85} mipmapBlur />
        </EffectComposer>
      </Canvas>

      {/* Crisp Status Overlay */}
      <div className="absolute bottom-3 left-3 px-2.5 py-1 rounded bg-black/75 border border-amber-500/40 text-[10px] font-mono text-amber-200 tracking-wider flex items-center gap-2">
        <span
          className={`w-2 h-2 rounded-full ${
            props.listening ? "bg-red-400 animate-ping" : props.speaking ? "bg-amber-300 animate-pulse" : "bg-amber-500"
          }`}
        />
        <span>
          {props.statusLabel ||
            (props.listening ? "LISTENING · LIVE MIC" : props.speaking ? "SPEAKING · VOICE SYNTH" : props.thinking ? "PROCESSING TOOLS" : "JARVIS NEURAL CORE · STANDBY")}
        </span>
      </div>
    </div>
  );
};
