import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { CityEnvironment } from "../types/simulation";

interface BuildingAnimationsProps {
  city: CityEnvironment;
  dayMode: boolean;
}

// ---------------------------------------------------------------------------
// Window grids on tall commercial buildings (height > 60)
// ---------------------------------------------------------------------------

function TallBuildingWindows({
  city,
  dayMode,
}: BuildingAnimationsProps) {
  const tallCommercial = useMemo(
    () =>
      city.buildings
        .filter((b) => b.kind === "commercial" && b.height > 60)
        .slice(0, 120),
    [city.buildings]
  );

  // For each building we create one instanced mesh.
  // We collect all window metadata upfront so useFrame can iterate without
  // allocating inside the render loop.
  const meshRefs = useRef<(THREE.InstancedMesh | null)[]>([]);

  const windowMeta = useMemo(() => {
    return tallCommercial.map((b) => {
      const cols = Math.max(1, Math.floor(b.width / 5));
      const rows = Math.max(1, Math.floor(b.height / 4));
      const count = cols * rows;

      // Per-window random data: phase (0–2π), freq (1/2 – 1/8 s⁻¹), type
      const phases = new Float32Array(count);
      const freqs = new Float32Array(count);
      // 0 = warm light, 1 = off, 2 = blue screen (~5 %)
      const types = new Uint8Array(count);
      for (let i = 0; i < count; i++) {
        phases[i] = Math.random() * Math.PI * 2;
        freqs[i] = 1 / (2 + Math.random() * 6); // 1/8 to 1/2 Hz
        const r = Math.random();
        types[i] = r < 0.05 ? 2 : r < 0.25 ? 1 : 0;
      }

      // Precompute instance matrices (static positions, identity rotation/scale)
      const dummy = new THREE.Object3D();
      const matrices: THREE.Matrix4[] = [];
      for (let row = 0; row < rows; row++) {
        for (let col = 0; col < cols; col++) {
          const wx = b.x - b.width / 2 + (col + 0.5) * (b.width / cols);
          const wy = (row + 0.5) * (b.height / rows);
          const wz = b.z + b.depth / 2 + 0.3;
          dummy.position.set(wx, wy, wz);
          dummy.rotation.set(0, 0, 0);
          dummy.scale.set(1, 1, 1);
          dummy.updateMatrix();
          matrices.push(dummy.matrix.clone());
        }
      }

      return { cols, rows, count, phases, freqs, types, matrices };
    });
  }, [tallCommercial]);

  // Colour objects we reuse in the loop
  const warmColor = useMemo(() => new THREE.Color("#fef3c7"), []);
  const offColor = useMemo(() => new THREE.Color("#1e293b"), []);
  const blueColor = useMemo(() => new THREE.Color("#38bdf8"), []);
  const tempColor = useMemo(() => new THREE.Color(), []);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    for (let bi = 0; bi < tallCommercial.length; bi++) {
      const mesh = meshRefs.current[bi];
      if (!mesh) continue;
      const meta = windowMeta[bi];
      for (let i = 0; i < meta.count; i++) {
        const on = Math.sin(t * meta.freqs[i] + meta.phases[i]) > 0.7;
        if (meta.types[i] === 2) {
          tempColor.copy(on ? blueColor : offColor);
        } else if (meta.types[i] === 1) {
          tempColor.copy(offColor);
        } else {
          tempColor.copy(on ? warmColor : offColor);
        }
        if (dayMode) {
          // Dim windows in day mode
          tempColor.multiplyScalar(0.3);
        }
        mesh.setColorAt(i, tempColor);
      }
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }
  });

  return (
    <>
      {tallCommercial.map((b, bi) => {
        const meta = windowMeta[bi];
        return (
          <instancedMesh
            key={b.id}
            ref={(el) => {
              meshRefs.current[bi] = el;
              if (el) {
                // Apply pre-computed matrices once
                for (let i = 0; i < meta.count; i++) {
                  el.setMatrixAt(i, meta.matrices[i]);
                }
                el.instanceMatrix.needsUpdate = true;
              }
            }}
            args={[undefined, undefined, meta.count]}
            frustumCulled={false}
          >
            <planeGeometry args={[0.8, 0.8]} />
            <meshBasicMaterial
              vertexColors
              transparent
              opacity={dayMode ? 0.3 : 1.0}
            />
          </instancedMesh>
        );
      })}
    </>
  );
}

// ---------------------------------------------------------------------------
// Rooftop HVAC rotating cylinders
// ---------------------------------------------------------------------------

