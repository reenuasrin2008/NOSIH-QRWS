import React, { useEffect, useMemo, useRef, useState } from "react";
import { ThreeEvent, useFrame } from "@react-three/fiber";
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

const MAX_DRONES = 128;
const MAX_ROTORS_PER_DRONE = 6;
const MAX_ROTORS = MAX_DRONES * MAX_ROTORS_PER_DRONE;
const MAX_SKIDS = MAX_DRONES * 2;

const QUAD_OFFSETS: [number, number, number][] = [
  [-2.7, 0.55, -2.7],
  [2.7, 0.55, -2.7],
  [-2.7, 0.55, 2.7],
  [2.7, 0.55, 2.7],
];

const HEX_OFFSETS: [number, number, number][] = [
  [-3.6, 0.55, 0],
  [3.6, 0.55, 0],
  [-2.0, 0.55, -3.1],
  [2.0, 0.55, -3.1],
  [-2.0, 0.55, 3.1],
  [2.0, 0.55, 3.1],
];

interface DroneKinematics {
  pos: THREE.Vector3;
  heading: number;
  pitch: number;
  bank: number;
  rpm: number;
  rotorAngle: number;
}

function getDroneAccent(drone: DroneState): string {
  if (drone.status === "DESTROYED") return "#dc2626";
  if (drone.status === "DAMAGED" || drone.status === "COMMUNICATION_LOST") return "#d97706";
  return CLASS_COLORS[drone.drone_type] || "#3b82f6";
}

function getDroneScale(drone: DroneState): number {
  if (drone.drone_type === "heavy_lift") return 3.3;
  if (drone.drone_type === "surveillance") return 2.3;
  return 2.7;
}

