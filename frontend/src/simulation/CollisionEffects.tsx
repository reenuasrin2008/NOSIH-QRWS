import React, { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { useSimStore } from "../state/simulationStore";
import { DroneState, Building } from "../types/simulation";

// ─── Types ────────────────────────────────────────────────────────────────────

interface CollisionEvent {
  id: string;
  x: number;
  y: number;
  z: number;
  createdAt: number;
  type: "drone" | "building";
}

// Statuses that mean the drone is airborne and can collide.
const IN_FLIGHT_STATUSES = new Set([
  "IN_FLIGHT",
  "TAKING_OFF",
  "DELIVERING",
  "RETURNING",
]);

// ─── Helpers ──────────────────────────────────────────────────────────────────

function dist3(a: [number, number, number], b: [number, number, number]): number {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  const dz = a[2] - b[2];
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

function collidesBuilding(drone: DroneState, building: Building): boolean {
  const dx = Math.abs(drone.position[0] - building.x);
  const dz = Math.abs(drone.position[2] - building.z);
  const halfW = building.width / 2 + 12;
  const halfD = building.depth / 2 + 12;
  return dx < halfW && dz < halfD && drone.position[1] < building.height + 15;
}

// 8 unit vectors in a circle on the XZ plane (precomputed).
const SPARK_DIRS: [number, number][] = Array.from({ length: 8 }, (_, i) => {
  const angle = (i / 8) * Math.PI * 2;
  return [Math.cos(angle), Math.sin(angle)];
});

// ─── Component ────────────────────────────────────────────────────────────────

export const CollisionEffects: React.FC = () => {
  const drones    = useSimStore((s) => s.activeState?.drones);
  const buildings = useSimStore((s) => s.city?.buildings);

  // All live collision events, mutated directly to avoid re-renders.
  const eventsRef = useRef<CollisionEvent[]>([]);

  // Track which pairs collided last frame to avoid re-spawning every frame.
  const activePairsRef = useRef<Set<string>>(new Set());

  // Per-event mesh refs for the ring, flash, and 8 sparks.
  // Keyed by event id.
  const ringRefs  = useRef<Map<string, THREE.Mesh>>(new Map());
  const flashRefs = useRef<Map<string, THREE.Mesh>>(new Map());
  const sparkRefs = useRef<Map<string, THREE.Mesh[]>>(new Map());

  useFrame(() => {
    const now = Date.now();
    const events = eventsRef.current;

    // ── 1. Detect new collisions ──────────────────────────────────────────

    const currentPairs = new Set<string>();

    if (drones && drones.length > 0) {
      // Drone-to-drone
      for (let i = 0; i < drones.length; i++) {
        const a = drones[i];
        if (!IN_FLIGHT_STATUSES.has(a.status)) continue;
        for (let j = i + 1; j < drones.length; j++) {
          const b = drones[j];
          if (!IN_FLIGHT_STATUSES.has(b.status)) continue;
          if (dist3(a.position, b.position) < 18) {
            const pairKey = `dd:${a.id}:${b.id}`;
            currentPairs.add(pairKey);
            if (!activePairsRef.current.has(pairKey) && events.length < 20) {
              const mx = (a.position[0] + b.position[0]) / 2;
              const my = (a.position[1] + b.position[1]) / 2;
              const mz = (a.position[2] + b.position[2]) / 2;
              events.push({
                id: `${pairKey}-${now}`,
                x: mx, y: my, z: mz,
                createdAt: now,
                type: "drone",
              });
            }
          }
        }
      }

      // Drone-to-building
      if (buildings) {
        for (const drone of drones) {
          if (!IN_FLIGHT_STATUSES.has(drone.status)) continue;
          for (const building of buildings) {
            if (collidesBuilding(drone, building)) {
              const pairKey = `db:${drone.id}:${building.id}`;
              currentPairs.add(pairKey);
              if (!activePairsRef.current.has(pairKey) && events.length < 20) {
                events.push({
                  id: `${pairKey}-${now}`,
                  x: drone.position[0],
                  y: drone.position[1],
                  z: drone.position[2],
                  createdAt: now,
                  type: "building",
                });
              }
            }
          }
        }
      }
    }

    activePairsRef.current = currentPairs;

    // ── 2. Animate and expire existing events ────────────────────────────

    const survived: CollisionEvent[] = [];

    for (const ev of events) {
      const age = (now - ev.createdAt) / 1000; // seconds

      if (age > 1.2) {
        // Clean up refs when the event dies.
        ringRefs.current.delete(ev.id);
        flashRefs.current.delete(ev.id);
        sparkRefs.current.delete(ev.id);
        continue;
      }

      survived.push(ev);

      // Ring: scale and opacity
      const ring = ringRefs.current.get(ev.id);
      if (ring) {
        const s = 1 + age * 40;
        ring.scale.set(s, s, 1);
        const mat = ring.material as THREE.MeshBasicMaterial;
        mat.opacity = Math.max(0, 1 - age);
      }

      // Flash: visible for first 0.3s
      const flash = flashRefs.current.get(ev.id);
      if (flash) {
        const mat = flash.material as THREE.MeshBasicMaterial;
        const o = Math.max(0, 1 - age * 3);
        mat.opacity = o;
        flash.visible = o > 0;
      }

      // Sparks: move outward and fade
      const sparks = sparkRefs.current.get(ev.id);
      if (sparks) {
        const opacity = Math.max(0, 1 - age);
        sparks.forEach((spark, idx) => {
          const [sx, sz] = SPARK_DIRS[idx];
          const dist = age * 80;
          spark.position.set(sx * dist, 0, sz * dist);
          const mat = spark.material as THREE.MeshBasicMaterial;
          mat.opacity = opacity;
        });
      }
    }

    eventsRef.current = survived;
  });

  // ─── Render ────────────────────────────────────────────────────────────────
  // We render a fixed pool approach: snapshot events once into JSX.
  // Because we don't setState, React never re-renders this component due to
  // frame-loop changes. We read eventsRef.current directly in the JSX to
  // produce a stable initial structure, and useFrame mutates the meshes.
  //
  // To ensure new events actually get DOM nodes, we drive a minimal re-render
  // via a version counter only when the events array length changes.

  const [, forceUpdate] = React.useReducer((x: number) => x + 1, 0);
  const prevLenRef = useRef(0);

  useFrame(() => {
    const len = eventsRef.current.length;
    if (len !== prevLenRef.current) {
      prevLenRef.current = len;
      forceUpdate();
    }
  });

  const events = eventsRef.current;

  return (
    <group>
      {events.map((ev) => {
        const ringColor   = ev.type === "drone" ? "#f97316" : "#ef4444";

        return (
          <group key={ev.id} position={[ev.x, ev.y, ev.z]}>
            {/* Expanding ring — rotated flat on XZ plane */}
            <mesh
              rotation={[-Math.PI / 2, 0, 0]}
              frustumCulled={false}
              ref={(el) => {
                if (el) ringRefs.current.set(ev.id, el);
              }}
            >
              <ringGeometry args={[0, 1, 32]} />
              <meshBasicMaterial
                color={ringColor}
                transparent
                opacity={1}
                side={THREE.DoubleSide}
                depthWrite={false}
              />
            </mesh>

            {/* Central flash sphere */}
            <mesh
              frustumCulled={false}
              ref={(el) => {
                if (el) flashRefs.current.set(ev.id, el);
              }}
            >
              <sphereGeometry args={[3, 8, 8]} />
              <meshBasicMaterial
                color="#fff7ed"
                transparent
                opacity={1}
                depthWrite={false}
              />
            </mesh>

            {/* 8 spark particles */}
            <group
              ref={(groupEl) => {
                if (!groupEl) return;
                // Collect child meshes into sparkRefs on first mount.
                if (!sparkRefs.current.has(ev.id)) {
                  const meshes: THREE.Mesh[] = [];
                  groupEl.children.forEach((child) => {
                    if (child instanceof THREE.Mesh) meshes.push(child);
                  });
                  if (meshes.length === 8) {
                    sparkRefs.current.set(ev.id, meshes);
                  }
                }
              }}
            >
              {SPARK_DIRS.map((_, idx) => (
                <mesh key={idx} frustumCulled={false}>
                  <sphereGeometry args={[1.2, 4, 4]} />
                  <meshBasicMaterial
                    color="#fbbf24"
                    transparent
                    opacity={1}
                    depthWrite={false}
                  />
                </mesh>
              ))}
            </group>
          </group>
        );
      })}
    </group>
  );
};
