import React, { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, Line, OrbitControls, Sky } from "@react-three/drei";
import * as THREE from "three";
import type { CountrySummary, DisasterEvent, GeoPoint } from "../shared/globalTypes";
import { createBuildingFacadeTexture } from "./textures";

/**
 * 10,000m x 10,000m Continuous Flat Open-World 7-Country GTA-Style Continent.
 * All 7 countries exist side-by-side on one giant navigable flat world connected by
 * inter-country highways, rivers, coastlines, and distinct biome districts.
 */
export const COUNTRY_FLAT_ANCHORS: Record<string, { x: number; z: number; radius: number; ground: string }> = {
  "COUNTRY-01": { x: 2600, z: -1200, radius: 1350, ground: "#687b64" }, // Aurelia Coast (East Coast)
  "COUNTRY-02": { x: 0, z: -2700, radius: 1350, ground: "#6f776d" },    // Valtoria Highlands (North)
  "COUNTRY-03": { x: 0, z: 0, radius: 1450, ground: "#5e7956" },        // Veridia Basin (Central River)
  "COUNTRY-04": { x: -2500, z: -400, radius: 1450, ground: "#7f9653" }, // Solara Plains (West Farmland)
  "COUNTRY-05": { x: -2100, z: 2200, radius: 1300, ground: "#5a6169" }, // Ferros Industrial (Southwest)
  "COUNTRY-06": { x: -2400, z: -2600, radius: 1400, ground: "#c9a675" },// Kalahar Steppe (Northwest Arid)
  "COUNTRY-07": { x: 1800, z: 2200, radius: 1400, ground: "#3d623b" },  // Sylva Reserve (Southeast Forest)
};

const HIGHWAY_LINKS: Array<[string, string]> = [
  ["COUNTRY-03", "COUNTRY-01"],
  ["COUNTRY-03", "COUNTRY-02"],
  ["COUNTRY-03", "COUNTRY-04"],
  ["COUNTRY-03", "COUNTRY-05"],
  ["COUNTRY-03", "COUNTRY-07"],
  ["COUNTRY-02", "COUNTRY-06"],
  ["COUNTRY-04", "COUNTRY-06"],
  ["COUNTRY-04", "COUNTRY-05"],
  ["COUNTRY-01", "COUNTRY-07"],
];

const CAR_COLORS = ["#dc2626", "#2563eb", "#facc15", "#f8fafc", "#1e293b", "#059669", "#ea580c", "#94a3b8"];
const PED_COLORS = ["#ef4444", "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#f8fafc", "#334155"];

function createRoadStripeTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 128;
  c.height = 128;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = "#252a32";
  ctx.fillRect(0, 0, 128, 128);
  ctx.fillStyle = "#eab308";
  ctx.fillRect(61, 0, 2, 128);
  ctx.fillRect(65, 0, 2, 128);
  ctx.fillStyle = "#e2e8f0";
  for (let y = 0; y < 128; y += 32) {
    ctx.fillRect(30, y, 2, 16);
    ctx.fillRect(96, y, 2, 16);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(1, 32);
  return tex;
}

function geoToFlatWorld(lat: number, lon: number, country: CountrySummary | undefined): [number, number] {
  if (!country) return [0, 0];
  const anchor = COUNTRY_FLAT_ANCHORS[country.country_id] || { x: 0, z: 0 };
  const dx = THREE.MathUtils.clamp((lon - country.center.lon) * 850, -900, 900);
  const dz = THREE.MathUtils.clamp(-(lat - country.center.lat) * 850, -900, 900);
  return [anchor.x + dx, anchor.z + dz];
}

interface BigFlatWorldProps {
  countries: CountrySummary[];
  disasters: DisasterEvent[];
  selectedCountryId: string;
  onSelectCountry: (countryId: string) => void;
  candidateRoutes?: Array<{ route_id: string; feasible: boolean; waypoints: GeoPoint[] }>;
  allDrones?: any[];
  allHospitals?: any[];
  allShelters?: any[];
  allAmbulances?: any[];
  allFireUnits?: any[];
  activeSwarms?: any[];
}

