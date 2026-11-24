import React, { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, Line, OrbitControls, Sky } from "@react-three/drei";
import * as THREE from "three";
import { globalApi } from "../shared/globalApi";
import { createBuildingFacadeTexture } from "./textures";
import { getTerrainHeight, getTerrainSlope, getWaterLevel } from "./terrainHeight";

interface UnifiedTerrainProps {
  countryId: string;
  archetype: string;
  countryName: string;
  dayMode: boolean;
}

const WORLD_SPAN = 1200;
const BOULEVARDS = [-240, -120, 0, 120, 240];
const CAR_COLORS = ["#dc2626", "#2563eb", "#facc15", "#f8fafc", "#1e293b", "#059669", "#ea580c", "#64748b"];
const PED_SHIRTS = ["#ef4444", "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#f8fafc", "#334155"];

function geoOffsetToLocal(lat: number, lon: number, centerLat: number, centerLon: number): [number, number] {
  const x = THREE.MathUtils.clamp((lon - centerLon) * 520, -420, 420);
  const z = THREE.MathUtils.clamp(-(lat - centerLat) * 520, -420, 420);
  return [x, z];
}

function createAsphaltTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#262b33";
  ctx.fillRect(0, 0, 256, 256);
  // Subtle aggregate grain
  for (let i = 0; i < 1600; i++) {
    const x = (i * 73) % 256;
    const y = (i * 137) % 256;
    ctx.fillStyle = i % 2 === 0 ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.08)";
    ctx.fillRect(x, y, 2, 2);
  }
  // Double yellow center line
  ctx.fillStyle = "#eab308";
  ctx.fillRect(123, 0, 3, 256);
  ctx.fillRect(130, 0, 3, 256);
  // Dashed white lane dividers
  ctx.fillStyle = "#e2e8f0";
  for (let y = 0; y < 256; y += 44) {
    ctx.fillRect(64, y, 3, 22);
    ctx.fillRect(189, y, 3, 22);
  }
  // Sidewalk curbs
  ctx.fillStyle = "#94a3b8";
  ctx.fillRect(0, 0, 14, 256);
  ctx.fillRect(242, 0, 14, 256);

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(1, 24);
  tex.anisotropy = 8;
  return tex;
}

