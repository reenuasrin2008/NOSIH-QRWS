import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { useSimStore } from "../state/simulationStore";

export const AiTacticalEffects: React.FC = () => {
  const aiScanPulses = useSimStore((s) => s.aiScanPulses);
  const aiDispatchBeams = useSimStore((s) => s.aiDispatchBeams);
  const pruneAiEffects = useSimStore((s) => s.pruneAiEffects);

  const sweepRefs = useRef<Record<string, THREE.Mesh | null>>({});
  const lastPrune = useRef(0);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (t - lastPrune.current > 1.5) {
      lastPrune.current = t;
      pruneAiEffects();
    }
    for (const p of aiScanPulses) {
      const m = sweepRefs.current[p.id];
      if (m) {
        const cycle = (t * 0.85) % 1.0;
        const sc = 0.25 + cycle * 0.95;
        m.scale.set(sc, sc, 1);
        m.rotation.z = t * 1.4;
      }
    }
  });

  const beamCurves = useMemo(() => {
    return aiDispatchBeams.map((b) => {
      const start = new THREE.Vector3(b.from[0], Math.max(12, b.from[1]), b.from[2]);
      const end = new THREE.Vector3(b.to[0], Math.max(8, b.to[1]), b.to[2]);
      const mid = start.clone().lerp(end, 0.5);
      mid.y += Math.min(260, start.distanceTo(end) * 0.24 + 55);
      const curve = new THREE.QuadraticBezierCurve3(start, mid, end);
      const geo = new THREE.TubeGeometry(curve, 32, 3.2, 8, false);
      return { id: b.id, geo, end };
    });
  }, [aiDispatchBeams]);

  return (
    <group>
      {/* Expanding Golden AI Thermal Radar Scan Domes */}
      {aiScanPulses.map((p) => (
        <group key={p.id} position={[p.point[0], 6, p.point[2]]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]} ref={(el) => { sweepRefs.current[p.id] = el; }}>
            <ringGeometry args={[p.radius * 0.78, p.radius, 48]} />
            <meshBasicMaterial color="#fbbf24" transparent opacity={0.75} side={THREE.DoubleSide} />
          </mesh>
          <mesh>
            <sphereGeometry args={[p.radius, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
            <meshBasicMaterial color="#f59e0b" transparent opacity={0.12} wireframe />
          </mesh>
        </group>
      ))}

      {/* Glowing AI Drone-to-Survivor Dispatch Beams */}
      {beamCurves.map((b) => (
        <group key={b.id}>
          <mesh geometry={b.geo}>
            <meshStandardMaterial color="#fbbf24" emissive="#f59e0b" emissiveIntensity={1.6} transparent opacity={0.82} />
          </mesh>
          <mesh position={b.end}>
            <sphereGeometry args={[9, 14, 14]} />
            <meshStandardMaterial color="#fef08a" emissive="#fbbf24" emissiveIntensity={2.0} />
          </mesh>
        </group>
      ))}
    </group>
  );
};
