import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import {
  AdaptiveDpr,
  Html,
  Line,
  OrbitControls,
  PerformanceMonitor,
} from "@react-three/drei";
import {
  Bloom,
  EffectComposer,
  ToneMapping,
  Vignette,
} from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";
import * as THREE from "three";
import type { CountrySummary, DisasterEvent, GeoPoint } from "../shared/globalTypes";
import {
  createBuildingFacadeTexture,
  createCommercialRoughnessMap,
  createResidentialBumpMap,
} from "./textures";
import { RealisticNPCs3D } from "./RealisticNPCs3D";
import { DisasterFootprint } from "./DisasterFootprint";
import { IntroCameraRig } from "./IntroCameraRig";

/**
 * 10,000m x 10,000m Continuous Flat 7-Country Architectural Diorama Open World.
 * Bright, crisp sunlit architectural model aesthetic with iconic landmarks,
 * winding turquoise Veridia River with rocky pebble banks, multi-tower suspension
 * bridges, Central Parks, coastal harbor ferries, drifting fluffy clouds,
 * 160 diorama vehicles, 220 articulated RealisticNPCs3D, and live backend assets.
 */
export const COUNTRY_FLAT_ANCHORS: Record<
  string,
  { x: number; z: number; radius: number; ground: string }
> = {
  "COUNTRY-01": { x: 2600, z: -1200, radius: 1350, ground: "#8ec182" }, // Aurelia Coast (East Coast)
  "COUNTRY-02": { x: 0, z: -2700, radius: 1350, ground: "#9ea89d" }, // Valtoria Highlands (North)
  "COUNTRY-03": { x: 0, z: 0, radius: 1450, ground: "#7eb974" }, // Veridia Basin (Central River)
  "COUNTRY-04": { x: -2500, z: -400, radius: 1450, ground: "#a5c272" }, // Solara Plains (West Farmland)
  "COUNTRY-05": { x: -2100, z: 2200, radius: 1300, ground: "#8f98a1" }, // Ferros Industrial (Southwest)
  "COUNTRY-06": { x: -2400, z: -2600, radius: 1400, ground: "#dfc295" }, // Kalahar Steppe (Northwest Arid)
  "COUNTRY-07": { x: 1800, z: 2200, radius: 1400, ground: "#619b62" }, // Sylva Reserve (Southeast Forest)
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

const SEDAN_COLORS = [
  "#2563eb",
  "#10b981",
  "#f97316",
  "#f8fafc",
  "#0ea5e9",
  "#64748b",
  "#8b5cf6",
  "#14b8a6",
];

const WARM_MIDRISE_TINTS = [
  "#e7cbb0", // warm sandstone
  "#d99b78", // terracotta brick
  "#efe5d5", // cream limestone
  "#c98566", // red-brown brick
  "#dce6ef", // pale architectural slate
  "#e2d2bc", // warm travertine
];

const TREE_GREENS = ["#4ea843", "#67bd52", "#3c8e39"];
const PEBBLE_COLORS = ["#c7c1b6", "#a8a298", "#d8d3c9", "#918c84", "#b8b0a3"];

function seededNoise(i: number): number {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453123;
  return x - Math.floor(x);
}

/** Winding Veridia River centerline Z for a given X in [-1800, 4800]. */
function veridiaRiverZ(x: number): number {
  return 210 + Math.sin(x * 0.00145) * 195 + Math.cos(x * 0.00072 + 0.6) * 95;
}

/** Clean 4-lane architectural diorama asphalt with double-yellow centerline & sidewalks. */
function createDioramaAsphaltTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 256;
  const ctx = c.getContext("2d")!;

  // Light concrete sidewalks on edges
  ctx.fillStyle = "#d5dce3";
  ctx.fillRect(0, 0, 256, 256);
  ctx.fillStyle = "#bcc5cf";
  for (let y = 0; y < 256; y += 32) {
    ctx.fillRect(0, y, 22, 2);
    ctx.fillRect(234, y, 22, 2);
  }

  // Crisp charcoal asphalt roadbed
  ctx.fillStyle = "#3a424d";
  ctx.fillRect(22, 0, 212, 256);

  // Subtle grain
  for (let i = 0; i < 900; i++) {
    const gx = 24 + seededNoise(i * 3) * 208;
    const gy = seededNoise(i * 3 + 1) * 256;
    ctx.fillStyle = i % 2 === 0 ? "rgba(255,255,255,0.035)" : "rgba(0,0,0,0.05)";
    ctx.fillRect(gx, gy, 2, 2);
  }

  // Double-yellow centerline
  ctx.fillStyle = "#facc15";
  ctx.fillRect(124, 0, 3, 256);
  ctx.fillRect(130, 0, 3, 256);

  // Dashed white lane dividers
  ctx.fillStyle = "#f1f5f9";
  for (let y = 10; y < 256; y += 42) {
    ctx.fillRect(74, y, 3, 22);
    ctx.fillRect(179, y, 3, 22);
  }

  // Solid white curb lines
  ctx.fillStyle = "#cbd5e1";
  ctx.fillRect(27, 0, 2, 256);
  ctx.fillRect(227, 0, 2, 256);

  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(1, 26);
  tex.anisotropy = 8;
  return tex;
}

/** Crisp white zebra crosswalk stripe texture. */
function createZebraCrosswalkTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 64;
  const ctx = c.getContext("2d")!;
  ctx.clearRect(0, 0, 256, 64);
  ctx.fillStyle = "#f8fafc";
  const stripes = 8;
  const sw = 256 / stripes;
  for (let i = 0; i < stripes; i++) {
    ctx.fillRect(i * sw + 6, 6, sw - 12, 52);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = 4;
  return tex;
}

/** Bright turquoise-blue architectural diorama water ripple texture. */
function createDioramaWaterTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 256;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = "#3ba4d9";
  ctx.fillRect(0, 0, 256, 256);

  for (let i = 0; i < 380; i++) {
    const x = seededNoise(i * 7) * 256;
    const y = seededNoise(i * 7 + 1) * 256;
    const w = 16 + seededNoise(i * 7 + 2) * 34;
    const h = 2 + seededNoise(i * 7 + 3) * 2.5;
    ctx.fillStyle = i % 3 === 0 ? "rgba(255,255,255,0.22)" : "rgba(18, 92, 138, 0.16)";
    ctx.fillRect(x, y, w, h);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(18, 4);
  tex.anisotropy = 4;
  return tex;
}

/** Art Deco warm limestone skyscraper facade with vertical fluted mullions. */
function createArtDecoFacadeTexture(dayMode: boolean): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 512;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = dayMode ? "#e6dac7" : "#404654";
  ctx.fillRect(0, 0, 256, 512);

  const cols = 8;
  const rows = 20;
  const cw = 256 / cols;
  const ch = 512 / rows;

  for (let col = 0; col < cols; col++) {
    // Raised vertical limestone piers
    ctx.fillStyle = dayMode ? "#f2e9da" : "#4b5263";
    ctx.fillRect(col * cw, 0, 6, 512);
    for (let row = 0; row < rows; row++) {
      const n = seededNoise(row * 31 + col * 17);
      const lit = !dayMode && n > 0.55;
      ctx.fillStyle = lit
        ? "#fde68a"
        : dayMode
        ? "#5f758a"
        : "#1e293b";
      ctx.fillRect(col * cw + 8, row * ch + 4, cw - 12, ch - 8);
    }
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 8;
  return tex;
}

/** Tapered blue-glass landmark spire tower facade texture. */
function createBlueGlassSpireTexture(dayMode: boolean): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 512;
  const ctx = c.getContext("2d")!;
  const grad = ctx.createLinearGradient(0, 0, 0, 512);
  if (dayMode) {
    grad.addColorStop(0, "#9ad0f5");
    grad.addColorStop(0.5, "#63a9dc");
    grad.addColorStop(1, "#3c7db3");
  } else {
    grad.addColorStop(0, "#23466e");
    grad.addColorStop(1, "#102138");
  }
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 256, 512);

  // Crisp architectural curtain-wall grid
  ctx.strokeStyle = dayMode ? "rgba(255,255,255,0.28)" : "rgba(148,197,255,0.22)";
  ctx.lineWidth = 2;
  for (let x = 0; x <= 256; x += 24) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, 512);
    ctx.stroke();
  }
  for (let y = 0; y <= 512; y += 18) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(256, y);
    ctx.stroke();
  }

  if (!dayMode) {
    for (let r = 0; r < 28; r++) {
      for (let col = 0; col < 10; col++) {
        if (seededNoise(r * 23 + col * 11) > 0.68) {
          ctx.fillStyle = "rgba(224, 242, 254, 0.72)";
          ctx.fillRect(col * 24 + 4, r * 18 + 4, 16, 10);
        }
      }
    }
  }

  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 8;
  return tex;
}

function geoToFlatWorld(
  lat: number,
  lon: number,
  country: CountrySummary | undefined
): [number, number] {
  if (!country) return [0, 0];
  const anchor = COUNTRY_FLAT_ANCHORS[country.country_id] || { x: 0, z: 0 };
  const dx = THREE.MathUtils.clamp((lon - country.center.lon) * 850, -900, 900);
  const dz = THREE.MathUtils.clamp(-(lat - country.center.lat) * 850, -900, 900);
  return [anchor.x + dx, anchor.z + dz];
}

