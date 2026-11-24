import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import * as THREE from "three";
import { DroneState, RecoveryArc } from "../types/simulation";

const AnimatedArc: React.FC<{ from: [number, number, number]; to: [number, number, number] }> = ({ from, to }) => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ref = useRef<any>(null);
  const pts = useMemo(() => {
    const p0 = new THREE.Vector3(...from);
    const p2 = new THREE.Vector3(...to);
    const mid = p0.clone().lerp(p2, 0.5);
    mid.y = Math.max(p0.y, p2.y) + 140;
    const curve = new THREE.QuadraticBezierCurve3(p0, mid, p2);
    return curve.getPoints(24).map((v) => [v.x, v.y, v.z] as [number, number, number]);
  }, [from, to]);

  useFrame((_, delta) => {
    if (ref.current?.material) ref.current.material.dashOffset -= delta * 45;
  });

  return <Line ref={ref} points={pts} color="#f59e0b" lineWidth={2.4} dashed dashSize={20} gapSize={12} transparent opacity={0.9} />;
};

export const RecoveryArcs: React.FC<{ arcs: RecoveryArc[]; drones: DroneState[] }> = ({ arcs, drones }) => {
  if (!arcs || arcs.length === 0) return null;
  return (
    <group>
      {arcs.map((arc, idx) => {
        const target = drones.find((d) => d.id === arc.to_drone_id);
        if (!target) return null;
        return <AnimatedArc key={`${arc.task_id}-${arc.to_drone_id}-${idx}`} from={arc.from_pos} to={target.position} />;
      })}
    </group>
  );
};
