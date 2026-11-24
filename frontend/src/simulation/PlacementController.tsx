import React, { useState } from "react";
import { ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import { useSimStore } from "../state/simulationStore";
import { api } from "../api/client";

export const PlacementController: React.FC<{ worldSize: number }> = ({ worldSize }) => {
  const placementMode = useSimStore((s) => s.placementMode);
  const selectedDroneId = useSimStore((s) => s.selectedDroneId);
  const setPendingLocation = useSimStore((s) => s.setPendingLocation);
  const setShowAddTargetModal = useSimStore((s) => s.setShowAddTargetModal);
  const setPlacementMode = useSimStore((s) => s.setPlacementMode);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setToast = useSimStore((s) => s.setToast);

  const [hoverPt, setHoverPt] = useState<[number, number, number] | null>(null);
  if (placementMode === "none") return null;

  const half = worldSize / 2;
  const clamp = (v: number) => Math.round(Math.max(60, Math.min(worldSize - 60, v)));

  const handleMove = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    setHoverPt([clamp(e.point.x), 4, clamp(e.point.z)]);
  };

  const handleClick = async (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    const x = clamp(e.point.x);
    const z = clamp(e.point.z);
    const pt: [number, number, number] = [x, 4, z];

    if (placementMode === "add_target") {
      setPendingLocation(pt);
      setShowAddTargetModal(true);
      setPlacementMode("none");
    } else if (placementMode === "set_waypoint" && selectedDroneId) {
      try {
        const res = await api.setDroneWaypoint(selectedDroneId, pt);
        applyServerPayload(res.state);
        setToast(`Waypoint assigned to ${selectedDroneId} at (${x}, ${z})`);
      } catch (err) {
        setToast(`Waypoint rejected: ${(err as Error).message}`);
      } finally {
        setPlacementMode("none");
      }
    }
  };

  return (
    <group>
      <mesh position={[half, 0.5, half]} rotation={[-Math.PI / 2, 0, 0]} onPointerMove={handleMove} onClick={handleClick}>
        <planeGeometry args={[worldSize, worldSize]} />
        <meshBasicMaterial transparent opacity={0.0} />
      </mesh>
      {hoverPt && (
        <group position={[hoverPt[0], 2, hoverPt[2]]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[20, 30, 32]} />
            <meshBasicMaterial color={placementMode === "add_target" ? "#dc2626" : "#3b82f6"} side={THREE.DoubleSide} />
          </mesh>
          <mesh position={[0, 36, 0]}>
            <cylinderGeometry args={[1.5, 1.5, 72, 8]} />
            <meshBasicMaterial color={placementMode === "add_target" ? "#dc2626" : "#3b82f6"} />
          </mesh>
        </group>
      )}
    </group>
  );
};