/** Builds a terrain-conforming road ribbon geometry following y = getTerrainHeight(x, z) + 0.45 */
function buildTerrainRoadGeometry(
  axis: "x" | "z",
  fixedCoord: number,
  archetype: string,
  waterLevel: number,
  width = 16
): THREE.BufferGeometry {
  const segs = 72;
  const start = -360;
  const end = 360;
  const positions: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];

  for (let i = 0; i <= segs; i++) {
    const t = i / segs;
    const along = start + (end - start) * t;
    const x0 = axis === "x" ? along : fixedCoord - width / 2;
    const x1 = axis === "x" ? along : fixedCoord + width / 2;
    const z0 = axis === "z" ? along : fixedCoord - width / 2;
    const z1 = axis === "z" ? along : fixedCoord + width / 2;
    const y0 = Math.max(waterLevel + 0.8, getTerrainHeight(x0, z0, archetype)) + 0.45;
    const y1 = Math.max(waterLevel + 0.8, getTerrainHeight(x1, z1, archetype)) + 0.45;

    positions.push(x0, y0, z0, x1, y1, z1);
    uvs.push(0, t, 1, t);
    if (i < segs) {
      const a = i * 2;
      indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geo.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geo.setIndex(indices);
  geo.computeVertexNormals();
  return geo;
}

const CameraPresetRig: React.FC<{ preset: "heli" | "skyline" | "street"; archetype: string }> = ({ preset, archetype }) => {
  const { camera } = useThree();
  const desired = useMemo(() => {
    const streetY = Math.max(6, getTerrainHeight(35, 118, archetype)) + 9;
    if (preset === "street") return new THREE.Vector3(35, streetY, 155);
    if (preset === "skyline") return new THREE.Vector3(195, 115, 225);
    return new THREE.Vector3(300, 235, 345);
  }, [preset, archetype]);

  useFrame((_, delta) => {
    camera.position.lerp(desired, Math.min(1, delta * 2.4));
  });
  return null;
};

const SculptedTerrainMesh: React.FC<{ archetype: string; floodBoost: number }> = ({ archetype, floodBoost }) => {
  const waterLevel = getWaterLevel(archetype, floodBoost);
  const waterRef = useRef<THREE.Mesh>(null);

  const geometry = useMemo(() => {
    const segs = 116;
    const geo = new THREE.PlaneGeometry(WORLD_SPAN, WORLD_SPAN, segs, segs);
    geo.rotateX(-Math.PI / 2);
    const pos = geo.attributes.position;
    const colors = new Float32Array(pos.count * 3);
    const low = archetype.toLowerCase();
    const c = new THREE.Color();

    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const z = pos.getZ(i);
      const y = getTerrainHeight(x, z, archetype);
      pos.setY(i, y);

      const slope = getTerrainSlope(x, z, archetype);
      const inCityCore = Math.abs(x) < 290 && Math.abs(z) < 290 && y >= waterLevel + 1.2;
      if (y < waterLevel + 1.5) {
        c.set("#cbb892"); // Sunlit coastal sand / riverbed
      } else if (low.includes("mountain") && y > 112) {
        c.set("#edf2f7"); // Alpine snow
      } else if (slope > 0.40) {
        c.set(low.includes("arid") ? "#a66944" : "#6c727a"); // Cliff rock
      } else if (inCityCore) {
        c.set("#5c636a"); // Urban concrete & parks ground base
      } else if (low.includes("arid")) {
        c.set(y > 38 ? "#bc7e50" : "#d4af7f");
      } else if (low.includes("forest")) {
        c.set(y > 55 ? "#2e5936" : "#3f6e40");
      } else if (low.includes("agricultural")) {
        const patch = (Math.floor((x + 600) / 85) + Math.floor((z + 600) / 85)) % 3;
        c.set(patch === 0 ? "#6a8e46" : patch === 1 ? "#949348" : "#4f773d");
      } else {
        c.set(y > 28 ? "#52704a" : "#658257");
      }
      colors[i * 3] = c.r;
      colors[i * 3 + 1] = c.g;
      colors[i * 3 + 2] = c.b;
    }

    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    return geo;
  }, [archetype, waterLevel]);

  useEffect(() => {
    return () => {
      geometry.dispose();
    };
  }, [geometry]);

  useFrame((state) => {
    if (waterRef.current) {
      waterRef.current.position.y = waterLevel + Math.sin(state.clock.elapsedTime * 1.4) * 0.18;
    }
  });

  return (
    <group>
      <mesh geometry={geometry} receiveShadow castShadow>
        <meshStandardMaterial vertexColors roughness={0.9} metalness={0.04} />
      </mesh>
      <mesh ref={waterRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, waterLevel, 0]} receiveShadow>
        <planeGeometry args={[WORLD_SPAN, WORLD_SPAN]} />
        <meshStandardMaterial color="#146c8e" roughness={0.14} metalness={0.35} transparent opacity={0.85} />
      </mesh>
    </group>
  );
};