/** Per-drone contextual overlays (labels, tethers, scan cones, cargo winch, destroyed effects). */
const DroneOverlay: React.FC<{
  drone: DroneState;
  selected: boolean;
  hovered: boolean;
  dayMode: boolean;
}> = ({ drone, selected, hovered, dayMode }) => {
  const winchRef = useRef<THREE.Group>(null);
  const sparkRef = useRef<THREE.Mesh>(null);
  const downwashRef = useRef<THREE.Mesh>(null);

  const isDestroyed = drone.status === "DESTROYED";
  const isFlying = ["IN_FLIGHT", "TAKING_OFF", "DELIVERING", "RETURNING"].includes(drone.status);
  const isDelivering = drone.status === "DELIVERING";
  const isSearchClass =
    drone.drone_type === "surveillance" || drone.drone_type === "search_rescue";
  const isScanning = isDelivering && isSearchClass;
  const isNightSearchlight = !dayMode && isFlying && !isDestroyed && isSearchClass;
  const isDroppingCargo =
    isDelivering && (drone.drone_type === "medical" || drone.drone_type === "heavy_lift");
  const accent = getDroneAccent(drone);
  const scale = getDroneScale(drone);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
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

  return (
    <group>
      {/* Ground Contact Shadow for Low-Altitude Drones */}
      {!isDestroyed && drone.position[1] < 55 && (
        <mesh position={[drone.position[0], 0.55, drone.position[2]]} rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[Math.max(4, 12 - drone.position[1] * 0.14), 18]} />
          <meshBasicMaterial
            color="#000000"
            transparent
            opacity={Math.max(0.08, 0.42 - drone.position[1] * 0.006)}
          />
        </mesh>
      )}

      {/* Rotor Downwash Dust Ring during Low-Altitude Delivery */}
      {isDelivering && !isDestroyed && (
        <mesh
          ref={downwashRef}
          position={[drone.position[0], 0.9, drone.position[2]]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
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
          <mesh
            position={[drone.position[0], 0.7, drone.position[2]]}
            rotation={[-Math.PI / 2, 0, 0]}
          >
            <ringGeometry args={[selected ? 11 : 5, selected ? 14 : 7, 20]} />
            <meshBasicMaterial
              color={selected ? "#ffffff" : accent}
              transparent
              opacity={selected ? 0.8 : 0.34}
              side={THREE.DoubleSide}
            />
          </mesh>
        </group>
      )}

      {/* Drone-Attached Contextual Overlays */}
      {(isDroppingCargo || isScanning || isNightSearchlight || selected || hovered || isDestroyed) && (
        <group position={drone.position} scale={[scale, scale, scale]}>
          {isDroppingCargo && (
            <group>
              <mesh position={[0, -5, 0]}>
                <cylinderGeometry args={[0.06, 0.06, 10, 4]} />
                <meshBasicMaterial color="#e2e8f0" />
              </mesh>
              <group ref={winchRef} position={[0, -6, 0]}>
                <mesh>
                  <boxGeometry args={[2.0, 1.25, 2.0]} />
                  <meshStandardMaterial
                    color={drone.drone_type === "medical" ? "#f8fafc" : "#eab308"}
                  />
                </mesh>
              </group>
            </group>
          )}

          {(isScanning || isNightSearchlight) && (
            <mesh position={[0, -16, 0]}>
              <coneGeometry args={[isScanning ? 11 : 7, 32, 16, 1, true]} />
              <meshBasicMaterial
                color={isScanning ? "#f59e0b" : "#e2e8f0"}
                transparent
                opacity={isScanning ? 0.15 : 0.09}
                side={THREE.DoubleSide}
              />
            </mesh>
          )}

          {(selected || hovered) && (
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.8, 0]}>
              <ringGeometry args={[5.5, 7.0, 24]} />
              <meshBasicMaterial
                color={selected ? "#ffffff" : "#cbd5e1"}
                side={THREE.DoubleSide}
              />
            </mesh>
          )}

          {isDestroyed && (
            <group>
              <mesh ref={sparkRef} position={[0, 1.5, 0]}>
                <dodecahedronGeometry args={[3.2, 0]} />
                <meshBasicMaterial color="#f97316" transparent opacity={0.75} />
              </mesh>
              <mesh position={[0, 14, 0]}>
                <cylinderGeometry args={[5.5, 2.2, 22, 10, 1, true]} />
                <meshBasicMaterial
                  color="#27272a"
                  transparent
                  opacity={0.48}
                  side={THREE.DoubleSide}
                />
              </mesh>
            </group>
          )}

          {(selected || hovered || isDestroyed) && (
            <Html position={[0, 6.8, 0]} center distanceFactor={680}>
              <div className="px-2 py-0.5 text-[10px] font-mono tabular-nums bg-black/85 border border-white/25 text-white whitespace-nowrap pointer-events-none shadow-lg">
                {drone.id} · {drone.status} · {drone.groundspeed_mps.toFixed(1)}m/s ·{" "}
                {drone.battery_percent.toFixed(0)}%
              </div>
            </Html>
          )}
        </group>
      )}
    </group>
  );
};

