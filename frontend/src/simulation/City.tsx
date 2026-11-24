import React, { useMemo, useRef, useEffect } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { CityEnvironment, Station } from "../types/simulation";
import { useSimStore } from "../state/simulationStore";
import {
  createAsphaltTexture,
  createBuildingFacadeTexture,
  createCommercialRoughnessMap,
  createResidentialBumpMap,
  createTerrainTexture,
} from "./textures";
import { createRealisticWaterMaterial } from "./WaterShader";

export const City: React.FC<{ city: CityEnvironment; stations: Station[]; dayMode: boolean }> = ({
  city, stations, dayMode,
}) => {
  const showRoads = useSimStore((s) => s.showRoads);
  const showBuildings = useSimStore((s) => s.showBuildings);
  const W = city.world_size || 4000;
  const halfW = W / 2;

  const commRef = useRef<THREE.InstancedMesh>(null);
  const resRef = useRef<THREE.InstancedMesh>(null);
  const indRef = useRef<THREE.InstancedMesh>(null);
  const roofRef = useRef<THREE.InstancedMesh>(null);
  const podiumRef = useRef<THREE.InstancedMesh>(null);
  const spireRef = useRef<THREE.InstancedMesh>(null);
  const tankRef = useRef<THREE.InstancedMesh>(null);
  const horizonRef = useRef<THREE.InstancedMesh>(null);
  const treeRef = useRef<THREE.InstancedMesh>(null);
  const treeTopRef = useRef<THREE.InstancedMesh>(null);
  const trunkRef = useRef<THREE.InstancedMesh>(null);
  const poleRef = useRef<THREE.InstancedMesh>(null);
  const lampRef = useRef<THREE.InstancedMesh>(null);
  const carRef = useRef<THREE.InstancedMesh>(null);
  const cabinRef = useRef<THREE.InstancedMesh>(null);
  const headlightRef = useRef<THREE.InstancedMesh>(null);
  const taillightRef = useRef<THREE.InstancedMesh>(null);
  const sirenRef = useRef<THREE.InstancedMesh>(null);
  const riverRef = useRef<THREE.Mesh>(null);
  const foamRef = useRef<THREE.Mesh>(null);
  const radarRef = useRef<THREE.Group>(null);

  const commTex = useMemo(() => createBuildingFacadeTexture("commercial", dayMode), [dayMode]);
  const commRough = useMemo(() => createCommercialRoughnessMap(), []);
  const resTex = useMemo(() => createBuildingFacadeTexture("residential", dayMode), [dayMode]);
  const resBump = useMemo(() => createResidentialBumpMap(), []);
  const roadTex = useMemo(() => createAsphaltTexture(), []);
  const groundTex = useMemo(() => createTerrainTexture(), []);
  const riverMat = useMemo(() => createRealisticWaterMaterial(dayMode, 0.55, 0.96), [dayMode]);
  const oceanMat = useMemo(() => createRealisticWaterMaterial(dayMode, 1.35, 0.98), [dayMode]);

  useEffect(() => {
    return () => {
      commTex.dispose();
      resTex.dispose();
      riverMat.dispose();
      oceanMat.dispose();
    };
  }, [commTex, resTex, riverMat, oceanMat]);

  useEffect(() => {
    return () => {
      commRough.dispose();
      resBump.dispose();
      roadTex.dispose();
      groundTex.dispose();
    };
  }, [commRough, resBump, roadTex, groundTex]);

  // Partition 1,000+ buildings into 3 GPU-instanced batches + landmarks
  const { commBlds, resBlds, indBlds, landmarks, tallBeacons } = useMemo(() => {
    const comm: typeof city.buildings = [];
    const res: typeof city.buildings = [];
    const ind: typeof city.buildings = [];
    const lm: typeof city.buildings = [];
    const beacons: [number, number, number][] = [];

    for (const b of city.buildings) {
      if (b.height > 125) beacons.push([b.x, b.height + 3, b.z]);
      if (b.kind === "hospital" || b.kind === "emergency_station" || b.has_helipad) {
        lm.push(b);
      } else if (b.kind === "commercial") {
        comm.push(b);
      } else if (b.kind === "industrial" || b.kind === "warehouse") {
        ind.push(b);
      } else {
        res.push(b);
      }
    }
    return { commBlds: comm, resBlds: res, indBlds: ind, landmarks: lm, tallBeacons: beacons };
  }, [city.buildings]);

  // Major intersection crosswalks
  const intersections = useMemo(() => {
    const pts: [number, number][] = [];
    const xs = [800, 1600, 2400, 3200];
    const zs = [800, 1600, 2400, 3200];
    for (const x of xs) for (const z of zs) pts.push([x, z]);
    return pts;
  }, []);



  // Populate instanced building batches + mechanical rooftop caps
  useEffect(() => {
    const dummy = new THREE.Object3D();
    const color = new THREE.Color();

    const fillBatch = (mesh: THREE.InstancedMesh | null, list: typeof city.buildings) => {
      if (!mesh) return;
      list.forEach((b, i) => {
        dummy.position.set(b.x, b.height / 2, b.z);
        dummy.rotation.set(0, 0, 0);
        dummy.scale.set(b.width, b.height, b.depth);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
        color.set(b.color);
        mesh.setColorAt(i, color);
      });
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    };

    fillBatch(commRef.current, commBlds);
    fillBatch(resRef.current, resBlds);
    fillBatch(indRef.current, indBlds);

    if (roofRef.current) {
      const allNonLm = [...commBlds, ...resBlds, ...indBlds];
      allNonLm.forEach((b, i) => {
        const capH = b.roof_style === "tiered" ? 10 : b.roof_style === "hvac" ? 4.5 : 1.4;
        const capScale = b.roof_style === "tiered" ? 0.62 : b.roof_style === "hvac" ? 0.42 : 0.96;
        dummy.position.set(b.x, b.height + capH / 2, b.z);
        dummy.scale.set(b.width * capScale, capH, b.depth * capScale);
        dummy.updateMatrix();
        roofRef.current!.setMatrixAt(i, dummy.matrix);
      });
      roofRef.current.instanceMatrix.needsUpdate = true;
    }

    // Ground-floor architectural granite podiums / lobbies for commercial towers
    if (podiumRef.current) {
      commBlds.forEach((b, i) => {
        const podH = Math.min(18, b.height * 0.18);
        dummy.position.set(b.x, podH / 2, b.z);
        dummy.scale.set(b.width * 1.14, podH, b.depth * 1.14);
        dummy.updateMatrix();
        podiumRef.current!.setMatrixAt(i, dummy.matrix);
      });
      podiumRef.current.instanceMatrix.needsUpdate = true;
    }

    // Tall communication spires on skyscrapers (> 115m)
    if (spireRef.current) {
      commBlds.forEach((b, i) => {
        if (b.height > 115) {
          const spH = 22 + (i % 4) * 9;
          dummy.position.set(b.x, b.height + 10 + spH / 2, b.z);
          dummy.scale.set(1.2, spH, 1.2);
        } else {
          dummy.scale.set(0, 0, 0);
        }
        dummy.updateMatrix();
        spireRef.current!.setMatrixAt(i, dummy.matrix);
      });
      spireRef.current.instanceMatrix.needsUpdate = true;
    }

    // Cylindrical rooftop water tanks on residential & apartment blocks
    if (tankRef.current) {
      resBlds.forEach((b, i) => {
        if (i % 2 === 0) {
          dummy.position.set(b.x + b.width * 0.22, b.height + 3.6, b.z - b.depth * 0.18);
          dummy.scale.set(3.2, 4.8, 3.2);
        } else {
          dummy.scale.set(0, 0, 0);
        }
        dummy.updateMatrix();
        tankRef.current!.setMatrixAt(i, dummy.matrix);
      });
      tankRef.current.instanceMatrix.needsUpdate = true;
    }
  }, [commBlds, resBlds, indBlds]);

  // Endless Horizon Perimeter Skyline Ring
  const horizonCount = 220;
  useEffect(() => {
    if (!horizonRef.current) return;
    const dummy = new THREE.Object3D();
    for (let i = 0; i < horizonCount; i++) {
      const angle = (i / horizonCount) * Math.PI * 2;
      // Leave eastern ocean vista open
      if (Math.cos(angle) > 0.55) {
        dummy.scale.set(0, 0, 0);
        dummy.updateMatrix();
        horizonRef.current.setMatrixAt(i, dummy.matrix);
        continue;
      }
      const ringDist = halfW + 460 + ((i * 73) % 900);
      const x = halfW + Math.cos(angle) * ringDist;
      const z = halfW + Math.sin(angle) * ringDist;
      const h = 35 + ((i * 47) % 130);
      const w = 70 + ((i * 31) % 90);
      dummy.position.set(x, h / 2, z);
      dummy.rotation.set(0, angle, 0);
      dummy.scale.set(w, h, w * 0.85);
      dummy.updateMatrix();
      horizonRef.current.setMatrixAt(i, dummy.matrix);
    }
    horizonRef.current.instanceMatrix.needsUpdate = true;
  }, [halfW]);

  // Multi-Tiered Lush Park Trees
  useEffect(() => {
    if (!treeRef.current || !treeTopRef.current || !trunkRef.current) return;
    const dummy = new THREE.Object3D();
    city.trees.forEach(([x, z, scale], i) => {
      dummy.position.set(x, 7.6 * scale, z);
      dummy.rotation.set(0, i, 0);
      dummy.scale.set(scale * 1.15, scale * 0.9, scale * 1.15);
      dummy.updateMatrix();
      treeRef.current!.setMatrixAt(i, dummy.matrix);

      dummy.position.set(x, 11.4 * scale, z);
      dummy.scale.set(scale * 0.82, scale * 0.78, scale * 0.82);
      dummy.updateMatrix();
      treeTopRef.current!.setMatrixAt(i, dummy.matrix);

      dummy.position.set(x, 2.8 * scale, z);
      dummy.scale.set(scale, scale, scale);
      dummy.updateMatrix();
      trunkRef.current!.setMatrixAt(i, dummy.matrix);
    });
    treeRef.current.instanceMatrix.needsUpdate = true;
    treeTopRef.current.instanceMatrix.needsUpdate = true;
    trunkRef.current.instanceMatrix.needsUpdate = true;
  }, [city.trees]);

  // Instanced Streetlights
  useEffect(() => {
    if (!poleRef.current || !lampRef.current) return;
    const dummy = new THREE.Object3D();
    city.streetlights.forEach(([x, z], i) => {
      dummy.position.set(x, 9, z);
      dummy.scale.set(1, 1, 1);
      dummy.updateMatrix();
      poleRef.current!.setMatrixAt(i, dummy.matrix);

      dummy.position.set(x, 18.2, z);
      dummy.updateMatrix();
      lampRef.current!.setMatrixAt(i, dummy.matrix);
    });
    poleRef.current.instanceMatrix.needsUpdate = true;
    lampRef.current.instanceMatrix.needsUpdate = true;
  }, [city.streetlights]);

  // Animated Ground Vehicles (Chassis + Cabin + Headlights + Taillights + Flashing Emergency Sirens)
  const vehiclePositions = useRef(city.vehicles.map((v) => ({ ...v })));
  const emergencyVehicles = useMemo(
    () => city.vehicles.map((v, idx) => ({ v, idx })).filter(({ v }) => v.kind === "ambulance" || v.kind === "fire_truck"),
    [city.vehicles]
  );

  useEffect(() => {
    vehiclePositions.current = city.vehicles.map((v) => ({ ...v }));
    if (carRef.current) {
      const color = new THREE.Color();
      city.vehicles.forEach((v, i) => {
        if (v.kind === "ambulance") color.set("#f1f5f9");
        else if (v.kind === "fire_truck") color.set("#dc2626");
        else color.set(i % 3 === 0 ? "#475569" : i % 3 === 1 ? "#334155" : "#64748b");
        carRef.current!.setColorAt(i, color);
      });
      if (carRef.current.instanceColor) carRef.current.instanceColor.needsUpdate = true;
    }
  }, [city.vehicles]);

  const dummyObj = useMemo(() => new THREE.Object3D(), []);
  const sirenColor = useMemo(() => new THREE.Color(), []);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    riverMat.uniforms.uTime.value = t;
    oceanMat.uniforms.uTime.value = t;
    if (foamRef.current) {
      foamRef.current.position.x = -24 + Math.sin(t * 1.8) * 9;
      (foamRef.current.material as THREE.MeshBasicMaterial).opacity = 0.28 + (Math.sin(t * 1.8) * 0.5 + 0.5) * 0.24;
    }
    if (radarRef.current) {
      radarRef.current.rotation.y += delta * 1.4;
    }

    if (carRef.current && vehiclePositions.current.length > 0) {
      const lim = W - 120;
      vehiclePositions.current.forEach((v, i) => {
        const dir = v.heading_rad >= 0 && v.heading_rad < Math.PI ? 1 : -1;
        if (v.axis === "x") {
          v.x += dir * v.speed_mps * delta;
          if (v.x > lim) v.x = 120;
          if (v.x < 120) v.x = lim;
        } else {
          v.z += dir * v.speed_mps * delta;
          if (v.z > lim) v.z = 120;
          if (v.z < 120) v.z = lim;
        }
        const onBridge = v.axis === "z" && Math.abs(v.z - city.river_z) < city.river_width * 0.72;
        const baseY = onBridge ? 14.2 : 2.1;
        const isTruck = v.kind === "fire_truck";

        // Chassis
        dummyObj.position.set(v.x, baseY, v.z);
        dummyObj.rotation.set(0, v.heading_rad, 0);
        dummyObj.scale.set(isTruck ? 1.7 : 1.35, isTruck ? 1.8 : 1.35, isTruck ? 2.1 : 1.45);
        dummyObj.updateMatrix();
        carRef.current!.setMatrixAt(i, dummyObj.matrix);

        // Cabin
        if (cabinRef.current) {
          dummyObj.position.set(v.x, baseY + 2.1, v.z);
          dummyObj.scale.set(isTruck ? 1.55 : 1.15, isTruck ? 1.2 : 0.95, isTruck ? 1.3 : 0.85);
          dummyObj.updateMatrix();
          cabinRef.current.setMatrixAt(i, dummyObj.matrix);
        }

        // Front Headlights & Rear Taillights
        const fx = Math.sin(v.heading_rad);
        const fz = Math.cos(v.heading_rad);
        const halfLen = isTruck ? 7.6 : 5.4;
        if (headlightRef.current) {
          dummyObj.position.set(v.x + fx * halfLen, baseY + 0.3, v.z + fz * halfLen);
          dummyObj.scale.set(isTruck ? 4.4 : 3.4, 0.75, 0.55);
          dummyObj.updateMatrix();
          headlightRef.current.setMatrixAt(i, dummyObj.matrix);
        }
        if (taillightRef.current) {
          dummyObj.position.set(v.x - fx * halfLen, baseY + 0.35, v.z - fz * halfLen);
          dummyObj.scale.set(isTruck ? 4.4 : 3.4, 0.7, 0.5);
          dummyObj.updateMatrix();
          taillightRef.current.setMatrixAt(i, dummyObj.matrix);
        }
      });

      carRef.current.instanceMatrix.needsUpdate = true;
      if (cabinRef.current) cabinRef.current.instanceMatrix.needsUpdate = true;
      if (headlightRef.current) headlightRef.current.instanceMatrix.needsUpdate = true;
      if (taillightRef.current) taillightRef.current.instanceMatrix.needsUpdate = true;

      // Flashing Red/Blue Emergency Lightbars on Ambulances & Fire Trucks
      if (sirenRef.current && emergencyVehicles.length > 0) {
        const flashPhase = Math.floor(t * 7.5) % 2;
        emergencyVehicles.forEach(({ idx }, eIdx) => {
          const v = vehiclePositions.current[idx];
          const onBridge = v.axis === "z" && Math.abs(v.z - city.river_z) < city.river_width * 0.72;
          dummyObj.position.set(v.x, (onBridge ? 14.2 : 2.1) + 3.6, v.z);
          dummyObj.rotation.set(0, v.heading_rad, 0);
          dummyObj.scale.set(3.2, 0.7, 1.1);
          dummyObj.updateMatrix();
          sirenRef.current!.setMatrixAt(eIdx, dummyObj.matrix);
          sirenColor.set((flashPhase + eIdx) % 2 === 0 ? "#ff2a2a" : "#2563eb");
          sirenRef.current!.setColorAt(eIdx, sirenColor);
        });
        sirenRef.current.instanceMatrix.needsUpdate = true;
        if (sirenRef.current.instanceColor) sirenRef.current.instanceColor.needsUpdate = true;
      }
    }
  });

  const allNonLmCount = commBlds.length + resBlds.length + indBlds.length;

  return (
    <group>
      {/* Massive Extended Urban Terrain */}
      <mesh position={[halfW, -0.6, halfW]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[W * 2.8, W * 2.8]} />
        <meshStandardMaterial map={groundTex} color={dayMode ? "#8b9288" : "#646d7a"} roughness={0.95} metalness={0.04} />
      </mesh>

      {/* Distant Endless Horizon Skyline Ring */}
      <instancedMesh ref={horizonRef} args={[undefined, undefined, horizonCount]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color={dayMode ? "#627285" : "#18202c"} roughness={0.95} />
      </instancedMesh>

      {/* Wide Adyar River Delta with Concrete Embankments */}
      <group position={[halfW, 0, city.river_z]}>
        <mesh ref={riverRef} position={[0, 0.45, 0]} rotation={[-Math.PI / 2, 0, 0]} material={riverMat}>
          <planeGeometry args={[W * 2.4, city.river_width, 64, 10]} />
        </mesh>
        <mesh position={[0, 1.8, -city.river_width / 2 - 4]} receiveShadow>
          <boxGeometry args={[W * 1.4, 3.8, 8]} />
          <meshStandardMaterial color="#4b535e" roughness={0.9} />
        </mesh>
        <mesh position={[0, 1.8, city.river_width / 2 + 4]} receiveShadow>
          <boxGeometry args={[W * 1.4, 3.8, 8]} />
          <meshStandardMaterial color="#4b535e" roughness={0.9} />
        </mesh>
      </group>

      {/* Arterial Highways, Crosswalks & River Flyover Bridges */}
      {showRoads && (
        <group>
          {city.roads.map((rd) => {
            const dx = rd.end[0] - rd.start[0];
            const dz = rd.end[1] - rd.start[1];
            const len = Math.hypot(dx, dz);
            const cx = (rd.start[0] + rd.end[0]) / 2;
            const cz = (rd.start[1] + rd.end[1]) / 2;
            const rotY = Math.atan2(dx, dz);
            return (
              <group key={rd.id}>
                <mesh position={[cx, 0.2, cz]} rotation={[0, rotY, 0]} receiveShadow>
                  <boxGeometry args={[rd.width, 0.35, len]} />
                  <meshStandardMaterial map={roadTex} color={rd.blocked ? "#6b3232" : "#ffffff"} roughness={0.86} />
                </mesh>
                {rd.is_bridge && (
                  <group position={[cx, 11.5, city.river_z]}>
                    <mesh castShadow receiveShadow>
                      <boxGeometry args={[rd.width + 4, 3.2, city.river_width + 72]} />
                      <meshStandardMaterial color={rd.blocked ? "#4a2424" : "#3a424e"} roughness={0.85} />
                    </mesh>
                    <mesh position={[-(rd.width / 2 + 1.5), 2.4, 0]}>
                      <boxGeometry args={[1.6, 2.0, city.river_width + 72]} />
                      <meshStandardMaterial color={rd.blocked ? "#dc2626" : "#64748b"} />
                    </mesh>
                    <mesh position={[rd.width / 2 + 1.5, 2.4, 0]}>
                      <boxGeometry args={[1.6, 2.0, city.river_width + 72]} />
                      <meshStandardMaterial color={rd.blocked ? "#dc2626" : "#64748b"} />
                    </mesh>
                    {[-55, 0, 55].map((pz) => (
                      <mesh key={pz} position={[0, -6.5, pz]}>
                        <boxGeometry args={[rd.width - 6, 12, 8]} />
                        <meshStandardMaterial color="#2c333d" roughness={0.9} />
                      </mesh>
                    ))}
                  </group>
                )}
              </group>
            );
          })}

          {/* Major Intersection Pedestrian Crosswalks */}
          {intersections.map(([ix, iz], idx) => (
            <group key={idx} position={[ix, 0.44, iz]}>
              <mesh position={[0, 0, -24]} rotation={[-Math.PI / 2, 0, 0]}>
                <planeGeometry args={[28, 4.5]} />
                <meshBasicMaterial color="#e2e8f0" transparent opacity={0.55} />
              </mesh>
              <mesh position={[0, 0, 24]} rotation={[-Math.PI / 2, 0, 0]}>
                <planeGeometry args={[28, 4.5]} />
                <meshBasicMaterial color="#e2e8f0" transparent opacity={0.55} />
              </mesh>
            </group>
          ))}
        </group>
      )}

      {/* GPU-Instanced 1,000+ Urban Buildings with Paired PBR Roughness/Bump Maps */}
      {showBuildings && (
        <group>
          {commBlds.length > 0 && (
            <instancedMesh ref={commRef} args={[undefined, undefined, commBlds.length]} castShadow receiveShadow>
              <boxGeometry args={[1, 1, 1]} />
              <meshStandardMaterial map={commTex} roughnessMap={commRough} roughness={1.0} metalness={0.48} />
            </instancedMesh>
          )}
          {resBlds.length > 0 && (
            <instancedMesh ref={resRef} args={[undefined, undefined, resBlds.length]} castShadow receiveShadow>
              <boxGeometry args={[1, 1, 1]} />
              <meshStandardMaterial map={resTex} bumpMap={resBump} bumpScale={0.85} roughness={0.84} metalness={0.06} />
            </instancedMesh>
          )}
          {indBlds.length > 0 && (
            <instancedMesh ref={indRef} args={[undefined, undefined, indBlds.length]} castShadow receiveShadow>
              <boxGeometry args={[1, 1, 1]} />
              <meshStandardMaterial color="#4d5560" roughness={0.88} metalness={0.14} />
            </instancedMesh>
          )}
          {allNonLmCount > 0 && (
            <instancedMesh ref={roofRef} args={[undefined, undefined, allNonLmCount]}>
              <boxGeometry args={[1, 1, 1]} />
              <meshStandardMaterial color="#252b35" roughness={0.82} />
            </instancedMesh>
          )}
          {commBlds.length > 0 && (
            <>
              <instancedMesh ref={podiumRef} args={[undefined, undefined, commBlds.length]} castShadow receiveShadow>
                <boxGeometry args={[1, 1, 1]} />
                <meshStandardMaterial color={dayMode ? "#4c5460" : "#1d232e"} roughness={0.72} metalness={0.22} />
              </instancedMesh>
              <instancedMesh ref={spireRef} args={[undefined, undefined, commBlds.length]}>
                <cylinderGeometry args={[0.35, 1.0, 1, 6]} />
                <meshStandardMaterial color="#94a3b8" metalness={0.8} roughness={0.25} />
              </instancedMesh>
            </>
          )}
          {resBlds.length > 0 && (
            <instancedMesh ref={tankRef} args={[undefined, undefined, resBlds.length]}>
              <cylinderGeometry args={[1, 1, 1, 10]} />
              <meshStandardMaterial color="#64748b" roughness={0.65} metalness={0.3} />
            </instancedMesh>
          )}

          {/* Landmark Hospitals, HQ & Helipad Towers */}
          {landmarks.map((b) => (
            <group key={b.id} position={[b.x, 0, b.z]}>
              <mesh position={[0, b.height / 2, 0]} castShadow receiveShadow>
                <boxGeometry args={[b.width, b.height, b.depth]} />
                <meshStandardMaterial map={commTex} roughnessMap={commRough} color={b.color} roughness={1.0} metalness={0.35} />
              </mesh>
              {b.kind === "hospital" && (
                <group position={[0, b.height + 0.8, 0]}>
                  <mesh rotation={[-Math.PI / 2, 0, 0]}><boxGeometry args={[28, 7, 0.4]} /><meshBasicMaterial color="#dc2626" /></mesh>
                  <mesh rotation={[-Math.PI / 2, 0, Math.PI / 2]}><boxGeometry args={[28, 7, 0.4]} /><meshBasicMaterial color="#dc2626" /></mesh>
                </group>
              )}
              {b.has_helipad && (
                <mesh position={[0, b.height + 0.7, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                  <ringGeometry args={[14, 17, 28]} />
                  <meshBasicMaterial color="#f8fafc" side={THREE.DoubleSide} />
                </mesh>
              )}
            </group>
          ))}

          {/* High-Intensity Red Aviation Obstruction Beacons (Trigger Selective Bloom) */}
          {tallBeacons.map(([bx, by, bz], idx) => (
            <mesh key={idx} position={[bx, by, bz]}>
              <sphereGeometry args={[1.9, 6, 6]} />
              <meshBasicMaterial color={[2.4, 0.25, 0.25]} toneMapped={false} />
            </mesh>
          ))}
        </group>
      )}

      {/* Eastern Marina Beachfront, Animated Surf Foam & Coastal Ocean */}
      <group position={[W + 260, 0, halfW]}>
        <mesh position={[-130, -0.35, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[240, W * 2.2]} />
          <meshStandardMaterial color={dayMode ? "#d1bc9a" : "#3a352c"} roughness={0.95} />
        </mesh>
        <mesh ref={foamRef} position={[-24, -0.1, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[26, W * 2.2]} />
          <meshBasicMaterial color="#f1f5f9" transparent opacity={0.38} />
        </mesh>
        <mesh position={[380, 0.25, 0]} rotation={[-Math.PI / 2, 0, 0]} material={oceanMat}>
          <planeGeometry args={[920, W * 2.4, 32, 64]} />
        </mesh>
      </group>



      {/* Spinning Airspace Radar Dish on Central Command HQ */}
      <group ref={radarRef} position={[2200, 52, 1750]}>
        <mesh position={[0, 3, 0]}><cylinderGeometry args={[1.2, 1.8, 6, 8]} /><meshStandardMaterial color="#475569" metalness={0.7} /></mesh>
        <mesh position={[0, 7, 0]}><boxGeometry args={[14, 3.2, 1.4]} /><meshStandardMaterial color="#e2e8f0" metalness={0.5} roughness={0.3} /></mesh>
      </group>

      {/* East Port Industrial Harbor Cranes & Shipping Containers */}
      <group position={[3580, 0, 1450]}>
        {[0, 180, 360].map((oz, idx) => (
          <group key={idx} position={[0, 0, oz]}>
            <mesh position={[0, 52, 0]} castShadow><boxGeometry args={[14, 104, 14]} /><meshStandardMaterial color="#b45309" roughness={0.65} metalness={0.35} /></mesh>
            <mesh position={[-38, 96, 0]} castShadow><boxGeometry args={[110, 9, 10]} /><meshStandardMaterial color="#c2410c" roughness={0.6} metalness={0.4} /></mesh>
            <mesh position={[45, 11, 25]} castShadow><boxGeometry args={[26, 12, 12]} /><meshStandardMaterial color="#1d4ed8" roughness={0.75} /></mesh>
            <mesh position={[45, 23, 25]} castShadow><boxGeometry args={[26, 12, 12]} /><meshStandardMaterial color="#991b1b" roughness={0.75} /></mesh>
            <mesh position={[45, 11, -20]} castShadow><boxGeometry args={[26, 12, 12]} /><meshStandardMaterial color="#15803d" roughness={0.75} /></mesh>
          </group>
        ))}
      </group>

      {/* Stations & Charging Pads */}
      {stations.map((st) => (
        <group key={st.id} position={[st.position[0], 0.6, st.position[2]]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[26, 33, 32]} />
            <meshBasicMaterial color={st.active ? (st.kind === "hospital" ? "#dc2626" : "#10b981") : "#475569"} side={THREE.DoubleSide} />
          </mesh>
        </group>
      ))}

      {/* Instanced Streetlights */}
      <instancedMesh ref={poleRef} args={[undefined, undefined, city.streetlights.length]}>
        <cylinderGeometry args={[0.45, 0.6, 18, 5]} />
        <meshStandardMaterial color="#334155" metalness={0.6} />
      </instancedMesh>
      <instancedMesh ref={lampRef} args={[undefined, undefined, city.streetlights.length]}>
        <sphereGeometry args={[1.4, 6, 6]} />
        <meshBasicMaterial color={dayMode ? "#cbd5e1" : [1.8, 1.45, 0.85]} toneMapped={dayMode} />
      </instancedMesh>

      {/* Sculpted Moving Traffic: Chassis, Tinted Cabins, Headlights, Taillights & Flashing Sirens */}
      <instancedMesh ref={carRef} args={[undefined, undefined, city.vehicles.length]} castShadow>
        <boxGeometry args={[3.8, 1.8, 7.4]} />
        <meshStandardMaterial roughness={0.32} metalness={0.55} />
      </instancedMesh>
      <instancedMesh ref={cabinRef} args={[undefined, undefined, city.vehicles.length]}>
        <boxGeometry args={[3.2, 1.4, 3.8]} />
        <meshStandardMaterial color={dayMode ? "#1e293b" : "#0f172a"} roughness={0.14} metalness={0.86} />
      </instancedMesh>
      <instancedMesh ref={headlightRef} args={[undefined, undefined, city.vehicles.length]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color={dayMode ? "#fef9c3" : [2.0, 1.9, 1.5]} toneMapped={dayMode} />
      </instancedMesh>
      <instancedMesh ref={taillightRef} args={[undefined, undefined, city.vehicles.length]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color={dayMode ? "#dc2626" : [2.2, 0.2, 0.2]} toneMapped={dayMode} />
      </instancedMesh>
      {emergencyVehicles.length > 0 && (
        <instancedMesh ref={sirenRef} args={[undefined, undefined, emergencyVehicles.length]}>
          <boxGeometry args={[1, 1, 1]} />
          <meshBasicMaterial toneMapped={false} />
        </instancedMesh>
      )}

      {/* Multi-Canopy Urban Park Trees */}
      <instancedMesh ref={treeRef} args={[undefined, undefined, city.trees.length]} castShadow>
        <dodecahedronGeometry args={[7.2, 1]} />
        <meshStandardMaterial color={dayMode ? "#2e633c" : "#193824"} roughness={0.9} />
      </instancedMesh>
      <instancedMesh ref={treeTopRef} args={[undefined, undefined, city.trees.length]}>
        <dodecahedronGeometry args={[5.8, 1]} />
        <meshStandardMaterial color={dayMode ? "#3b7a4a" : "#1f472c"} roughness={0.88} />
      </instancedMesh>
      <instancedMesh ref={trunkRef} args={[undefined, undefined, city.trees.length]}>
        <cylinderGeometry args={[1.1, 1.5, 6.8, 5]} />
        <meshStandardMaterial color="#3b2618" roughness={0.95} />
      </instancedMesh>
    </group>
  );
};