const GtaWorldScene: React.FC<{
  liveData: any;
  archetype: string;
  timeOfDay: "golden" | "day" | "night";
  cameraPreset: "heli" | "skyline" | "street";
}> = ({ liveData, archetype, timeOfDay, cameraPreset }) => {
  const dayMode = timeOfDay !== "night";
  const isGolden = timeOfDay === "golden";

  const cycloneRef = useRef<THREE.Mesh>(null);
  const carsGroupRef = useRef<THREE.Group>(null);
  const pedBodyRef = useRef<THREE.InstancedMesh>(null);
  const pedHeadRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);

  const centerLat = liveData?.country?.center?.lat ?? 19.8;
  const centerLon = liveData?.country?.center?.lon ?? 84.5;
  const disasters: any[] = liveData?.disasters || [];
  const hasFlood = disasters.some((d) => d.disaster_type === "FLOOD" || d.disaster_type === "CYCLONE");
  const maxSeverity = disasters.reduce((m, d) => Math.max(m, d.severity || 0), 0);
  const floodBoost = hasFlood ? maxSeverity * 4.8 : 0;
  const waterLevel = getWaterLevel(archetype, floodBoost);

  // PBR Architectural Facade & Asphalt Textures
  const commercialTex = useMemo(() => createBuildingFacadeTexture("commercial", dayMode), [dayMode]);
  const residentialTex = useMemo(() => createBuildingFacadeTexture("residential", dayMode), [dayMode]);
  const asphaltTex = useMemo(() => createAsphaltTexture(), []);

  // Terrain-Conforming GTA Boulevards
  const roadGeometries = useMemo(() => {
    const list: THREE.BufferGeometry[] = [];
    for (const coord of BOULEVARDS) {
      list.push(buildTerrainRoadGeometry("x", coord, archetype, waterLevel, 16));
      list.push(buildTerrainRoadGeometry("z", coord, archetype, waterLevel, 16));
    }
    return list;
  }, [archetype, waterLevel]);

  useEffect(() => {
    return () => {
      commercialTex.dispose();
      residentialTex.dispose();
    };
  }, [commercialTex, residentialTex]);

  useEffect(() => {
    return () => {
      asphaltTex.dispose();
    };
  }, [asphaltTex]);

  useEffect(() => {
    return () => {
      roadGeometries.forEach((g) => g.dispose());
    };
  }, [roadGeometries]);

  // GTA Downtown Skyscrapers & Mid-rise Blocks seated between boulevards on real terrain height
  const buildings = useMemo(() => {
    const out: Array<{
      x: number; y: number; z: number; w: number; h: number; d: number;
      commercial: boolean; hasSpire: boolean; storefrontColor: string;
    }> = [];
    const storefronts = ["#0284c7", "#d97706", "#059669", "#dc2626", "#4f46e5", "#475569"];
    let idx = 0;
    for (let bx = -2; bx <= 1; bx++) {
      for (let bz = -2; bz <= 1; bz++) {
        const cx = bx * 120 + 60;
        const cz = bz * 120 + 60;
        // 4 varied buildings per city block
        for (const [ox, oz] of [[-26, -26], [26, -26], [-26, 26], [26, 26]]) {
          idx++;
          const x = cx + ox + ((idx % 3) - 1) * 4;
          const z = cz + oz + (((idx * 7) % 3) - 1) * 4;
          const y = getTerrainHeight(x, z, archetype);
          if (y < waterLevel + 1.5) continue;
          const distCenter = Math.hypot(x, z);
          const commercial = distCenter < 155;
          const h = commercial
            ? 38 + ((idx * 19) % 72) // Downtown Los Santos glass towers
            : 14 + ((idx * 13) % 24); // Mid-rise stucco apartments
          out.push({
            x, y, z,
            w: commercial ? 22 + (idx % 4) * 4 : 18 + (idx % 3) * 4,
            h,
            d: commercial ? 22 + ((idx + 1) % 4) * 4 : 18 + ((idx + 2) % 3) * 4,
            commercial,
            hasSpire: commercial && h > 78,
            storefrontColor: storefronts[idx % storefronts.length],
          });
        }
      }
    }
    return out;
  }, [archetype, waterLevel]);

  // Boulevard Palm Trees & Surrounding Forest Trees seated on 3D Terrain
  const streetPalms = useMemo(() => {
    const out: Array<{ x: number; y: number; z: number }> = [];
    for (const b of [-120, 0, 120]) {
      for (let along = -300; along <= 300; along += 55) {
        const x = along;
        const z = b + 12;
        const y = getTerrainHeight(x, z, archetype);
        if (y >= waterLevel + 1.2) out.push({ x, y, z });
      }
    }
    return out;
  }, [archetype, waterLevel]);

  // 48 Moving GTA Vehicles (Sedans, Taxis, SUVs, Buses) along boulevards
  const trafficCars = useMemo(
    () =>
      Array.from({ length: 48 }, (_, i) => ({
        axis: i % 2 === 0 ? "x" : "z",
        road: BOULEVARDS[i % BOULEVARDS.length],
        laneOffset: i % 4 < 2 ? 3.8 : -3.8,
        dir: i % 4 < 2 ? 1 : -1,
        start: ((i * 53) % 660) - 330,
        speed: 22 + (i % 5) * 6,
        color: CAR_COLORS[i % CAR_COLORS.length],
        isBus: i % 9 === 0,
      })),
    []
  );

  // 140 Animated Sidewalk Pedestrians
  const pedCount = 140;
  const pedestrians = useMemo(
    () =>
      Array.from({ length: pedCount }, (_, i) => ({
        axis: i % 2 === 0 ? "x" : "z",
        road: BOULEVARDS[i % BOULEVARDS.length] + (i % 4 < 2 ? 9.5 : -9.5),
        start: ((i * 37) % 620) - 310,
        dir: i % 3 === 0 ? -1 : 1,
        speed: 4.2 + (i % 4) * 1.1,
        phase: i * 0.9,
        color: new THREE.Color(PED_SHIRTS[i % PED_SHIRTS.length]),
      })),
    []
  );

  useEffect(() => {
    if (pedBodyRef.current) {
      pedestrians.forEach((p, idx) => pedBodyRef.current!.setColorAt(idx, p.color));
      if (pedBodyRef.current.instanceColor) pedBodyRef.current.instanceColor.needsUpdate = true;
    }
  }, [pedestrians]);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const evacBoost = disasters.length > 0 ? 1.85 : 1.0;

    if (cycloneRef.current) cycloneRef.current.rotation.y += 0.025;

    // Move GTA traffic along real 3D terrain height!
    if (carsGroupRef.current) {
      carsGroupRef.current.children.forEach((car, idx) => {
        const c = trafficCars[idx];
        const raw = ((c.start + t * c.speed * c.dir + 3600) % 700) - 350;
        const x = c.axis === "x" ? raw : c.road + c.laneOffset;
        const z = c.axis === "z" ? raw : c.road + c.laneOffset;
        const y = Math.max(waterLevel + 1.0, getTerrainHeight(x, z, archetype)) + 1.65;
        car.position.set(x, y, z);
        car.rotation.y = c.axis === "x" ? (c.dir > 0 ? Math.PI / 2 : -Math.PI / 2) : (c.dir > 0 ? 0 : Math.PI);
      });
    }

    // Move animated sidewalk pedestrians along real 3D terrain height!
    if (pedBodyRef.current && pedHeadRef.current) {
      for (let i = 0; i < pedCount; i++) {
        const p = pedestrians[i];
        const raw = ((p.start + t * p.speed * evacBoost * p.dir + 3600) % 640) - 320;
        const x = p.axis === "x" ? raw : p.road;
        const z = p.axis === "z" ? raw : p.road;
        const y = Math.max(waterLevel + 0.9, getTerrainHeight(x, z, archetype));
        const bob = Math.abs(Math.sin(t * 7.2 * evacBoost + p.phase)) * 0.4;

        dummy.position.set(x, y + 1.8 + bob, z);
        dummy.scale.set(1, 1, 1);
        dummy.updateMatrix();
        pedBodyRef.current.setMatrixAt(i, dummy.matrix);

        dummy.position.set(x, y + 3.5 + bob, z);
        dummy.updateMatrix();
        pedHeadRef.current.setMatrixAt(i, dummy.matrix);
      }
      pedBodyRef.current.instanceMatrix.needsUpdate = true;
      pedHeadRef.current.instanceMatrix.needsUpdate = true;
    }
  });

  const hospitals: any[] = liveData?.hospitals || [];
  const shelters: any[] = liveData?.shelters || [];
  const ambulances: any[] = liveData?.ambulances || [];
  const drones: any[] = liveData?.drones || [];

  const sunPos: [number, number, number] = isGolden ? [380, 68, 220] : [260, 290, 220];

  return (
    <>
      {dayMode ? (
        <Sky sunPosition={sunPos} turbidity={isGolden ? 8 : 3.5} rayleigh={isGolden ? 2.4 : 1.1} mieCoefficient={0.006} />
      ) : (
        <color attach="background" args={["#070d18"]} />
      )}
      <fogExp2 attach="fog" args={[isGolden ? "#e6b88a" : dayMode ? "#c2d5e8" : "#070d18", isGolden ? 0.00065 : 0.00055]} />
      <ambientLight intensity={isGolden ? 0.55 : dayMode ? 0.65 : 0.24} color={isGolden ? "#ffe4c4" : "#dbeafe"} />
      <directionalLight
        position={sunPos}
        intensity={isGolden ? 2.3 : dayMode ? 1.9 : 0.6}
        color={isGolden ? "#ffba73" : dayMode ? "#fff7e8" : "#60a5fa"}
        castShadow
        shadow-mapSize={[2048, 2048]}
      />
      <hemisphereLight args={[isGolden ? "#ffd1a3" : dayMode ? "#dbeafe" : "#1e293b", "#3d4a3a", 0.52]} />

      <CameraPresetRig preset={cameraPreset} archetype={archetype} />
      <SculptedTerrainMesh archetype={archetype} floodBoost={floodBoost} />

      {/* Terrain-Conforming Asphalt Boulevards with Yellow Lines & Sidewalks */}
      {roadGeometries.map((geo, idx) => (
        <mesh key={idx} geometry={geo} receiveShadow>
          <meshStandardMaterial map={asphaltTex} roughness={0.85} metalness={0.05} />
        </mesh>
      ))}

      {/* GTA Downtown Glass Skyscrapers & Stucco Apartments with Rooftop Details */}
      {buildings.map((b, idx) => (
        <group key={idx} position={[b.x, b.y, b.z]}>
          {/* Ground-floor storefront awning */}
          <mesh position={[0, 2.5, 0]} castShadow receiveShadow>
            <boxGeometry args={[b.w + 0.6, 5, b.d + 0.6]} />
            <meshStandardMaterial color={b.storefrontColor} roughness={0.6} />
          </mesh>
          {/* Main textured architectural tower */}
          <mesh position={[0, b.h / 2 + 2, 0]} castShadow receiveShadow>
            <boxGeometry args={[b.w, b.h, b.d]} />
            <meshStandardMaterial
              map={b.commercial ? commercialTex : residentialTex}
              roughness={b.commercial ? 0.25 : 0.78}
              metalness={b.commercial ? 0.45 : 0.05}
            />
          </mesh>
          {/* Rooftop HVAC / Penthouse + Optional Spire */}
          <mesh position={[0, b.h + 3.8, 0]}>
            <boxGeometry args={[b.w * 0.45, 3.6, b.d * 0.45]} />
            <meshStandardMaterial color="#475569" roughness={0.8} />
          </mesh>
          {b.hasSpire && (
            <mesh position={[0, b.h + 13, 0]}>
              <cylinderGeometry args={[0.3, 0.8, 18, 6]} />
              <meshStandardMaterial color="#cbd5e1" metalness={0.8} roughness={0.2} />
            </mesh>
          )}
        </group>
      ))}

      {/* GTA Los Santos Boulevard Palm Trees */}
      {streetPalms.map((p, idx) => (
        <group key={idx} position={[p.x, p.y, p.z]}>
          <mesh position={[0, 7, 0]} castShadow>
            <cylinderGeometry args={[0.45, 0.75, 14, 6]} />
            <meshStandardMaterial color="#785a3c" roughness={0.95} />
          </mesh>
          <mesh position={[0, 14.5, 0]} castShadow>
            <coneGeometry args={[4.8, 4.2, 7]} />
            <meshStandardMaterial color="#2f6f36" roughness={0.82} />
          </mesh>
        </group>
      ))}

      {/* 48 Animated GTA Street Vehicles (Sedans, Taxis, SUVs, Buses) */}
      <group ref={carsGroupRef}>
        {trafficCars.map((c, idx) => (
          <group key={idx}>
            <mesh castShadow>
              <boxGeometry args={[c.isBus ? 3.4 : 2.6, c.isBus ? 3.4 : 1.8, c.isBus ? 11.5 : 5.4]} />
              <meshStandardMaterial color={c.color} roughness={0.28} metalness={0.55} />
            </mesh>
            {!c.isBus && (
              <mesh position={[0, 1.35, -0.3]}>
                <boxGeometry args={[2.2, 1.1, 2.8]} />
                <meshStandardMaterial color="#0f172a" roughness={0.15} metalness={0.7} />
              </mesh>
            )}
            {/* Headlights & Taillights */}
            <mesh position={[0, 0.1, c.isBus ? 5.8 : 2.75]}>
              <boxGeometry args={[2.1, 0.45, 0.2]} />
              <meshStandardMaterial color="#fef9c3" emissive="#fef08a" emissiveIntensity={dayMode ? 0.5 : 2.4} />
            </mesh>
            <mesh position={[0, 0.1, c.isBus ? -5.8 : -2.75]}>
              <boxGeometry args={[2.1, 0.45, 0.2]} />
              <meshStandardMaterial color="#ef4444" emissive="#dc2626" emissiveIntensity={dayMode ? 0.6 : 2.2} />
            </mesh>
          </group>
        ))}
      </group>

      {/* 140 Animated Sidewalk Pedestrians */}
      <instancedMesh ref={pedBodyRef} args={[undefined, undefined, pedCount]} castShadow>
        <capsuleGeometry args={[0.7, 1.7, 4, 8]} />
        <meshStandardMaterial roughness={0.85} />
      </instancedMesh>
      <instancedMesh ref={pedHeadRef} args={[undefined, undefined, pedCount]}>
        <sphereGeometry args={[0.62, 8, 8]} />
        <meshStandardMaterial color="#e6be9a" roughness={0.75} />
      </instancedMesh>

      {/* Real Backend Hospitals seated on 3D Terrain */}
      {hospitals.map((h) => {
        const [x, z] = geoOffsetToLocal(h.location.lat, h.location.lon, centerLat, centerLon);
        const y = Math.max(waterLevel + 1.2, getTerrainHeight(x, z, archetype));
        return (
          <group key={h.hospital_id} position={[x, y, z]}>
            <mesh position={[0, 12, 0]} castShadow>
              <boxGeometry args={[26, 24, 20]} />
              <meshStandardMaterial color="#f8fafc" roughness={0.45} />
            </mesh>
            <mesh position={[0, 24.5, 0]}>
              <boxGeometry args={[10, 0.8, 3]} />
              <meshStandardMaterial color="#dc2626" emissive="#dc2626" emissiveIntensity={0.6} />
            </mesh>
            <mesh position={[0, 24.5, 0]}>
              <boxGeometry args={[3, 0.8, 10]} />
              <meshStandardMaterial color="#dc2626" emissive="#dc2626" emissiveIntensity={0.6} />
            </mesh>
            <Html position={[0, 30, 0]} distanceFactor={360} style={{ pointerEvents: "none" }}>
              <div className="px-1.5 py-0.5 rounded bg-slate-950/90 border border-sky-400/80 text-[10px] font-mono text-sky-100 whitespace-nowrap">
                HOSP · {h.available_beds} BEDS
              </div>
            </Html>
          </group>
        );
      })}

      {/* Real Backend Relief Shelters */}
      {shelters.map((s) => {
        const [x, z] = geoOffsetToLocal(s.location.lat, s.location.lon, centerLat, centerLon);
        const y = Math.max(waterLevel + 1.2, getTerrainHeight(x, z, archetype));
        return (
          <group key={s.shelter_id} position={[x, y, z]}>
            <mesh position={[0, 5, 0]} castShadow>
              <cylinderGeometry args={[9, 11, 10, 8]} />
              <meshStandardMaterial color="#0284c7" roughness={0.55} />
            </mesh>
            <Html position={[0, 14, 0]} distanceFactor={380} style={{ pointerEvents: "none" }}>
              <div className="px-1.5 py-0.5 rounded bg-slate-950/85 border border-emerald-500/80 text-[10px] font-mono text-emerald-200 whitespace-nowrap">
                SHELTER · {s.remaining_capacity} CAP
              </div>
            </Html>
          </group>
        );
      })}

      {/* Real Backend Emergency Ambulances */}
      {ambulances.map((a) => {
        const [x, z] = geoOffsetToLocal(a.location.lat, a.location.lon, centerLat, centerLon);
        const y = Math.max(waterLevel + 1.0, getTerrainHeight(x, z, archetype));
        return (
          <group key={a.ambulance_id} position={[x, y + 1.9, z]}>
            <mesh castShadow>
              <boxGeometry args={[3.4, 3.0, 7.6]} />
              <meshStandardMaterial color="#ffffff" roughness={0.3} />
            </mesh>
            <mesh position={[0, 1.85, 1.8]}>
              <boxGeometry args={[2.4, 0.65, 1.2]} />
              <meshStandardMaterial color="#ef4444" emissive="#ef4444" emissiveIntensity={2.2} />
            </mesh>
          </group>
        );
      })}

      {/* Real Backend Drones flying above the GTA skyline */}
      {drones.map((d) => {
        const [x, z] = geoOffsetToLocal(d.location.lat, d.location.lon, centerLat, centerLon);
        const groundY = Math.max(waterLevel, getTerrainHeight(x, z, archetype));
        const alt = d.status === "IN_FLIGHT" || d.status === "ASSIGNED" ? groundY + 75 : groundY + 34;
        const color = d.status === "DESTROYED" ? "#ef4444" : d.status === "IN_FLIGHT" ? "#22c55e" : "#38bdf8";
        return (
          <group key={d.drone_id} position={[x, alt, z]}>
            <mesh>
              <octahedronGeometry args={[3.0, 0]} />
              <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.85} />
            </mesh>
            <Line points={[[0, 0, 0], [0, -(alt - groundY), 0]]} color={color} lineWidth={0.8} transparent opacity={0.3} />
          </group>
        );
      })}

      {/* Active Disaster Volumetric Effects */}
      {disasters.map((ev) => {
        const [x, z] = geoOffsetToLocal(ev.origin.lat, ev.origin.lon, centerLat, centerLon);
        const y = Math.max(waterLevel, getTerrainHeight(x, z, archetype));
        if (ev.disaster_type === "CYCLONE") {
          return (
            <mesh key={ev.event_id} ref={cycloneRef} position={[x, y + 105, z]}>
              <coneGeometry args={[105, 210, 24, 1, true]} />
              <meshStandardMaterial color="#cbd5e1" transparent opacity={0.3} side={THREE.DoubleSide} />
            </mesh>
          );
        }
        if (ev.disaster_type === "FIRE" || ev.disaster_type === "WILDFIRE") {
          return (
            <mesh key={ev.event_id} position={[x, y + 18, z]}>
              <sphereGeometry args={[28, 16, 16]} />
              <meshStandardMaterial color="#f97316" emissive="#ea580c" emissiveIntensity={1.6} transparent opacity={0.62} />
            </mesh>
          );
        }
        return null;
      })}

      <OrbitControls maxPolarAngle={Math.PI / 2.06} minDistance={45} maxDistance={860} />
    </>
  );
};

