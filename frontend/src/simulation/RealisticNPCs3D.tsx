import React, { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

export interface RealisticNPCs3DProps {
  anchors: Record<string, { x: number; z: number }>;
  hasActiveDisaster: boolean;
}

interface NPCAgent {
  kind: "sidewalk" | "park";
  ax: number;
  az: number;
  // Sidewalk parameters
  axis: "x" | "z";
  side: number;
  offset: number;
  spanHalf: number;
  dir: 1 | -1;
  // Park loop parameters
  parkCenterX: number;
  parkCenterZ: number;
  parkRadiusX: number;
  parkRadiusZ: number;
  parkAngle: number;
  parkDir: 1 | -1;
  // Motion & appearance
  baseSpeed: number;
  stridePhase: number;
  scale: number;
  crosswalkCycleOffset: number;
  skinColor: THREE.Color;
  shirtColor: THREE.Color;
  pantsColor: THREE.Color;
}

const NPC_COUNT = 220;

const SKIN_TONES = [
  "#f5d0b5",
  "#eac09e",
  "#dca278",
  "#c68652",
  "#a5693d",
  "#7d4a26",
  "#f0c4a8",
  "#b87a4b",
];

const SHIRT_COLORS = [
  "#1d4ed8", // cobalt jacket
  "#b91c1c", // crimson coat
  "#0f766e", // teal windbreaker
  "#d97706", // ochre sweater
  "#334155", // slate blazer
  "#15803d", // forest jacket
  "#e2e8f0", // crisp light shirt
  "#7c3aed", // plum cardigan
  "#c2410c", // terracotta jacket
  "#0369a1", // sky parka
  "#475569", // charcoal vest
  "#be123c", // rose coat
];

const PANTS_COLORS = [
  "#1e293b", // dark navy
  "#334155", // charcoal
  "#1e3a8a", // denim blue
  "#78644d", // khaki
  "#3f4d3b", // olive
  "#4a3728", // espresso brown
  "#475569", // medium slate
];

// Crosswalk positions along each city's main avenue sidewalks
const CROSSWALK_STOPS = [-280, -34, 34, 280];

function seededRand(seed: number): number {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453123;
  return x - Math.floor(x);
}

/**
 * 220 articulated multi-part realistic NPCs across the 7 countries rendered via
 * separate InstancedMeshes for heads, torsos, left/right legs, and left/right arms.
 * Walks along sidewalks and Central Park paths, pauses briefly at zebra crosswalks,
 * faces exact travel direction, and switches to evacuation running during active disasters.
 */
export const RealisticNPCs3D: React.FC<RealisticNPCs3DProps> = ({
  anchors,
  hasActiveDisaster,
}) => {
  const headRef = useRef<THREE.InstancedMesh>(null);
  const torsoRef = useRef<THREE.InstancedMesh>(null);
  const leftLegRef = useRef<THREE.InstancedMesh>(null);
  const rightLegRef = useRef<THREE.InstancedMesh>(null);
  const leftArmRef = useRef<THREE.InstancedMesh>(null);
  const rightArmRef = useRef<THREE.InstancedMesh>(null);

  // Reusable scratch Object3D to avoid per-frame allocations
  const dummy = useMemo(() => {
    const obj = new THREE.Object3D();
    obj.rotation.order = "YXZ";
    return obj;
  }, []);

  // Shared geometries & materials with explicit disposal on unmount
  const resources = useMemo(() => {
    const headGeo = new THREE.SphereGeometry(0.72, 10, 8);
    const torsoGeo = new THREE.BoxGeometry(1.55, 2.15, 0.92);
    const legGeo = new THREE.BoxGeometry(0.56, 2.35, 0.62);
    const armGeo = new THREE.BoxGeometry(0.44, 1.95, 0.48);

    const headMat = new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.02 });
    const torsoMat = new THREE.MeshStandardMaterial({ roughness: 0.82, metalness: 0.04 });
    const legMat = new THREE.MeshStandardMaterial({ roughness: 0.88, metalness: 0.02 });
    const armMat = new THREE.MeshStandardMaterial({ roughness: 0.82, metalness: 0.04 });

    return { headGeo, torsoGeo, legGeo, armGeo, headMat, torsoMat, legMat, armMat };
  }, []);

  useEffect(() => {
    return () => {
      resources.headGeo.dispose();
      resources.torsoGeo.dispose();
      resources.legGeo.dispose();
      resources.armGeo.dispose();
      resources.headMat.dispose();
      resources.torsoMat.dispose();
      resources.legMat.dispose();
      resources.armMat.dispose();
    };
  }, [resources]);

  // Deterministically distribute 220 NPCs across all provided country anchors
  const agents = useMemo<NPCAgent[]>(() => {
    const anchorList = Object.values(anchors);
    if (anchorList.length === 0) return [];

    return Array.from({ length: NPC_COUNT }, (_, i) => {
      const a = anchorList[i % anchorList.length];
      const r1 = seededRand(i * 11 + 3);
      const r2 = seededRand(i * 17 + 7);
      const r3 = seededRand(i * 23 + 13);
      const r4 = seededRand(i * 29 + 19);

      // ~30% walk along each city's Central Park path loop, ~70% along boulevard sidewalks
      const isPark = i % 10 < 3;
      const sideSign = i % 4 < 2 ? 1 : -1;
      const sideLane = sideSign * (20.5 + (i % 3) * 1.4);

      return {
        kind: isPark ? "park" : "sidewalk",
        ax: a.x,
        az: a.z,
        axis: i % 2 === 0 ? "x" : "z",
        side: sideLane,
        offset: (r1 * 2 - 1) * 440,
        spanHalf: 460,
        dir: r2 > 0.5 ? 1 : -1,
        parkCenterX: a.x + 215,
        parkCenterZ: a.z + 215,
        parkRadiusX: 72 + r1 * 48,
        parkRadiusZ: 62 + r2 * 44,
        parkAngle: r3 * Math.PI * 2,
        parkDir: r4 > 0.5 ? 1 : -1,
        baseSpeed: 10.5 + r3 * 4.5,
        stridePhase: r4 * Math.PI * 2,
        scale: 0.92 + (i % 5) * 0.045,
        crosswalkCycleOffset: r2 * 8.0,
        skinColor: new THREE.Color(SKIN_TONES[i % SKIN_TONES.length]),
        shirtColor: new THREE.Color(SHIRT_COLORS[(i * 3) % SHIRT_COLORS.length]),
        pantsColor: new THREE.Color(PANTS_COLORS[(i * 5) % PANTS_COLORS.length]),
      };
    });
  }, [anchors]);

  // Persistent per-agent mutable simulation state (position progress & crosswalk pause timer)
  const simStateRef = useRef<{
    progress: Float32Array;
    pauseTimer: Float32Array;
    lastStopIdx: Int8Array;
    stride: Float32Array;
  } | null>(null);

  useEffect(() => {
    const progress = new Float32Array(agents.length);
    const pauseTimer = new Float32Array(agents.length);
    const lastStopIdx = new Int8Array(agents.length);
    const stride = new Float32Array(agents.length);
    for (let i = 0; i < agents.length; i++) {
      progress[i] = agents[i].kind === "park" ? agents[i].parkAngle : agents[i].offset;
      pauseTimer[i] = 0;
      lastStopIdx[i] = -1;
      stride[i] = agents[i].stridePhase;
    }
    simStateRef.current = { progress, pauseTimer, lastStopIdx, stride };
  }, [agents]);

  // Apply per-instance natural skin tones, realistic jackets/shirts, and trousers
  useEffect(() => {
    if (
      !headRef.current ||
      !torsoRef.current ||
      !leftLegRef.current ||
      !rightLegRef.current ||
      !leftArmRef.current ||
      !rightArmRef.current
    ) {
      return;
    }

    for (let i = 0; i < agents.length; i++) {
      const ag = agents[i];
      headRef.current.setColorAt(i, ag.skinColor);
      torsoRef.current.setColorAt(i, ag.shirtColor);
      leftArmRef.current.setColorAt(i, ag.shirtColor);
      rightArmRef.current.setColorAt(i, ag.shirtColor);
      leftLegRef.current.setColorAt(i, ag.pantsColor);
      rightLegRef.current.setColorAt(i, ag.pantsColor);
    }

    const meshes = [
      headRef.current,
      torsoRef.current,
      leftLegRef.current,
      rightLegRef.current,
      leftArmRef.current,
      rightArmRef.current,
    ];
    for (const m of meshes) {
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    }
  }, [agents]);

  useFrame((_, rawDelta) => {
    const sim = simStateRef.current;
    if (
      !sim ||
      agents.length === 0 ||
      !headRef.current ||
      !torsoRef.current ||
      !leftLegRef.current ||
      !rightLegRef.current ||
      !leftArmRef.current ||
      !rightArmRef.current
    ) {
      return;
    }

    const dt = Math.min(rawDelta, 0.05);
    const evacBoost = hasActiveDisaster ? 2.15 : 1.0;

    for (let i = 0; i < agents.length; i++) {
      const ag = agents[i];
      const s = ag.scale;

      let px = 0;
      let pz = 0;
      let yaw = 0;
      let isMoving = true;

      if (ag.kind === "sidewalk") {
        let pos = sim.progress[i];

        // In normal conditions, pause briefly when reaching a zebra crosswalk
        if (!hasActiveDisaster && sim.pauseTimer[i] > 0) {
          sim.pauseTimer[i] = Math.max(0, sim.pauseTimer[i] - dt);
          isMoving = false;
        } else {
          if (hasActiveDisaster) {
            sim.pauseTimer[i] = 0;
          }
          const step = ag.baseSpeed * evacBoost * dt * ag.dir;
          const prevPos = pos;
          pos += step;

          // Wrap cleanly along the boulevard span
          if (pos > ag.spanHalf) {
            pos = -ag.spanHalf;
            sim.lastStopIdx[i] = -1;
          } else if (pos < -ag.spanHalf) {
            pos = ag.spanHalf;
            sim.lastStopIdx[i] = -1;
          } else if (!hasActiveDisaster) {
            // Check if crossing a zebra crosswalk stop line
            for (let cIdx = 0; cIdx < CROSSWALK_STOPS.length; cIdx++) {
              if (sim.lastStopIdx[i] === cIdx) continue;
              const stop = CROSSWALK_STOPS[cIdx];
              const crossed =
                (ag.dir === 1 && prevPos < stop && pos >= stop) ||
                (ag.dir === -1 && prevPos > stop && pos <= stop);
              if (crossed) {
                pos = stop;
                sim.lastStopIdx[i] = cIdx;
                // Brief realistic crosswalk pause (1.1s to 2.2s)
                sim.pauseTimer[i] = 1.1 + ((i * 37 + cIdx * 13) % 11) * 0.1;
                isMoving = false;
                break;
              }
            }
          }
          sim.progress[i] = pos;
        }

        if (ag.axis === "x") {
          px = ag.ax + pos;
          pz = ag.az + ag.side;
          yaw = ag.dir === 1 ? Math.PI / 2 : -Math.PI / 2;
        } else {
          px = ag.ax + ag.side;
          pz = ag.az + pos;
          yaw = ag.dir === 1 ? 0 : Math.PI;
        }
      } else {
        // Walking / jogging around the Central Park winding path loop
        const avgRadius = 0.5 * (ag.parkRadiusX + ag.parkRadiusZ);
        const angularSpeed = (ag.baseSpeed * evacBoost) / Math.max(20, avgRadius);
        const angle = (sim.progress[i] + angularSpeed * dt * ag.parkDir) % (Math.PI * 2);
        sim.progress[i] = angle;

        px = ag.parkCenterX + Math.cos(angle) * ag.parkRadiusX;
        pz = ag.parkCenterZ + Math.sin(angle) * ag.parkRadiusZ;

        // Exact tangent velocity vector for facing direction
        const vx = -Math.sin(angle) * ag.parkRadiusX * ag.parkDir;
        const vz = Math.cos(angle) * ag.parkRadiusZ * ag.parkDir;
        yaw = Math.atan2(vx, vz);
      }

      // Advance stride cycle when moving; ease limbs to neutral standing pose when paused
      let legSwing = 0;
      let armSwing = 0;
      let bob = 0;
      const torsoPitch = !isMoving ? 0 : hasActiveDisaster ? 0.17 : 0.04;

      if (isMoving) {
        const cadence = hasActiveDisaster ? 13.5 : 7.6;
        sim.stride[i] += dt * cadence * (ag.baseSpeed / 12);
        const phase = sim.stride[i];
        const maxSwing = hasActiveDisaster ? 0.72 : 0.44;
        legSwing = Math.sin(phase) * maxSwing;
        armSwing = -legSwing * (hasActiveDisaster ? 0.95 : 0.78);
        bob = Math.abs(Math.sin(phase)) * (hasActiveDisaster ? 0.48 : 0.22) * s;
      }

      const cosY = Math.cos(yaw);
      const sinY = Math.sin(yaw);

      // Vertical landmark heights (feet sit cleanly on y = 0.72 sidewalk surface)
      const groundY = 0.72;
      const legLen = 2.35 * s;
      const torsoH = 2.15 * s;
      const armLen = 1.95 * s;

      const hipY = groundY + legLen + bob;
      const torsoCenterY = hipY + torsoH * 0.5;
      const shoulderY = hipY + torsoH * 0.88;
      const headCenterY = hipY + torsoH + 0.76 * s;

      // 1. Head
      const headForward = Math.sin(torsoPitch) * 0.45 * s;
      dummy.position.set(px + headForward * sinY, headCenterY, pz + headForward * cosY);
      dummy.rotation.set(torsoPitch * 0.5, yaw, 0);
      dummy.scale.set(s, s, s);
      dummy.updateMatrix();
      headRef.current.setMatrixAt(i, dummy.matrix);

      // 2. Torso
      dummy.position.set(px, torsoCenterY, pz);
      dummy.rotation.set(torsoPitch, yaw, 0);
      dummy.scale.set(s, s, s);
      dummy.updateMatrix();
      torsoRef.current.setMatrixAt(i, dummy.matrix);

      // 3. Left Leg (pivoted at hip joint)
      const hipOffset = 0.42 * s;
      const halfLeg = legLen * 0.5;
      {
        const localX = hipOffset;
        const dy = -halfLeg * Math.cos(legSwing);
        const dz = -halfLeg * Math.sin(legSwing);
        dummy.position.set(
          px + localX * cosY + dz * sinY,
          hipY + dy,
          pz - localX * sinY + dz * cosY
        );
        dummy.rotation.set(legSwing, yaw, 0);
        dummy.scale.set(s, s, s);
        dummy.updateMatrix();
        leftLegRef.current.setMatrixAt(i, dummy.matrix);
      }

      // 4. Right Leg (opposite phase, pivoted at hip joint)
      {
        const localX = -hipOffset;
        const rSwing = -legSwing;
        const dy = -halfLeg * Math.cos(rSwing);
        const dz = -halfLeg * Math.sin(rSwing);
        dummy.position.set(
          px + localX * cosY + dz * sinY,
          hipY + dy,
          pz - localX * sinY + dz * cosY
        );
        dummy.rotation.set(rSwing, yaw, 0);
        dummy.scale.set(s, s, s);
        dummy.updateMatrix();
        rightLegRef.current.setMatrixAt(i, dummy.matrix);
      }

      // 5. Left Arm (pivoted at shoulder joint)
      const shoulderOffset = 1.04 * s;
      const halfArm = armLen * 0.5;
      {
        const localX = shoulderOffset;
        const dy = -halfArm * Math.cos(armSwing);
        const dz = -halfArm * Math.sin(armSwing);
        dummy.position.set(
          px + localX * cosY + dz * sinY,
          shoulderY + dy,
          pz - localX * sinY + dz * cosY
        );
        dummy.rotation.set(armSwing, yaw, 0);
        dummy.scale.set(s, s, s);
        dummy.updateMatrix();
        leftArmRef.current.setMatrixAt(i, dummy.matrix);
      }

      // 6. Right Arm (opposite phase, pivoted at shoulder joint)
      {
        const localX = -shoulderOffset;
        const rArmSwing = -armSwing;
        const dy = -halfArm * Math.cos(rArmSwing);
        const dz = -halfArm * Math.sin(rArmSwing);
        dummy.position.set(
          px + localX * cosY + dz * sinY,
          shoulderY + dy,
          pz - localX * sinY + dz * cosY
        );
        dummy.rotation.set(rArmSwing, yaw, 0);
        dummy.scale.set(s, s, s);
        dummy.updateMatrix();
        rightArmRef.current.setMatrixAt(i, dummy.matrix);
      }
    }

    headRef.current.instanceMatrix.needsUpdate = true;
    torsoRef.current.instanceMatrix.needsUpdate = true;
    leftLegRef.current.instanceMatrix.needsUpdate = true;
    rightLegRef.current.instanceMatrix.needsUpdate = true;
    leftArmRef.current.instanceMatrix.needsUpdate = true;
    rightArmRef.current.instanceMatrix.needsUpdate = true;
  });

  if (agents.length === 0) return null;

  return (
    <group name="realistic-npcs-3d">
      <instancedMesh
        ref={headRef}
        args={[resources.headGeo, resources.headMat, agents.length]}
        castShadow
        frustumCulled={false}
      />
      <instancedMesh
        ref={torsoRef}
        args={[resources.torsoGeo, resources.torsoMat, agents.length]}
        castShadow
        frustumCulled={false}
      />
      <instancedMesh
        ref={leftLegRef}
        args={[resources.legGeo, resources.legMat, agents.length]}
        castShadow
        frustumCulled={false}
      />
      <instancedMesh
        ref={rightLegRef}
        args={[resources.legGeo, resources.legMat, agents.length]}
        castShadow
        frustumCulled={false}
      />
      <instancedMesh
        ref={leftArmRef}
        args={[resources.armGeo, resources.armMat, agents.length]}
        castShadow
        frustumCulled={false}
      />
      <instancedMesh
        ref={rightArmRef}
        args={[resources.armGeo, resources.armMat, agents.length]}
        castShadow
        frustumCulled={false}
      />
    </group>
  );
};
