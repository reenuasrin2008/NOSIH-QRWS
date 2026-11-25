import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { DisasterEvent, SimulatedSurvivor } from "../types/simulation";
import { useSimStore } from "../state/simulationStore";

interface DisasterVisualsProps {
  disasters: DisasterEvent[];
  survivors: SimulatedSurvivor[];
  windDirectionDeg: number;
}

const MAX_SURVIVORS = 120;
const MAX_DEBRIS = 160;
const MAX_EMBERS = 180;

const FLOOD_VERT = `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const FLOOD_FRAG = `
uniform float uTime;
uniform float uSeverity;
varying vec2 vUv;
void main() {
  vec2 c = vUv - 0.5;
  float dist = length(c) * 2.0;
  float wave = sin(dist * 18.0 - uTime * 3.2) * 0.5 + 0.5;
  float shimmer = sin((vUv.x + vUv.y) * 24.0 + uTime * 2.1) * 0.15;
  vec3 deep = vec3(0.06, 0.24, 0.58);
  vec3 foam = vec3(0.38, 0.72, 0.98);
  vec3 col = mix(deep, foam, wave * 0.32 + shimmer + smoothstep(0.82, 1.0, dist) * 0.45);
  float alpha = (0.42 + uSeverity * 0.25) * (1.0 - smoothstep(0.94, 1.0, dist));
  gl_FragColor = vec4(col, alpha);
}
`;

const FIRE_FRAG = `
uniform float uTime;
uniform float uSeverity;
varying vec2 vUv;
void main() {
  vec2 c = vUv - 0.5;
  float dist = length(c) * 2.0;
  float flicker = sin(dist * 14.0 - uTime * 6.5) * 0.2 + sin(vUv.x * 20.0 + uTime * 4.0) * 0.12;
  vec3 core = vec3(1.0, 0.78, 0.22);
  vec3 edge = vec3(0.92, 0.24, 0.04);
  vec3 col = mix(core, edge, clamp(dist + flicker, 0.0, 1.0));
  float alpha = (0.55 + uSeverity * 0.3) * (1.0 - smoothstep(0.75, 1.0, dist));
  gl_FragColor = vec4(col * 1.4, alpha);
}
`;

export const DisasterVisuals: React.FC<DisasterVisualsProps> = ({
  disasters,
  survivors,
  windDirectionDeg,
}) => {
  const showHazards = useSimStore((s) => s.showHazards);
  const showSurvivors = useSimStore((s) => s.showSurvivors);
  const enableFire = useSimStore((s) => s.enableFire);
  const enableFlood = useSimStore((s) => s.enableFlood);

  const survivorMeshRef = useRef<THREE.InstancedMesh>(null);
  const debrisMeshRef = useRef<THREE.InstancedMesh>(null);
  const emberMeshRef = useRef<THREE.InstancedMesh>(null);
  const vortexGroupRef = useRef<THREE.Group>(null);
  const lightningRef = useRef<THREE.PointLight>(null);

  const dummy = useMemo(() => new THREE.Object3D(), []);
  const tmpColor = useMemo(() => new THREE.Color(), []);

  const floodMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: FLOOD_VERT,
        fragmentShader: FLOOD_FRAG,
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        uniforms: { uTime: { value: 0 }, uSeverity: { value: 0.8 } },
      }),
    []
  );

  const fireMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: FLOOD_VERT,
        fragmentShader: FIRE_FRAG,
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        uniforms: { uTime: { value: 0 }, uSeverity: { value: 0.85 } },
      }),
    []
  );

  const activeDisasters = useMemo(
    () =>
      disasters.filter(
        (d) =>
          d.status !== "RESOLVED" &&
          d.status !== "CREATED" &&
          d.status !== "SCHEDULED"
      ),
    [disasters]
  );

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    floodMat.uniforms.uTime.value = t;
    fireMat.uniforms.uTime.value = t;

    // 1. Instanced Simulated Survivor Beacons
    const sm = survivorMeshRef.current;
    if (sm) {
      const count = showSurvivors ? Math.min(survivors.length, MAX_SURVIVORS) : 0;
      sm.count = count;
      for (let i = 0; i < count; i++) {
        const s = survivors[i];
        const pulse = 1.0 + Math.sin(t * 4.5 + i) * 0.22;
        dummy.position.set(s.position[0], Math.max(4, s.position[1] + 5.5 + Math.sin(t * 2.5 + i) * 1.4), s.position[2]);
        dummy.rotation.set(0, t * 1.8 + i, 0);
        dummy.scale.set(4.5 * pulse, 7.5 * pulse, 4.5 * pulse);
        dummy.updateMatrix();
        sm.setMatrixAt(i, dummy.matrix);

        if (s.status === "EVACUATED" || s.status === "MEDICAL_ASSISTANCE") {
          tmpColor.set("#10b981");
        } else if (s.priority === "critical") {
          tmpColor.set("#ef4444");
        } else if (s.priority === "high") {
          tmpColor.set("#f59e0b");
        } else {
          tmpColor.set("#38bdf8");
        }
        sm.setColorAt(i, tmpColor);
      }
      sm.instanceMatrix.needsUpdate = true;
      if (sm.instanceColor) sm.instanceColor.needsUpdate = true;
    }

    // 2. Instanced Debris / Floating Debris / Landslide Boulders
    const dm = debrisMeshRef.current;
    if (dm) {
      let idx = 0;
      const debrisDisasters = showHazards
        ? activeDisasters.filter(
            (d) =>
              d.type === "building_collapse" ||
              d.type === "landslide" ||
              d.type === "earthquake" ||
              (d.type === "flood" && enableFlood)
          )
        : [];
      for (const d of debrisDisasters) {
        const perEvent = Math.min(24, Math.floor(MAX_DEBRIS / Math.max(1, debrisDisasters.length)));
        for (let j = 0; j < perEvent && idx < MAX_DEBRIS; j++) {
          const angle = (j / perEvent) * Math.PI * 2 + (d.seed % 17);
          const dist = (((j * 37) % 100) / 100) * d.affected_radius * 0.82;
          const x = d.epicentre.x + Math.cos(angle + (d.type === "flood" ? t * 0.1 : 0)) * dist;
          const z = d.epicentre.z + Math.sin(angle + (d.type === "flood" ? t * 0.1 : 0)) * dist;
          const y = d.type === "flood" ? Math.max(1.2, d.water_level_m + Math.sin(t * 2.4 + j) * 0.4) : 3.2;
          const sz = d.type === "landslide" ? 7.5 : d.type === "building_collapse" ? 9.0 : 5.5;
          dummy.position.set(x, y, z);
          dummy.rotation.set(j * 0.7, j * 1.1, j * 0.4);
          dummy.scale.set(sz, sz * 0.65, sz * 0.85);
          dummy.updateMatrix();
          dm.setMatrixAt(idx, dummy.matrix);
          tmpColor.set(d.type === "flood" ? "#64748b" : d.type === "landslide" ? "#78553a" : "#52525b");
          dm.setColorAt(idx, tmpColor);
          idx++;
        }
      }
      dm.count = idx;
      dm.instanceMatrix.needsUpdate = true;
      if (dm.instanceColor) dm.instanceColor.needsUpdate = true;
    }

    // 3. Instanced Fire Embers, Smoke & Earthquake Dust
    const em = emberMeshRef.current;
    if (em) {
      let idx = 0;
      const windRad = (windDirectionDeg * Math.PI) / 180;
      const plumeDisasters = showHazards
        ? activeDisasters.filter((d) => (d.type === "fire" && enableFire) || d.type === "earthquake" || d.type === "building_collapse")
        : [];
      for (const d of plumeDisasters) {
        const perEv = Math.min(45, Math.floor(MAX_EMBERS / Math.max(1, plumeDisasters.length)));
        for (let j = 0; j < perEv && idx < MAX_EMBERS; j++) {
          const cycle = (t * (0.45 + (j % 5) * 0.08) + j * 0.13) % 1.0;
          const baseAng = j * 2.399;
          const baseR = (((j * 29) % 100) / 100) * d.affected_radius * 0.65;
          const drift = cycle * 85 * d.severity;
          const x = d.epicentre.x + Math.cos(baseAng) * baseR + Math.cos(windRad) * drift;
          const z = d.epicentre.z + Math.sin(baseAng) * baseR + Math.sin(windRad) * drift;
          const y = 6 + cycle * (d.type === "fire" ? 115 * d.severity : 58 * d.severity);
          const sc = (1 - cycle) * 7.5 + 2.5;
          dummy.position.set(x, y, z);
          dummy.rotation.set(0, 0, 0);
          dummy.scale.set(sc, sc, sc);
          dummy.updateMatrix();
          em.setMatrixAt(idx, dummy.matrix);
          if (d.type === "fire") {
            tmpColor.set(cycle < 0.38 ? "#ff6b1a" : "#3f3f46");
          } else {
            tmpColor.set("#a8a29e");
          }
          em.setColorAt(idx, tmpColor);
          idx++;
        }
      }
      em.count = idx;
      em.instanceMatrix.needsUpdate = true;
      if (em.instanceColor) em.instanceColor.needsUpdate = true;
    }

    // 4. Cyclone Vortex Spin & Periodic Lightning
    if (vortexGroupRef.current) {
      vortexGroupRef.current.rotation.y = t * 1.25;
    }
    if (lightningRef.current) {
      const hasCyclone = activeDisasters.some((d) => d.type === "cyclone");
      lightningRef.current.intensity = hasCyclone && Math.sin(t * 7.3) > 0.965 ? 8.5 : 0.0;
    }
  });

  if (!showHazards && !showSurvivors) return null;

  return (
    <group>
      <instancedMesh ref={survivorMeshRef} args={[undefined, undefined, MAX_SURVIVORS]} frustumCulled={false}>
        <octahedronGeometry args={[1, 0]} />
        <meshStandardMaterial emissive="#ffffff" emissiveIntensity={0.65} roughness={0.25} />
      </instancedMesh>

      <instancedMesh ref={debrisMeshRef} args={[undefined, undefined, MAX_DEBRIS]} frustumCulled={false}>
        <dodecahedronGeometry args={[1, 0]} />
        <meshStandardMaterial roughness={0.92} metalness={0.05} />
      </instancedMesh>

      <instancedMesh ref={emberMeshRef} args={[undefined, undefined, MAX_EMBERS]} frustumCulled={false}>
        <sphereGeometry args={[1, 6, 6]} />
        <meshStandardMaterial emissive="#ff5500" emissiveIntensity={0.85} transparent opacity={0.76} />
      </instancedMesh>

      <pointLight ref={lightningRef} position={[2000, 460, 2000]} color="#bae6fd" distance={4500} intensity={0} />

      {showHazards &&
        activeDisasters.map((d) => {
          const { x, z } = d.epicentre;
          if (d.type === "flood" && enableFlood) {
            const waterH = Math.max(1.5, d.water_level_m * 1.5);
            return (
              <group key={d.event_id} position={[x, waterH, z]}>
                <mesh rotation={[-Math.PI / 2, 0, 0]} material={floodMat}>
                  <circleGeometry args={[d.affected_radius, 48]} />
                </mesh>
              </group>
            );
          }

          if (d.type === "earthquake") {
            return (
              <group key={d.event_id} position={[x, 2.4, z]}>
                <mesh rotation={[-Math.PI / 2, 0, 0]}>
                  <ringGeometry args={[d.affected_radius * 0.88, d.affected_radius, 48]} />
                  <meshBasicMaterial color="#f59e0b" transparent opacity={0.72} side={THREE.DoubleSide} />
                </mesh>
                <mesh rotation={[-Math.PI / 2, 0, 0]}>
                  <ringGeometry args={[d.affected_radius * 0.42, d.affected_radius * 0.48, 36]} />
                  <meshBasicMaterial color="#ef4444" transparent opacity={0.6} side={THREE.DoubleSide} />
                </mesh>
              </group>
            );
          }

          if (d.type === "fire" && enableFire) {
            return (
              <group key={d.event_id} position={[x, 3.2, z]}>
                <mesh rotation={[-Math.PI / 2, 0, 0]} material={fireMat}>
                  <circleGeometry args={[d.affected_radius, 40]} />
                </mesh>
                <pointLight position={[0, 48, 0]} color="#ff6b1a" intensity={2.4 * d.severity} distance={d.affected_radius * 2.2} />
              </group>
            );
          }

          if (d.type === "cyclone") {
            return (
              <group key={d.event_id} ref={vortexGroupRef} position={[x, 180, z]}>
                {[0, 1, 2].map((ring) => (
                  <mesh key={ring} position={[0, ring * 55, 0]} rotation={[Math.PI / 2, 0, 0]}>
                    <torusGeometry args={[120 + ring * 75, 10, 10, 40]} />
                    <meshStandardMaterial color="#94a3b8" transparent opacity={0.3 - ring * 0.05} />
                  </mesh>
                ))}
              </group>
            );
          }

          return (
            <group key={d.event_id} position={[x, 2.5, z]}>
              <mesh rotation={[-Math.PI / 2, 0, 0]}>
                <ringGeometry args={[d.affected_radius * 0.88, d.affected_radius, 36]} />
                <meshBasicMaterial color="#d97706" transparent opacity={0.65} side={THREE.DoubleSide} />
              </mesh>
            </group>
          );
        })}
    </group>
  );
};
