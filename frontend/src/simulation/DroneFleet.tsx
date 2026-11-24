import React, { useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { Html, Line } from "@react-three/drei";
import * as THREE from "three";
import { DroneState } from "../types/simulation";
import { useSimStore } from "../state/simulationStore";

const CLASS_COLORS: Record<string, string> = {
  surveillance: "#e2e8f0",
  medical: "#ef4444",
  heavy_lift: "#eab308",
  search_rescue: "#10b981",
};

const DroneMesh: React.FC<{ drone: DroneState; selected: boolean; dayMode: boolean; windSpeed: number; onSelect: () => void }> = ({
  drone, selected, dayMode, windSpeed, onSelect,
}) => {
  const groupRef = useRef<THREE.Group>(null);
  const rotorsRef = useRef<THREE.Group>(null);
  const strobeRef = useRef<THREE.Mesh>(null);
  const winchRef = useRef<THREE.Group>(null);
  const sparkRef = useRef<THREE.Mesh>(null);
  const downwashRef = useRef<THREE.Mesh>(null);
  const rpmRef = useRef(0);
  const smoothHeading = useRef(drone.heading_rad);
  const smoothPitch = useRef(0);
  const smoothBank = useRef(0);
  const [hovered, setHovered] = useState(false);

  const targetVec = useRef(new THREE.Vector3(...drone.position));
  targetVec.current.set(drone.position[0], drone.position[1], drone.position[2]);

  const isDestroyed = drone.status === "DESTROYED";
  const isDamaged = drone.status === "DAMAGED" || drone.status === "COMMUNICATION_LOST";
  const isFlying = ["IN_FLIGHT", "TAKING_OFF", "DELIVERING", "RETURNING"].includes(drone.status);
  const isDelivering = drone.status === "DELIVERING";
  const isSearchClass = drone.drone_type === "surveillance" || drone.drone_type === "search_rescue";
  const isScanning = isDelivering && isSearchClass;
  const isNightSearchlight = !dayMode && isFlying && !isDestroyed && isSearchClass;
  const isDroppingCargo = isDelivering && (drone.drone_type === "medical" || drone.drone_type === "heavy_lift");
  const isHex = drone.drone_type === "heavy_lift";
  const accent = isDestroyed ? "#dc2626" : isDamaged ? "#d97706" : CLASS_COLORS[drone.drone_type] || "#3b82f6";

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    // Smooth exponential damping for realistic inertia & aerodynamic wind buffeting
    const seed = drone.id.charCodeAt(drone.id.length - 1);
    const gustAmp = isFlying && !isDestroyed ? Math.min(0.06, 0.012 + windSpeed * 0.0025) : 0;
    const gustRoll = Math.sin(t * 3.1 + seed) * gustAmp;
    const gustPitch = Math.cos(t * 2.6 + seed * 1.3) * gustAmp * 0.8;

    if (groupRef.current) {
      groupRef.current.position.lerp(targetVec.current, 1 - Math.exp(-6.8 * delta));
      if (isDelivering) {
        groupRef.current.position.y += Math.sin(t * 3.8 + seed) * 0.22;
      }
      groupRef.current.rotation.order = "YXZ";
      if (isDestroyed && drone.position[1] > 4) {
        groupRef.current.rotation.y += delta * 6.5;
        groupRef.current.rotation.x = 0.55;
        groupRef.current.rotation.z = 0.82;
      } else {
        const dH = ((drone.heading_rad - smoothHeading.current + Math.PI) % (2 * Math.PI)) - Math.PI;
        smoothHeading.current += dH * (1 - Math.exp(-7.5 * delta));
        const tgtPitch = isDestroyed ? 0.35 : drone.pitch_rad + gustPitch;
        const tgtBank = isDestroyed ? 0.65 : drone.bank_rad + gustRoll;
        smoothPitch.current += (tgtPitch - smoothPitch.current) * (1 - Math.exp(-6.5 * delta));
        smoothBank.current += (tgtBank - smoothBank.current) * (1 - Math.exp(-6.5 * delta));
        groupRef.current.rotation.y = smoothHeading.current;
        groupRef.current.rotation.x = smoothPitch.current;
        groupRef.current.rotation.z = smoothBank.current;
      }
    }
    // Realistic rotor RPM ramp-up and spin-down inertia
    const targetRpm = isFlying && !isDestroyed ? 46 : 0;
    rpmRef.current += (targetRpm - rpmRef.current) * (1 - Math.exp(-3.2 * delta));
    if (rotorsRef.current && rpmRef.current > 0.2) {
      rotorsRef.current.children.forEach((r, idx) => {
        r.rotation.y += delta * (idx % 2 === 0 ? rpmRef.current : -rpmRef.current);
      });
    }
    if (strobeRef.current) {
      strobeRef.current.visible = !isDestroyed && Math.floor(t * 3.2) % 2 === 0;
    }
    if (winchRef.current && isDroppingCargo) {
      const dropDepth = 4 + (Math.sin(t * 2.2) * 0.5 + 0.5) * 9;
      winchRef.current.position.y = -dropDepth;
    }
    if (downwashRef.current && isDelivering) {
      const p = (t * 1.4) % 1;
      const sc = 1 + p * 2.8;
      downwashRef.current.scale.set(sc, sc, 1);
      (downwashRef.current.material as THREE.MeshBasicMaterial).opacity = (1 - p) * 0.35;
    }
    if (sparkRef.current && isDestroyed) {
      const s = 1 + Math.sin(t * 18) * 0.35;
      sparkRef.current.scale.set(s, s, s);
    }
  });

  const rotorOffsets: [number, number, number][] = isHex
    ? [[-3.6, 0.55, 0], [3.6, 0.55, 0], [-2.0, 0.55, -3.1], [2.0, 0.55, -3.1], [-2.0, 0.55, 3.1], [2.0, 0.55, 3.1]]
    : [[-2.7, 0.55, -2.7], [2.7, 0.55, -2.7], [-2.7, 0.55, 2.7], [2.7, 0.55, 2.7]];

  const scale = isHex ? 3.3 : drone.drone_type === "surveillance" ? 2.3 : 2.7;

  return (
    <group>
      {/* Ground Contact Shadow for Low-Altitude Drones */}
      {!isDestroyed && drone.position[1] < 55 && (
        <mesh position={[drone.position[0], 0.55, drone.position[2]]} rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[Math.max(4, 12 - drone.position[1] * 0.14), 18]} />
          <meshBasicMaterial color="#000000" transparent opacity={Math.max(0.08, 0.42 - drone.position[1] * 0.006)} />
        </mesh>
      )}

      {/* Rotor Downwash Dust Ring during Low-Altitude Delivery */}
      {isDelivering && !isDestroyed && (
        <mesh ref={downwashRef} position={[drone.position[0], 0.9, drone.position[2]]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[7, 11, 24]} />
          <meshBasicMaterial color="#d6d3d1" transparent opacity={0.3} side={THREE.DoubleSide} />
        </mesh>
      )}

      {/* Subtle Altitude Ground-Track Tether */}
      {isFlying && !isDestroyed && drone.position[1] > 12 && (
        <group>
          <Line
            points={[drone.position, [drone.position[0], 0.8, drone.position[2]]]}
            color={selected ? "#ffffff" : accent}
            lineWidth={selected ? 1.6 : 0.8}
            transparent
            opacity={selected ? 0.7 : 0.25}
          />
          <mesh position={[drone.position[0], 0.7, drone.position[2]]} rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[selected ? 11 : 5, selected ? 14 : 7, 20]} />
            <meshBasicMaterial color={selected ? "#ffffff" : accent} transparent opacity={selected ? 0.8 : 0.34} side={THREE.DoubleSide} />
          </mesh>
        </group>
      )}

      <group
        ref={groupRef}
        position={drone.position}
        scale={[scale, scale, scale]}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { setHovered(false); document.body.style.cursor = "auto"; }}
        onClick={(e) => { e.stopPropagation(); onSelect(); }}
      >
        {/* Sculpted Carbon-Fiber Main Fuselage */}
        <mesh castShadow>
          <boxGeometry args={[2.6, 0.88, 4.3]} />
          <meshStandardMaterial color={isDestroyed ? "#451a1a" : "#1c212b"} metalness={0.65} roughness={0.32} />
        </mesh>
        {/* Aerodynamic Nose Cone */}
        <mesh position={[0, 0.05, 2.45]} rotation={[Math.PI / 2, 0, 0]}>
          <coneGeometry args={[1.1, 1.1, 6]} />
          <meshStandardMaterial color={isDestroyed ? "#451a1a" : "#272e3b"} metalness={0.55} roughness={0.35} />
        </mesh>
        {/* Top Avionics Canopy Shell with Class Livery */}
        <mesh position={[0, 0.62, 0.1]}>
          <boxGeometry args={[2.1, 0.45, 2.9]} />
          <meshStandardMaterial color={accent} roughness={0.32} metalness={0.25} />
        </mesh>
        {/* GPS Puck Mast */}
        <mesh position={[0, 1.05, -0.7]}>
          <cylinderGeometry args={[0.38, 0.38, 0.22, 12]} />
          <meshStandardMaterial color="#e2e8f0" roughness={0.3} />
        </mesh>

        {/* Twin Underslung LiPo Battery Packs */}
        <mesh position={[-0.7, -0.55, -0.3]}><boxGeometry args={[0.75, 0.45, 2.1]} /><meshStandardMaterial color="#111827" roughness={0.5} /></mesh>
        <mesh position={[0.7, -0.55, -0.3]}><boxGeometry args={[0.75, 0.45, 2.1]} /><meshStandardMaterial color="#111827" roughness={0.5} /></mesh>

        {/* T-Style Carbon Landing Gear Struts & Skids */}
        <mesh position={[-1.4, -1.25, 0]}><boxGeometry args={[0.22, 0.22, 3.9]} /><meshStandardMaterial color="#334155" metalness={0.6} /></mesh>
        <mesh position={[1.4, -1.25, 0]}><boxGeometry args={[0.22, 0.22, 3.9]} /><meshStandardMaterial color="#334155" metalness={0.6} /></mesh>
        <mesh position={[-1.2, -0.75, 0.9]} rotation={[0, 0, 0.25]}><boxGeometry args={[0.16, 1.1, 0.2]} /><meshStandardMaterial color="#334155" /></mesh>
        <mesh position={[1.2, -0.75, 0.9]} rotation={[0, 0, -0.25]}><boxGeometry args={[0.16, 1.1, 0.2]} /><meshStandardMaterial color="#334155" /></mesh>
        <mesh position={[-1.2, -0.75, -0.9]} rotation={[0, 0, 0.25]}><boxGeometry args={[0.16, 1.1, 0.2]} /><meshStandardMaterial color="#334155" /></mesh>
        <mesh position={[1.2, -0.75, -0.9]} rotation={[0, 0, -0.25]}><boxGeometry args={[0.16, 1.1, 0.2]} /><meshStandardMaterial color="#334155" /></mesh>

        {/* 3-Axis Optical/Thermal Gimbal Turret with Lens */}
        <group position={[0, -0.72, 1.45]}>
          <mesh><sphereGeometry args={[0.58, 12, 12]} /><meshStandardMaterial color="#0f172a" metalness={0.8} roughness={0.18} /></mesh>
          <mesh position={[0, 0, 0.48]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.26, 0.26, 0.2, 12]} />
            <meshStandardMaterial color="#38bdf8" metalness={0.95} roughness={0.05} />
          </mesh>
        </group>

        {/* Package Winch Drop Sequence during Delivery */}
        {isDroppingCargo && (
          <group>
            <mesh position={[0, -5, 0]}><cylinderGeometry args={[0.06, 0.06, 10, 4]} /><meshBasicMaterial color="#e2e8f0" /></mesh>
            <group ref={winchRef} position={[0, -6, 0]}>
              <mesh><boxGeometry args={[2.0, 1.25, 2.0]} /><meshStandardMaterial color={drone.drone_type === "medical" ? "#f8fafc" : "#eab308"} /></mesh>
            </group>
          </group>
        )}

        {/* Tubular Carbon Arms + Brushless Motor Bells */}
        {rotorOffsets.map(([rx, , rz], idx) => {
          const len = Math.hypot(rx, rz);
          const ang = Math.atan2(rx, rz);
          return (
            <group key={idx}>
              <mesh position={[rx / 2, 0.16, rz / 2]} rotation={[Math.PI / 2, 0, -ang]}>
                <cylinderGeometry args={[0.16, 0.2, len, 8]} />
                <meshStandardMaterial color="#334155" metalness={0.7} roughness={0.3} />
              </mesh>
              <mesh position={[rx, 0.34, rz]}>
                <cylinderGeometry args={[0.38, 0.34, 0.42, 12]} />
                <meshStandardMaterial color="#0f172a" metalness={0.85} roughness={0.2} />
              </mesh>
            </group>
          );
        })}

        {/* Aviation LED Nav Lights (Port Red, Starboard Green, Tail Strobe) */}
        <mesh position={[-2.4, 0.35, 2.0]}><sphereGeometry args={[0.26, 6, 6]} /><meshBasicMaterial color={[2.6, 0.25, 0.25]} toneMapped={false} /></mesh>
        <mesh position={[2.4, 0.35, 2.0]}><sphereGeometry args={[0.26, 6, 6]} /><meshBasicMaterial color={[0.25, 2.4, 0.5]} toneMapped={false} /></mesh>
        <mesh ref={strobeRef} position={[0, 0.7, -2.2]}><sphereGeometry args={[0.28, 6, 6]} /><meshBasicMaterial color={[2.5, 2.5, 2.5]} toneMapped={false} /></mesh>

        {/* Spinning Dual-Blade Propellers + Motion Blur Discs */}
        <group ref={rotorsRef}>
          {rotorOffsets.map(([rx, ry, rz], idx) => (
            <group key={idx} position={[rx, ry + 0.08, rz]}>
              <mesh><cylinderGeometry args={[0.16, 0.16, 0.15, 8]} /><meshStandardMaterial color="#cbd5e1" metalness={0.8} /></mesh>
              <mesh><boxGeometry args={[2.5, 0.06, 0.24]} /><meshBasicMaterial color={isDestroyed ? "#7f1d1d" : "#f1f5f9"} /></mesh>
              {isFlying && !isDestroyed && (
                <mesh rotation={[-Math.PI / 2, 0, 0]}>
                  <ringGeometry args={[0.28, 1.28, 20]} />
                  <meshBasicMaterial color="#e2e8f0" transparent opacity={0.22} side={THREE.DoubleSide} />
                </mesh>
              )}
            </group>
          ))}
        </group>

        {(isScanning || isNightSearchlight) && (
          <mesh position={[0, -16, 0]}>
            <coneGeometry args={[isScanning ? 11 : 7, 32, 16, 1, true]} />
            <meshBasicMaterial color={isScanning ? "#f59e0b" : "#e2e8f0"} transparent opacity={isScanning ? 0.15 : 0.09} side={THREE.DoubleSide} />
          </mesh>
        )}

        {(selected || hovered) && (
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.8, 0]}>
            <ringGeometry args={[5.5, 7.0, 24]} />
            <meshBasicMaterial color={selected ? "#ffffff" : "#cbd5e1"} side={THREE.DoubleSide} />
          </mesh>
        )}

        {isDestroyed && (
          <group>
            <mesh ref={sparkRef} position={[0, 1.5, 0]}><dodecahedronGeometry args={[3.2, 0]} /><meshBasicMaterial color="#f97316" transparent opacity={0.75} /></mesh>
            <mesh position={[0, 14, 0]}><cylinderGeometry args={[5.5, 2.2, 22, 10, 1, true]} /><meshBasicMaterial color="#27272a" transparent opacity={0.48} side={THREE.DoubleSide} /></mesh>
          </group>
        )}

        {(selected || hovered || isDestroyed) && (
          <Html position={[0, 6.8, 0]} center distanceFactor={680}>
            <div className="px-2 py-0.5 text-[10px] font-mono tabular-nums bg-black/85 border border-white/25 text-white whitespace-nowrap pointer-events-none shadow-lg">
              {drone.id} · {drone.status} · {drone.groundspeed_mps.toFixed(1)}m/s · {drone.battery_percent.toFixed(0)}%
            </div>
          </Html>
        )}
      </group>
    </group>
  );
};

export const DroneFleet: React.FC<{ drones: DroneState[]; dayMode?: boolean; windSpeed?: number }> = ({ drones, dayMode = false, windSpeed = 6.0 }) => {
  const selectedDroneId = useSimStore((s) => s.selectedDroneId);
  const selectDrone = useSimStore((s) => s.selectDrone);
  return (
    <group>
      {drones.map((d) => (
        <DroneMesh key={d.id} drone={d} selected={d.id === selectedDroneId} dayMode={dayMode} windSpeed={windSpeed} onSelect={() => selectDrone(d.id)} />
      ))}
    </group>
  );
};
