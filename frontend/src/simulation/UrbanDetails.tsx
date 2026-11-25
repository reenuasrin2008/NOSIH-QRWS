import React, { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { CityEnvironment } from "../types/simulation";

/**
 * GTA 5 / Los Santos inspired GPU-instanced urban polish:
 * - Glowing neon rooftop billboards & avenue signs
 * - Tropical palm trees along the riverfront & coastal boulevards
 * - Bright yellow construction tower cranes with slowly rotating jibs
 * - Colorful shipping containers & bobbing harbor boats along the river
 */
export const UrbanDetails: React.FC<{ city: CityEnvironment; dayMode: boolean }> = ({ city, dayMode }) => {
  const billboardRef = useRef<THREE.InstancedMesh>(null);
  const palmTrunkRef = useRef<THREE.InstancedMesh>(null);
  const palmCrownRef = useRef<THREE.InstancedMesh>(null);
  const containerRef = useRef<THREE.InstancedMesh>(null);
  const boatRef = useRef<THREE.InstancedMesh>(null);
  const craneJibRefs = useRef<Array<THREE.Mesh | null>>([]);

  const W = city.world_size || 4000;
  const riverZ = city.river_z || 2000;
  const riverW = city.river_width || 120;

  const { billboards, palms, containers, boats, cranes } = useMemo(() => {
    // 1. Rooftop neon billboards on tall commercial towers
    const bbs = city.buildings
      .filter((b) => b.kind === "commercial" && b.height > 65)
      .slice(0, 75)
      .map((b, i) => ({
        x: b.x,
        y: b.height + 8,
        z: b.z + b.depth * 0.42,
        w: Math.min(28, b.width * 0.72),
        h: 10,
        rotY: (i % 4) * (Math.PI / 2),
        color: ["#38bdf8", "#f43f5e", "#fbbf24", "#34d399", "#a855f7", "#fb923c"][i % 6],
      }));

    // 2. Coastal / Riverfront Palm Trees (Los Santos boulevard vibe)
    const pms: Array<{ x: number; z: number; h: number; lean: number }> = [];
    for (let i = 0; i < 110; i++) {
      const side = i % 2 === 0 ? -1 : 1;
      const x = 160 + ((i * 71) % (W - 320));
      const z = riverZ + side * (riverW * 0.62 + 14 + (i % 5) * 7);
      pms.push({ x, z, h: 16 + (i % 7) * 2.2, lean: ((i % 5) - 2) * 0.06 });
    }

    // 3. Colorful Harbor Shipping Containers near eastern/western river docks
    const cnts: Array<{ x: number; y: number; z: number; color: string; rotY: number }> = [];
    const cColors = ["#dc2626", "#2563eb", "#eab308", "#0d9488", "#ea580c", "#e2e8f0"];
    for (let i = 0; i < 64; i++) {
      const clusterX = i < 32 ? 420 + (i % 8) * 26 : W - 520 + (i % 8) * 26;
      const row = Math.floor((i % 32) / 8);
      const stack = i % 3 === 0 ? 1 : 0;
      cnts.push({
        x: clusterX,
        y: 3.5 + stack * 7.2,
        z: riverZ - riverW * 0.75 - 24 - row * 14,
        color: cColors[i % cColors.length],
        rotY: (i % 2) * 0.04,
      });
    }

    // 4. Colorful Harbor Boats & Yachts cruising the river
    const bts = Array.from({ length: 14 }, (_, i) => ({
      x: 240 + i * ((W - 480) / 14),
      z: riverZ + ((i % 3) - 1) * (riverW * 0.22),
      dir: i % 2 === 0 ? 1 : -1,
      speed: 7 + (i % 4) * 3.5,
      color: ["#f8fafc", "#ef4444", "#0284c7", "#f59e0b", "#10b981"][i % 5],
    }));

    // 5. Skyline Construction Cranes (yellow/orange like GTA 5 downtown)
    const crns = city.buildings
      .filter((b) => b.height > 85)
      .slice(0, 5)
      .map((b, i) => ({
        x: b.x + b.width * 0.7,
        z: b.z + b.depth * 0.7,
        h: b.height + 42 + i * 8,
      }));

    return { billboards: bbs, palms: pms, containers: cnts, boats: bts, cranes: crns };
  }, [city.buildings, W, riverZ, riverW]);

  useEffect(() => {
    const dummy = new THREE.Object3D();
    const col = new THREE.Color();

    if (billboardRef.current) {
      billboards.forEach((b, i) => {
        dummy.position.set(b.x, b.y, b.z);
        dummy.rotation.set(0, b.rotY, 0);
        dummy.scale.set(b.w, b.h, 1.4);
        dummy.updateMatrix();
        billboardRef.current!.setMatrixAt(i, dummy.matrix);
        col.set(b.color);
        billboardRef.current!.setColorAt(i, col);
      });
      billboardRef.current.instanceMatrix.needsUpdate = true;
      if (billboardRef.current.instanceColor) billboardRef.current.instanceColor.needsUpdate = true;
    }

    if (palmTrunkRef.current && palmCrownRef.current) {
      palms.forEach((p, i) => {
        dummy.position.set(p.x, p.h / 2, p.z);
        dummy.rotation.set(p.lean, i * 0.7, p.lean * 0.5);
        dummy.scale.set(1.1, p.h, 1.1);
        dummy.updateMatrix();
        palmTrunkRef.current!.setMatrixAt(i, dummy.matrix);

        dummy.position.set(p.x + p.lean * p.h * 0.35, p.h + 1.5, p.z);
        dummy.rotation.set(0, i * 1.1, 0);
        dummy.scale.set(7.5, 3.2, 7.5);
        dummy.updateMatrix();
        palmCrownRef.current!.setMatrixAt(i, dummy.matrix);
      });
      palmTrunkRef.current.instanceMatrix.needsUpdate = true;
      palmCrownRef.current.instanceMatrix.needsUpdate = true;
    }

    if (containerRef.current) {
      containers.forEach((c, i) => {
        dummy.position.set(c.x, c.y, c.z);
        dummy.rotation.set(0, c.rotY, 0);
        dummy.scale.set(20, 6.8, 8.2);
        dummy.updateMatrix();
        containerRef.current!.setMatrixAt(i, dummy.matrix);
        col.set(c.color);
        containerRef.current!.setColorAt(i, col);
      });
      containerRef.current.instanceMatrix.needsUpdate = true;
      if (containerRef.current.instanceColor) containerRef.current.instanceColor.needsUpdate = true;
    }
  }, [billboards, palms, containers]);

  const boatDummy = useMemo(() => new THREE.Object3D(), []);
  const boatCol = useMemo(() => new THREE.Color(), []);
  const boatsColored = useRef(false);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (boatRef.current) {
      boats.forEach((b, i) => {
        const span = W - 260;
        const rawX = (b.x + b.dir * b.speed * t) % span;
        const x = rawX < 130 ? rawX + span : rawX;
        const bob = Math.sin(t * 2.2 + i) * 0.45;
        boatDummy.position.set(x, 2.8 + bob, b.z);
        boatDummy.rotation.set(0, b.dir > 0 ? 0 : Math.PI, Math.sin(t * 1.8 + i) * 0.04);
        boatDummy.scale.set(22, 5.2, 8.5);
        boatDummy.updateMatrix();
        boatRef.current!.setMatrixAt(i, boatDummy.matrix);
        if (!boatsColored.current) {
          boatCol.set(b.color);
          boatRef.current!.setColorAt(i, boatCol);
        }
      });
      boatRef.current.instanceMatrix.needsUpdate = true;
      if (!boatsColored.current && boatRef.current.instanceColor) {
        boatRef.current.instanceColor.needsUpdate = true;
        boatsColored.current = true;
      }
    }

    craneJibRefs.current.forEach((jib, idx) => {
      if (jib) jib.rotation.y = Math.sin(t * 0.14 + idx * 1.7) * 0.85;
    });
  });

  return (
    <group>
      {/* Glowing Neon Rooftop Billboards */}
      {billboards.length > 0 && (
        <instancedMesh ref={billboardRef} args={[undefined, undefined, billboards.length]} frustumCulled={false}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial
            emissive="#ffffff"
            emissiveIntensity={dayMode ? 0.55 : 1.35}
            roughness={0.25}
          />
        </instancedMesh>
      )}

      {/* Coastal Palm Trees */}
      <instancedMesh ref={palmTrunkRef} args={[undefined, undefined, palms.length]} frustumCulled={false}>
        <cylinderGeometry args={[0.45, 0.75, 1, 6]} />
        <meshStandardMaterial color="#8b5e3c" roughness={0.9} />
      </instancedMesh>
      <instancedMesh ref={palmCrownRef} args={[undefined, undefined, palms.length]} frustumCulled={false}>
        <coneGeometry args={[1, 1, 7]} />
        <meshStandardMaterial color="#16a34a" roughness={0.75} />
      </instancedMesh>

      {/* Colorful Harbor Shipping Containers */}
      <instancedMesh ref={containerRef} args={[undefined, undefined, containers.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial roughness={0.65} metalness={0.25} />
      </instancedMesh>

      {/* Cruising Harbor Boats & Yachts */}
      <instancedMesh ref={boatRef} args={[undefined, undefined, boats.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial roughness={0.35} metalness={0.2} />
      </instancedMesh>

      {/* Downtown Yellow Construction Tower Cranes */}
      {cranes.map((c, idx) => (
        <group key={idx} position={[c.x, 0, c.z]}>
          <mesh position={[0, c.h / 2, 0]}>
            <boxGeometry args={[4.5, c.h, 4.5]} />
            <meshStandardMaterial color="#eab308" roughness={0.5} metalness={0.4} />
          </mesh>
          <mesh position={[0, c.h, 0]} ref={(el) => { craneJibRefs.current[idx] = el; }}>
            <boxGeometry args={[72, 3.2, 3.2]} />
            <meshStandardMaterial color="#f59e0b" roughness={0.45} metalness={0.45} />
          </mesh>
        </group>
      ))}
    </group>
  );
};
