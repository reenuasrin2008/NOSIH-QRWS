import React, { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { RescueTask } from "../types/simulation";
import { useSimStore } from "../state/simulationStore";

function markerColor(t: RescueTask): string {
  if (t.status === "completed") return "#10b981";
  if (t.status === "requires_reassignment" || t.status === "unassigned") return "#ef4444";
  if (t.priority === "critical") return "#dc2626";
  if (t.priority === "high") return "#d97706";
  if (t.priority === "medium") return "#ca8a04";
  return "#3b82f6";
}

const RadarPulseRing: React.FC<{ color: string; offset: number }> = ({ color, offset }) => {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    if (!ref.current) return;
    const phase = (state.clock.elapsedTime * 0.85 + offset) % 1;
    const s = 1 + phase * 4.8;
    ref.current.scale.set(s, s, 1);
    (ref.current.material as THREE.MeshBasicMaterial).opacity = (1 - phase) * 0.65;
  });
  return (
    <mesh ref={ref} position={[0, 1.2, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[8, 10.5, 24]} />
      <meshBasicMaterial color={color} transparent opacity={0.6} side={THREE.DoubleSide} />
    </mesh>
  );
};

/** Realistic rising emergency distress flare for Critical missions. */
const EmergencySignalFlare: React.FC<{ offset: number }> = ({ offset }) => {
  const flareRef = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    if (!flareRef.current) return;
    const phase = (state.clock.elapsedTime * 0.32 + offset) % 1;
    // Parabolic flare ascent & gentle parachute drift
    const y = 8 + Math.sin(phase * Math.PI) * 95;
    const drift = phase * 18;
    flareRef.current.position.set(drift, y, drift * 0.6);
    const scale = phase < 0.88 ? 1.0 : Math.max(0.01, (1 - phase) * 8);
    flareRef.current.scale.setScalar(scale);
  });
  return (
    <mesh ref={flareRef} position={[0, 12, 0]}>
      <sphereGeometry args={[2.6, 8, 8]} />
      <meshBasicMaterial color={[3.2, 0.38, 0.25]} toneMapped={false} />
    </mesh>
  );
};

const AnimatedBeacon: React.FC<{ color: string; isSelected: boolean; isCompleted: boolean; offset: number }> = ({
  color, isSelected, isCompleted, offset,
}) => {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((state, delta) => {
    if (!ref.current) return;
    ref.current.rotation.y += delta * (isCompleted ? 0.5 : 1.9);
    if (!isCompleted) {
      ref.current.position.y = 20 + Math.sin(state.clock.elapsedTime * 2.6 + offset) * 3.5;
    }
  });
  return (
    <mesh ref={ref} position={[0, isCompleted ? 8 : 20, 0]}>
      <octahedronGeometry args={[isSelected ? 12 : 8, 0]} />
      <meshStandardMaterial color={color} roughness={0.32} metalness={0.25} />
    </mesh>
  );
};

export const RescueMarkers: React.FC<{ tasks: RescueTask[] }> = ({ tasks }) => {
  const selectedTaskId = useSimStore((s) => s.selectedTaskId);
  const selectTask = useSimStore((s) => s.selectTask);
  const setCameraFocusPoint = useSimStore((s) => s.setCameraFocusPoint);

  return (
    <group>
      {tasks.map((t, idx) => {
        const color = markerColor(t);
        const isSelected = t.id === selectedTaskId;
        const isCompleted = t.status === "completed";
        const isCritical = !isCompleted && t.priority === "critical";
        const isUrgent = !isCompleted && (t.priority === "critical" || t.priority === "high");
        return (
          <group
            key={t.id}
            position={[t.location[0], 0, t.location[2]]}
            onClick={(e) => { e.stopPropagation(); selectTask(t.id); setCameraFocusPoint(t.location); }}
          >
            {!isCompleted && (
              <mesh position={[0, 34, 0]}>
                <cylinderGeometry args={[0.9, 0.9, 68, 6]} />
                <meshBasicMaterial color={color} transparent opacity={0.42} />
              </mesh>
            )}
            <AnimatedBeacon color={color} isSelected={isSelected} isCompleted={isCompleted} offset={idx * 0.4} />
            {isUrgent && <RadarPulseRing color={color} offset={idx * 0.13} />}
            {isCritical && <EmergencySignalFlare offset={idx * 0.27} />}
            {isSelected && (
              <Html position={[0, 52, 0]} center distanceFactor={680}>
                <div className="px-2 py-1 text-[10px] font-mono bg-black/90 border border-white/25 text-white whitespace-nowrap pointer-events-none">
                  <div className="font-semibold">{t.id} [{t.priority.toUpperCase()}]</div>
                  <div className="text-zinc-400">{t.name} · {t.status}</div>
                  <div className="text-zinc-200">UNIT: {t.assigned_drone_id || "UNASSIGNED"}</div>
                </div>
              </Html>
            )}
          </group>
        );
      })}
    </group>
  );
};