const CameraFlyRig: React.FC<{
  selectedCountryId: string;
  preset: "continent" | "country" | "street";
  controlsRef: React.RefObject<any>;
}> = ({ selectedCountryId, preset, controlsRef }) => {
  const { camera } = useThree();
  const anchor = COUNTRY_FLAT_ANCHORS[selectedCountryId] || { x: 0, z: 0 };

  const targetPos = useMemo(() => {
    if (preset === "continent") return new THREE.Vector3(0, 4200, 4800);
    if (preset === "street") return new THREE.Vector3(anchor.x + 120, 42, anchor.z + 240);
    return new THREE.Vector3(anchor.x + 620, 460, anchor.z + 780);
  }, [anchor.x, anchor.z, preset]);

  const lookTarget = useMemo(() => {
    if (preset === "continent") return new THREE.Vector3(0, 0, 0);
    return new THREE.Vector3(anchor.x, 10, anchor.z);
  }, [anchor.x, anchor.z, preset]);

  const transitioningRef = useRef(true);

  useEffect(() => {
    transitioningRef.current = true;
  }, [selectedCountryId, preset]);

  useEffect(() => {
    const ctrl = controlsRef.current;
    if (!ctrl) return;
    const stopTransition = () => {
      transitioningRef.current = false;
    };
    ctrl.addEventListener("start", stopTransition);
    return () => ctrl.removeEventListener("start", stopTransition);
  }, [controlsRef]);

  useFrame((_, delta) => {
    if (!transitioningRef.current) return;
    const alpha = Math.min(1, delta * 2.6);
    camera.position.lerp(targetPos, alpha);
    if (controlsRef.current) {
      controlsRef.current.target.lerp(lookTarget, alpha);
      controlsRef.current.update();
    }
    if (camera.position.distanceTo(targetPos) < 4.0) {
      transitioningRef.current = false;
    }
  });

  return null;
};

const BigFlatWorldScene: React.FC<
  BigFlatWorldProps & {
    timeOfDay: "golden" | "day" | "night";
    cameraPreset: "continent" | "country" | "street";
  }