function HvacAnimations({ city }: { city: CityEnvironment }) {
  const hvacBuildings = useMemo(
    () =>
      city.buildings.filter((b) => b.roof_style === "hvac").slice(0, 80),
    [city.buildings]
  );

  const hvacRefs = useRef<(THREE.Mesh | null)[]>([]);

  useFrame((_, delta) => {
    for (let i = 0; i < hvacBuildings.length; i++) {
      const mesh = hvacRefs.current[i];
      if (!mesh) continue;
      // Vary speed by index: faster for lower indices
      const speed = 0.4 + (i % 7) * 0.15;
      mesh.rotation.y += delta * speed;
    }
  });

  return (
    <>
      {hvacBuildings.map((b, i) => (
        <mesh
          key={b.id}
          ref={(el) => {
            hvacRefs.current[i] = el;
          }}
          position={[b.x, b.height + 2, b.z]}
          frustumCulled={false}
        >
          <cylinderGeometry args={[1.5, 1.5, 0.8, 8]} />
          <meshStandardMaterial color="#94a3b8" metalness={0.6} roughness={0.4} />
        </mesh>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Construction cranes
// ---------------------------------------------------------------------------

const CRANE_POSITIONS: [number, number, number][] = [
  [600, 0, 600],
  [2800, 0, 800],
  [3400, 0, 2600],
];

function ConstructionCranes() {
  const jibRefs = useRef<(THREE.Group | null)[]>([]);

  useFrame((_, delta) => {
    for (const group of jibRefs.current) {
      if (group) group.rotation.y += delta * 0.08;
    }
  });

  return (
    <>
      {CRANE_POSITIONS.map(([cx, cy, cz], idx) => {
        const towerHeight = 120;
        const towerY = cy + towerHeight / 2;
        const jibY = cy + towerHeight;

        return (
          <group key={idx} position={[cx, cy, cz]}>
            {/* Tower */}
            <mesh position={[0, towerY, 0]} frustumCulled={false}>
              <boxGeometry args={[6, towerHeight, 6]} />
              <meshStandardMaterial color="#f59e0b" />
            </mesh>

            {/* Rotating jib assembly */}
            <group
              ref={(el) => {
                jibRefs.current[idx] = el;
              }}
              position={[0, jibY, 0]}
            >
              {/* Main jib arm */}
              <mesh position={[40, 2, 0]} frustumCulled={false}>
                <boxGeometry args={[80, 4, 4]} />
                <meshStandardMaterial color="#f59e0b" />
              </mesh>

              {/* Counter-jib */}
              <mesh position={[-15, 2, 0]} frustumCulled={false}>
                <boxGeometry args={[30, 4, 4]} />
                <meshStandardMaterial color="#f59e0b" />
              </mesh>

              {/* Hanging cable: thin cylinder from jib tip down 20 units */}
              <mesh position={[80, -10, 0]} frustumCulled={false}>
                <cylinderGeometry args={[0.15, 0.15, 20, 4]} />
                <meshStandardMaterial color="#475569" />
              </mesh>

              {/* Hook block at cable end */}
              <mesh position={[80, -20, 0]} frustumCulled={false}>
                <boxGeometry args={[2, 2, 2]} />
                <meshStandardMaterial color="#1e293b" />
              </mesh>
            </group>
          </group>
        );
      })}
    </>
  );
}

// ---------------------------------------------------------------------------
// Blinking telecom tower
// ---------------------------------------------------------------------------

function TelecomTower() {
  const light120Ref = useRef<THREE.Mesh | null>(null);
  const light150Ref = useRef<THREE.Mesh | null>(null);
  const light178Ref = useRef<THREE.Mesh | null>(null);

  const onColor = useMemo(() => new THREE.Color("#ef4444"), []);
  const offColor = useMemo(() => new THREE.Color("#450a0a"), []);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const on = Math.floor(t * 2) % 2 === 0;
    const color = on ? onColor : offColor;
    for (const ref of [light120Ref, light150Ref, light178Ref]) {
      const mesh = ref.current;
      if (mesh) {
        (mesh.material as THREE.MeshBasicMaterial).color.copy(color);
      }
    }
  });

  const towerBaseX = 2000;
  const towerBaseZ = 1800;

  return (
    <group position={[towerBaseX, 0, towerBaseZ]}>
      {/* Main tower shaft */}
      <mesh position={[0, 90, 0]} frustumCulled={false}>
        <cylinderGeometry args={[2, 4, 180, 8]} />
        <meshStandardMaterial color="#334155" metalness={0.5} roughness={0.5} />
      </mesh>

      {/* Cross-arm at height 140 — along X */}
      <mesh position={[0, 140, 0]} frustumCulled={false}>
        <boxGeometry args={[40, 3, 3]} />
        <meshStandardMaterial color="#475569" />
      </mesh>

      {/* Cross-arm at height 140 — rotated 90° along Y (along Z) */}
      <mesh position={[0, 140, 0]} rotation={[0, Math.PI / 2, 0]} frustumCulled={false}>
        <boxGeometry args={[40, 3, 3]} />
        <meshStandardMaterial color="#475569" />
      </mesh>

      {/* Blink light at height 120 */}
      <mesh ref={light120Ref} position={[0, 120, 0]} frustumCulled={false}>
        <sphereGeometry args={[1.2, 8, 8]} />
        <meshBasicMaterial color="#ef4444" />
      </mesh>

      {/* Blink light at height 150 */}
      <mesh ref={light150Ref} position={[0, 150, 0]} frustumCulled={false}>
        <sphereGeometry args={[1.2, 8, 8]} />
        <meshBasicMaterial color="#ef4444" />
      </mesh>

      {/* Blink light at height 178 */}
      <mesh ref={light178Ref} position={[0, 178, 0]} frustumCulled={false}>
        <sphereGeometry args={[1.2, 8, 8]} />
        <meshBasicMaterial color="#ef4444" />
      </mesh>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Root export
// ---------------------------------------------------------------------------

export function BuildingAnimations({ city, dayMode }: BuildingAnimationsProps) {
  return (
    <>
      <TallBuildingWindows city={city} dayMode={dayMode} />
      <HvacAnimations city={city} />
      <ConstructionCranes />
      <TelecomTower />
    </>
  );
}
