import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html, Line } from "@react-three/drei";
import * as THREE from "three";
import { DroneState, GhostRoute } from "../types/simulation";
import { useSimStore } from "../state/simulationStore";

const ROUTE_COLORS: Record<string, string> = {
  slate: "#94a3b8",
  blue: "#3b82f6",
  amber: "#f59e0b",
  green: "#10b981",
  orange: "#f97316",
  red: "#ef4444",
};

const AnimatedSplineRoute: React.FC<{
  waypoints: [number, number, number][];
  color: string;
  highlighted?: boolean;
  dimmed?: boolean;
}> = ({ waypoints, color, highlighted = false, dimmed = false }) => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const lineRef = useRef<any>(null);

  const curvePts = useMemo(() => {
    if (waypoints.length < 3) return waypoints;
    const vecs = waypoints.map((w) => new THREE.Vector3(w[0], w[1], w[2]));
    const curve = new THREE.CatmullRomCurve3(vecs, false, "catmullrom", 0.35);
    return curve.getPoints(Math.min(64, waypoints.length * 8)).map((v) => [v.x, v.y, v.z] as [number, number, number]);
  }, [waypoints]);

  useFrame((_, delta) => {
    if (lineRef.current?.material) {
      lineRef.current.material.dashOffset -= delta * (highlighted ? 44 : 24);
    }
  });

  return (
    <group>
      {/* Solid core glow line for selected drone so its path is unmistakably clear */}
      {highlighted && (
        <Line
          points={curvePts}
          color="#ffffff"
          lineWidth={4.2}
          transparent
          opacity={0.45}
        />
      )}
      <Line
        ref={lineRef}
        points={curvePts}
        color={highlighted ? "#38bdf8" : color}
        lineWidth={highlighted ? 3.2 : 1.7}
        dashed
        dashSize={highlighted ? 24 : 18}
        gapSize={highlighted ? 10 : 10}
        transparent
        opacity={highlighted ? 0.98 : dimmed ? 0.16 : 0.78}
      />
    </group>
  );
};

export const FlightPaths: React.FC<{ drones: DroneState[]; ghostRoutes: Record<string, GhostRoute[]> }> = ({
  drones,
  ghostRoutes,
}) => {
  const showRoutes = useSimStore((s) => s.showRoutes);
  const showGhostRoutes = useSimStore((s) => s.showGhostRoutes);
  const activeView = useSimStore((s) => s.activeView);
  const selectedDroneId = useSimStore((s) => s.selectedDroneId);

  const selectedDrone = useMemo(
    () => drones.find((d) => d.id === selectedDroneId) || null,
    [drones, selectedDroneId]
  );

  return (
    <group>
      {/* Always render selected drone's full 3D path, waypoints, and destination lock — even if global routes are hidden */}
      {selectedDrone && selectedDrone.current_route && selectedDrone.current_route.waypoints.length >= 2 && (
        <group>
          <AnimatedSplineRoute
            waypoints={[selectedDrone.position, ...selectedDrone.current_route.waypoints.slice(1)]}
            color="#38bdf8"
            highlighted
          />
          {/* 3D Waypoint Nodes along Selected Drone's Path */}
          {selectedDrone.current_route.waypoints.map((wp, idx) => {
            const isGoal = idx === selectedDrone.current_route!.waypoints.length - 1;
            if (idx === 0) return null;
            return (
              <group key={idx} position={wp}>
                <mesh>
                  <sphereGeometry args={[isGoal ? 6.5 : 3.2, 12, 12]} />
                  <meshBasicMaterial
                    color={isGoal ? [0.25, 2.2, 1.4] : [0.35, 1.8, 2.5]}
                    toneMapped={false}
                  />
                </mesh>
                {isGoal && (
                  <>
                    {/* Destination Ground Lock Ring */}
                    <mesh position={[0, -wp[1] + 1.2, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                      <ringGeometry args={[18, 25, 32]} />
                      <meshBasicMaterial color="#38bdf8" side={THREE.DoubleSide} transparent opacity={0.85} />
                    </mesh>
                    {/* Vertical Destination Beacon */}
                    <Line
                      points={[[0, 0, 0], [0, -wp[1] + 1.2, 0]]}
                      color="#38bdf8"
                      lineWidth={1.5}
                      transparent
                      opacity={0.7}
                    />
                    <Html position={[0, 14, 0]} center distanceFactor={720}>
                      <div className="px-2 py-0.5 text-[10px] font-mono tabular-nums bg-black/90 border border-sky-400/70 text-sky-200 whitespace-nowrap pointer-events-none shadow-lg">
                        {selectedDrone.id} → {selectedDrone.active_task_id || "BASE"} ·{" "}
                        {selectedDrone.current_route!.distance_m.toFixed(0)}m · ETA {selectedDrone.eta_seconds.toFixed(0)}s
                      </div>
                    </Html>
                  </>
                )}
              </group>
            );
          })}
        </group>
      )}

      {/* Other Fleet Routes (dimmed when a specific drone is selected so focus stays on the clicked drone) */}
      {showRoutes &&
        drones.map((d) => {
          if (d.id === selectedDroneId) return null;
          if (!d.current_route || d.current_route.waypoints.length < 2) return null;
          return (
            <AnimatedSplineRoute
              key={d.current_route.route_id}
              waypoints={d.current_route.waypoints}
              color={ROUTE_COLORS[d.current_route.color_tag] || "#3b82f6"}
              dimmed={Boolean(selectedDroneId)}
            />
          );
        })}

      {showRoutes &&
        showGhostRoutes &&
        Object.entries(ghostRoutes).map(([strat, routes]) => {
          if (strat === activeView) return null;
          const ghostColor = strat === "quantum" ? "#d97706" : strat === "hybrid" ? "#10b981" : "#64748b";
          return routes.map((rt, idx) =>
            rt.waypoints.length >= 2 ? (
              <Line
                key={`ghost-${strat}-${rt.drone_id}-${idx}`}
                points={rt.waypoints}
                color={ghostColor}
                lineWidth={1.1}
                dashed
                dashSize={14}
                gapSize={10}
                transparent
                opacity={selectedDroneId ? 0.1 : 0.28}
              />
            ) : null
          );
        })}
    </group>
  );
};