> = ({
  countries,
  disasters,
  selectedCountryId,
  onSelectCountry,
  candidateRoutes = [],
  allDrones = [],
  allHospitals = [],
  allShelters = [],
  allAmbulances = [],
  allFireUnits = [],
  activeSwarms = [],
  timeOfDay,
  cameraPreset,
}) => {
  const controlsRef = useRef<any>(null);
  const commMeshRef = useRef<THREE.InstancedMesh>(null);
  const resMeshRef = useRef<THREE.InstancedMesh>(null);
  const carsMeshRef = useRef<THREE.InstancedMesh>(null);
  const pedsMeshRef = useRef<THREE.InstancedMesh>(null);
  const treesTrunkRef = useRef<THREE.InstancedMesh>(null);
  const treesCanopyRef = useRef<THREE.InstancedMesh>(null);
  const cycloneRef = useRef<THREE.Group>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);

  const dayMode = timeOfDay !== "night";
  const isGolden = timeOfDay === "golden";

  const commercialTex = useMemo(() => createBuildingFacadeTexture("commercial", dayMode), [dayMode]);
  const residentialTex = useMemo(() => createBuildingFacadeTexture("residential", dayMode), [dayMode]);
  const roadTex = useMemo(() => createRoadStripeTexture(), []);
  const liveDronesRef = useRef<THREE.Group>(null);
  const quantumRingRef = useRef<THREE.Mesh>(null);

  useEffect(() => () => {
    commercialTex.dispose();
    residentialTex.dispose();
    roadTex.dispose();
  }, [commercialTex, residentialTex, roadTex]);

  // Generate 700 GTA commercial towers + 700 mid-rise apartments across ALL 7 countries on the big flat map
  const { commBuildings, resBuildings } = useMemo(() => {
    const comm: Array<{ x: number; z: number; w: number; h: number; d: number }> = [];
    const res: Array<{ x: number; z: number; w: number; h: number; d: number }> = [];
    const ids = Object.keys(COUNTRY_FLAT_ANCHORS);

    ids.forEach((cid, cIdx) => {
      const a = COUNTRY_FLAT_ANCHORS[cid];
      for (let i = 0; i < 84; i++) {
        const ang = i * 2.39996 + cIdx;
        const r = 55 + Math.sqrt(i) * 78;
        const x = a.x + Math.cos(ang) * r;
        const z = a.z + Math.sin(ang) * r;
        // Keep central avenue cross clear
        if (Math.abs(x - a.x) < 28 || Math.abs(z - a.z) < 28) continue;
        const isDowntown = r < 340;
        const seed = cIdx * 100 + i;
        if (isDowntown) {
          comm.push({
            x,
            z,
            w: 28 + (seed % 4) * 8,
            h: 55 + ((seed * 19) % 130),
            d: 28 + ((seed + 2) % 4) * 8,
          });
        } else {
          res.push({
            x,
            z,
            w: 22 + (seed % 3) * 6,
            h: 18 + ((seed * 13) % 36),
            d: 22 + ((seed + 1) % 3) * 6,
          });
        }
      }
    });
    return { commBuildings: comm, resBuildings: res };
  }, []);

  // Populate building instanced matrices once
  useEffect(() => {
    if (commMeshRef.current) {
      commBuildings.forEach((b, i) => {
        dummy.position.set(b.x, b.h / 2, b.z);
        dummy.scale.set(b.w, b.h, b.d);
        dummy.rotation.set(0, 0, 0);
        dummy.updateMatrix();
        commMeshRef.current!.setMatrixAt(i, dummy.matrix);
      });
      commMeshRef.current.instanceMatrix.needsUpdate = true;
    }
    if (resMeshRef.current) {
      resBuildings.forEach((b, i) => {
        dummy.position.set(b.x, b.h / 2, b.z);
        dummy.scale.set(b.w, b.h, b.d);
        dummy.rotation.set(0, 0, 0);
        dummy.updateMatrix();
        resMeshRef.current!.setMatrixAt(i, dummy.matrix);
      });
      resMeshRef.current.instanceMatrix.needsUpdate = true;
    }
  }, [commBuildings, resBuildings, dummy]);

  // 160 moving vehicles across all 7 countries + inter-country highways
  const vehicles = useMemo(() => {
    const ids = Object.keys(COUNTRY_FLAT_ANCHORS);
    return Array.from({ length: 160 }, (_, i) => {
      if (i < 60) {
        const [fromId, toId] = HIGHWAY_LINKS[i % HIGHWAY_LINKS.length];
        return {
          mode: "highway" as const,
          a: COUNTRY_FLAT_ANCHORS[fromId],
          b: COUNTRY_FLAT_ANCHORS[toId],
          speed: 0.018 + (i % 5) * 0.004,
          phase: (i * 0.17) % 1,
          color: new THREE.Color(CAR_COLORS[i % CAR_COLORS.length]),
        };
      }
      const anchor = COUNTRY_FLAT_ANCHORS[ids[i % ids.length]];
      return {
        mode: "city" as const,
        a: anchor,
        b: anchor,
        axis: i % 2 === 0 ? "x" : "z",
        speed: 45 + (i % 4) * 14,
        phase: (i * 97) % 1200,
        dir: i % 4 < 2 ? 1 : -1,
        color: new THREE.Color(CAR_COLORS[i % CAR_COLORS.length]),
      };
    });
  }, []);

  // 420 instanced trees (boulevard palms & Sylva forest groves) on the flat world
  const trees = useMemo(() => {
    const out: Array<{ x: number; z: number; h: number; r: number }> = [];
    const ids = Object.keys(COUNTRY_FLAT_ANCHORS);
    ids.forEach((cid, cIdx) => {
      const a = COUNTRY_FLAT_ANCHORS[cid];
      const count = cid === "COUNTRY-07" ? 130 : cid === "COUNTRY-06" ? 18 : 45;
      for (let i = 0; i < count; i++) {
        const ang = i * 2.39996 + cIdx * 1.7;
        const dist = cid === "COUNTRY-07" ? 260 + Math.sqrt(i) * 95 : 420 + Math.sqrt(i) * 95;
        const x = a.x + Math.cos(ang) * dist;
        const z = a.z + Math.sin(ang) * dist;
        if (Math.abs(x - a.x) < 35 || Math.abs(z - a.z) < 35) continue;
        out.push({ x, z, h: 16 + (i % 4) * 5, r: 9 + (i % 3) * 3 });
      }
    });
    return out;
  }, []);

  useEffect(() => {
    if (treesTrunkRef.current && treesCanopyRef.current) {
      trees.forEach((tr, i) => {
        dummy.position.set(tr.x, tr.h * 0.45, tr.z);
        dummy.scale.set(2.2, tr.h * 0.9, 2.2);
        dummy.rotation.set(0, 0, 0);
        dummy.updateMatrix();
        treesTrunkRef.current!.setMatrixAt(i, dummy.matrix);

        dummy.position.set(tr.x, tr.h * 1.05, tr.z);
        dummy.scale.set(tr.r, tr.h * 0.9, tr.r);
        dummy.updateMatrix();
        treesCanopyRef.current!.setMatrixAt(i, dummy.matrix);
      });
      treesTrunkRef.current.instanceMatrix.needsUpdate = true;
      treesCanopyRef.current.instanceMatrix.needsUpdate = true;
    }
  }, [trees, dummy]);

  // 240 sidewalk pedestrians across all 7 countries
  const pedestrians = useMemo(() => {
    const ids = Object.keys(COUNTRY_FLAT_ANCHORS);
    return Array.from({ length: 240 }, (_, i) => {
      const a = COUNTRY_FLAT_ANCHORS[ids[i % ids.length]];
      return {
        ax: a.x,
        az: a.z,
        axis: i % 2 === 0 ? "x" : "z",
        offset: ((i * 53) % 900) - 450,
        side: i % 4 < 2 ? 18 : -18,
        speed: 8 + (i % 4) * 2.5,
        dir: i % 3 === 0 ? -1 : 1,
        phase: i * 0.8,
        color: new THREE.Color(PED_COLORS[i % PED_COLORS.length]),
      };
    });
  }, []);

  useEffect(() => {
    if (carsMeshRef.current) {
      vehicles.forEach((v, i) => carsMeshRef.current!.setColorAt(i, v.color));
      if (carsMeshRef.current.instanceColor) carsMeshRef.current.instanceColor.needsUpdate = true;
    }
    if (pedsMeshRef.current) {
      pedestrians.forEach((p, i) => pedsMeshRef.current!.setColorAt(i, p.color));
      if (pedsMeshRef.current.instanceColor) pedsMeshRef.current.instanceColor.needsUpdate = true;
    }
  }, [vehicles, pedestrians]);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (cycloneRef.current) {
      cycloneRef.current.children.forEach((ch) => {
        ch.rotation.y += 0.03;
      });
    }
    if (quantumRingRef.current) {
      quantumRingRef.current.rotation.z = t * 0.25;
    }
    // Realistic smooth orbiting, banking, and altitude bobbing on all 98 live drones
    if (liveDronesRef.current) {
      liveDronesRef.current.children.forEach((grp, idx) => {
        const dStatus = allDrones[idx]?.status;
        if (dStatus !== "IN_FLIGHT" && dStatus !== "ASSIGNED") {
          return;
        }
        if (grp.userData.baseX === undefined) {
          grp.userData.baseX = grp.position.x;
          grp.userData.baseY = grp.position.y;
          grp.userData.baseZ = grp.position.z;
        }
        const ang = t * (0.45 + (idx % 5) * 0.08) + idx * 0.9;
        grp.position.x = grp.userData.baseX + Math.cos(ang) * 42;
        grp.position.z = grp.userData.baseZ + Math.sin(ang) * 42;
        grp.position.y = grp.userData.baseY + Math.sin(t * 2.4 + idx) * 3.5;
        grp.rotation.y = -ang;
        grp.rotation.z = Math.sin(ang) * 0.14;
      });
    }

    if (carsMeshRef.current) {
      vehicles.forEach((v, i) => {
        if (v.mode === "highway") {
          const u = (v.phase + t * v.speed) % 1;
          const x = THREE.MathUtils.lerp(v.a.x, v.b.x, u);
          const z = THREE.MathUtils.lerp(v.a.z, v.b.z, u);
          const ang = Math.atan2(v.b.x - v.a.x, v.b.z - v.a.z);
          dummy.position.set(x, 3.2, z);
          dummy.rotation.set(0, ang, 0);
          dummy.scale.set(5.5, 4.2, 12.5);
        } else {
          const span = ((v.phase + t * v.speed * (v.dir || 1) + 4800) % 1400) - 700;
          const x = v.axis === "x" ? v.a.x + span : v.a.x + (v.dir === 1 ? 7 : -7);
          const z = v.axis === "z" ? v.a.z + span : v.a.z + (v.dir === 1 ? 7 : -7);
          dummy.position.set(x, 3.0, z);
          dummy.rotation.set(0, v.axis === "x" ? Math.PI / 2 : 0, 0);
          dummy.scale.set(5.0, 3.8, 11.0);
        }
        dummy.updateMatrix();
        carsMeshRef.current!.setMatrixAt(i, dummy.matrix);
      });
      carsMeshRef.current.instanceMatrix.needsUpdate = true;
    }

    if (pedsMeshRef.current) {
      const evacBoost = disasters.some((d) => d.status === "ACTIVE") ? 1.9 : 1.0;
      pedestrians.forEach((p, i) => {
        const span = ((p.offset + t * p.speed * evacBoost * p.dir + 4800) % 900) - 450;
        const x = p.axis === "x" ? p.ax + span : p.ax + p.side;
        const z = p.axis === "z" ? p.az + span : p.az + p.side;
        const bob = Math.abs(Math.sin(t * 7 + p.phase)) * 0.6;
        dummy.position.set(x, 3.2 + bob, z);
        dummy.rotation.set(0, 0, 0);
        dummy.scale.set(2.2, 5.2, 2.2);
        dummy.updateMatrix();
        pedsMeshRef.current!.setMatrixAt(i, dummy.matrix);
      });
      pedsMeshRef.current.instanceMatrix.needsUpdate = true;
    }
  });

  const countryById = useMemo(
    () => Object.fromEntries(countries.map((c) => [c.country_id, c])),
    [countries]
  );

  const sunPos: [number, number, number] = isGolden ? [3600, 520, 2200] : [2200, 3400, 1800];

  return (
    <>
      {dayMode ? (
        <Sky sunPosition={sunPos} turbidity={isGolden ? 7.5 : 3.2} rayleigh={isGolden ? 2.2 : 1.0} />
      ) : (
        <color attach="background" args={["#070d18"]} />
      )}
      <fogExp2 attach="fog" args={[isGolden ? "#e2b992" : dayMode ? "#c4d7e8" : "#070d18", 0.000095]} />
      <ambientLight intensity={isGolden ? 0.58 : dayMode ? 0.68 : 0.28} />
      <directionalLight
        position={sunPos}
        intensity={isGolden ? 2.2 : dayMode ? 1.85 : 0.65}
        color={isGolden ? "#ffc07a" : dayMode ? "#fff7e8" : "#60a5fa"}
        castShadow
      />
      <hemisphereLight args={[isGolden ? "#ffd1a3" : "#dbeafe", "#3b4938", 0.55]} />

      <CameraFlyRig selectedCountryId={selectedCountryId} preset={cameraPreset} controlsRef={controlsRef} />

      {/* Giant 14,000m Ocean Base + 10,000m x 10,000m Flat Open-World Continent */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -2.5, 0]} receiveShadow>
        <planeGeometry args={[18000, 18000]} />
        <meshStandardMaterial color="#135d7d" roughness={0.18} metalness={0.3} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[9600, 9600]} />
        <meshStandardMaterial color={dayMode ? "#657d5a" : "#1c2520"} roughness={0.94} />
      </mesh>

      {/* Central Veridia River Channel + Coastal Harbor Bay + Multi-Span Highway Bridges */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[1400, 0.35, 160]}>
        <planeGeometry args={[6800, 145]} />
        <meshStandardMaterial color="#18789e" roughness={0.14} metalness={0.32} />
      </mesh>
      {[0, 1200, 2600].map((bx) => (
        <group key={bx} position={[bx, 6, 160]}>
          <mesh>
            <boxGeometry args={[42, 4, 170]} />
            <meshStandardMaterial color="#94a3b8" roughness={0.75} />
          </mesh>
          <mesh position={[-19, 10, 0]}>
            <boxGeometry args={[2, 16, 165]} />
            <meshStandardMaterial color="#cbd5e1" metalness={0.5} roughness={0.35} />
          </mesh>
          <mesh position={[19, 10, 0]}>
            <boxGeometry args={[2, 16, 165]} />
            <meshStandardMaterial color="#cbd5e1" metalness={0.5} roughness={0.35} />
          </mesh>
        </group>
      ))}
      {/* Airport Runway in Veridia Central & Aurelia Coast */}
      {[[420, -480], [2980, -1580]].map(([rx, rz], idx) => (
        <group key={idx} position={[rx, 0.75, rz]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[360, 44]} />
            <meshStandardMaterial color="#334155" roughness={0.85} />
          </mesh>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.1, 0]}>
            <planeGeometry args={[320, 3]} />
            <meshStandardMaterial color="#f8fafc" />
          </mesh>
        </group>
      ))}
      {/* Patchwork Farmland Fields in Solara Plains (COUNTRY-04) */}
      {[[-3100, -700, "#7ea34d"], [-3100, -250, "#b8a653"], [-2650, -950, "#5e8744"], [-2100, -950, "#9ab056"]].map(([fx, fz, col]: any, idx) => (
        <mesh key={idx} rotation={[-Math.PI / 2, 0, 0]} position={[fx, 0.4, fz]}>
          <planeGeometry args={[420, 360]} />
          <meshStandardMaterial color={col} roughness={0.95} />
        </mesh>
      ))}
      {/* Industrial Cooling Towers in Ferros Industrial Union (COUNTRY-05) */}
      {[[-2550, 2450], [-2380, 2550], [-2210, 2450]].map(([tx, tz], idx) => (
        <mesh key={idx} position={[tx, 65, tz]}>
          <cylinderGeometry args={[32, 48, 130, 18]} />
          <meshStandardMaterial color="#94a3b8" roughness={0.82} />
        </mesh>
      ))}

      {/* 7 Country Biome Ground Patches, Border Outlines, City Boulevards & Interactive Labels */}
      {countries.map((c) => {
        const a = COUNTRY_FLAT_ANCHORS[c.country_id];
        if (!a) return null;
        const isSel = c.country_id === selectedCountryId;
        const ringPts: [number, number, number][] = Array.from({ length: 25 }, (_, i) => {
          const ang = (i / 24) * Math.PI * 2;
          return [a.x + Math.cos(ang) * a.radius, 1.8, a.z + Math.sin(ang) * a.radius];
        });

        return (
          <group key={c.country_id}>
            {/* Country Biome Ground */}
            <mesh
              rotation={[-Math.PI / 2, 0, 0]}
              position={[a.x, 0.25, a.z]}
              onClick={(e) => {
                e.stopPropagation();
                onSelectCountry(c.country_id);
              }}
            >
              <circleGeometry args={[a.radius, 36]} />
              <meshStandardMaterial color={a.ground} roughness={0.93} />
            </mesh>

            {/* Country Border Line */}
            <Line points={ringPts} color={isSel ? "#38bdf8" : c.color} lineWidth={isSel ? 3.0 : 1.4} />

            {/* Cross-City Asphalt Boulevards */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[a.x, 0.65, a.z]}>
              <planeGeometry args={[1650, 34]} />
              <meshStandardMaterial map={roadTex} roughness={0.85} />
            </mesh>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[a.x, 0.66, a.z]}>
              <planeGeometry args={[34, 1650]} />
              <meshStandardMaterial map={roadTex} roughness={0.85} />
            </mesh>

            {/* Mountain Peaks in Country 02 (Valtoria) & Forest Canopy in Country 07 (Sylva) */}
            {c.country_id === "COUNTRY-02" &&
              [[-550, -520, 420], [580, -480, 480], [0, -760, 540]].map(([ox, oz, h], idx) => (
                <mesh key={idx} position={[a.x + ox, h / 2, a.z + oz]}>
                  <coneGeometry args={[360, h, 7]} />
                  <meshStandardMaterial color="#7b838c" roughness={0.9} />
                </mesh>
              ))}

            {/* Floating Country Nameplate */}
            <Html position={[a.x, 195, a.z]} distanceFactor={2600} style={{ pointerEvents: "none" }}>
              <div
                className={`px-2 py-1 rounded text-xs font-mono whitespace-nowrap border shadow-md ${
                  isSel
                    ? "bg-white/95 border-blue-500 text-blue-900 font-bold"
                    : "bg-white/90 border-slate-300 text-slate-800"
                }`}
              >
                {c.country_id} · {c.name.toUpperCase()} {c.active_disasters > 0 ? "[ALERT]" : ""}
              </div>
            </Html>
          </group>
        );
      })}

      {/* Inter-Country 4-Lane Transcontinental Highways */}
      {HIGHWAY_LINKS.map(([idA, idB], idx) => {
        const A = COUNTRY_FLAT_ANCHORS[idA];
        const B = COUNTRY_FLAT_ANCHORS[idB];
        const dx = B.x - A.x;
        const dz = B.z - A.z;
        const len = Math.hypot(dx, dz);
        const angle = Math.atan2(dx, dz);
        return (
          <mesh
            key={idx}
            position={[(A.x + B.x) / 2, 0.55, (A.z + B.z) / 2]}
            rotation={[-Math.PI / 2, 0, -angle]}
          >
            <planeGeometry args={[32, len]} />
            <meshStandardMaterial map={roadTex} roughness={0.85} />
          </mesh>
        );
      })}

      {/* Instanced GTA Commercial Skyscrapers & Residential Apartments across all 7 Countries */}
      <instancedMesh ref={commMeshRef} args={[undefined, undefined, commBuildings.length]} castShadow receiveShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={commercialTex} roughness={0.28} metalness={0.42} />
      </instancedMesh>
      <instancedMesh ref={resMeshRef} args={[undefined, undefined, resBuildings.length]} castShadow receiveShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={residentialTex} roughness={0.8} metalness={0.05} />
      </instancedMesh>

      {/* 420 Instanced Boulevard & Forest Trees */}
      <instancedMesh ref={treesTrunkRef} args={[undefined, undefined, trees.length]}>
        <cylinderGeometry args={[0.5, 0.7, 1, 6]} />
        <meshStandardMaterial color="#6b4f35" roughness={0.95} />
      </instancedMesh>
      <instancedMesh ref={treesCanopyRef} args={[undefined, undefined, trees.length]} castShadow>
        <coneGeometry args={[1, 1.4, 7]} />
        <meshStandardMaterial color="#2f6b3a" roughness={0.85} />
      </instancedMesh>

      {/* 160 Moving GTA Vehicles + 240 Animated Pedestrians */}
      <instancedMesh ref={carsMeshRef} args={[undefined, undefined, vehicles.length]} castShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial roughness={0.3} metalness={0.5} />
      </instancedMesh>
      <instancedMesh ref={pedsMeshRef} args={[undefined, undefined, pedestrians.length]}>
        <capsuleGeometry args={[0.45, 0.7, 4, 6]} />
        <meshStandardMaterial roughness={0.85} />
      </instancedMesh>

      {/* Live Backend Hospitals across all 7 Countries */}
      {allHospitals.map((h) => {
        const [x, z] = geoToFlatWorld(h.location.lat, h.location.lon, countryById[h.country_id]);
        return (
          <group key={h.hospital_id} position={[x, 0, z]}>
            <mesh position={[0, 22, 0]}>
              <boxGeometry args={[46, 44, 36]} />
              <meshStandardMaterial color="#f8fafc" roughness={0.45} />
            </mesh>
            <mesh position={[0, 45, 0]}>
              <boxGeometry args={[20, 1.5, 6]} />
              <meshStandardMaterial color="#dc2626" emissive="#dc2626" emissiveIntensity={0.8} />
            </mesh>
            <mesh position={[0, 45, 0]}>
              <boxGeometry args={[6, 1.5, 20]} />
              <meshStandardMaterial color="#dc2626" emissive="#dc2626" emissiveIntensity={0.8} />
            </mesh>
          </group>
        );
      })}

      {/* Live Backend Ambulances positioned on flat world */}
      {allAmbulances.map((a) => {
        const [ax, az] = geoToFlatWorld(a.location.lat, a.location.lon, countryById[a.country_id]);
        const isActive = a.status !== "AVAILABLE";
        return (
          <group key={a.ambulance_id} position={[ax, 3.5, az]}>
            <mesh>
              <boxGeometry args={[7, 5, 14]} />
              <meshStandardMaterial color="#ffffff" roughness={0.35} />
            </mesh>
            <mesh position={[0, 3.2, 3]}>
              <boxGeometry args={[4.5, 1.2, 2.2]} />
              <meshStandardMaterial color={isActive ? "#ef4444" : "#38bdf8"} emissive={isActive ? "#ef4444" : "#0284c7"} emissiveIntensity={isActive ? 2.0 : 0.4} />
            </mesh>
          </group>
        );
      })}

      {/* Live Backend Fire & Rescue Units */}
      {allFireUnits.map((f) => {
        const [fx, fz] = geoToFlatWorld(f.location.lat, f.location.lon, countryById[f.country_id]);
        const active = f.status === "ON_SCENE" || f.status === "DISPATCHED";
        return (
          <group key={f.unit_id} position={[fx, 4, fz]}>
            <mesh>
              <boxGeometry args={[7.5, 6, 16]} />
              <meshStandardMaterial color="#dc2626" roughness={0.4} />
            </mesh>
            <mesh position={[0, 3.8, 3.5]}>
              <boxGeometry args={[4.5, 1.2, 2.2]} />
              <meshStandardMaterial color="#fef08a" emissive="#f59e0b" emissiveIntensity={active ? 2.2 : 0.4} />
            </mesh>
          </group>
        );
      })}

      {/* Active Swarm Coverage Perimeter Rings */}
      {activeSwarms
        .filter((sw) => sw.status === "ACTIVE")
        .map((sw) => {
          const [sx, sz] = geoToFlatWorld(sw.target_center.lat, sw.target_center.lon, countryById[sw.country_id]);
          return (
            <mesh key={sw.swarm_id} rotation={[-Math.PI / 2, 0, 0]} position={[sx, 12, sz]}>
              <ringGeometry args={[180, 195, 48]} />
              <meshBasicMaterial color="#10b981" transparent opacity={0.55} side={THREE.DoubleSide} />
            </mesh>
          );
        })}

      {/* Live Backend Relief Shelters */}
      {allShelters.map((s) => {
        const [x, z] = geoToFlatWorld(s.location.lat, s.location.lon, countryById[s.country_id]);
        return (
          <mesh key={s.shelter_id} position={[x, 9, z]}>
            <cylinderGeometry args={[16, 20, 18, 8]} />
            <meshStandardMaterial color="#0284c7" roughness={0.55} />
          </mesh>
        );
      })}

      {/* Quantum-Inspired Phase Telemetry Halo over Active Country */}
      <mesh
        ref={quantumRingRef}
        rotation={[-Math.PI / 2, 0, 0]}
        position={[
          (COUNTRY_FLAT_ANCHORS[selectedCountryId]?.x ?? 0),
          14,
          (COUNTRY_FLAT_ANCHORS[selectedCountryId]?.z ?? 0),
        ]}
      >
        <ringGeometry args={[520, 540, 96]} />
        <meshBasicMaterial color="#38bdf8" transparent opacity={0.35} side={THREE.DoubleSide} />
      </mesh>

      {/* Live Backend Drones (All 98 across 7 Countries with smooth banking motion) */}
      <group ref={liveDronesRef}>
      {allDrones.map((d) => {
        const [x, z] = geoToFlatWorld(d.location.lat, d.location.lon, countryById[d.country_id]);
        const y = d.status === "IN_FLIGHT" || d.status === "ASSIGNED" ? 165 : 85;
        const color = d.status === "DESTROYED" ? "#ef4444" : d.status === "IN_FLIGHT" ? "#22c55e" : "#38bdf8";
        return (
          <group key={d.drone_id} position={[x, y, z]}>
            <mesh>
              <octahedronGeometry args={[9, 0]} />
              <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.9} />
            </mesh>
            <mesh position={[0, 1.5, 0]}>
              <boxGeometry args={[22, 1.5, 2.2]} />
              <meshStandardMaterial color="#e2e8f0" metalness={0.7} roughness={0.25} />
            </mesh>
            <mesh position={[0, 1.5, 0]}>
              <boxGeometry args={[2.2, 1.5, 22]} />
              <meshStandardMaterial color="#e2e8f0" metalness={0.7} roughness={0.25} />
            </mesh>
            <Line points={[[0, 0, 0], [0, -y, 0]]} color={color} lineWidth={0.8} transparent opacity={0.28} />
          </group>
        );
      })}
      </group>

      {/* Active Disasters (Cyclone Funnel, Flood Pool, Fire Glow) */}
      <group ref={cycloneRef}>
        {disasters
          .filter((d) => d.status === "ACTIVE")
          .map((ev) => {
            const [x, z] = geoToFlatWorld(ev.origin.lat, ev.origin.lon, countryById[ev.country_id]);
            if (ev.disaster_type === "CYCLONE") {
              return (
                <mesh key={ev.event_id} position={[x, 210, z]}>
                  <coneGeometry args={[260, 420, 24, 1, true]} />
                  <meshStandardMaterial color="#cbd5e1" transparent opacity={0.32} side={THREE.DoubleSide} />
                </mesh>
              );
            }
            if (ev.disaster_type === "FLOOD") {
              return (
                <mesh key={ev.event_id} rotation={[-Math.PI / 2, 0, 0]} position={[x, 2.2, z]}>
                  <circleGeometry args={[Math.max(220, ev.radius_km * 35), 32]} />
                  <meshStandardMaterial color="#0ea5e9" transparent opacity={0.5} />
                </mesh>
              );
            }
            return (
              <mesh key={ev.event_id} position={[x, 45, z]}>
                <sphereGeometry args={[85, 16, 16]} />
                <meshStandardMaterial color="#f97316" emissive="#ea580c" emissiveIntensity={1.6} transparent opacity={0.62} />
              </mesh>
            );
          })}
      </group>

      {/* Candidate 3D Drone Routes from JARVIS / Route Explorer */}
      {candidateRoutes.slice(0, 10).map((rc) => {
        const c = countryById[selectedCountryId];
        const pts = rc.waypoints.map((w) => {
          const [wx, wz] = geoToFlatWorld(w.lat, w.lon, c);
          return new THREE.Vector3(wx, Math.max(110, w.elevation_m * 1.4), wz);
        });
        if (pts.length < 2) return null;
        return (
          <Line
            key={rc.route_id}
            points={pts}
            color={rc.feasible ? "#22c55e" : "#ef4444"}
            lineWidth={rc.feasible ? 3.0 : 1.5}
          />
        );
      })}

      <OrbitControls ref={controlsRef} maxPolarAngle={Math.PI / 2.08} minDistance={120} maxDistance={7800} />
    </>
  );
};

