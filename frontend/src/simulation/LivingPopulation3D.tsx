import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

interface Props {
  worldSize: number;
  hasActiveDisaster: boolean;
  dayMode: boolean;
}

const CLOTHING_PALETTE = [
  "#2563EB", "#DC2626", "#059669", "#D97706", "#4F46E5",
  "#475569", "#0891B2", "#9333EA", "#BE123C", "#334155",
];

/**
 * High-performance instanced living population & emergency vehicle renderer:
 * - 260 synthetic pedestrians walking sidewalks/plazas, switching to directed evacuation during disasters
 * - 14 active emergency ambulances with flashing red/blue roof lightbars moving along major avenues
 */
export const LivingPopulation3D: React.FC<Props> = ({ worldSize, hasActiveDisaster }) => {
  const pedBodyRef = useRef<THREE.InstancedMesh>(null);
  const pedHeadRef = useRef<THREE.InstancedMesh>(null);
  const ambGroupRef = useRef<THREE.Group>(null);

  const pedCount = 260;
  const dummy = useMemo(() => new THREE.Object3D(), []);

  const pedestrians = useMemo(() => {
    const avenues = [800, 1600, 2400, 3200];
    return Array.from({ length: pedCount }, (_, i) => {
      const axis = i % 2 === 0 ? "x" : "z";
      const avenue = avenues[i % avenues.length] + ((i % 3) - 1) * 34;
      const offset = ((i * 73) % (worldSize - 400)) + 200;
      return {
        axis,
        avenue,
        basePos: offset,
        dir: i % 4 < 2 ? 1 : -1,
        speed: 5.5 + (i % 5) * 1.4,
        phase: i * 0.7,
        heightScale: 0.85 + (i % 4) * 0.1,
        color: new THREE.Color(CLOTHING_PALETTE[i % CLOTHING_PALETTE.length]),
      };
    });
  }, [worldSize]);

  const ambulances = useMemo(
    () =>
      Array.from({ length: 12 }, (_, i) => ({
        axis: i % 2 === 0 ? "x" : "z",
        lane: [800, 1600, 2400, 3200][i % 4] + (i % 2 === 0 ? 14 : -14),
        start: (i * 310) % (worldSize - 300),
        speed: 42 + (i % 4) * 9,
        dir: i % 3 === 0 ? -1 : 1,
      })),
    [worldSize]
  );

  // Set realistic clothing colors once
  React.useEffect(() => {
    if (pedBodyRef.current) {
      pedestrians.forEach((p, idx) => {
        pedBodyRef.current!.setColorAt(idx, p.color);
      });
      if (pedBodyRef.current.instanceColor) {
        pedBodyRef.current.instanceColor.needsUpdate = true;
      }
    }
  }, [pedestrians]);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const evacBoost = hasActiveDisaster ? 2.15 : 1.0;

    if (pedBodyRef.current && pedHeadRef.current) {
      for (let i = 0; i < pedCount; i++) {
        const p = pedestrians[i];
        const travel = (p.basePos + t * p.speed * evacBoost * p.dir + worldSize * 10) % (worldSize - 200) + 100;
        const x = p.axis === "x" ? travel : p.avenue;
        const z = p.axis === "z" ? travel : p.avenue;
        const bob = Math.abs(Math.sin(t * 7.5 * evacBoost + p.phase)) * 0.65;

        dummy.position.set(x, 3.2 * p.heightScale + bob, z);
        dummy.scale.set(1, p.heightScale, 1);
        dummy.rotation.set(0, p.axis === "x" ? (p.dir > 0 ? Math.PI / 2 : -Math.PI / 2) : (p.dir > 0 ? 0 : Math.PI), 0);
        dummy.updateMatrix();
        pedBodyRef.current.setMatrixAt(i, dummy.matrix);

        dummy.position.set(x, 6.6 * p.heightScale + bob, z);
        dummy.scale.set(1, 1, 1);
        dummy.updateMatrix();
        pedHeadRef.current.setMatrixAt(i, dummy.matrix);
      }
      pedBodyRef.current.instanceMatrix.needsUpdate = true;
      pedHeadRef.current.instanceMatrix.needsUpdate = true;
    }

    if (ambGroupRef.current) {
      const flashRed = Math.floor(t * 8) % 2 === 0;
      ambGroupRef.current.children.forEach((grp, idx) => {
        const a = ambulances[idx];
        const pos = (a.start + t * a.speed * a.dir + worldSize * 20) % (worldSize - 240) + 120;
        if (a.axis === "x") {
          grp.position.set(pos, 4.5, a.lane);
          grp.rotation.y = a.dir > 0 ? Math.PI / 2 : -Math.PI / 2;
        } else {
          grp.position.set(a.lane, 4.5, pos);
          grp.rotation.y = a.dir > 0 ? 0 : Math.PI;
        }
        const lightbar = grp.children[2] as THREE.Mesh | undefined;
        if (lightbar && lightbar.material instanceof THREE.MeshStandardMaterial) {
          lightbar.material.emissive.set(flashRed ? "#ef4444" : "#3b82f6");
        }
      });
    }
  });

  return (
    <group>
      {/* Instanced Synthetic Pedestrians */}
      <instancedMesh ref={pedBodyRef} args={[undefined, undefined, pedCount]} castShadow>
        <capsuleGeometry args={[1.4, 3.4, 4, 8]} />
        <meshStandardMaterial roughness={0.85} />
      </instancedMesh>
      <instancedMesh ref={pedHeadRef} args={[undefined, undefined, pedCount]}>
        <sphereGeometry args={[1.15, 8, 8]} />
        <meshStandardMaterial color="#e6be9a" roughness={0.75} />
      </instancedMesh>

      {/* Emergency Ambulances with Flashing Lightbars */}
      <group ref={ambGroupRef}>
        {ambulances.map((_, idx) => (
          <group key={idx}>
            <mesh castShadow>
              <boxGeometry args={[8.5, 7.5, 19]} />
              <meshStandardMaterial color="#f8fafc" roughness={0.35} metalness={0.15} />
            </mesh>
            <mesh position={[0, 0.4, 0]}>
              <boxGeometry args={[8.8, 1.4, 18.6]} />
              <meshStandardMaterial color="#dc2626" roughness={0.4} />
            </mesh>
            <mesh position={[0, 4.4, 4.5]}>
              <boxGeometry args={[5.5, 1.2, 2.2]} />
              <meshStandardMaterial color="#ef4444" emissive="#ef4444" emissiveIntensity={2.2} />
            </mesh>
          </group>
        ))}
      </group>
    </group>
  );
};