export const DroneFleet: React.FC<{
  drones: DroneState[];
  dayMode?: boolean;
  windSpeed?: number;
}> = ({ drones, dayMode = false, windSpeed = 6.0 }) => {
  const selectedDroneId = useSimStore((s) => s.selectedDroneId);
  const selectDrone = useSimStore((s) => s.selectDrone);
  const [hoveredDroneId, setHoveredDroneId] = useState<string | null>(null);

  // InstancedMesh refs for low-draw-call fleet rendering
  const fuselageRef = useRef<THREE.InstancedMesh>(null);
  const noseRef = useRef<THREE.InstancedMesh>(null);
  const canopyRef = useRef<THREE.InstancedMesh>(null);
  const gimbalRef = useRef<THREE.InstancedMesh>(null);
  const skidRef = useRef<THREE.InstancedMesh>(null);
  const motorBellRef = useRef<THREE.InstancedMesh>(null);
  const rotorBladeRef = useRef<THREE.InstancedMesh>(null);
  const rotorDiscRef = useRef<THREE.InstancedMesh>(null);
  const navPortRef = useRef<THREE.InstancedMesh>(null);
  const navStbdRef = useRef<THREE.InstancedMesh>(null);
  const navStrobeRef = useRef<THREE.InstancedMesh>(null);

  const kinematicsRef = useRef<Map<string, DroneKinematics>>(new Map());

  useEffect(() => {
    return () => {
      document.body.style.cursor = "auto";
    };
  }, []);

  // Reusable scratch math objects (zero allocations inside useFrame)
  const scratch = useMemo(
    () => ({
      targetPos: new THREE.Vector3(),
      droneMat: new THREE.Matrix4(),
      localMat: new THREE.Matrix4(),
      worldMat: new THREE.Matrix4(),
      zeroMat: new THREE.Matrix4().makeScale(0, 0, 0),
      quat: new THREE.Quaternion(),
      euler: new THREE.Euler(0, 0, 0, "YXZ"),
      scaleVec: new THREE.Vector3(),
      partPos: new THREE.Vector3(),
      partQuat: new THREE.Quaternion(),
      partEuler: new THREE.Euler(),
      partScale: new THREE.Vector3(1, 1, 1),
      color: new THREE.Color(),
    }),
    []
  );

  useFrame((state, delta) => {
    const dt = Number.isFinite(delta) ? Math.min(Math.max(delta, 0), 0.05) : 0.016;
    const t = state.clock.elapsedTime;
    const count = Math.min(drones.length, MAX_DRONES);

    // Prune stale drone kinematics entries after scenario resets
    if (kinematicsRef.current.size > drones.length + 16) {
      const activeIds = new Set(drones.map((d) => d.id));
      for (const key of kinematicsRef.current.keys()) {
        if (!activeIds.has(key)) kinematicsRef.current.delete(key);
      }
    }

    const fuselageMesh = fuselageRef.current;
    const noseMesh = noseRef.current;
    const canopyMesh = canopyRef.current;
    const gimbalMesh = gimbalRef.current;
    const skidMesh = skidRef.current;
    const motorMesh = motorBellRef.current;
    const bladeMesh = rotorBladeRef.current;
    const discMesh = rotorDiscRef.current;
    const portMesh = navPortRef.current;
    const stbdMesh = navStbdRef.current;
    const strobeMesh = navStrobeRef.current;

    if (
      !fuselageMesh ||
      !noseMesh ||
      !canopyMesh ||
      !gimbalMesh ||
      !skidMesh ||
      !motorMesh ||
      !bladeMesh ||
      !discMesh ||
      !portMesh ||
      !stbdMesh ||
      !strobeMesh
    ) {
      return;
    }

    let rotorIdx = 0;
    let skidIdx = 0;

    for (let i = 0; i < count; i++) {
      const drone = drones[i];
      const px = Number.isFinite(drone.position?.[0]) ? drone.position[0] : 0;
      const py = Number.isFinite(drone.position?.[1]) ? drone.position[1] : 0;
      const pz = Number.isFinite(drone.position?.[2]) ? drone.position[2] : 0;
      const safeHeading = Number.isFinite(drone.heading_rad) ? drone.heading_rad : 0;
      const safePitch = Number.isFinite(drone.pitch_rad) ? drone.pitch_rad : 0;
      const safeBank = Number.isFinite(drone.bank_rad) ? drone.bank_rad : 0;

      let kin = kinematicsRef.current.get(drone.id);
      if (!kin) {
        kin = {
          pos: new THREE.Vector3(px, py, pz),
          heading: safeHeading,
          pitch: safePitch,
          bank: safeBank,
          rpm: 0,
          rotorAngle: 0,
        };
        kinematicsRef.current.set(drone.id, kin);
      }

      const isDestroyed = drone.status === "DESTROYED";
      const isFlying = ["IN_FLIGHT", "TAKING_OFF", "DELIVERING", "RETURNING"].includes(
        drone.status
      );
      const isDelivering = drone.status === "DELIVERING";
      const isHex = drone.drone_type === "heavy_lift";
      const seed = drone.id.charCodeAt(drone.id.length - 1);

      const gustAmp = isFlying && !isDestroyed ? Math.min(0.06, 0.012 + windSpeed * 0.0025) : 0;
      const gustRoll = Math.sin(t * 3.1 + seed) * gustAmp;
      const gustPitch = Math.cos(t * 2.6 + seed * 1.3) * gustAmp * 0.8;

      scratch.targetPos.set(px, py, pz);
      const posAlpha = 1 - Math.exp(-6.8 * dt);
      kin.pos.lerp(scratch.targetPos, posAlpha);
      const hoverY = isDelivering ? Math.sin(t * 3.8 + seed) * 0.22 : 0;

      if (isDestroyed && py > 4) {
        kin.heading += dt * 6.5;
        kin.pitch = 0.55;
        kin.bank = 0.82;
      } else {
        const diffH = safeHeading - kin.heading;
        const dH = Math.atan2(Math.sin(diffH), Math.cos(diffH));
        kin.heading += dH * (1 - Math.exp(-7.5 * dt));
        const tgtPitch = isDestroyed ? 0.35 : safePitch + gustPitch;
        const tgtBank = isDestroyed ? 0.65 : safeBank + gustRoll;
        kin.pitch += (tgtPitch - kin.pitch) * (1 - Math.exp(-6.5 * dt));
        kin.bank += (tgtBank - kin.bank) * (1 - Math.exp(-6.5 * dt));
      }

      const targetRpm = isFlying && !isDestroyed ? 46 : 0;
      kin.rpm += (targetRpm - kin.rpm) * (1 - Math.exp(-3.2 * dt));
      kin.rotorAngle += dt * kin.rpm;

      const sc = getDroneScale(drone);
      scratch.euler.set(kin.pitch, kin.heading, kin.bank, "YXZ");
      scratch.quat.setFromEuler(scratch.euler);
      scratch.scaleVec.set(sc, sc, sc);
      scratch.partPos.set(kin.pos.x, kin.pos.y + hoverY, kin.pos.z);
      scratch.droneMat.compose(scratch.partPos, scratch.quat, scratch.scaleVec);

      // 1. Main Fuselage
      fuselageMesh.setMatrixAt(i, scratch.droneMat);
      scratch.color.set(isDestroyed ? "#451a1a" : "#1c212b");
      fuselageMesh.setColorAt(i, scratch.color);

      // 2. Aerodynamic Nose Cone
      scratch.partPos.set(0, 0.05, 2.45);
      scratch.partEuler.set(Math.PI / 2, 0, 0);
      scratch.partQuat.setFromEuler(scratch.partEuler);
      scratch.partScale.set(1, 1, 1);
      scratch.localMat.compose(scratch.partPos, scratch.partQuat, scratch.partScale);
      scratch.worldMat.multiplyMatrices(scratch.droneMat, scratch.localMat);
      noseMesh.setMatrixAt(i, scratch.worldMat);
      scratch.color.set(isDestroyed ? "#451a1a" : "#272e3b");
      noseMesh.setColorAt(i, scratch.color);

      // 3. Top Avionics Canopy Shell (status & class livery color via setColorAt)
      scratch.partPos.set(0, 0.62, 0.1);
      scratch.partQuat.identity();
      scratch.localMat.compose(scratch.partPos, scratch.partQuat, scratch.partScale);
      scratch.worldMat.multiplyMatrices(scratch.droneMat, scratch.localMat);
      canopyMesh.setMatrixAt(i, scratch.worldMat);
      scratch.color.set(getDroneAccent(drone));
      canopyMesh.setColorAt(i, scratch.color);

      // 4. Underslung Gimbal Turret
      scratch.partPos.set(0, -0.72, 1.45);
      scratch.partQuat.identity();
      scratch.localMat.compose(scratch.partPos, scratch.partQuat, scratch.partScale);
      scratch.worldMat.multiplyMatrices(scratch.droneMat, scratch.localMat);
      gimbalMesh.setMatrixAt(i, scratch.worldMat);

      // 5. Twin Landing Skids
      for (let side = -1; side <= 1; side += 2) {
        scratch.partPos.set(side * 1.4, -1.25, 0);
        scratch.partQuat.identity();
        scratch.localMat.compose(scratch.partPos, scratch.partQuat, scratch.partScale);
        scratch.worldMat.multiplyMatrices(scratch.droneMat, scratch.localMat);
        skidMesh.setMatrixAt(skidIdx, scratch.worldMat);
        skidIdx += 1;
      }

      // 6. Aviation LED Nav Lights (Port Red, Starboard Green, Tail Strobe)
      scratch.partPos.set(-2.4, 0.35, 2.0);
      scratch.partQuat.identity();
      scratch.localMat.compose(scratch.partPos, scratch.partQuat, scratch.partScale);
      scratch.worldMat.multiplyMatrices(scratch.droneMat, scratch.localMat);
      portMesh.setMatrixAt(i, scratch.worldMat);

      scratch.partPos.set(2.4, 0.35, 2.0);
      scratch.localMat.compose(scratch.partPos, scratch.partQuat, scratch.partScale);
      scratch.worldMat.multiplyMatrices(scratch.droneMat, scratch.localMat);
      stbdMesh.setMatrixAt(i, scratch.worldMat);

      const strobeOn = !isDestroyed && Math.floor(t * 3.2 + seed) % 2 === 0;
      if (strobeOn) {
        scratch.partPos.set(0, 0.7, -2.2);
        scratch.localMat.compose(scratch.partPos, scratch.partQuat, scratch.partScale);
        scratch.worldMat.multiplyMatrices(scratch.droneMat, scratch.localMat);
        strobeMesh.setMatrixAt(i, scratch.worldMat);
      } else {
        strobeMesh.setMatrixAt(i, scratch.zeroMat);
      }

      // 7. Motor Bells, Spinning Propellers & Motion-Blur Rotor Discs
      const offsets = isHex ? HEX_OFFSETS : QUAD_OFFSETS;
      for (let r = 0; r < offsets.length; r++) {
        const [rx, ry, rz] = offsets[r];

        // Motor bell
        scratch.partPos.set(rx, 0.34, rz);
        scratch.partQuat.identity();
        scratch.localMat.compose(scratch.partPos, scratch.partQuat, scratch.partScale);
        scratch.worldMat.multiplyMatrices(scratch.droneMat, scratch.localMat);
        motorMesh.setMatrixAt(rotorIdx, scratch.worldMat);

        // Spinning blade
        const spinDir = r % 2 === 0 ? 1 : -1;
        scratch.partPos.set(rx, ry + 0.08, rz);
        scratch.partEuler.set(0, kin.rotorAngle * spinDir, 0);
        scratch.partQuat.setFromEuler(scratch.partEuler);
        scratch.localMat.compose(scratch.partPos, scratch.partQuat, scratch.partScale);
        scratch.worldMat.multiplyMatrices(scratch.droneMat, scratch.localMat);
        bladeMesh.setMatrixAt(rotorIdx, scratch.worldMat);
        scratch.color.set(isDestroyed ? "#7f1d1d" : "#f1f5f9");
        bladeMesh.setColorAt(rotorIdx, scratch.color);

        // Motion-blur rotor disc when flying
        if (isFlying && !isDestroyed) {
          scratch.partPos.set(rx, ry + 0.09, rz);
          scratch.partEuler.set(-Math.PI / 2, 0, 0);
          scratch.partQuat.setFromEuler(scratch.partEuler);
          scratch.localMat.compose(scratch.partPos, scratch.partQuat, scratch.partScale);
          scratch.worldMat.multiplyMatrices(scratch.droneMat, scratch.localMat);
          discMesh.setMatrixAt(rotorIdx, scratch.worldMat);
        } else {
          discMesh.setMatrixAt(rotorIdx, scratch.zeroMat);
        }

        rotorIdx += 1;
      }
    }

    fuselageMesh.count = count;
    noseMesh.count = count;
    canopyMesh.count = count;
    gimbalMesh.count = count;
    portMesh.count = count;
    stbdMesh.count = count;
    strobeMesh.count = count;
    skidMesh.count = skidIdx;
    motorMesh.count = rotorIdx;
    bladeMesh.count = rotorIdx;
    discMesh.count = rotorIdx;

    if (fuselageMesh.instanceMatrix) fuselageMesh.instanceMatrix.needsUpdate = true;
    if (noseMesh.instanceMatrix) noseMesh.instanceMatrix.needsUpdate = true;
    if (canopyMesh.instanceMatrix) canopyMesh.instanceMatrix.needsUpdate = true;
    if (gimbalMesh.instanceMatrix) gimbalMesh.instanceMatrix.needsUpdate = true;
    if (portMesh.instanceMatrix) portMesh.instanceMatrix.needsUpdate = true;
    if (stbdMesh.instanceMatrix) stbdMesh.instanceMatrix.needsUpdate = true;
    if (strobeMesh.instanceMatrix) strobeMesh.instanceMatrix.needsUpdate = true;
    if (skidMesh.instanceMatrix) skidMesh.instanceMatrix.needsUpdate = true;
    if (motorMesh.instanceMatrix) motorMesh.instanceMatrix.needsUpdate = true;
    if (bladeMesh.instanceMatrix) bladeMesh.instanceMatrix.needsUpdate = true;
    if (discMesh.instanceMatrix) discMesh.instanceMatrix.needsUpdate = true;

    if (fuselageMesh.instanceColor) fuselageMesh.instanceColor.needsUpdate = true;
    if (noseMesh.instanceColor) noseMesh.instanceColor.needsUpdate = true;
    if (canopyMesh.instanceColor) canopyMesh.instanceColor.needsUpdate = true;
    if (bladeMesh.instanceColor) bladeMesh.instanceColor.needsUpdate = true;
  });

  const handlePointerOver = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    const idx = e.instanceId;
    if (idx !== undefined && drones[idx]) {
      setHoveredDroneId(drones[idx].id);
      document.body.style.cursor = "pointer";
    }
  };

  const handlePointerOut = () => {
    setHoveredDroneId(null);
    document.body.style.cursor = "auto";
  };

  const handleClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    const idx = e.instanceId;
    if (idx !== undefined && drones[idx]) {
      selectDrone(drones[idx].id);
    }
  };

  return (
    <group>
      {/* Instanced Sculpted Carbon-Fiber Main Fuselages (interactive selection target) */}
      <instancedMesh
        ref={fuselageRef}
        args={[undefined, undefined, MAX_DRONES]}
        castShadow
        frustumCulled={false}
        onPointerOver={handlePointerOver}
        onPointerOut={handlePointerOut}
        onClick={handleClick}
      >
        <boxGeometry args={[2.6, 0.88, 4.3]} />
        <meshStandardMaterial color="#ffffff" metalness={0.65} roughness={0.32} />
      </instancedMesh>

      {/* Instanced Aerodynamic Nose Cones */}
      <instancedMesh
        ref={noseRef}
        args={[undefined, undefined, MAX_DRONES]}
        frustumCulled={false}
      >
        <coneGeometry args={[1.1, 1.1, 6]} />
        <meshStandardMaterial color="#ffffff" metalness={0.55} roughness={0.35} />
      </instancedMesh>

      {/* Instanced Avionics Canopy Shells with Status/Class Livery Colors */}
      <instancedMesh
        ref={canopyRef}
        args={[undefined, undefined, MAX_DRONES]}
        frustumCulled={false}
        onPointerOver={handlePointerOver}
        onPointerOut={handlePointerOut}
        onClick={handleClick}
      >
        <boxGeometry args={[2.1, 0.45, 2.9]} />
        <meshStandardMaterial color="#ffffff" roughness={0.32} metalness={0.25} />
      </instancedMesh>

      {/* Instanced Optical/Thermal Gimbal Turrets */}
      <instancedMesh
        ref={gimbalRef}
        args={[undefined, undefined, MAX_DRONES]}
        frustumCulled={false}
      >
        <sphereGeometry args={[0.58, 10, 10]} />
        <meshStandardMaterial color="#0f172a" metalness={0.8} roughness={0.18} />
      </instancedMesh>

      {/* Instanced Carbon Landing Skids */}
      <instancedMesh
        ref={skidRef}
        args={[undefined, undefined, MAX_SKIDS]}
        frustumCulled={false}
      >
        <boxGeometry args={[0.22, 0.22, 3.9]} />
        <meshStandardMaterial color="#334155" metalness={0.6} roughness={0.35} />
      </instancedMesh>

      {/* Instanced Brushless Motor Bells */}
      <instancedMesh
        ref={motorBellRef}
        args={[undefined, undefined, MAX_ROTORS]}
        frustumCulled={false}
      >
        <cylinderGeometry args={[0.38, 0.34, 0.42, 10]} />
        <meshStandardMaterial color="#0f172a" metalness={0.85} roughness={0.2} />
      </instancedMesh>

      {/* Instanced Spinning Dual-Blade Propellers */}
      <instancedMesh
        ref={rotorBladeRef}
        args={[undefined, undefined, MAX_ROTORS]}
        frustumCulled={false}
      >
        <boxGeometry args={[2.5, 0.06, 0.24]} />
        <meshBasicMaterial color="#ffffff" />
      </instancedMesh>

      {/* Instanced Motion-Blur Rotor Discs */}
      <instancedMesh
        ref={rotorDiscRef}
        args={[undefined, undefined, MAX_ROTORS]}
        frustumCulled={false}
      >
        <ringGeometry args={[0.28, 1.28, 18]} />
        <meshBasicMaterial color="#e2e8f0" transparent opacity={0.22} side={THREE.DoubleSide} />
      </instancedMesh>

      {/* Instanced Aviation LED Nav Lights (HDR Bloom-ready) */}
      <instancedMesh
        ref={navPortRef}
        args={[undefined, undefined, MAX_DRONES]}
        frustumCulled={false}
      >
        <sphereGeometry args={[0.26, 6, 6]} />
        <meshBasicMaterial color={[2.6, 0.25, 0.25]} toneMapped={false} />
      </instancedMesh>
      <instancedMesh
        ref={navStbdRef}
        args={[undefined, undefined, MAX_DRONES]}
        frustumCulled={false}
      >
        <sphereGeometry args={[0.26, 6, 6]} />
        <meshBasicMaterial color={[0.25, 2.4, 0.5]} toneMapped={false} />
      </instancedMesh>
      <instancedMesh
        ref={navStrobeRef}
        args={[undefined, undefined, MAX_DRONES]}
        frustumCulled={false}
      >
        <sphereGeometry args={[0.28, 6, 6]} />
        <meshBasicMaterial color={[2.5, 2.5, 2.5]} toneMapped={false} />
      </instancedMesh>

      {/* Contextual Per-Drone Overlays (tethers, scan cones, winch, labels) */}
      {drones.map((d) => (
        <DroneOverlay
          key={d.id}
          drone={d}
          selected={d.id === selectedDroneId}
          hovered={d.id === hoveredDroneId}
          dayMode={dayMode}
        />
      ))}
    </group>
  );
};