export const BigFlatOpenWorld3D: React.FC<BigFlatWorldProps> = (props) => {
  const [timeOfDay, setTimeOfDay] = useState<"golden" | "day" | "night">("day");
  const [cameraPreset, setCameraPreset] = useState<"continent" | "country" | "street">("country");

  return (
    <div className="w-full h-full relative bg-[#E8F1F8] select-none">
      <Canvas
        shadows
        camera={{ position: [620, 460, 780], fov: 48, near: 4, far: 24000 }}
        gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.08 }}
      >
        <BigFlatWorldScene {...props} timeOfDay={timeOfDay} cameraPreset={cameraPreset} />
      </Canvas>

      {/* Bottom-Left GTA Square Radar Minimap of All 7 Countries */}
      <div className="absolute bottom-4 left-4 w-48 h-36 rounded bg-white/95 border border-slate-300 shadow-md p-2 shadow-lg">
        <div className="text-[9px] font-mono text-slate-500 flex justify-between mb-1">
          <span>CONTINENT RADAR (10×10 KM)</span>
          <span className="text-emerald-400">7 NATIONS</span>
        </div>
        <div className="relative w-full h-[104px] bg-[#E8F1F8] rounded-sm border border-slate-300 overflow-hidden">
          {props.countries.map((c) => {
            const a = COUNTRY_FLAT_ANCHORS[c.country_id];
            if (!a) return null;
            const leftPct = ((a.x + 4200) / 8400) * 100;
            const topPct = ((a.z + 4200) / 8400) * 100;
            const isSel = c.country_id === props.selectedCountryId;
            return (
              <button
                key={c.country_id}
                onClick={() => props.onSelectCountry(c.country_id)}
                title={c.name}
                className={`absolute -translate-x-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full border ${
                  c.active_disasters > 0
                    ? "bg-red-500 border-white animate-pulse"
                    : isSel
                    ? "bg-sky-400 border-white"
                    : "bg-emerald-500/80 border-slate-900"
                }`}
                style={{ left: `${leftPct}%`, top: `${topPct}%` }}
              />
            );
          })}
        </div>
      </div>

      {/* Bottom-Right Camera & Time-of-Day Bar */}
      <div className="absolute bottom-4 right-4 flex items-center gap-1.5 bg-white/95 border border-slate-300 shadow-sm rounded px-2.5 py-1.5 text-[11px] font-mono">
        {(["continent", "country", "street"] as const).map((p) => (
          <button
            key={p}
            onClick={() => setCameraPreset(p)}
            className={`px-2 py-0.5 rounded uppercase ${cameraPreset === p ? "bg-sky-600 text-white" : "text-slate-700 hover:bg-slate-800"}`}
          >
            {p}
          </button>
        ))}
        <span className="text-slate-600">|</span>
        {(["golden", "day", "night"] as const).map((tod) => (
          <button
            key={tod}
            onClick={() => setTimeOfDay(tod)}
            className={`px-2 py-0.5 rounded uppercase ${timeOfDay === tod ? "bg-amber-600 text-white" : "text-slate-700 hover:bg-slate-800"}`}
          >
            {tod}
          </button>
        ))}
      </div>
    </div>
  );
};