/** Build a smooth winding ribbon geometry for the Veridia River. */
function buildWindingRiverGeometry(
  xStart: number,
  xEnd: number,
  segments: number,
  halfWidth: number
): THREE.BufferGeometry {
  const positions: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];

  for (let i = 0; i <= segments; i++) {
    const u = i / segments;
    const x = THREE.MathUtils.lerp(xStart, xEnd, u);
    const z = veridiaRiverZ(x);
    const dx = 12;
    const dz = veridiaRiverZ(x + dx) - veridiaRiverZ(x - dx);
    const len = Math.hypot(2 * dx, dz) || 1;
    // Perpendicular normal in XZ plane
    const nx = -dz / len;
    const nz = (2 * dx) / len;
    // Widen slightly as river reaches the eastern coastal harbor
    const w = halfWidth * (1 + u * 0.55);

    positions.push(x + nx * w, 0, z + nz * w);
    positions.push(x - nx * w, 0, z - nz * w);
    uvs.push(u * 12, 0);
    uvs.push(u * 12, 1);

    if (i < segments) {
      const base = i * 2;
      indices.push(base, base + 1, base + 2);
      indices.push(base + 1, base + 3, base + 2);
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geo.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geo.setIndex(indices);
  geo.computeVertexNormals();
  return geo;
}

export interface DioramaOpenWorldProps {
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

/**
 * CameraFlyRig: ONLY lerps during active country/preset transitions,
 * and stops immediately upon arrival OR when the user drags/zooms OrbitControls.
 */
const CameraFlyRig: React.FC<{
  selectedCountryId: string;
  preset: "continent" | "country" | "street";
  controlsRef: React.RefObject<any>;
  transitioningRef: React.MutableRefObject<boolean>;
  introActiveRef: React.MutableRefObject<boolean>;
}> = ({ selectedCountryId, preset, controlsRef, transitioningRef, introActiveRef }) => {
  const { camera } = useThree();
  const anchor = COUNTRY_FLAT_ANCHORS[selectedCountryId] || { x: 0, z: 0 };

  const targetPos = useMemo(() => {
    if (preset === "continent") return new THREE.Vector3(0, 4100, 4700);
    if (preset === "street") return new THREE.Vector3(anchor.x + 155, 68, anchor.z + 245);
    return new THREE.Vector3(anchor.x + 640, 480, anchor.z + 780);
  }, [anchor.x, anchor.z, preset]);

  const lookTarget = useMemo(() => {
    if (preset === "continent") return new THREE.Vector3(0, 0, 0);
    return new THREE.Vector3(anchor.x, 12, anchor.z);
  }, [anchor.x, anchor.z, preset]);

  useEffect(() => {
    if (introActiveRef.current) return;
    transitioningRef.current = true;
  }, [selectedCountryId, preset, transitioningRef, introActiveRef]);

  useEffect(() => {
    const ctrl = controlsRef.current;
    if (!ctrl) return;
    const stopTransition = () => {
      transitioningRef.current = false;
    };
    ctrl.addEventListener("start", stopTransition);
    return () => ctrl.removeEventListener("start", stopTransition);
  }, [controlsRef, transitioningRef]);

  useFrame((_, delta) => {
    if (introActiveRef.current || !transitioningRef.current) return;
    const alpha = Math.min(1, delta * 2.8);
    camera.position.lerp(targetPos, alpha);
    if (controlsRef.current) {
      controlsRef.current.target.lerp(lookTarget, alpha);
      controlsRef.current.update();
    }
    const posDone = camera.position.distanceTo(targetPos) < 4.0;
    const targetDone =
      !controlsRef.current || controlsRef.current.target.distanceTo(lookTarget) < 4.0;
    if (posDone && targetDone) {
      transitioningRef.current = false;
    }
  });

  return null;
};

/** Iconic Stepped Art Deco Stone Skyscraper with Spire (Empire State / Chrysler style). */
const ArtDecoSkyscraper: React.FC<{
  position: [number, number, number];
  scale?: number;
  facadeTex: THREE.CanvasTexture;
}> = ({ position, scale = 1, facadeTex }) => (
  <group position={position} scale={[scale, scale, scale]}>
    {/* Podium base */}
    <mesh position={[0, 14, 0]} castShadow receiveShadow>
      <boxGeometry args={[52, 28, 44]} />
      <meshStandardMaterial map={facadeTex} color="#efe3cf" roughness={0.62} />
    </mesh>
    {/* Mid tower shaft */}
    <mesh position={[0, 62, 0]} castShadow receiveShadow>
      <boxGeometry args={[38, 72, 34]} />
      <meshStandardMaterial map={facadeTex} color="#eadcc6" roughness={0.58} />
    </mesh>
    {/* Upper setback */}
    <mesh position={[0, 114, 0]} castShadow receiveShadow>
      <boxGeometry args={[28, 36, 26]} />
      <meshStandardMaterial map={facadeTex} color="#f3e8d7" roughness={0.55} />
    </mesh>
    {/* Crown tier */}
    <mesh position={[0, 142, 0]} castShadow>
      <boxGeometry args={[18, 20, 18]} />
      <meshStandardMaterial color="#f5ecdc" roughness={0.45} metalness={0.18} />
    </mesh>
    {/* Art Deco tapered cap */}
    <mesh position={[0, 160, 0]} castShadow>
      <cylinderGeometry args={[3.5, 11, 18, 8]} />
      <meshStandardMaterial color="#d8dee6" metalness={0.65} roughness={0.28} />
    </mesh>
    {/* Spire needle */}
    <mesh position={[0, 186, 0]}>
      <cylinderGeometry args={[0.5, 2.2, 36, 8]} />
      <meshStandardMaterial color="#e2e8f0" metalness={0.8} roughness={0.2} />
    </mesh>
  </group>
);

/** Iconic Tapered Blue-Glass Spire Tower (One WTC architectural diorama style). */
const TaperedGlassTower: React.FC<{
  position: [number, number, number];
  scale?: number;
  glassTex: THREE.CanvasTexture;
}> = ({ position, scale = 1, glassTex }) => (
  <group position={position} scale={[scale, scale, scale]}>
    {/* Square glass plinth */}
    <mesh position={[0, 16, 0]} castShadow receiveShadow>
      <boxGeometry args={[42, 32, 42]} />
      <meshStandardMaterial map={glassTex} color="#b8dcf7" roughness={0.18} metalness={0.48} />
    </mesh>
    {/* Tapered 4-sided crystal obelisk */}
    <mesh position={[0, 98, 0]} rotation={[0, Math.PI / 4, 0]} castShadow receiveShadow>
      <cylinderGeometry args={[19, 29, 136, 4]} />
      <meshStandardMaterial map={glassTex} color="#c5e4fb" roughness={0.14} metalness={0.55} />
    </mesh>
    {/* Rooftop parapet & comms ring */}
    <mesh position={[0, 169, 0]}>
      <cylinderGeometry args={[12, 13, 6, 16]} />
      <meshStandardMaterial color="#e2e8f0" metalness={0.65} roughness={0.25} />
    </mesh>
    {/* Spire mast */}
    <mesh position={[0, 194, 0]}>
      <cylinderGeometry args={[0.6, 2.0, 46, 8]} />
      <meshStandardMaterial color="#f1f5f9" metalness={0.82} roughness={0.18} />
    </mesh>
  </group>
);

/** Elevated Water Tower on Metal Lattice Stilts (diorama hallmark). */
const ElevatedWaterTower: React.FC<{ position: [number, number, number] }> = ({ position }) => (
  <group position={position}>
    {/* 4 angled support legs */}
    {[
      [-7, -7],
      [7, -7],
      [-7, 7],
      [7, 7],
    ].map(([lx, lz], idx) => (
      <mesh key={idx} position={[lx, 13, lz]} castShadow>
        <cylinderGeometry args={[0.75, 1.0, 26, 6]} />
        <meshStandardMaterial color="#64748b" metalness={0.55} roughness={0.45} />
      </mesh>
    ))}
    {/* Cross brace ring */}
    <mesh position={[0, 12, 0]}>
      <boxGeometry args={[15, 1.2, 15]} />
      <meshStandardMaterial color="#94a3b8" metalness={0.5} roughness={0.5} wireframe />
    </mesh>
    {/* Platform deck */}
    <mesh position={[0, 26, 0]} castShadow>
      <cylinderGeometry args={[11.5, 11.5, 1.8, 16]} />
      <meshStandardMaterial color="#cbd5e1" roughness={0.6} />
    </mesh>
    {/* Cylindrical tank */}
    <mesh position={[0, 36, 0]} castShadow>
      <cylinderGeometry args={[10.5, 10.5, 18, 18]} />
      <meshStandardMaterial color="#d8e2ec" metalness={0.42} roughness={0.38} />
    </mesh>
    {/* Conical roof */}
    <mesh position={[0, 49, 0]} castShadow>
      <coneGeometry args={[11.6, 8.5, 18]} />
      <meshStandardMaterial color="#94a3b8" metalness={0.45} roughness={0.4} />
    </mesh>
  </group>
);

/** Circular Stone Water Fountain / Reservoir with sparkling turquoise basin & plume. */
const CircularStoneFountain: React.FC<{ position: [number, number, number] }> = ({ position }) => (
  <group position={position}>
    {/* Outer textured stone wall */}
    <mesh position={[0, 5.5, 0]} castShadow receiveShadow>
      <cylinderGeometry args={[28, 30, 11, 20, 1, true]} />
      <meshStandardMaterial color="#c8c2b7" roughness={0.92} side={THREE.DoubleSide} />
    </mesh>
    {/* Stone coping rim */}
    <mesh position={[0, 11, 0]} rotation={[Math.PI / 2, 0, 0]} castShadow>
      <torusGeometry args={[28, 2.4, 8, 24]} />
      <meshStandardMaterial color="#dbd6cc" roughness={0.86} />
    </mesh>
    {/* Sparkling turquoise water fill */}
    <mesh position={[0, 8.2, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <circleGeometry args={[26.5, 24]} />
      <meshStandardMaterial color="#38bdf8" roughness={0.14} metalness={0.28} />
    </mesh>
    {/* Central stone pedestal & spray plume */}
    <mesh position={[0, 10, 0]} castShadow>
      <cylinderGeometry args={[2.2, 3.6, 12, 10]} />
      <meshStandardMaterial color="#d6d3d1" roughness={0.8} />
    </mesh>
    <mesh position={[0, 18.5, 0]}>
      <coneGeometry args={[6.5, 9, 12]} />
      <meshStandardMaterial color="#e0f2fe" transparent opacity={0.78} roughness={0.1} />
    </mesh>
  </group>
);

/** Multi-Tower Architectural Suspension Bridge with Catenary Cables. */
const SuspensionBridge: React.FC<{
  position: [number, number, number];
  spanLength?: number;
  rotationY?: number;
}> = ({ position, spanLength = 250, rotationY = 0 }) => {
  const half = spanLength / 2;
  const towerOffset = spanLength * 0.28;

  const { leftCable, rightCable } = useMemo(() => {
    const lPts: [number, number, number][] = [];
    const rPts: [number, number, number][] = [];
    const steps = 20;
    for (let i = 0; i <= steps; i++) {
      const u = i / steps;
      const z = THREE.MathUtils.lerp(-half, half, u);
      // Realistic catenary sag between towers and anchorages
      let y = 12;
      if (Math.abs(z) <= towerOffset) {
        const norm = z / towerOffset;
        y = 18 + norm * norm * 40;
      } else {
        const outerNorm = (Math.abs(z) - towerOffset) / (half - towerOffset);
        y = 58 * (1 - outerNorm) + 12 * outerNorm;
      }
      lPts.push([-17, y, z]);
      rPts.push([17, y, z]);
    }
    return { leftCable: lPts, rightCable: rPts };
  }, [half, towerOffset]);

  return (
    <group position={position} rotation={[0, rotationY, 0]}>
      {/* Bridge Roadway Deck */}
      <mesh position={[0, 11, 0]} castShadow receiveShadow>
        <boxGeometry args={[38, 4.5, spanLength]} />
        <meshStandardMaterial color="#64748b" roughness={0.8} />
      </mesh>
      {/* Asphalt surface stripe */}
      <mesh position={[0, 13.4, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[32, spanLength - 4]} />
        <meshStandardMaterial color="#3b4452" roughness={0.85} />
      </mesh>
      {/* Twin Stone/Sandstone Bridge Towers */}
      {[-towerOffset, towerOffset].map((tz, tIdx) => (
        <group key={tIdx} position={[0, 0, tz]}>
          <mesh position={[-17, 32, 0]} castShadow>
            <boxGeometry args={[6.5, 64, 9]} />
            <meshStandardMaterial color="#cbbba3" roughness={0.78} />
          </mesh>
          <mesh position={[17, 32, 0]} castShadow>
            <boxGeometry args={[6.5, 64, 9]} />
            <meshStandardMaterial color="#cbbba3" roughness={0.78} />
          </mesh>
          {/* Upper & mid cross-beams */}
          <mesh position={[0, 56, 0]} castShadow>
            <boxGeometry args={[39, 6, 8]} />
            <meshStandardMaterial color="#d6c8b2" roughness={0.75} />
          </mesh>
          <mesh position={[0, 34, 0]} castShadow>
            <boxGeometry args={[34, 4.5, 7]} />
            <meshStandardMaterial color="#c4b39a" roughness={0.78} />
          </mesh>
        </group>
      ))}
      {/* Main Catenary Suspension Cables */}
      <Line points={leftCable} color="#e2e8f0" lineWidth={2.2} />
      <Line points={rightCable} color="#e2e8f0" lineWidth={2.2} />
      {/* Vertical Suspender Cables */}
      {[-0.36, -0.2, -0.08, 0.08, 0.2, 0.36].map((frac, idx) => {
        const z = frac * spanLength;
        const norm = Math.min(1, Math.abs(z) / towerOffset);
        const topY = Math.abs(z) <= towerOffset ? 18 + norm * norm * 40 : 38;
        const h = Math.max(4, topY - 12);
        return (
          <React.Fragment key={idx}>
            <mesh position={[-17, 12 + h / 2, z]}>
              <cylinderGeometry args={[0.35, 0.35, h, 4]} />
              <meshStandardMaterial color="#cbd5e1" metalness={0.5} />
            </mesh>
            <mesh position={[17, 12 + h / 2, z]}>
              <cylinderGeometry args={[0.35, 0.35, h, 4]} />
              <meshStandardMaterial color="#cbd5e1" metalness={0.5} />
            </mesh>
          </React.Fragment>
        );
      })}
    </group>
  );
};

const DioramaWorldScene: React.FC<
  DioramaOpenWorldProps & {
    timeOfDay: "day" | "golden" | "night";
    cameraPreset: "continent" | "country" | "street";
    quality: "high" | "low";
    prefersReducedMotion: boolean;
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
  quality,
  prefersReducedMotion,
}) => {
  const controlsRef = useRef<any>(null);
  const transitioningRef = useRef<boolean>(false);
  const introActiveRef = useRef<boolean>(false);

  // InstancedMesh refs for 60 FPS diorama rendering
  const commMeshRef = useRef<THREE.InstancedMesh>(null);
  const resMeshRef = useRef<THREE.InstancedMesh>(null);
  const carBodyRef = useRef<THREE.InstancedMesh>(null);
  const carCabinRef = useRef<THREE.InstancedMesh>(null);
  const treeTrunkRef = useRef<THREE.InstancedMesh>(null);
  const treeCanopyARef = useRef<THREE.InstancedMesh>(null);
  const treeCanopyBRef = useRef<THREE.InstancedMesh>(null);
  const treeCanopyCRef = useRef<THREE.InstancedMesh>(null);
  const pebbleRef = useRef<THREE.InstancedMesh>(null);
  const cloudPuffRef = useRef<THREE.InstancedMesh>(null);
  const waveCrestRef = useRef<THREE.InstancedMesh>(null);

  const ferriesGroupRef = useRef<THREE.Group>(null);
  const liveDronesRef = useRef<THREE.Group>(null);
  const cycloneRef = useRef<THREE.Group>(null);
  const quantumRingRef = useRef<THREE.Mesh>(null);

  const dummy = useMemo(() => new THREE.Object3D(), []);

  const dayMode = timeOfDay !== "night";
  const isGolden = timeOfDay === "golden";
  const hasActiveDisaster = useMemo(
    () => disasters.some((d) => d.status === "ACTIVE"),
    [disasters]
  );

  // Procedural CanvasTextures + shared geometries — ALL disposed on unmount
  const textures = useMemo(() => {
    return {
      commercial: createBuildingFacadeTexture("commercial", dayMode),
      residential: createBuildingFacadeTexture("residential", dayMode),
      commRough: createCommercialRoughnessMap(),
      resBump: createResidentialBumpMap(),
      asphalt: createDioramaAsphaltTexture(),
      crosswalk: createZebraCrosswalkTexture(),
      water: createDioramaWaterTexture(),
      artDeco: createArtDecoFacadeTexture(dayMode),
      blueGlass: createBlueGlassSpireTexture(dayMode),
    };
  }, [dayMode]);

  useEffect(() => {
    return () => {
      textures.commercial.dispose();
      textures.residential.dispose();
      textures.commRough.dispose();
      textures.resBump.dispose();
      textures.asphalt.dispose();
      textures.crosswalk.dispose();
      textures.water.dispose();
      textures.artDeco.dispose();
      textures.blueGlass.dispose();
    };
  }, [textures]);

  const riverGeo = useMemo(() => buildWindingRiverGeometry(-1750, 4800, 72, 76), []);
  useEffect(() => {
    return () => riverGeo.dispose();
  }, [riverGeo]);

  // Generate commercial towers + warm brick/sandstone mid-rises across all 7 countries
  const { commBuildings, resBuildings } = useMemo(() => {
    const comm: Array<{ x: number; z: number; w: number; h: number; d: number; color: THREE.Color }> = [];
    const res: Array<{ x: number; z: number; w: number; h: number; d: number; color: THREE.Color }> = [];
    const ids = Object.keys(COUNTRY_FLAT_ANCHORS);

    ids.forEach((cid, cIdx) => {
      const a = COUNTRY_FLAT_ANCHORS[cid];
      for (let i = 0; i < 82; i++) {
        const ang = i * 2.39996 + cIdx;
        const r = 68 + Math.sqrt(i) * 76;
        const x = a.x + Math.cos(ang) * r;
        const z = a.z + Math.sin(ang) * r;
        // Keep central boulevards, Central Park (+215,+215), and Veridia River clear
        if (Math.abs(x - a.x) < 36 || Math.abs(z - a.z) < 36) continue;
        if (Math.hypot(x - (a.x + 215), z - (a.z + 215)) < 155) continue;
        if (x > -1800 && x < 4800 && Math.abs(z - veridiaRiverZ(x)) < 115) continue;

        const seed = cIdx * 100 + i;
        if (r < 320) {
          comm.push({
            x,
            z,
            w: 28 + (seed % 4) * 7,
            h: 54 + ((seed * 19) % 115),
            d: 28 + ((seed + 2) % 4) * 7,
            color: new THREE.Color(
              seed % 3 === 0 ? "#dbeafe" : seed % 3 === 1 ? "#f1e8db" : "#e2e8f0"
            ),
          });
        } else {
          res.push({
            x,
            z,
            w: 22 + (seed % 3) * 6,
            h: 20 + ((seed * 13) % 34),
            d: 22 + ((seed + 1) % 3) * 6,
            color: new THREE.Color(WARM_MIDRISE_TINTS[seed % WARM_MIDRISE_TINTS.length]),
          });
        }
      }
    });
    return { commBuildings: comm, resBuildings: res };
  }, []);

  useEffect(() => {
    if (commMeshRef.current) {
      commBuildings.forEach((b, i) => {
        dummy.position.set(b.x, b.h / 2, b.z);
        dummy.scale.set(b.w, b.h, b.d);
        dummy.rotation.set(0, 0, 0);
        dummy.updateMatrix();
        commMeshRef.current!.setMatrixAt(i, dummy.matrix);
        commMeshRef.current!.setColorAt(i, b.color);
      });
      commMeshRef.current.instanceMatrix.needsUpdate = true;
      if (commMeshRef.current.instanceColor) commMeshRef.current.instanceColor.needsUpdate = true;
    }
    if (resMeshRef.current) {
      resBuildings.forEach((b, i) => {
        dummy.position.set(b.x, b.h / 2, b.z);
        dummy.scale.set(b.w, b.h, b.d);
        dummy.rotation.set(0, 0, 0);
        dummy.updateMatrix();
        resMeshRef.current!.setMatrixAt(i, dummy.matrix);
        resMeshRef.current!.setColorAt(i, b.color);
      });
      resMeshRef.current.instanceMatrix.needsUpdate = true;
      if (resMeshRef.current.instanceColor) resMeshRef.current.instanceColor.needsUpdate = true;
    }
  }, [commBuildings, resBuildings, dummy]);

  // Lush rounded multi-sphere tree clusters (Central Parks + boulevard & Sylva forest groves)
  const trees = useMemo(() => {
    const out: Array<{ x: number; z: number; h: number; r: number; color: THREE.Color }> = [];
    const ids = Object.keys(COUNTRY_FLAT_ANCHORS);

    ids.forEach((cid, cIdx) => {
      const a = COUNTRY_FLAT_ANCHORS[cid];

      // 28 lush rounded trees framing each city's Central Park around the winding blue pond
      const parkCx = a.x + 215;
      const parkCz = a.z + 215;
      for (let p = 0; p < 28; p++) {
        const ang = (p / 28) * Math.PI * 2 + cIdx * 0.3;
        const rad = 82 + (p % 3) * 20;
        const tx = parkCx + Math.cos(ang) * rad;
        const tz = parkCz + Math.sin(ang) * rad * 0.88;
        out.push({
          x: tx,
          z: tz,
          h: 13 + (p % 4) * 3.5,
          r: 9 + (p % 3) * 2.5,
          color: new THREE.Color(TREE_GREENS[(p + cIdx) % TREE_GREENS.length]),
        });
      }

      // Outer biome groves (dense in Sylva Reserve, sparse in Kalahar Steppe)
      const count = cid === "COUNTRY-07" ? 120 : cid === "COUNTRY-06" ? 16 : 38;
      for (let i = 0; i < count; i++) {
        const ang = i * 2.39996 + cIdx * 1.7;
        const dist = cid === "COUNTRY-07" ? 270 + Math.sqrt(i) * 92 : 430 + Math.sqrt(i) * 88;
        const tx = a.x + Math.cos(ang) * dist;
        const tz = a.z + Math.sin(ang) * dist;
        if (Math.abs(tx - a.x) < 42 || Math.abs(tz - a.z) < 42) continue;
        if (tx > -1800 && tx < 4800 && Math.abs(tz - veridiaRiverZ(tx)) < 110) continue;
        out.push({
          x: tx,
          z: tz,
          h: 15 + (i % 4) * 4,
          r: 10 + (i % 3) * 2.8,
          color: new THREE.Color(TREE_GREENS[(i + cIdx) % TREE_GREENS.length]),
        });
      }
    });
    return out;
  }, []);

  useEffect(() => {
    if (
      !treeTrunkRef.current ||
      !treeCanopyARef.current ||
      !treeCanopyBRef.current ||
      !treeCanopyCRef.current
    ) {
      return;
    }

    trees.forEach((tr, i) => {
      // Trunk
      dummy.position.set(tr.x, tr.h * 0.42, tr.z);
      dummy.scale.set(2.1, tr.h * 0.85, 2.1);
      dummy.rotation.set(0, 0, 0);
      dummy.updateMatrix();
      treeTrunkRef.current!.setMatrixAt(i, dummy.matrix);

      // Rounded multi-sphere foliage cluster (3 overlapping puffs per tree)
      dummy.position.set(tr.x, tr.h * 0.96, tr.z);
      dummy.scale.set(tr.r * 1.05, tr.r * 0.95, tr.r * 1.05);
      dummy.updateMatrix();
      treeCanopyARef.current!.setMatrixAt(i, dummy.matrix);
      treeCanopyARef.current!.setColorAt(i, tr.color);

      dummy.position.set(tr.x + tr.r * 0.48, tr.h * 0.84, tr.z + tr.r * 0.35);
      dummy.scale.set(tr.r * 0.78, tr.r * 0.75, tr.r * 0.78);
      dummy.updateMatrix();
      treeCanopyBRef.current!.setMatrixAt(i, dummy.matrix);
      treeCanopyBRef.current!.setColorAt(i, tr.color);

      dummy.position.set(tr.x - tr.r * 0.44, tr.h * 0.86, tr.z - tr.r * 0.36);
      dummy.scale.set(tr.r * 0.72, tr.r * 0.72, tr.r * 0.72);
      dummy.updateMatrix();
      treeCanopyCRef.current!.setMatrixAt(i, dummy.matrix);
      treeCanopyCRef.current!.setColorAt(i, tr.color);
    });

    treeTrunkRef.current.instanceMatrix.needsUpdate = true;
    treeCanopyARef.current.instanceMatrix.needsUpdate = true;
    treeCanopyBRef.current.instanceMatrix.needsUpdate = true;
    treeCanopyCRef.current.instanceMatrix.needsUpdate = true;
    if (treeCanopyARef.current.instanceColor) treeCanopyARef.current.instanceColor.needsUpdate = true;
    if (treeCanopyBRef.current.instanceColor) treeCanopyBRef.current.instanceColor.needsUpdate = true;
    if (treeCanopyCRef.current.instanceColor) treeCanopyCRef.current.instanceColor.needsUpdate = true;
  }, [trees, dummy]);

  // Rocky / pebble stone riverbanks hugging both sides of the winding Veridia River
  const riverPebbles = useMemo(() => {
    const pebbles: Array<{
      x: number;
      z: number;
      sx: number;
      sy: number;
      sz: number;
      ry: number;
      color: THREE.Color;
    }> = [];
    const steps = 170;
    for (let i = 0; i < steps; i++) {
      const u = i / (steps - 1);
      const x = THREE.MathUtils.lerp(-1720, 4720, u);
      const z = veridiaRiverZ(x);
      const halfW = 76 * (1 + u * 0.55) + 10;
      for (const side of [-1, 1]) {
        const jitterX = (seededNoise(i * 13 + side) - 0.5) * 18;
        const jitterZ = (seededNoise(i * 19 + side * 7) - 0.5) * 14;
        const r = 8 + seededNoise(i * 29 + side * 3) * 10;
        pebbles.push({
          x: x + jitterX,
          z: z + side * halfW + jitterZ,
          sx: r * 1.35,
          sy: r * 0.62,
          sz: r * 1.15,
          ry: seededNoise(i * 41 + side) * Math.PI,
          color: new THREE.Color(PEBBLE_COLORS[(i + (side > 0 ? 2 : 0)) % PEBBLE_COLORS.length]),
        });
      }
    }
    return pebbles;
  }, []);

  useEffect(() => {
    if (!pebbleRef.current) return;
    riverPebbles.forEach((p, i) => {
      dummy.position.set(p.x, p.sy * 0.45, p.z);
      dummy.scale.set(p.sx, p.sy, p.sz);
      dummy.rotation.set(0, p.ry, 0);
      dummy.updateMatrix();
      pebbleRef.current!.setMatrixAt(i, dummy.matrix);
      pebbleRef.current!.setColorAt(i, p.color);
    });
    pebbleRef.current.instanceMatrix.needsUpdate = true;
    if (pebbleRef.current.instanceColor) pebbleRef.current.instanceColor.needsUpdate = true;
  }, [riverPebbles, dummy]);

  // Fluffy stylized multi-sphere white clouds drifting gently above the 7 cities
  const cloudPuffs = useMemo(() => {
    const puffs: Array<{
      baseX: number;
      baseY: number;
      baseZ: number;
      rx: number;
      ry: number;
      rz: number;
      driftSpeed: number;
      phase: number;
    }> = [];
    const anchorList = Object.values(COUNTRY_FLAT_ANCHORS);
    anchorList.forEach((a, cIdx) => {
      // 4 fluffy clouds per country city
      for (let cl = 0; cl < 4; cl++) {
        const cx = a.x + (seededNoise(cIdx * 31 + cl * 7) - 0.5) * 1200;
        const cz = a.z + (seededNoise(cIdx * 43 + cl * 11) - 0.5) * 1200;
        const cy = 340 + (cl % 3) * 65 + seededNoise(cIdx * 17 + cl) * 40;
        const driftSpeed = 10 + (cl % 3) * 4.5;
        const phase = cIdx * 1.4 + cl * 2.1;
        // 6 overlapping puffs per cloud
        const offsets: Array<[number, number, number, number]> = [
          [0, 0, 0, 44],
          [-38, -6, 6, 34],
          [38, -5, -4, 35],
          [-18, 12, -10, 32],
          [20, 10, 12, 30],
          [0, -8, 18, 28],
        ];
        for (const [ox, oy, oz, rad] of offsets) {
          puffs.push({
            baseX: cx + ox,
            baseY: cy + oy,
            baseZ: cz + oz,
            rx: rad * 1.15,
            ry: rad * 0.78,
            rz: rad * 0.95,
            driftSpeed,
            phase,
          });
        }
      }
    });
    return puffs;
  }, []);

  // Stylized white wave crests floating on the coastal harbor & ocean
  const waveCrests = useMemo(() => {
    const waves: Array<{ x: number; z: number; len: number; phase: number }> = [];
    for (let i = 0; i < 90; i++) {
      const side = i % 3;
      const x =
        side === 0
          ? 4950 + seededNoise(i * 11) * 1400 // East coastal harbor
          : side === 1
          ? -4500 + seededNoise(i * 13) * 9000 // South bay
          : 3400 + seededNoise(i * 17) * 1400; // Harbor inlet
      const z =
        side === 0
          ? -3800 + seededNoise(i * 19) * 7600
          : side === 1
          ? 4950 + seededNoise(i * 23) * 1200
          : 420 + seededNoise(i * 29) * 1400;
      waves.push({
        x,
        z,
        len: 26 + seededNoise(i * 31) * 28,
        phase: i * 0.7,
      });
    }
    return waves;
  }, []);

  // 160 moving vehicles: yellow taxis, red city buses, and colorful sedans
  const vehicles = useMemo(() => {
    const ids = Object.keys(COUNTRY_FLAT_ANCHORS);
    return Array.from({ length: 160 }, (_, i) => {
      const kind: "taxi" | "bus" | "sedan" =
        i % 5 === 0 ? "taxi" : i % 8 === 0 ? "bus" : "sedan";
      const colorHex =
        kind === "taxi"
          ? "#facc15"
          : kind === "bus"
          ? "#dc2626"
          : SEDAN_COLORS[i % SEDAN_COLORS.length];

      if (i < 58) {
        const [fromId, toId] = HIGHWAY_LINKS[i % HIGHWAY_LINKS.length];
        return {
          mode: "highway" as const,
          kind,
          a: COUNTRY_FLAT_ANCHORS[fromId],
          b: COUNTRY_FLAT_ANCHORS[toId],
          axis: "x" as const,
          dir: 1 as const,
          speed: kind === "bus" ? 0.015 : 0.02 + (i % 5) * 0.004,
          phase: (i * 0.17) % 1,
          laneOffset: i % 2 === 0 ? 7.5 : -7.5,
          color: new THREE.Color(colorHex),
          cabinColor: new THREE.Color(kind === "bus" ? "#e0f2fe" : kind === "taxi" ? "#fef08a" : "#dbeafe"),
        };
      }

      const anchor = COUNTRY_FLAT_ANCHORS[ids[i % ids.length]];
      return {
        mode: "city" as const,
        kind,
        a: anchor,
        b: anchor,
        axis: i % 2 === 0 ? ("x" as const) : ("z" as const),
        dir: i % 4 < 2 ? (1 as const) : (-1 as const),
        speed: kind === "bus" ? 36 : 48 + (i % 4) * 14,
        phase: (i * 97) % 1300,
        laneOffset: 7.5,
        color: new THREE.Color(colorHex),
        cabinColor: new THREE.Color(kind === "bus" ? "#e0f2fe" : kind === "taxi" ? "#fef08a" : "#dbeafe"),
      };
    });
  }, []);

  useEffect(() => {
    if (carBodyRef.current && carCabinRef.current) {
      vehicles.forEach((v, i) => {
        carBodyRef.current!.setColorAt(i, v.color);
        carCabinRef.current!.setColorAt(i, v.cabinColor);
      });
      if (carBodyRef.current.instanceColor) carBodyRef.current.instanceColor.needsUpdate = true;
      if (carCabinRef.current.instanceColor) carCabinRef.current.instanceColor.needsUpdate = true;
    }
  }, [vehicles]);

  // Animated coastal harbor commuter ferries
  const ferryRoutes = useMemo(
    () => [
      { cx: 5180, cz: -650, rx: 240, rz: 620, speed: 0.11, phase: 0.0 },
      { cx: 5320, cz: 1150, rx: 280, rz: 580, speed: 0.095, phase: 2.1 },
      { cx: 4450, cz: 320, rx: 320, rz: 120, speed: 0.14, phase: 4.0 },
      { cx: 1400, cz: 5180, rx: 720, rz: 180, speed: 0.09, phase: 1.3 },
    ],
    []
  );

  const countryById = useMemo(
    () => Object.fromEntries(countries.map((c) => [c.country_id, c])),
    [countries]
  );

  // Precompute drone anchors from real backend telemetry
  const droneTargets = useMemo(() => {
    return allDrones.map((d) => {
      const [x, z] = geoToFlatWorld(d.location.lat, d.location.lon, countryById[d.country_id]);
      return { x, z, status: d.status as string };
    });
  }, [allDrones, countryById]);

  useFrame((state, rawDelta) => {
    const t = state.clock.elapsedTime;
    const dt = Math.min(rawDelta, 0.05);

    // Animate water ripple drift
    textures.water.offset.x = (t * 0.045) % 1;

    if (cycloneRef.current) {
      cycloneRef.current.children.forEach((ch) => {
        ch.rotation.y += dt * 1.8;
      });
    }
    if (quantumRingRef.current) {
      quantumRingRef.current.rotation.z = t * 0.25;
    }

    // Gentle cloud drift above the cities
    if (cloudPuffRef.current) {
      cloudPuffs.forEach((cp, i) => {
        const driftX = ((t * cp.driftSpeed + cp.phase * 80) % 2400) - 1200;
        const bobY = Math.sin(t * 0.45 + cp.phase) * 4.5;
        dummy.position.set(cp.baseX + driftX * 0.35, cp.baseY + bobY, cp.baseZ);
        dummy.rotation.set(0, 0, 0);
        dummy.scale.set(cp.rx, cp.ry, cp.rz);
        dummy.updateMatrix();
        cloudPuffRef.current!.setMatrixAt(i, dummy.matrix);
      });
      cloudPuffRef.current.instanceMatrix.needsUpdate = true;
    }

    // Stylized white wave crests gently pulsing & drifting
    if (waveCrestRef.current) {
      waveCrests.forEach((w, i) => {
        const surge = Math.sin(t * 1.4 + w.phase);
        dummy.position.set(w.x + surge * 8, -1.6 + Math.abs(surge) * 0.45, w.z);
        dummy.rotation.set(0, 0, 0);
        dummy.scale.set(w.len, 0.9, 5.5 + surge * 1.2);
        dummy.updateMatrix();
        waveCrestRef.current!.setMatrixAt(i, dummy.matrix);
      });
      waveCrestRef.current.instanceMatrix.needsUpdate = true;
    }

    // Animated white-and-blue commuter ferries gliding in the coastal harbor
    if (ferriesGroupRef.current) {
      ferriesGroupRef.current.children.forEach((ferry, idx) => {
        const r = ferryRoutes[idx];
        if (!r) return;
        const ang = t * r.speed + r.phase;
        const fx = r.cx + Math.cos(ang) * r.rx;
        const fz = r.cz + Math.sin(ang) * r.rz;
        const vx = -Math.sin(ang) * r.rx;
        const vz = Math.cos(ang) * r.rz;
        ferry.position.set(fx, -0.4 + Math.sin(t * 2.2 + idx) * 0.5, fz);
        ferry.rotation.set(0, Math.atan2(vx, vz), Math.sin(t * 1.8 + idx) * 0.03);
      });
    }

    // 98 live backend drones:
    // ONLY IN_FLIGHT / ASSIGNED orbit around their real backend anchor;
    // AVAILABLE sit parked cleanly; DESTROYED sit red grounded.
    if (liveDronesRef.current) {
      liveDronesRef.current.children.forEach((grp, idx) => {
        const info = droneTargets[idx];
        if (!info) return;

        if (info.status === "IN_FLIGHT" || info.status === "ASSIGNED") {
          const ang = t * (0.48 + (idx % 5) * 0.07) + idx * 0.85;
          grp.position.set(
            info.x + Math.cos(ang) * 44,
            158 + Math.sin(t * 2.4 + idx) * 4.0,
            info.z + Math.sin(ang) * 44
          );
          grp.rotation.set(0.08, -ang, Math.sin(ang) * 0.16);
        } else if (info.status === "DESTROYED") {
          grp.position.set(info.x, 4.0, info.z);
          grp.rotation.set(0.28, idx * 0.7, 0.34);
        } else {
          // AVAILABLE: parked on helipad/ground
          grp.position.set(info.x, 6.5, info.z);
          grp.rotation.set(0, (idx % 4) * (Math.PI / 2), 0);
        }
      });
    }

    // 160 moving diorama vehicles (yellow taxis, red city buses, colorful sedans)
    if (carBodyRef.current && carCabinRef.current) {
      vehicles.forEach((v, i) => {
        let vx = 0;
        let vz = 0;
        let yaw = 0;

        if (v.mode === "highway") {
          const u = (v.phase + t * v.speed) % 1;
          const dx = v.b.x - v.a.x;
          const dz = v.b.z - v.a.z;
          const len = Math.hypot(dx, dz) || 1;
          const nx = -dz / len;
          const nz = dx / len;
          vx = THREE.MathUtils.lerp(v.a.x, v.b.x, u) + nx * v.laneOffset;
          vz = THREE.MathUtils.lerp(v.a.z, v.b.z, u) + nz * v.laneOffset;
          yaw = Math.atan2(dx, dz);
        } else {
          const span = ((v.phase + t * v.speed * v.dir + 4900) % 1400) - 700;
          vx = v.axis === "x" ? v.a.x + span : v.a.x + v.dir * v.laneOffset;
          vz = v.axis === "z" ? v.a.z + span : v.a.z + v.dir * v.laneOffset;
          yaw = v.axis === "x" ? (v.dir === 1 ? Math.PI / 2 : -Math.PI / 2) : v.dir === 1 ? 0 : Math.PI;
        }

        const isBus = v.kind === "bus";
        const bw = isBus ? 6.2 : 5.2;
        const bh = isBus ? 5.6 : 2.8;
        const bl = isBus ? 18.5 : 11.4;

        // Main lower body
        dummy.position.set(vx, 0.8 + bh / 2, vz);
        dummy.rotation.set(0, yaw, 0);
        dummy.scale.set(bw, bh, bl);
        dummy.updateMatrix();
        carBodyRef.current!.setMatrixAt(i, dummy.matrix);

        // Upper cabin / roof
        const cw = bw * 0.86;
        const ch = isBus ? 1.8 : 2.0;
        const cl = isBus ? bl * 0.92 : bl * 0.54;
        dummy.position.set(vx, 0.8 + bh + ch / 2 - 0.15, vz);
        dummy.rotation.set(0, yaw, 0);
        dummy.scale.set(cw, ch, cl);
        dummy.updateMatrix();
        carCabinRef.current!.setMatrixAt(i, dummy.matrix);
      });
      carBodyRef.current.instanceMatrix.needsUpdate = true;
      carCabinRef.current.instanceMatrix.needsUpdate = true;
    }
  });

  const bgColor = isGolden ? "#fce8cc" : dayMode ? "#dceeff" : "#0c172a";
  const fogColor = isGolden ? "#f7dec0" : dayMode ? "#dceeff" : "#0c172a";
  const sunPos: [number, number, number] = isGolden
    ? [3400, 950, 2200]
    : dayMode
    ? [2400, 3600, 2100]
    : [-1800, 2600, -1600];

  const handleOrbitStart = useCallback(() => {
    transitioningRef.current = false;
    introActiveRef.current = false;
  }, []);

  const activeAnchor = COUNTRY_FLAT_ANCHORS[selectedCountryId] || { x: 0, z: 0 };
  const shadowRes = quality === "high" ? 2048 : 1024;

  return (
    <>
      <color attach="background" args={[bgColor]} />
      <fogExp2 attach="fog" args={[fogColor, isGolden ? 0.000072 : dayMode ? 0.000068 : 0.000098]} />

      {/* Subtle atmospheric realism: balanced ambient, soft ground bounce, warm key, cool sky fill & skyline rim */}
      <ambientLight intensity={isGolden ? 0.52 : dayMode ? 0.58 : 0.26} />
      <hemisphereLight
        args={[
          isGolden ? "#ffe4c4" : dayMode ? "#dceeff" : "#334155",
          dayMode ? "#6d8f68" : "#0b1324",
          dayMode ? 0.72 : 0.42,
        ]}
      />
      {/* Warm directional key light with soft ground shadow contrast */}
      <directionalLight
        position={sunPos}
        intensity={isGolden ? 2.35 : dayMode ? 2.15 : 0.82}
        color={isGolden ? "#ffc785" : dayMode ? "#fff4dc" : "#93c5fd"}
        castShadow
        shadow-mapSize-width={shadowRes}
        shadow-mapSize-height={shadowRes}
        shadow-camera-near={200}
        shadow-camera-far={12000}
        shadow-camera-left={-3600}
        shadow-camera-right={3600}
        shadow-camera-top={3600}
        shadow-camera-bottom={-3600}
        shadow-bias={-0.00035}
        shadow-normalBias={0.6}
        shadow-radius={3.5}
      />
      {/* Cool sky fill light from opposite azimuth */}
      <directionalLight
        position={[-2600, 1900, -2400]}
        intensity={isGolden ? 0.55 : dayMode ? 0.65 : 0.36}
        color={isGolden ? "#c7ddff" : dayMode ? "#b3daff" : "#38bdf8"}
      />
      {/* Subtle horizon rim light for crisp skyline silhouettes */}
      <directionalLight
        position={[0, 1450, -3400]}
        intensity={isGolden ? 0.42 : dayMode ? 0.34 : 0.28}
        color={isGolden ? "#fed7aa" : dayMode ? "#e0f2fe" : "#60a5fa"}
      />

      <IntroCameraRig
        anchor={activeAnchor}
        controlsRef={controlsRef}
        introActiveRef={introActiveRef}
        transitioningRef={transitioningRef}
        quality={quality}
        prefersReducedMotion={prefersReducedMotion}
      />

      <CameraFlyRig
        selectedCountryId={selectedCountryId}
        preset={cameraPreset}
        controlsRef={controlsRef}
        transitioningRef={transitioningRef}
        introActiveRef={introActiveRef}
      />

      {/* Sunlit Azure Ocean Base */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -2.5, 0]} receiveShadow>
        <planeGeometry args={[20000, 20000]} />
        <meshStandardMaterial
          map={textures.water}
          color={dayMode ? "#56b1e6" : "#153657"}
          roughness={0.22}
          metalness={0.18}
        />
      </mesh>

      {/* 10x10 km Continuous Architectural Diorama Continent Slab with Warm Beveled Base */}
      <mesh position={[0, -14, 0]} receiveShadow>
        <boxGeometry args={[9660, 28, 9660]} />
        <meshStandardMaterial color={dayMode ? "#c8b297" : "#272e3a"} roughness={0.92} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]} receiveShadow>
        <planeGeometry args={[9600, 9600]} />
        <meshStandardMaterial color={dayMode ? "#87b97c" : "#1c2a24"} roughness={0.94} />
      </mesh>

      {/* Winding Turquoise-Blue Veridia River */}
      <mesh geometry={riverGeo} position={[0, 0.45, 0]} receiveShadow>
        <meshStandardMaterial
          map={textures.water}
          color={dayMode ? "#2ec2ec" : "#124e73"}
          roughness={0.14}
          metalness={0.25}
        />
      </mesh>

      {/* Rocky / Pebble Stone Riverbanks along the Veridia River */}
      <instancedMesh
        ref={pebbleRef}
        args={[undefined, undefined, riverPebbles.length]}
        castShadow
        receiveShadow
      >
        <dodecahedronGeometry args={[1, 0]} />
        <meshStandardMaterial roughness={0.92} />
      </instancedMesh>

      {/* Multi-Tower Architectural Suspension Bridges over Veridia River & Harbor */}
      <SuspensionBridge position={[0, 0, veridiaRiverZ(0)]} spanLength={245} />
      <SuspensionBridge position={[1450, 0, veridiaRiverZ(1450)]} spanLength={260} />
      <SuspensionBridge position={[3250, 0, veridiaRiverZ(3250)]} spanLength={290} />

      {/* Animated White-and-Blue Coastal Harbor Commuter Ferries */}
      <group ref={ferriesGroupRef}>
        {ferryRoutes.map((_, idx) => (
          <group key={idx}>
            {/* Blue hull */}
            <mesh position={[0, 2.5, 0]} castShadow>
              <boxGeometry args={[18, 5, 48]} />
              <meshStandardMaterial color="#1d6fa5" roughness={0.35} />
            </mesh>
            {/* White passenger cabin */}
            <mesh position={[0, 7.5, -2]} castShadow>
              <boxGeometry args={[15, 6, 34]} />
              <meshStandardMaterial color="#f8fafc" roughness={0.3} />
            </mesh>
            {/* Navy window stripe */}
            <mesh position={[0, 8.2, -2]}>
              <boxGeometry args={[15.5, 2.2, 28]} />
              <meshStandardMaterial color="#0f172a" roughness={0.2} metalness={0.4} />
            </mesh>
            {/* Upper wheelhouse */}
            <mesh position={[0, 12.2, 8]} castShadow>
              <boxGeometry args={[10, 4, 11]} />
              <meshStandardMaterial color="#ffffff" roughness={0.3} />
            </mesh>
            {/* Trailing foam wake */}
            <mesh position={[0, 0.3, -32]} rotation={[-Math.PI / 2, 0, 0]}>
              <planeGeometry args={[14, 24]} />
              <meshBasicMaterial color="#ffffff" transparent opacity={0.55} />
            </mesh>
          </group>
        ))}
      </group>

      {/* Stylized White Wave Crests */}
      <instancedMesh ref={waveCrestRef} args={[undefined, undefined, waveCrests.length]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={dayMode ? 0.72 : 0.28} />
      </instancedMesh>

      {/* Fluffy Stylized Multi-Sphere White Clouds Drifting Above Cities */}
      <instancedMesh ref={cloudPuffRef} args={[undefined, undefined, cloudPuffs.length]}>
        <sphereGeometry args={[1, 10, 8]} />
        <meshStandardMaterial
          color={isGolden ? "#fff2e0" : dayMode ? "#ffffff" : "#334155"}
          roughness={0.95}
          transparent
          opacity={dayMode ? 0.94 : 0.55}
        />
      </instancedMesh>

      {/* Airport Runways in Veridia Central & Aurelia Coast */}
      {[
        [480, -520],
        [3020, -1580],
      ].map(([rx, rz], idx) => (
        <group key={idx} position={[rx, 0.72, rz]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
            <planeGeometry args={[360, 44]} />
            <meshStandardMaterial color="#475569" roughness={0.85} />
          </mesh>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.08, 0]}>
            <planeGeometry args={[320, 3]} />
            <meshStandardMaterial color="#f8fafc" />
          </mesh>
        </group>
      ))}

      {/* Patchwork Sunlit Farmland Fields in Solara Plains (COUNTRY-04) */}
      {[
        [-3100, -700, "#9bc45d"],
        [-3100, -250, "#d8c46a"],
        [-2650, -950, "#7eb058"],
        [-2100, -950, "#b4cc68"],
      ].map(([fx, fz, col]: any, idx) => (
        <mesh key={idx} rotation={[-Math.PI / 2, 0, 0]} position={[fx, 0.38, fz]} receiveShadow>
          <planeGeometry args={[420, 360]} />
          <meshStandardMaterial color={col} roughness={0.95} />
        </mesh>
      ))}

      {/* Industrial Cooling Towers in Ferros Industrial Union (COUNTRY-05) */}
      {[
        [-2550, 2450],
        [-2380, 2550],
        [-2210, 2450],
      ].map(([tx, tz], idx) => (
        <mesh key={idx} position={[tx, 65, tz]} castShadow receiveShadow>
          <cylinderGeometry args={[32, 48, 130, 18]} />
          <meshStandardMaterial color="#cbd5e1" roughness={0.8} />
        </mesh>
      ))}

      {/* 7 Country Sectors, Boulevards, Zebra Crosswalks, Central Parks, Iconic Landmarks & Nameplates */}
      {countries.map((c, cIdx) => {
        const a = COUNTRY_FLAT_ANCHORS[c.country_id];
        if (!a) return null;
        const isSel = c.country_id === selectedCountryId;
        const ringPts: [number, number, number][] = Array.from({ length: 33 }, (_, i) => {
          const ang = (i / 32) * Math.PI * 2;
          return [a.x + Math.cos(ang) * a.radius, 1.6, a.z + Math.sin(ang) * a.radius];
        });

        const parkX = a.x + 215;
        const parkZ = a.z + 215;

        return (
          <group key={c.country_id}>
            {/* Country Biome Ground Sector */}
            <mesh
              rotation={[-Math.PI / 2, 0, 0]}
              position={[a.x, 0.22, a.z]}
              receiveShadow
              onClick={(e) => {
                e.stopPropagation();
                onSelectCountry(c.country_id);
              }}
            >
              <circleGeometry args={[a.radius, 40]} />
              <meshStandardMaterial
                color={dayMode ? a.ground : "#243038"}
                roughness={0.93}
              />
            </mesh>

            {/* Clean Urban Diorama Plaza Apron in City Center */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[a.x, 0.34, a.z]} receiveShadow>
              <circleGeometry args={[430, 32]} />
              <meshStandardMaterial color={dayMode ? "#d8dde3" : "#273242"} roughness={0.88} />
            </mesh>

            {/* Country Border Outline */}
            <Line
              points={ringPts}
              color={isSel ? "#0284c7" : c.color}
              lineWidth={isSel ? 3.0 : 1.4}
            />

            {/* 4-Lane Cross-City Asphalt Boulevards */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[a.x, 0.62, a.z]} receiveShadow>
              <planeGeometry args={[1650, 38]} />
              <meshStandardMaterial map={textures.asphalt} roughness={0.84} />
            </mesh>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[a.x, 0.64, a.z]} receiveShadow>
              <planeGeometry args={[38, 1650]} />
              <meshStandardMaterial map={textures.asphalt} roughness={0.84} />
            </mesh>

            {/* White Zebra Crosswalks at Main Intersections & Mid-Block Crossings */}
            {[-280, -34, 34, 280].map((offset, cwIdx) => (
              <React.Fragment key={cwIdx}>
                <mesh
                  rotation={[-Math.PI / 2, 0, Math.PI / 2]}
                  position={[a.x + offset, 0.7, a.z]}
                >
                  <planeGeometry args={[30, 12]} />
                  <meshStandardMaterial map={textures.crosswalk} transparent roughness={0.75} />
                </mesh>
                <mesh rotation={[-Math.PI / 2, 0, 0]} position={[a.x, 0.7, a.z + offset]}>
                  <planeGeometry args={[30, 12]} />
                  <meshStandardMaterial map={textures.crosswalk} transparent roughness={0.75} />
                </mesh>
              </React.Fragment>
            ))}

            {/* Green Central Park with Winding Blue Pond & Walking Path */}
            <group position={[parkX, 0.48, parkZ]}>
              <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
                <circleGeometry args={[136, 28]} />
                <meshStandardMaterial color={dayMode ? "#78be62" : "#1e4228"} roughness={0.92} />
              </mesh>
              {/* Sandy park path ring */}
              <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.08, 0]}>
                <ringGeometry args={[76, 86, 32]} />
                <meshStandardMaterial color={dayMode ? "#e5d5bc" : "#4b463d"} roughness={0.9} />
              </mesh>
              {/* Winding blue pond (multi-lobe organic pool) */}
              <mesh rotation={[-Math.PI / 2, 0, 0]} position={[-12, 0.14, -8]}>
                <circleGeometry args={[42, 22]} />
                <meshStandardMaterial color="#3bb6e6" roughness={0.14} metalness={0.22} />
              </mesh>
              <mesh rotation={[-Math.PI / 2, 0, 0]} position={[24, 0.14, 16]}>
                <circleGeometry args={[32, 20]} />
                <meshStandardMaterial color="#3bb6e6" roughness={0.14} metalness={0.22} />
              </mesh>
            </group>

            {/* Iconic Architectural Landmarks in Each City */}
            <ArtDecoSkyscraper
              position={[a.x - 110, 0, a.z - 105]}
              scale={c.country_id === "COUNTRY-03" || c.country_id === "COUNTRY-01" ? 1.15 : 0.88}
              facadeTex={textures.artDeco}
            />
            <TaperedGlassTower
              position={[a.x + 108, 0, a.z - 115]}
              scale={c.country_id === "COUNTRY-03" || c.country_id === "COUNTRY-01" ? 1.12 : 0.85}
              glassTex={textures.blueGlass}
            />
            <ElevatedWaterTower position={[a.x - 245, 0, a.z + 185]} />
            {cIdx % 2 === 0 && <CircularStoneFountain position={[a.x - 115, 0, a.z + 115]} />}

            {/* Stylized Snow-Capped Mountain Peaks in Valtoria Highlands (COUNTRY-02) */}
            {c.country_id === "COUNTRY-02" &&
              [
                [-560, -520, 420],
                [580, -480, 470],
                [0, -760, 540],
              ].map(([ox, oz, h], idx) => (
                <group key={idx} position={[a.x + ox, 0, a.z + oz]}>
                  <mesh position={[0, h / 2, 0]} castShadow receiveShadow>
                    <coneGeometry args={[350, h, 8]} />
                    <meshStandardMaterial color="#8f9aa6" roughness={0.9} />
                  </mesh>
                  <mesh position={[0, h * 0.84, 0]}>
                    <coneGeometry args={[112, h * 0.34, 8]} />
                    <meshStandardMaterial color="#f8fafc" roughness={0.8} />
                  </mesh>
                </group>
              ))}

            {/* Clean Floating Country Nameplate */}
            <Html position={[a.x, 225, a.z]} distanceFactor={2600} style={{ pointerEvents: "none" }}>
              <div
                className={`px-2.5 py-1 rounded-md text-xs font-mono whitespace-nowrap border shadow-md ${
                  isSel
                    ? "bg-white/95 border-sky-500 text-sky-900 font-bold"
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
            position={[(A.x + B.x) / 2, 0.54, (A.z + B.z) / 2]}
            rotation={[-Math.PI / 2, 0, -angle]}
            receiveShadow
          >
            <planeGeometry args={[34, len]} />
            <meshStandardMaterial map={textures.asphalt} roughness={0.85} />
          </mesh>
        );
      })}

      {/* Instanced Commercial Towers & Warm Brick/Sandstone Mid-Rises */}
      <instancedMesh
        ref={commMeshRef}
        args={[undefined, undefined, commBuildings.length]}
        castShadow
        receiveShadow
      >
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial
          map={textures.commercial}
          roughnessMap={textures.commRough}
          roughness={0.34}
          metalness={0.32}
        />
      </instancedMesh>
      <instancedMesh
        ref={resMeshRef}
        args={[undefined, undefined, resBuildings.length]}
        castShadow
        receiveShadow
      >
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial
          map={textures.residential}
          bumpMap={textures.resBump}
          bumpScale={0.4}
          roughness={0.82}
          metalness={0.04}
        />
      </instancedMesh>

      {/* Lush Instanced Multi-Sphere Tree Clusters (60 FPS) */}
      <instancedMesh ref={treeTrunkRef} args={[undefined, undefined, trees.length]} castShadow>
        <cylinderGeometry args={[0.5, 0.72, 1, 6]} />
        <meshStandardMaterial color="#7c5c3e" roughness={0.95} />
      </instancedMesh>
      <instancedMesh ref={treeCanopyARef} args={[undefined, undefined, trees.length]} castShadow>
        <sphereGeometry args={[1, 9, 7]} />
        <meshStandardMaterial roughness={0.85} />
      </instancedMesh>
      <instancedMesh ref={treeCanopyBRef} args={[undefined, undefined, trees.length]} castShadow>
        <sphereGeometry args={[1, 8, 6]} />
        <meshStandardMaterial roughness={0.85} />
      </instancedMesh>
      <instancedMesh ref={treeCanopyCRef} args={[undefined, undefined, trees.length]} castShadow>
        <sphereGeometry args={[1, 8, 6]} />
        <meshStandardMaterial roughness={0.85} />
      </instancedMesh>

      {/* 160 Moving Diorama Vehicles (Yellow Taxis, Red City Buses, Colorful Sedans) */}
      <instancedMesh ref={carBodyRef} args={[undefined, undefined, vehicles.length]} castShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial roughness={0.32} metalness={0.35} />
      </instancedMesh>
      <instancedMesh ref={carCabinRef} args={[undefined, undefined, vehicles.length]} castShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial roughness={0.22} metalness={0.42} />
      </instancedMesh>

      {/* 220 Articulated Multi-Part Realistic NPCs */}
      <RealisticNPCs3D anchors={COUNTRY_FLAT_ANCHORS} hasActiveDisaster={hasActiveDisaster} />

      {/* Live Backend Hospitals with Red Crosses */}
      {allHospitals.map((h) => {
        const [x, z] = geoToFlatWorld(h.location.lat, h.location.lon, countryById[h.country_id]);
        return (
          <group key={h.hospital_id} position={[x, 0, z]}>
            <mesh position={[0, 22, 0]} castShadow receiveShadow>
              <boxGeometry args={[48, 44, 38]} />
              <meshStandardMaterial color="#ffffff" roughness={0.42} />
            </mesh>
            <mesh position={[0, 45, 0]}>
              <boxGeometry args={[22, 1.8, 6.5]} />
              <meshStandardMaterial color="#dc2626" emissive="#dc2626" emissiveIntensity={0.65} />
            </mesh>
            <mesh position={[0, 45, 0]}>
              <boxGeometry args={[6.5, 1.8, 22]} />
              <meshStandardMaterial color="#dc2626" emissive="#dc2626" emissiveIntensity={0.65} />
            </mesh>
          </group>
        );
      })}

      {/* Live Backend Ambulances */}
      {allAmbulances.map((a) => {
        const [ax, az] = geoToFlatWorld(a.location.lat, a.location.lon, countryById[a.country_id]);
        const isActive = a.status !== "AVAILABLE";
        return (
          <group key={a.ambulance_id} position={[ax, 3.6, az]}>
            <mesh castShadow>
              <boxGeometry args={[7.2, 5.2, 14.5]} />
              <meshStandardMaterial color="#ffffff" roughness={0.32} />
            </mesh>
            <mesh position={[0, 0.2, 0]}>
              <boxGeometry args={[7.4, 1.4, 14.6]} />
              <meshStandardMaterial color="#dc2626" roughness={0.4} />
            </mesh>
            <mesh position={[0, 3.4, 3.2]}>
              <boxGeometry args={[4.6, 1.2, 2.2]} />
              <meshStandardMaterial
                color={isActive ? "#ef4444" : "#38bdf8"}
                emissive={isActive ? "#ef4444" : "#0284c7"}
                emissiveIntensity={isActive ? 2.0 : 0.45}
              />
            </mesh>
          </group>
        );
      })}

      {/* Live Backend Fire & Rescue Units */}
      {allFireUnits.map((f) => {
        const [fx, fz] = geoToFlatWorld(f.location.lat, f.location.lon, countryById[f.country_id]);
        const active = f.status === "ON_SCENE" || f.status === "DISPATCHED";
        return (
          <group key={f.unit_id} position={[fx, 4.0, fz]}>
            <mesh castShadow>
              <boxGeometry args={[7.6, 6.2, 16.5]} />
              <meshStandardMaterial color="#dc2626" roughness={0.38} />
            </mesh>
            {/* Silver roof ladder */}
            <mesh position={[0, 3.5, -2]}>
              <boxGeometry args={[3.2, 0.8, 12]} />
              <meshStandardMaterial color="#e2e8f0" metalness={0.65} roughness={0.3} />
            </mesh>
            <mesh position={[0, 3.9, 4.5]}>
              <boxGeometry args={[4.6, 1.2, 2.2]} />
              <meshStandardMaterial
                color="#fef08a"
                emissive="#f59e0b"
                emissiveIntensity={active ? 2.2 : 0.4}
              />
            </mesh>
          </group>
        );
      })}

      {/* Active Swarm Coverage Perimeter Rings */}
      {activeSwarms
        .filter((sw) => sw.status === "ACTIVE")
        .map((sw) => {
          const [sx, sz] = geoToFlatWorld(
            sw.target_center.lat,
            sw.target_center.lon,
            countryById[sw.country_id]
          );
          return (
            <mesh key={sw.swarm_id} rotation={[-Math.PI / 2, 0, 0]} position={[sx, 12, sz]}>
              <ringGeometry args={[180, 198, 48]} />
              <meshBasicMaterial color="#10b981" transparent opacity={0.6} side={THREE.DoubleSide} />
            </mesh>
          );
        })}

      {/* Live Backend Relief Shelters */}
      {allShelters.map((s) => {
        const [x, z] = geoToFlatWorld(s.location.lat, s.location.lon, countryById[s.country_id]);
        return (
          <group key={s.shelter_id} position={[x, 0, z]}>
            <mesh position={[0, 9, 0]} castShadow>
              <cylinderGeometry args={[16, 21, 18, 8]} />
              <meshStandardMaterial color="#0284c7" roughness={0.5} />
            </mesh>
            <mesh position={[0, 19, 0]}>
              <cylinderGeometry args={[12, 16, 3, 8]} />
              <meshStandardMaterial color="#f8fafc" roughness={0.4} />
            </mesh>
          </group>
        );
      })}

      {/* Quantum Phase Telemetry Halo over Active Country */}
      <mesh
        ref={quantumRingRef}
        rotation={[-Math.PI / 2, 0, 0]}
        position={[
          COUNTRY_FLAT_ANCHORS[selectedCountryId]?.x ?? 0,
          12,
          COUNTRY_FLAT_ANCHORS[selectedCountryId]?.z ?? 0,
        ]}
      >
        <ringGeometry args={[520, 540, 96]} />
        <meshBasicMaterial color="#0284c7" transparent opacity={0.32} side={THREE.DoubleSide} />
      </mesh>

      {/* 98 Banking Quadcopter Drones (IN_FLIGHT/ASSIGNED orbit; AVAILABLE parked; DESTROYED red grounded) */}
      <group ref={liveDronesRef}>
        {allDrones.map((d, idx) => {
          const info = droneTargets[idx] || { x: 0, z: 0, status: d.status };
          const isFlying = info.status === "IN_FLIGHT" || info.status === "ASSIGNED";
          const isDestroyed = info.status === "DESTROYED";
          const y = isFlying ? 158 : isDestroyed ? 4.0 : 6.5;
          const color = isDestroyed ? "#ef4444" : isFlying ? "#16a34a" : "#0284c7";
          return (
            <group key={d.drone_id} position={[info.x, y, info.z]}>
              {/* Quadcopter core chassis */}
              <mesh castShadow>
                <octahedronGeometry args={[8.2, 0]} />
                <meshStandardMaterial
                  color={color}
                  emissive={color}
                  emissiveIntensity={isFlying ? 0.85 : 0.35}
                  roughness={0.35}
                />
              </mesh>
              {/* Cross rotor arms */}
              <mesh position={[0, 1.5, 0]}>
                <boxGeometry args={[23, 1.5, 2.2]} />
                <meshStandardMaterial color="#f1f5f9" metalness={0.65} roughness={0.25} />
              </mesh>
              <mesh position={[0, 1.5, 0]}>
                <boxGeometry args={[2.2, 1.5, 23]} />
                <meshStandardMaterial color="#f1f5f9" metalness={0.65} roughness={0.25} />
              </mesh>
              {/* 4 Rotor guard rings */}
              {[
                [-11, 0],
                [11, 0],
                [0, -11],
                [0, 11],
              ].map(([rx, rz], rIdx) => (
                <mesh key={rIdx} position={[rx, 2.4, rz]} rotation={[-Math.PI / 2, 0, 0]}>
                  <ringGeometry args={[3.2, 4.4, 12]} />
                  <meshBasicMaterial
                    color={isDestroyed ? "#ef4444" : "#334155"}
                    side={THREE.DoubleSide}
                  />
                </mesh>
              ))}
              {/* Ground drop-line telemetry tether only while airborne */}
              {isFlying && (
                <Line
                  points={[
                    [0, 0, 0],
                    [0, -y, 0],
                  ]}
                  color={color}
                  lineWidth={0.9}
                  transparent
                  opacity={0.3}
                />
              )}
            </group>
          );
        })}
      </group>

      {/* Animated Semantic Disaster Footprints & Flickering Fire Lights */}
      <DisasterFootprint
        disasters={disasters}
        countryById={countryById}
        geoToFlatWorld={geoToFlatWorld}
      />

      {/* Active Disasters (Cyclone Funnel, Flood Disk, Fire Glow) */}
      <group ref={cycloneRef}>
        {disasters
          .filter((d) => d.status === "ACTIVE")
          .map((ev) => {
            const [x, z] = geoToFlatWorld(
              ev.origin.lat,
              ev.origin.lon,
              countryById[ev.country_id]
            );
            if (ev.disaster_type === "CYCLONE") {
              return (
                <mesh key={ev.event_id} position={[x, 210, z]}>
                  <coneGeometry args={[250, 420, 24, 1, true]} />
                  <meshStandardMaterial
                    color="#94a3b8"
                    transparent
                    opacity={0.38}
                    side={THREE.DoubleSide}
                  />
                </mesh>
              );
            }
            if (ev.disaster_type === "FLOOD") {
              return (
                <mesh key={ev.event_id} rotation={[-Math.PI / 2, 0, 0]} position={[x, 2.2, z]}>
                  <circleGeometry args={[Math.max(220, ev.radius_km * 35), 32]} />
                  <meshStandardMaterial color="#0ea5e9" transparent opacity={0.55} />
                </mesh>
              );
            }
            return (
              <mesh key={ev.event_id} position={[x, 46, z]}>
                <sphereGeometry args={[86, 16, 16]} />
                <meshStandardMaterial
                  color="#f97316"
                  emissive="#ea580c"
                  emissiveIntensity={1.55}
                  transparent
                  opacity={0.64}
                />
              </mesh>
            );
          })}
      </group>

      {/* Candidate 3D Drone Routes */}
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
            color={rc.feasible ? "#16a34a" : "#ef4444"}
            lineWidth={rc.feasible ? 3.0 : 1.5}
          />
        );
      })}

      <OrbitControls
        ref={controlsRef}
        onStart={handleOrbitStart}
        maxPolarAngle={Math.PI / 2.08}
        minDistance={100}
        maxDistance={7800}
        enableDamping
        dampingFactor={0.07}
      />

      {quality === "high" && !prefersReducedMotion && (
        <EffectComposer multisampling={0}>
          <Bloom mipmapBlur luminanceThreshold={1.08} intensity={0.35} />
          <Vignette eskil={false} offset={0.22} darkness={0.32} />
          <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
        </EffectComposer>
      )}
    </>
  );
};

export const DioramaOpenWorld3D: React.FC<DioramaOpenWorldProps> = (props) => {
  const [timeOfDay, setTimeOfDay] = useState<"day" | "golden" | "night">("day");
  const [cameraPreset, setCameraPreset] = useState<"continent" | "country" | "street">("country");
  const [quality, setQuality] = useState<"high" | "low">("high");
  const [prefersReducedMotion, setPrefersReducedMotion] = useState<boolean>(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = (e: MediaQueryListEvent) => setPrefersReducedMotion(e.matches);
    setPrefersReducedMotion(mq.matches);
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);

  return (
    <div className="w-full h-full relative bg-[#DCEEFF] select-none">
      <Canvas
        shadows
        camera={{ position: [640, 480, 780], fov: 46, near: 4, far: 26000 }}
        gl={{
          antialias: true,
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.06,
        }}
      >
        <PerformanceMonitor
          onDecline={() => setQuality("low")}
          onIncline={() => setQuality("high")}
        />
        <AdaptiveDpr pixelated />
        <DioramaWorldScene
          {...props}
          timeOfDay={timeOfDay}
          cameraPreset={cameraPreset}
          quality={quality}
          prefersReducedMotion={prefersReducedMotion}
        />
      </Canvas>

      {/* Bottom-Left Light-Theme 7-Nation Corner Radar Minimap */}
      <div className="absolute bottom-4 left-4 w-52 h-40 rounded-lg bg-white/95 border border-slate-200 shadow-lg p-2.5 backdrop-blur-sm">
        <div className="text-[9px] font-mono font-semibold text-slate-500 flex justify-between items-center mb-1.5">
          <span>DIORAMA RADAR (10×10 KM)</span>
          <span className="text-emerald-600 font-bold">7 NATIONS</span>
        </div>
        <div className="relative w-full h-[112px] bg-[#DCEEFF] rounded border border-sky-200 overflow-hidden">
          {/* Subtle continent silhouette on minimap */}
          <div className="absolute inset-2 rounded bg-emerald-100/70 border border-emerald-200/80" />
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
                title={`${c.country_id} · ${c.name}`}
                className={`absolute -translate-x-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full border-2 transition-transform hover:scale-125 ${
                  c.active_disasters > 0
                    ? "bg-red-500 border-white animate-pulse shadow"
                    : isSel
                    ? "bg-sky-600 border-white ring-2 ring-sky-300 shadow"
                    : "bg-emerald-500 border-white shadow-sm"
                }`}
                style={{ left: `${leftPct}%`, top: `${topPct}%` }}
              />
            );
          })}
        </div>
      </div>

      {/* Bottom-Right Continent/Country/Street & Day/Golden/Night Controls */}
      <div className="absolute bottom-4 right-4 flex items-center gap-1.5 bg-white/95 border border-slate-200 shadow-lg rounded-lg px-2.5 py-1.5 text-[11px] font-mono backdrop-blur-sm">
        {(["continent", "country", "street"] as const).map((p) => (
          <button
            key={p}
            onClick={() => setCameraPreset(p)}
            className={`px-2 py-1 rounded uppercase font-medium transition-colors ${
              cameraPreset === p
                ? "bg-sky-600 text-white shadow-sm"
                : "text-slate-700 hover:bg-slate-100"
            }`}
          >
            {p}
          </button>
        ))}
        <span className="text-slate-300 px-0.5">|</span>
        {(["day", "golden", "night"] as const).map((tod) => (
          <button
            key={tod}
            onClick={() => setTimeOfDay(tod)}
            className={`px-2 py-1 rounded uppercase font-medium transition-colors ${
              timeOfDay === tod
                ? "bg-amber-500 text-white shadow-sm"
                : "text-slate-700 hover:bg-slate-100"
            }`}
          >
            {tod}
          </button>
        ))}
        <span className="text-slate-300 px-0.5">|</span>
        <button
          onClick={() => setQuality((q) => (q === "high" ? "low" : "high"))}
          title="Toggle graphics quality (post-processing and shadows)"
          className={`px-2 py-1 rounded uppercase font-medium transition-colors ${
            quality === "high"
              ? "bg-emerald-600 text-white shadow-sm"
              : "bg-slate-200 text-slate-800 hover:bg-slate-300"
          }`}
        >
          {quality === "high" ? "HIGH GFX" : "LOW GFX"}
        </button>
      </div>
    </div>
  );
};