export const Unified3DTerrainWorld: React.FC<UnifiedTerrainProps> = ({
  countryId,
  archetype,
  countryName,
  dayMode,
}) => {
  const [liveData, setLiveData] = useState<any>(null);
  const [timeOfDay, setTimeOfDay] = useState<"golden" | "day" | "night">(dayMode ? "golden" : "night");
  const [cameraPreset, setCameraPreset] = useState<"heli" | "skyline" | "street">("skyline");

  useEffect(() => {
    let active = true;
    const ac = new AbortController();
    const load = () => {
      globalApi.getOverview().catch(() => {});
      fetch(`/api/world/live-entities/${countryId}`, { signal: ac.signal })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then((d) => {
          if (active) setLiveData(d);
        })
        .catch(() => {});
    };
    load();
    const id = window.setInterval(load, 2500);
    return () => {
      active = false;
      ac.abort();
      window.clearInterval(id);
    };
  }, [countryId]);

  const activeAlertCount = liveData?.disasters?.length ?? 0;

  return (
    <div className="w-full h-full relative bg-[#0b1117] select-none">
      <Canvas
        shadows
        camera={{ position: [195, 115, 225], fov: 48, near: 1.5, far: 4000 }}
        gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.08 }}
      >
        <GtaWorldScene liveData={liveData} archetype={archetype} timeOfDay={timeOfDay} cameraPreset={cameraPreset} />
      </Canvas>

      {/* GTA-Style Top-Right District & Alert Status Stack */}
      <div className="absolute top-4 right-4 text-right pointer-events-none drop-shadow-[0_2px_6px_rgba(0,0,0,0.9)]">
        <div className="text-2xl font-black tracking-wide text-white uppercase">{countryName}</div>
        <div className="text-xs font-mono text-amber-300 uppercase">
          {archetype} · {activeAlertCount > 0 ? `${activeAlertCount} ACTIVE DISASTER ALERT` : "CITY STATUS NORMAL"}
        </div>
        <div className="text-xs font-mono text-emerald-400 mt-0.5">
          DRONES {liveData?.drones?.length ?? 0} · AMBULANCES {liveData?.ambulances?.length ?? 0} · HOSPITALS {liveData?.hospitals?.length ?? 0}
        </div>
      </div>

      {/* GTA-Style Bottom-Left Square Radar Minimap */}
      <div className="absolute bottom-4 left-4 w-44 h-32 rounded bg-[#0c141d]/90 border-2 border-slate-700/90 p-2 overflow-hidden shadow-lg">
        <div className="text-[9px] font-mono text-slate-400 flex justify-between mb-1">
          <span>RADAR · {countryId}</span>
          <span className="text-emerald-400">LIVE</span>
        </div>
        <div className="relative w-full h-22 bg-[#162231] rounded-sm border border-slate-800 h-[88px]">
          {/* Boulevard grid lines */}
          {[20, 40, 60, 80].map((p) => (
            <React.Fragment key={p}>
              <div className="absolute top-0 bottom-0 w-px bg-slate-600/40" style={{ left: `${p}%` }} />
              <div className="absolute left-0 right-0 h-px bg-slate-600/40" style={{ top: `${p}%` }} />
            </React.Fragment>
          ))}
          {(liveData?.hospitals || []).slice(0, 6).map((h: any, i: number) => (
            <div
              key={h.hospital_id}
              className="absolute w-2 h-2 rounded-full bg-sky-400 border border-white"
              style={{ left: `${25 + (i * 15) % 55}%`, top: `${22 + (i * 23) % 55}%` }}
            />
          ))}
          {(liveData?.disasters || []).map((d: any) => (
            <div
              key={d.event_id}
              className="absolute w-5 h-5 rounded-full bg-red-500/45 border border-red-400 animate-pulse"
              style={{ left: "46%", top: "42%" }}
            />
          ))}
        </div>
      </div>

      {/* GTA Camera & Time-of-Day Controls (Bottom-Right) */}
      <div className="absolute bottom-4 right-4 flex items-center gap-1.5 bg-[#0c141d]/90 border border-slate-700 rounded px-2 py-1.5 text-[11px] font-mono">
        {(["street", "skyline", "heli"] as const).map((p) => (
          <button
            key={p}
            onClick={() => setCameraPreset(p)}
            className={`px-2 py-0.5 rounded uppercase ${cameraPreset === p ? "bg-sky-600 text-white" : "text-slate-300 hover:bg-slate-800"}`}
          >
            {p}
          </button>
        ))}
        <span className="text-slate-600">|</span>
        {(["golden", "day", "night"] as const).map((tod) => (
          <button
            key={tod}
            onClick={() => setTimeOfDay(tod)}
            className={`px-2 py-0.5 rounded uppercase ${timeOfDay === tod ? "bg-amber-600 text-white" : "text-slate-300 hover:bg-slate-800"}`}
          >
            {tod}
          </button>
        ))}
      </div>
    </div>
  );
};
