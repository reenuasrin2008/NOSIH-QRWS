import { buildLaneLoop, sampleTrafficPath, type TrafficPath } from "./roadGraph.ts";

export interface LayoutAnchor {
  x: number;
  z: number;
  radius: number;
  ground: string;
}

export interface LayoutPoint {
  x: number;
  z: number;
}

export interface LayoutRoad {
  id: string;
  countryId: string | null;
  kind: "boulevard" | "highway" | "access";
  width: number;
  points: LayoutPoint[];
}

export interface OrganicShape {
  id: string;
  countryId: string;
  x: number;
  z: number;
  rx: number;
  rz: number;
  rotation: number;
  points: LayoutPoint[];
}

export interface LayoutLake extends OrganicShape {
  kind: "lake" | "park";
}

export interface LayoutForest extends OrganicShape {
  treeCount: number;
  floorColor: string;
}

export interface LayoutPark extends OrganicShape {
  path: LayoutPoint[];
  lake: LayoutLake;
}

export interface GroundPatch extends OrganicShape {
  color: string;
}

export interface HospitalPad {
  id: string;
  countryId: string;
  x: number;
  z: number;
  rotationY: number;
  accessRoad: LayoutRoad;
}

export interface ShelterPad {
  id: string;
  countryId: string;
  x: number;
  z: number;
  rotationY: number;
  accessRoad: LayoutRoad;
}

export interface CountryLayout {
  countryId: string;
  anchor: LayoutAnchor;
  boundary: OrganicShape;
  hub: OrganicShape;
  groundPatches: GroundPatch[];
  roads: LayoutRoad[];
  collisionRoads: LayoutRoad[];
  park: LayoutPark;
  lakes: LayoutLake[];
  forests: LayoutForest[];
  hospitalPads: HospitalPad[];
  shelterPads: ShelterPad[];
}

export interface WorldLayout {
  countries: Record<string, CountryLayout>;
  roads: LayoutRoad[];
  trafficRoutes: TrafficPath[];
}

export interface LayoutBuilding {
  id: string;
  countryId: string;
  x: number;
  z: number;
  width: number;
  depth: number;
  height: number;
  rotationY: number;
  color: string;
  kind: "commercial" | "residential";
}

export interface LayoutTree {
  id: string;
  countryId: string;
  x: number;
  z: number;
  height: number;
  radius: number;
  rotationY: number;
  color: string;
  kind: "broadleaf" | "conifer" | "acacia";
}

export interface HospitalPlacementRequest {
  id: string;
  countryId: string;
  x: number;
  z: number;
}

export interface RoadsideSpot {
  id: string;
  countryId: string;
  x: number;
  z: number;
  rotationY: number;
}

export const COUNTRY_FLAT_ANCHORS: Record<string, LayoutAnchor> = {
  "COUNTRY-01": { x: 2600, z: -1200, radius: 1700, ground: "#8ec182" },
  "COUNTRY-02": { x: 0, z: -2700, radius: 1700, ground: "#9ea89d" },
  "COUNTRY-03": { x: 0, z: 0, radius: 1800, ground: "#7eb974" },
  "COUNTRY-04": { x: -2500, z: -400, radius: 1800, ground: "#a5c272" },
  "COUNTRY-05": { x: -2100, z: 2200, radius: 1650, ground: "#8f98a1" },
  "COUNTRY-06": { x: -2400, z: -2600, radius: 1750, ground: "#dfc295" },
  "COUNTRY-07": { x: 1800, z: 2200, radius: 1750, ground: "#619b62" },
};

export const HIGHWAY_LINKS: Array<[string, string]> = [
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

export const WORLD_LAYOUT = {
  boulevardWidth: 46,
  highwayWidth: 34,
  accessWidth: 16,
  hubRadius: 56,
  hospitalWidth: 84,
  hospitalDepth: 66,
  hospitalRadius: Math.hypot(42, 33),
  hospitalMargin: 18,
  hospitalPadCount: 8,
  shelterRadius: 36,
  shelterMargin: 16,
  shelterPadCount: 8,
  shelterAccessWidth: 12,
  lakeShore: 14,
} as const;

const TAU = Math.PI * 2;
const BUILDING_TINTS = [
  "#e7cbb0", "#d99b78", "#efe5d5", "#c98566", "#dce6ef", "#e2d2bc",
  "#cbd5e1", "#b8c6d1", "#d8c7b5", "#e8ddd0",
];
const TREE_COLORS = ["#3c8e39", "#4ea843", "#67bd52", "#2f6b3a", "#558b2f", "#7cb342"];
const CONIFER_COLORS = ["#234f3a", "#2f6b4f", "#3b7455", "#1f4936"];
const ACACIA_COLORS = ["#6b8e3d", "#7fa14b", "#558b2f", "#8aa653"];
const TERRAIN_PALETTES: Record<string, string[]> = {
  "COUNTRY-01": ["#78ad72", "#93bd7d", "#6f9f69", "#a3c48b"],
  "COUNTRY-02": ["#87978b", "#9aa89a", "#778b7d", "#aab5a5"],
  "COUNTRY-03": ["#6fac65", "#83b975", "#5f9b5d", "#9ac284"],
  "COUNTRY-04": ["#9fb864", "#b2c875", "#91aa58", "#c2cf88"],
  "COUNTRY-05": ["#7f8f83", "#929e91", "#728277", "#a2aa97"],
  "COUNTRY-06": ["#c9ad7d", "#d8bf91", "#b99c6d", "#e0cba4"],
  "COUNTRY-07": ["#4f8b55", "#619b62", "#427b4b", "#76a96c"],
};
const FOREST_FLOORS: Record<string, string> = {
  "COUNTRY-01": "#427447",
  "COUNTRY-02": "#3f5d4b",
  "COUNTRY-03": "#477a43",
  "COUNTRY-04": "#6f833e",
  "COUNTRY-05": "#4e6853",
  "COUNTRY-06": "#817b45",
  "COUNTRY-07": "#315f3d",
};
const BUILDING_PROFILES: Record<string, { target: number; maxHeight: number; towerChance: number }> = {
  "COUNTRY-01": { target: 235, maxHeight: 155, towerChance: 0.28 },
  "COUNTRY-02": { target: 205, maxHeight: 105, towerChance: 0.12 },
  "COUNTRY-03": { target: 245, maxHeight: 175, towerChance: 0.34 },
  "COUNTRY-04": { target: 185, maxHeight: 62, towerChance: 0.03 },
  "COUNTRY-05": { target: 205, maxHeight: 78, towerChance: 0.06 },
  "COUNTRY-06": { target: 155, maxHeight: 68, towerChance: 0.03 },
  "COUNTRY-07": { target: 165, maxHeight: 82, towerChance: 0.08 },
};
const LAKE_CANDIDATES: Record<string, Array<[number, number, number, number]>> = {
  "COUNTRY-01": [[-570, 430, 310, 175], [520, 470, 265, 155], [650, -330, 210, 125]],
  "COUNTRY-02": [[520, 390, 285, 145], [-530, -430, 330, 175], [580, -180, 190, 110]],
  "COUNTRY-03": [[-535, 405, 285, 165], [535, -405, 310, 175], [690, 525, 225, 135]],
  "COUNTRY-04": [[-535, 525, 375, 205], [590, -315, 270, 150], [-160, 650, 240, 135]],
  "COUNTRY-05": [[565, 390, 300, 165], [-495, -510, 265, 145], [620, -160, 190, 115]],
  "COUNTRY-06": [[-535, 425, 225, 105], [510, 475, 185, 95]],
  "COUNTRY-07": [[-525, 430, 335, 210], [545, -365, 305, 190], [660, 510, 255, 160]],
};
const FOREST_CANDIDATES: Record<string, Array<[number, number, number, number, number]>> = {
  "COUNTRY-01": [[-610, -390, 390, 270, 150], [620, 210, 350, 260, 130]],
  "COUNTRY-02": [[-560, 390, 420, 290, 210], [570, -410, 390, 280, 190], [80, 690, 450, 250, 160]],
  "COUNTRY-03": [[-650, -430, 360, 250, 135], [610, 600, 390, 270, 150], [-160, 720, 430, 230, 120]],
  "COUNTRY-04": [[-690, -510, 410, 240, 70], [690, 480, 380, 230, 65], [80, 720, 500, 210, 55]],
  "COUNTRY-05": [[-650, 430, 350, 240, 90], [590, -520, 320, 220, 80]],
  "COUNTRY-06": [[-570, 350, 350, 210, 38], [570, -420, 320, 190, 30], [180, 650, 380, 200, 26]],
  "COUNTRY-07": [[-490, -390, 510, 370, 250], [455, 360, 500, 350, 245], [40, 720, 570, 290, 210], [-720, 250, 330, 300, 170]],
};
const PARK_CANDIDATES: Array<[number, number]> = [
  [215, 215], [-275, 245], [285, -235], [-250, -260],
];

interface RandomSource {
  (): number;
}

function hashSeed(text: string): number {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function mulberry32(seed: number): RandomSource {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let value = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function range(random: RandomSource, min: number, max: number): number {
  return min + random() * (max - min);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function makeOrganicShape(
  id: string,
  countryId: string,
  x: number,
  z: number,
  rx: number,
  rz: number,
  rotation: number,
  random: RandomSource,
  segments = 48
): OrganicShape {
  const phaseA = random() * TAU;
  const phaseB = random() * TAU;
  const points: LayoutPoint[] = [];
  for (let i = 0; i < segments; i += 1) {
    const angle = (i / segments) * TAU;
    const wobble = 1
      + Math.sin(angle * 3 + phaseA) * 0.095
      + Math.sin(angle * 7 + phaseB) * 0.045
      + (random() - 0.5) * 0.035;
    const localX = Math.cos(angle) * rx * wobble;
    const localZ = Math.sin(angle) * rz * wobble;
    points.push({
      x: x + localX * Math.cos(rotation) - localZ * Math.sin(rotation),
      z: z + localX * Math.sin(rotation) + localZ * Math.cos(rotation),
    });
  }
  return { id, countryId, x, z, rx, rz, rotation, points };
}

export function veridiaRiverZ(x: number): number {
  return 210 + Math.sin(x * 0.00145) * 195 + Math.cos(x * 0.00072 + 0.6) * 95;
}

function veridiaRiverHalfWidth(x: number): number {
  const u = clamp((x + 1750) / (4800 + 1750), 0, 1);
  return 76 * (1 + u * 0.55);
}

export function riverClearance(x: number, z: number, footprint = 0): number {
  const margin = footprint + 4;
  if (x < -1750 - margin || x > 4800 + margin) return Number.POSITIVE_INFINITY;
  return Math.abs(z - veridiaRiverZ(x)) - veridiaRiverHalfWidth(x) - footprint;
}

export function pointInPolygon(point: LayoutPoint, polygon: readonly LayoutPoint[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const a = polygon[i];
    const b = polygon[j];
    const crosses = (a.z > point.z) !== (b.z > point.z)
      && point.x < ((b.x - a.x) * (point.z - a.z)) / ((b.z - a.z) || 1e-12) + a.x;
    if (crosses) inside = !inside;
  }
  return inside;
}

export function distanceToPolyline(point: LayoutPoint, polyline: readonly LayoutPoint[]): number {
  let best = Number.POSITIVE_INFINITY;
  for (let i = 1; i < polyline.length; i += 1) {
    const a = polyline[i - 1];
    const b = polyline[i];
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const lengthSquared = dx * dx + dz * dz;
    const t = lengthSquared > 0
      ? clamp(((point.x - a.x) * dx + (point.z - a.z) * dz) / lengthSquared, 0, 1)
      : 0;
    const distance = Math.hypot(point.x - (a.x + dx * t), point.z - (a.z + dz * t));
    best = Math.min(best, distance);
  }
  return best;
}

export function signedShapeClearance(point: LayoutPoint, shape: OrganicShape): number {
  const edgeDistance = distanceToPolyline(point, shape.points);
  return pointInPolygon(point, shape.points) ? -edgeDistance : edgeDistance;
}

/** Positive inside a country boundary, negative outside. */
export function boundaryClearance(point: LayoutPoint, boundary: OrganicShape): number {
  const edgeDistance = distanceToPolyline(point, boundary.points);
  return pointInPolygon(point, boundary.points) ? edgeDistance : -edgeDistance;
}

export function polylineLength(points: readonly LayoutPoint[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    total += Math.hypot(points[i].x - points[i - 1].x, points[i].z - points[i - 1].z);
  }
  return total;
}

export interface PolylineSample {
  point: LayoutPoint;
  tangent: LayoutPoint;
  normal: LayoutPoint;
}

export function samplePolyline(points: readonly LayoutPoint[], distance: number): PolylineSample {
  const total = polylineLength(points);
  let remaining = clamp(distance, 0, total);
  for (let i = 1; i < points.length; i += 1) {
    const a = points[i - 1];
    const b = points[i];
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const length = Math.hypot(dx, dz);
    if (remaining <= length || i === points.length - 1) {
      const t = length > 0 ? clamp(remaining / length, 0, 1) : 0;
      const tangent = { x: dx / (length || 1), z: dz / (length || 1) };
      return {
        point: { x: a.x + dx * t, z: a.z + dz * t },
        tangent,
        normal: { x: -tangent.z, z: tangent.x },
      };
    }
    remaining -= length;
  }
  const last = points[points.length - 1];
  return { point: { ...last }, tangent: { x: 1, z: 0 }, normal: { x: 0, z: 1 } };
}

export function roadNetworkClearance(
  x: number,
  z: number,
  roads: readonly LayoutRoad[],
  hubs: readonly OrganicShape[] = []
): number {
  const point = { x, z };
  let clearance = Number.POSITIVE_INFINITY;
  for (const road of roads) {
    clearance = Math.min(clearance, distanceToPolyline(point, road.points) - road.width / 2);
  }
  for (const hub of hubs) clearance = Math.min(clearance, signedShapeClearance(point, hub));
  return clearance;
}

/** Exact finite-road containment; unlike clearance, this rejects points beyond an endpoint. */
export function pointOnRoadNetwork(
  x: number,
  z: number,
  roads: readonly LayoutRoad[],
  hubs: readonly OrganicShape[] = [],
  margin = 0.5
): boolean {
  const point = { x, z };
  for (const road of roads) {
    for (let i = 1; i < road.points.length; i += 1) {
      const a = road.points[i - 1];
      const b = road.points[i];
      const dx = b.x - a.x;
      const dz = b.z - a.z;
      const lengthSquared = dx * dx + dz * dz;
      if (lengthSquared <= 1e-12) continue;
      const t = ((x - a.x) * dx + (z - a.z) * dz) / lengthSquared;
      if (t < -margin || t > 1 + margin) continue;
      const closestX = a.x + dx * t;
      const closestZ = a.z + dz * t;
      if (Math.hypot(x - closestX, z - closestZ) > road.width / 2 + margin) continue;
      if (t < 0 && (x - a.x) * dx + (z - a.z) * dz < -margin) continue;
      if (t > 1 && (x - b.x) * dx + (z - b.z) * dz > margin) continue;
      return true;
    }
  }
  return hubs.some((hub) => signedShapeClearance(point, hub) <= margin);
}

function nearestPointOnRoad(point: LayoutPoint, road: LayoutRoad): { point: LayoutPoint; distance: number } {
  let best = { point: road.points[0], distance: Number.POSITIVE_INFINITY };
  for (let i = 1; i < road.points.length; i += 1) {
    const a = road.points[i - 1];
    const b = road.points[i];
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const lengthSquared = dx * dx + dz * dz;
    const t = clamp(((point.x - a.x) * dx + (point.z - a.z) * dz) / (lengthSquared || 1), 0, 1);
    const candidate = { x: a.x + dx * t, z: a.z + dz * t };
    const distance = Math.hypot(point.x - candidate.x, point.z - candidate.z);
    if (distance < best.distance) best = { point: candidate, distance };
  }
  return best;
}

function shapeInsideBoundary(shape: OrganicShape, boundary: OrganicShape, margin: number): boolean {
  return shape.points.every((point) => boundaryClearance(point, boundary) > margin);
}

function shapeClearOfRoads(
  shape: OrganicShape,
  roads: readonly LayoutRoad[],
  hubs: readonly OrganicShape[],
  margin: number
): boolean {
  const samples = [shape.points[0], ...shape.points.filter((_, index) => index % 4 === 0), { x: shape.x, z: shape.z }];
  if (samples.some((point) => roadNetworkClearance(point.x, point.z, roads, hubs) < margin)) return false;
  for (const road of roads) {
    const step = Math.max(1, Math.floor(road.points.length / 36));
    for (let i = 0; i < road.points.length; i += step) {
      const point = road.points[i];
      if (signedShapeClearance(point, shape) < road.width / 2 + margin) return false;
    }
  }
  return true;
}

function shapesClear(a: OrganicShape, b: OrganicShape, margin: number): boolean {
  const aSamples = a.points.filter((_, index) => index % 3 === 0);
  const bSamples = b.points.filter((_, index) => index % 3 === 0);
  return aSamples.every((point) => signedShapeClearance(point, b) >= margin)
    && bSamples.every((point) => signedShapeClearance(point, a) >= margin);
}

function makeCityRoads(countryId: string, anchor: LayoutAnchor, random: RandomSource): LayoutRoad[] {
  const span = 840;
  const segments = 36;
  const phaseA = random() * TAU;
  const phaseB = random() * TAU;
  const slopeA = range(random, -0.035, 0.035);
  const slopeB = range(random, -0.04, 0.04);
  const avenue: LayoutPoint[] = [];
  const crossStreet: LayoutPoint[] = [];
  for (let i = 0; i <= segments; i += 1) {
    const t = i / segments * 2 - 1;
    avenue.push({
      x: anchor.x + t * span,
      z: anchor.z + t * span * slopeA + Math.sin(t * 2.35 + phaseA) * 34,
    });
    crossStreet.push({
      x: anchor.x - 42 + t * span * slopeB + Math.sin(t * 2.05 + phaseB) * 39,
      z: anchor.z + t * span,
    });
  }
  return [
    { id: `${countryId}-avenue`, countryId, kind: "boulevard", width: WORLD_LAYOUT.boulevardWidth, points: avenue },
    { id: `${countryId}-cross-street`, countryId, kind: "boulevard", width: WORLD_LAYOUT.boulevardWidth, points: crossStreet },
  ];
}

function makeHighwayRoads(random: RandomSource): LayoutRoad[] {
  return HIGHWAY_LINKS.map(([fromId, toId], index) => {
    const from = COUNTRY_FLAT_ANCHORS[fromId];
    const to = COUNTRY_FLAT_ANCHORS[toId];
    const dx = to.x - from.x;
    const dz = to.z - from.z;
    const length = Math.hypot(dx, dz);
    const normal = { x: -dz / length, z: dx / length };
    const bend = range(random, 55, 135) * (index % 2 === 0 ? 1 : -1);
    const phase = random() * TAU;
    const points: LayoutPoint[] = [];
    for (let i = 0; i <= 40; i += 1) {
      const u = i / 40;
      const offset = Math.sin(u * Math.PI) * bend + Math.sin(u * Math.PI * 2 + phase) * bend * 0.16;
      points.push({
        x: from.x + dx * u + normal.x * offset,
        z: from.z + dz * u + normal.z * offset,
      });
    }
    return {
      id: `highway-${fromId}-${toId}`,
      countryId: null,
      kind: "highway" as const,
      width: WORLD_LAYOUT.highwayWidth,
      points,
    };
  });
}

function makeGroundPatches(countryId: string, anchor: LayoutAnchor, random: RandomSource): GroundPatch[] {
  const palette = TERRAIN_PALETTES[countryId] ?? TERRAIN_PALETTES["COUNTRY-03"];
  return Array.from({ length: 9 }, (_, index) => {
    const angle = index / 9 * TAU + range(random, -0.2, 0.2);
    const distance = range(random, 180, anchor.radius * 0.68);
    const patch = makeOrganicShape(
      `${countryId}-ground-${index}`,
      countryId,
      anchor.x + Math.cos(angle) * distance,
      anchor.z + Math.sin(angle) * distance,
      range(random, 240, 510),
      range(random, 190, 420),
      random() * TAU,
      random,
      36
    );
    return { ...patch, color: palette[index % palette.length] };
  });
}

function makePark(
  countryId: string,
  country: CountryLayout,
  primaryRoads: readonly LayoutRoad[],
  random: RandomSource
): LayoutPark {
  let park: OrganicShape | null = null;
  for (const [offsetX, offsetZ] of PARK_CANDIDATES) {
    const candidate = makeOrganicShape(
      `${countryId}-park`, countryId, country.anchor.x + offsetX, country.anchor.z + offsetZ,
      148, 124, range(random, -0.35, 0.35), random
    );
    if (!shapeInsideBoundary(candidate, country.boundary, 30)) continue;
    if (!shapeClearOfRoads(candidate, primaryRoads, [country.hub], 18)) continue;
    if (candidate.points.some((point) => riverClearance(point.x, point.z, 8) < 0)) continue;
    park = candidate;
    break;
  }
  if (!park) {
    park = makeOrganicShape(
      `${countryId}-park`, countryId, country.anchor.x + 215, country.anchor.z + 215,
      148, 124, 0, random
    );
  }

  const path: LayoutPoint[] = [];
  for (let i = 0; i <= 28; i += 1) {
    const u = i / 28;
    path.push({
      x: park.x + (u * 2 - 1) * park.rx * 0.72,
      z: park.z + Math.sin(u * Math.PI * 2.2 + park.rotation) * park.rz * 0.24,
    });
  }
  const lake = makeOrganicShape(
    `${countryId}-park-lake`, countryId,
    park.x + range(random, -24, 24), park.z + range(random, -18, 18),
    range(random, 34, 46), range(random, 24, 34), random() * TAU, random, 36
  ) as LayoutLake;
  lake.kind = "park";
  return { ...park, path, lake };
}

function makeLakes(country: CountryLayout, primaryRoads: readonly LayoutRoad[], random: RandomSource): LayoutLake[] {
  const candidates = LAKE_CANDIDATES[country.countryId] ?? LAKE_CANDIDATES["COUNTRY-03"];
  const lakes: LayoutLake[] = [];
  for (let index = 0; index < candidates.length; index += 1) {
    const [offsetX, offsetZ, rx, rz] = candidates[index];
    let accepted: LayoutLake | null = null;
    for (let attempt = 0; attempt < 12 && !accepted; attempt += 1) {
      const jitterX = attempt === 0 ? 0 : range(random, -95, 95);
      const jitterZ = attempt === 0 ? 0 : range(random, -95, 95);
      const candidate = makeOrganicShape(
        `${country.countryId}-lake-${index}`,
        country.countryId,
        country.anchor.x + offsetX + jitterX,
        country.anchor.z + offsetZ + jitterZ,
        rx * range(random, 0.9, 1.08),
        rz * range(random, 0.9, 1.08),
        random() * TAU,
        random
      ) as LayoutLake;
      candidate.kind = "lake";
      if (!shapeInsideBoundary(candidate, country.boundary, 28)) continue;
      if (!shapeClearOfRoads(candidate, primaryRoads, [country.hub], 18)) continue;
      if (candidate.points.some((point) => riverClearance(point.x, point.z, 12) < 0)) continue;
      if (!shapesClear(candidate, country.park, 32)) continue;
      if (lakes.some((lake) => !shapesClear(candidate, lake, 45))) continue;
      accepted = candidate;
    }
    if (accepted) lakes.push(accepted);
  }
  return lakes;
}

function makeHospitalPads(
  country: CountryLayout,
  worldRoads: LayoutRoad[],
  random: RandomSource
): HospitalPad[] {
  const pads: HospitalPad[] = [];
  const rings = [185, 275, 365, 465, 565, 665];
  for (const radius of rings) {
    for (let slot = 0; slot < 16 && pads.length < WORLD_LAYOUT.hospitalPadCount; slot += 1) {
      const angle = slot / 16 * TAU + range(random, -0.16, 0.16) + radius * 0.0023;
      const x = country.anchor.x + Math.cos(angle) * (radius + range(random, -18, 18));
      const z = country.anchor.z + Math.sin(angle) * (radius + range(random, -18, 18));
      if (boundaryClearance({ x, z }, country.boundary) < WORLD_LAYOUT.hospitalRadius + 45) continue;
      if (roadNetworkClearance(x, z, worldRoads, [country.hub]) < WORLD_LAYOUT.hospitalRadius + WORLD_LAYOUT.hospitalMargin) continue;
      if (riverClearance(x, z, WORLD_LAYOUT.hospitalRadius + 15) < 0) continue;
      if (signedShapeClearance({ x, z }, country.park) < WORLD_LAYOUT.hospitalRadius + 30) continue;
      if (country.lakes.some((lake) => signedShapeClearance({ x, z }, lake) < WORLD_LAYOUT.hospitalRadius + 24)) continue;
      if (pads.some((pad) => Math.hypot(pad.x - x, pad.z - z) < 155)) continue;

      let nearest: { road: LayoutRoad; point: LayoutPoint; distance: number } | null = null;
      for (const road of country.roads) {
        const result = nearestPointOnRoad({ x, z }, road);
        if (!nearest || result.distance < nearest.distance) nearest = { road, point: result.point, distance: result.distance };
      }
      if (!nearest || nearest.distance < WORLD_LAYOUT.hospitalRadius + 35) continue;
      const direction = {
        x: (x - nearest.point.x) / nearest.distance,
        z: (z - nearest.point.z) / nearest.distance,
      };
      const start = {
        x: nearest.point.x + direction.x * (nearest.road.width / 2 - 1),
        z: nearest.point.z + direction.z * (nearest.road.width / 2 - 1),
      };
      const end = {
        x: x - direction.x * (WORLD_LAYOUT.hospitalRadius + 9),
        z: z - direction.z * (WORLD_LAYOUT.hospitalRadius + 9),
      };
      const accessPoints: LayoutPoint[] = [];
      for (let i = 0; i <= 12; i += 1) {
        const u = i / 12;
        const curve = Math.sin(u * Math.PI) * 9;
        accessPoints.push({
          x: start.x + (end.x - start.x) * u - direction.z * curve,
          z: start.z + (end.z - start.z) * u + direction.x * curve,
        });
      }
      const accessRoad: LayoutRoad = {
        id: `${country.countryId}-hospital-access-${pads.length + 1}`,
        countryId: country.countryId,
        kind: "access",
        width: WORLD_LAYOUT.accessWidth,
        points: accessPoints,
      };
      if (pads.some((existing) =>
        distanceToPolyline(existing, accessPoints) - WORLD_LAYOUT.accessWidth / 2
        < WORLD_LAYOUT.hospitalRadius + 10
      )) continue;

      pads.push({
        id: `${country.countryId}-hospital-pad-${pads.length + 1}`,
        countryId: country.countryId,
        x,
        z,
        rotationY: Math.atan2(-direction.z, direction.x),
        accessRoad,
      });
    }
  }
  return pads;
}

function makeShelterPads(
  country: CountryLayout,
  worldRoads: LayoutRoad[],
  random: RandomSource
): ShelterPad[] {
  const pads: ShelterPad[] = [];
  const rings = [155, 235, 320, 410, 510, 610, 710];
  for (const radius of rings) {
    for (let slot = 0; slot < 16 && pads.length < WORLD_LAYOUT.shelterPadCount; slot += 1) {
      const angle = slot / 16 * TAU + range(random, -0.18, 0.18) + radius * 0.0017;
      const x = country.anchor.x + Math.cos(angle) * (radius + range(random, -16, 16));
      const z = country.anchor.z + Math.sin(angle) * (radius + range(random, -16, 16));
      if (boundaryClearance({ x, z }, country.boundary) < WORLD_LAYOUT.shelterRadius + 38) continue;
      if (roadNetworkClearance(x, z, worldRoads, [country.hub]) < WORLD_LAYOUT.shelterRadius + WORLD_LAYOUT.shelterMargin) continue;
      if (riverClearance(x, z, WORLD_LAYOUT.shelterRadius + 12) < 0) continue;
      if (signedShapeClearance({ x, z }, country.park) < WORLD_LAYOUT.shelterRadius + 26) continue;
      if (country.lakes.some((lake) => signedShapeClearance({ x, z }, lake) < WORLD_LAYOUT.shelterRadius + 20)) continue;
      if (country.hospitalPads.some((pad) => Math.hypot(pad.x - x, pad.z - z) < WORLD_LAYOUT.shelterRadius + WORLD_LAYOUT.hospitalRadius + 28)) continue;
      if (pads.some((pad) => Math.hypot(pad.x - x, pad.z - z) < 125)) continue;

      let nearest: { road: LayoutRoad; point: LayoutPoint; distance: number } | null = null;
      for (const road of country.roads) {
        const result = nearestPointOnRoad({ x, z }, road);
        if (!nearest || result.distance < nearest.distance) nearest = { road, point: result.point, distance: result.distance };
      }
      if (!nearest || nearest.distance < WORLD_LAYOUT.shelterRadius + 30) continue;
      const direction = {
        x: (x - nearest.point.x) / nearest.distance,
        z: (z - nearest.point.z) / nearest.distance,
      };
      const start = {
        x: nearest.point.x + direction.x * (nearest.road.width / 2 - 1),
        z: nearest.point.z + direction.z * (nearest.road.width / 2 - 1),
      };
      const end = {
        x: x - direction.x * (WORLD_LAYOUT.shelterRadius + 8),
        z: z - direction.z * (WORLD_LAYOUT.shelterRadius + 8),
      };
      const accessPoints: LayoutPoint[] = [];
      for (let i = 0; i <= 10; i += 1) {
        const u = i / 10;
        const curve = Math.sin(u * Math.PI) * 7;
        accessPoints.push({
          x: start.x + (end.x - start.x) * u - direction.z * curve,
          z: start.z + (end.z - start.z) * u + direction.x * curve,
        });
      }
      if (country.hospitalPads.some((pad) =>
        distanceToPolyline(pad, accessPoints) - WORLD_LAYOUT.shelterAccessWidth / 2
        < WORLD_LAYOUT.hospitalRadius + 10
      )) continue;
      if (pads.some((pad) =>
        distanceToPolyline(pad, accessPoints) - WORLD_LAYOUT.shelterAccessWidth / 2
        < WORLD_LAYOUT.shelterRadius + 10
      )) continue;
      const accessRoad: LayoutRoad = {
        id: `${country.countryId}-shelter-access-${pads.length + 1}`,
        countryId: country.countryId,
        kind: "access",
        width: WORLD_LAYOUT.shelterAccessWidth,
        points: accessPoints,
      };
      pads.push({
        id: `${country.countryId}-shelter-pad-${pads.length + 1}`,
        countryId: country.countryId,
        x,
        z,
        rotationY: Math.atan2(-direction.z, direction.x),
        accessRoad,
      });
    }
  }
  return pads;
}

function makeForests(country: CountryLayout, random: RandomSource): LayoutForest[] {
  const candidates = FOREST_CANDIDATES[country.countryId] ?? FOREST_CANDIDATES["COUNTRY-03"];
  return candidates.map(([offsetX, offsetZ, rx, rz, treeCount], index) => {
    const forest = makeOrganicShape(
      `${country.countryId}-forest-${index}`,
      country.countryId,
      country.anchor.x + offsetX,
      country.anchor.z + offsetZ,
      rx,
      rz,
      random() * TAU,
      random,
      44
    );
    return {
      ...forest,
      treeCount,
      floorColor: FOREST_FLOORS[country.countryId] ?? FOREST_FLOORS["COUNTRY-03"],
    };
  });
}

export function createWorldLayout(): WorldLayout {
  const countries: Record<string, CountryLayout> = {};
  const cityRoads: LayoutRoad[] = [];
  Object.entries(COUNTRY_FLAT_ANCHORS).forEach(([countryId, anchor], index) => {
    const random = mulberry32(hashSeed(`${countryId}|world-layout|20261124`));
    const boundary = makeOrganicShape(
      `${countryId}-boundary`, countryId, anchor.x, anchor.z,
      anchor.radius, anchor.radius * range(random, 0.9, 1.02), range(random, -0.12, 0.12), random, 72
    );
    const hub = makeOrganicShape(
      `${countryId}-hub`, countryId, anchor.x, anchor.z,
      WORLD_LAYOUT.hubRadius, WORLD_LAYOUT.hubRadius * 0.92, random() * TAU, random, 36
    );
    const roads = makeCityRoads(countryId, anchor, random);
    cityRoads.push(...roads);
    countries[countryId] = {
      countryId,
      anchor,
      boundary,
      hub,
      groundPatches: makeGroundPatches(countryId, anchor, random),
      roads,
      collisionRoads: [],
      park: null as unknown as LayoutPark,
      lakes: [],
      forests: [],
      hospitalPads: [],
      shelterPads: [],
    };
    void index;
  });

  const highwayRandom = mulberry32(hashSeed("world-highways|20261124"));
  const primaryRoads = [...cityRoads, ...makeHighwayRoads(highwayRandom)];
  Object.values(countries).forEach((country) => {
    const random = mulberry32(hashSeed(`${country.countryId}|world-features|20261124`));
    country.park = makePark(country.countryId, country, primaryRoads, random);
    country.lakes = makeLakes(country, primaryRoads, random);
  });

  const roads = [...primaryRoads];
  Object.values(countries).forEach((country) => {
    const random = mulberry32(hashSeed(`${country.countryId}|hospital-pads|20261124`));
    country.hospitalPads = makeHospitalPads(country, roads, random);
    roads.push(...country.hospitalPads.map((pad) => pad.accessRoad));
    const shelterRandom = mulberry32(hashSeed(`${country.countryId}|shelter-pads|20261124`));
    country.shelterPads = makeShelterPads(country, roads, shelterRandom);
    roads.push(...country.shelterPads.map((pad) => pad.accessRoad));
  });
  Object.values(countries).forEach((country) => {
    country.collisionRoads = roads.filter((road) =>
      road.countryId === country.countryId
      || (road.kind === "highway"
        && nearestPointOnRoad(country.anchor, road).distance < country.anchor.radius + 650)
    );
    const random = mulberry32(hashSeed(`${country.countryId}|forests|20261124`));
    country.forests = makeForests(country, random);
  });

  const trafficRoutes = roads
    .filter((road) => road.kind !== "access")
    .map((road) => buildLaneLoop(road.points, 7.5));
  return { countries, roads, trafficRoutes };
}

function buildingExtents(building: LayoutBuilding): { x: number; z: number; radius: number } {
  const cos = Math.abs(Math.cos(building.rotationY));
  const sin = Math.abs(Math.sin(building.rotationY));
  return {
    x: cos * building.width / 2 + sin * building.depth / 2,
    z: sin * building.width / 2 + cos * building.depth / 2,
    radius: Math.hypot(building.width / 2, building.depth / 2),
  };
}

function buildingsOverlap(a: LayoutBuilding, b: LayoutBuilding, gap = 8): boolean {
  const ea = buildingExtents(a);
  const eb = buildingExtents(b);
  return Math.abs(a.x - b.x) < ea.x + eb.x + gap && Math.abs(a.z - b.z) < ea.z + eb.z + gap;
}

const LANDMARK_EXCLUSIONS: Array<[number, number, number, number]> = [
  [-110, -105, 72, 64], [108, -115, 64, 64], [-245, 185, 42, 42], [-115, 115, 68, 68],
];

function landmarkBlocksBuilding(countryId: string, building: LayoutBuilding): boolean {
  const extents = buildingExtents(building);
  const anchor = COUNTRY_FLAT_ANCHORS[countryId];
  return LANDMARK_EXCLUSIONS.some(([x, z, width, depth]) =>
    Math.abs(building.x - (anchor.x + x)) < extents.x + width / 2 + 12
    && Math.abs(building.z - (anchor.z + z)) < extents.z + depth / 2 + 12
  );
}

export function buildingPoseClear(
  world: WorldLayout,
  country: CountryLayout,
  building: LayoutBuilding,
  ignoreBuildingId?: string
): boolean {
  const extents = buildingExtents(building);
  if (boundaryClearance(building, country.boundary) < extents.radius + 24) return false;
  if (roadNetworkClearance(building.x, building.z, country.collisionRoads, [country.hub]) < extents.radius + 8) return false;
  if (riverClearance(building.x, building.z, extents.radius + 12) < 0) return false;
  if (signedShapeClearance(building, country.park) < extents.radius + 14) return false;
  if (signedShapeClearance(building, country.park.lake) < extents.radius + 12) return false;
  if (country.lakes.some((lake) => signedShapeClearance(building, lake) < extents.radius + 12)) return false;
  if (country.forests.some((forest) => signedShapeClearance(building, forest) < extents.radius + 14)) return false;
  if (country.hospitalPads.some((pad) => Math.hypot(building.x - pad.x, building.z - pad.z) < extents.radius + 72)) return false;
  if (country.shelterPads.some((pad) => Math.hypot(building.x - pad.x, building.z - pad.z) < extents.radius + 52)) return false;
  if (landmarkBlocksBuilding(country.countryId, building)) return false;
  void ignoreBuildingId;
  return true;
}

export function generateBuildings(world: WorldLayout): LayoutBuilding[] {
  const buildings: LayoutBuilding[] = [];
  Object.values(world.countries).forEach((country) => {
    const random = mulberry32(hashSeed(`${country.countryId}|buildings|20261124`));
    const profile = BUILDING_PROFILES[country.countryId] ?? BUILDING_PROFILES["COUNTRY-03"];
    const countryBuildings: LayoutBuilding[] = [];
    const buildingGrid = new Map<string, LayoutBuilding[]>();
    const gridSize = 96;
    const gridKey = (x: number, z: number) => `${Math.floor(x / gridSize)},${Math.floor(z / gridSize)}`;
    const nearbyBuildings = (x: number, z: number) => {
      const cellX = Math.floor(x / gridSize);
      const cellZ = Math.floor(z / gridSize);
      const nearby: LayoutBuilding[] = [];
      for (let dx = -1; dx <= 1; dx += 1) {
        for (let dz = -1; dz <= 1; dz += 1) {
          nearby.push(...(buildingGrid.get(`${cellX + dx},${cellZ + dz}`) ?? []));
        }
      }
      return nearby;
    };
    const tryAdd = (x: number, z: number, rotationY: number, tangentAligned: boolean) => {
      if (countryBuildings.length >= profile.target) return;
      const distanceFromCenter = Math.hypot(x - country.anchor.x, z - country.anchor.z);
      const downtown = clamp(1 - distanceFromCenter / 720, 0, 1);
      const commercial = random() < 0.28 + downtown * 0.42;
      const width = range(random, 28, commercial ? 58 : 50);
      const depth = range(random, 26, commercial ? 50 : 44);
      const height = commercial
        ? range(random, 48, profile.maxHeight) * (0.55 + downtown * 0.65)
        : range(random, 20, country.countryId === "COUNTRY-04" ? 42 : 68);
      const building: LayoutBuilding = {
        id: `${country.countryId}-building-${countryBuildings.length + 1}`,
        countryId: country.countryId,
        x,
        z,
        width,
        depth,
        height,
        rotationY: tangentAligned ? rotationY : rotationY + range(random, -0.22, 0.22),
        color: BUILDING_TINTS[Math.floor(random() * BUILDING_TINTS.length)],
        kind: commercial ? "commercial" : "residential",
      };
      if (!buildingPoseClear(world, country, building)) return;
      if (nearbyBuildings(x, z).some((other) => buildingsOverlap(building, other))) return;
      countryBuildings.push(building);
      const key = gridKey(x, z);
      const cell = buildingGrid.get(key) ?? [];
      cell.push(building);
      buildingGrid.set(key, cell);
    };

    for (const road of country.roads) {
      const total = polylineLength(road.points);
      for (let distance = 105; distance < total - 105 && countryBuildings.length < profile.target; distance += 82) {
        const sample = samplePolyline(road.points, distance);
        const rotationY = Math.atan2(-sample.tangent.z, sample.tangent.x);
        for (const side of [-1, 1]) {
          for (const lot of [-1, 1]) {
            const setback = road.width / 2 + range(random, 52, 76);
            tryAdd(
              sample.point.x + sample.normal.x * side * setback + sample.tangent.x * lot * 19,
              sample.point.z + sample.normal.z * side * setback + sample.tangent.z * lot * 19,
              rotationY,
              true
            );
          }
        }
      }
    }

    let attempts = 0;
    while (countryBuildings.length < profile.target && attempts < 3200) {
      attempts += 1;
      const angle = random() * TAU;
      const radius = Math.sqrt(random()) * Math.min(country.anchor.radius * 0.7, 980);
      tryAdd(
        country.anchor.x + Math.cos(angle) * radius,
        country.anchor.z + Math.sin(angle) * radius,
        random() * Math.PI,
        false
      );
    }
    buildings.push(...countryBuildings);
  });
  return buildings;
}

function distanceToBuilding(x: number, z: number, building: LayoutBuilding): number {
  const extents = buildingExtents(building);
  const gapX = Math.max(Math.abs(x - building.x) - extents.x, 0);
  const gapZ = Math.max(Math.abs(z - building.z) - extents.z, 0);
  return Math.hypot(gapX, gapZ);
}

export function treePoseClear(
  world: WorldLayout,
  country: CountryLayout,
  buildings: readonly LayoutBuilding[],
  x: number,
  z: number,
  radius: number
): boolean {
  if (boundaryClearance({ x, z }, country.boundary) < radius + 18) return false;
  if (roadNetworkClearance(x, z, country.collisionRoads, [country.hub]) < radius + 8) return false;
  if (riverClearance(x, z, radius + 8) < 0) return false;
  if (signedShapeClearance({ x, z }, country.park.lake) < radius + 7) return false;
  if (distanceToPolyline({ x, z }, country.park.path) < radius + 5) return false;
  if (country.lakes.some((lake) => signedShapeClearance({ x, z }, lake) < radius + 8)) return false;
  if (country.hospitalPads.some((pad) => Math.hypot(x - pad.x, z - pad.z) < radius + 70)) return false;
  if (country.shelterPads.some((pad) => Math.hypot(x - pad.x, z - pad.z) < radius + 48)) return false;
  return !buildings.some((building) => building.countryId === country.countryId
    && distanceToBuilding(x, z, building) < radius + 7);
}

function treeKind(countryId: string, random: RandomSource): LayoutTree["kind"] {
  const roll = random();
  if (countryId === "COUNTRY-07") return roll < 0.62 ? "conifer" : "broadleaf";
  if (countryId === "COUNTRY-02") return roll < 0.5 ? "conifer" : "broadleaf";
  if (countryId === "COUNTRY-06") return roll < 0.72 ? "acacia" : "broadleaf";
  if (countryId === "COUNTRY-04") return roll < 0.48 ? "acacia" : "broadleaf";
  return roll < 0.12 ? "conifer" : "broadleaf";
}

function treeColor(kind: LayoutTree["kind"], random: RandomSource): string {
  const palette = kind === "conifer" ? CONIFER_COLORS : kind === "acacia" ? ACACIA_COLORS : TREE_COLORS;
  return palette[Math.floor(random() * palette.length)];
}

export function generateTrees(world: WorldLayout, buildings: readonly LayoutBuilding[]): LayoutTree[] {
  const trees: LayoutTree[] = [];
  Object.values(world.countries).forEach((country) => {
    const random = mulberry32(hashSeed(`${country.countryId}|trees|20261124`));
    let countryTreeCount = 0;
    const addTree = (x: number, z: number, kind: LayoutTree["kind"], height: number, radius: number) => {
      if (!treePoseClear(world, country, buildings, x, z, radius)) return;
      countryTreeCount += 1;
      trees.push({
        id: `${country.countryId}-tree-${countryTreeCount}`,
        countryId: country.countryId,
        x,
        z,
        height,
        radius,
        rotationY: random() * TAU,
        color: treeColor(kind, random),
        kind,
      });
    };

    for (const forest of country.forests) {
      let added = 0;
      let attempts = 0;
      const targetCount = Math.round(forest.treeCount * 0.68);
      while (added < targetCount && attempts < targetCount * 14) {
        attempts += 1;
        const x = range(random, forest.x - forest.rx * 1.15, forest.x + forest.rx * 1.15);
        const z = range(random, forest.z - forest.rz * 1.15, forest.z + forest.rz * 1.15);
        if (!pointInPolygon({ x, z }, forest.points)) continue;
        const kind = treeKind(country.countryId, random);
        const height = kind === "conifer" ? range(random, 20, 39) : range(random, 13, 29);
        const radius = kind === "conifer" ? range(random, 7, 11) : range(random, 8, 14);
        const before = trees.length;
        addTree(x, z, kind, height, radius);
        if (trees.length > before) added += 1;
      }
    }

    let parkTrees = 0;
    let parkAttempts = 0;
    while (parkTrees < 46 && parkAttempts < 700) {
      parkAttempts += 1;
      const x = range(random, country.park.x - country.park.rx, country.park.x + country.park.rx);
      const z = range(random, country.park.z - country.park.rz, country.park.z + country.park.rz);
      if (!pointInPolygon({ x, z }, country.park.points)) continue;
      const before = trees.length;
      addTree(x, z, "broadleaf", range(random, 11, 21), range(random, 6, 10));
      if (trees.length > before) parkTrees += 1;
    }

    for (const road of country.roads) {
      const total = polylineLength(road.points);
      for (let distance = 130; distance < total - 130; distance += 118) {
        const sample = samplePolyline(road.points, distance);
        for (const side of [-1, 1]) {
          const offset = road.width / 2 + range(random, 10, 16);
          addTree(
            sample.point.x + sample.normal.x * side * offset,
            sample.point.z + sample.normal.z * side * offset,
            "broadleaf",
            range(random, 10, 17),
            range(random, 5.5, 8)
          );
        }
      }
    }
  });
  return trees;
}

export function assignHospitalPads(
  world: WorldLayout,
  requests: readonly HospitalPlacementRequest[]
): Map<string, HospitalPad> {
  const placements = new Map<string, HospitalPad>();
  const used = new Set<string>();
  const sorted = [...requests].sort((a, b) => a.id.localeCompare(b.id));
  for (const request of sorted) {
    const pads = world.countries[request.countryId]?.hospitalPads ?? [];
    const available = pads.filter((pad) => !used.has(pad.id));
    const pad = [...available].sort((a, b) =>
      Math.hypot(a.x - request.x, a.z - request.z) - Math.hypot(b.x - request.x, b.z - request.z)
    )[0];
    if (!pad) continue;
    placements.set(request.id, pad);
    used.add(pad.id);
  }
  return placements;
}

export function assignShelterPads(
  world: WorldLayout,
  requests: readonly HospitalPlacementRequest[]
): Map<string, ShelterPad> {
  const placements = new Map<string, ShelterPad>();
  const used = new Set<string>();
  const sorted = [...requests].sort((a, b) => a.id.localeCompare(b.id));
  for (const request of sorted) {
    const pads = world.countries[request.countryId]?.shelterPads ?? [];
    const available = pads.filter((pad) => !used.has(pad.id));
    const pad = [...available].sort((a, b) =>
      Math.hypot(a.x - request.x, a.z - request.z) - Math.hypot(b.x - request.x, b.z - request.z)
    )[0];
    if (!pad) continue;
    placements.set(request.id, pad);
    used.add(pad.id);
  }
  return placements;
}

export function generateRoadsideSpots(
  world: WorldLayout,
  kind: "ambulance" | "fire",
  buildings: readonly LayoutBuilding[] = [],
  trees: readonly LayoutTree[] = []
): Record<string, RoadsideSpot[]> {
  const spots: Record<string, RoadsideSpot[]> = {};
  Object.values(world.countries).forEach((country) => {
    const countrySpots: RoadsideSpot[] = [];
    for (const road of country.roads) {
      const total = polylineLength(road.points);
      for (let distance = 165; distance < total - 165; distance += 96) {
        const sample = samplePolyline(road.points, distance);
        for (const side of [-1, 1]) {
          const offset = road.width / 2 + (kind === "fire" ? 8.5 : 7.5);
          const x = sample.point.x + sample.normal.x * side * offset;
          const z = sample.point.z + sample.normal.z * side * offset;
          if (buildings.some((building) => building.countryId === country.countryId && distanceToBuilding(x, z, building) < 13)) continue;
          if (trees.some((tree) => tree.countryId === country.countryId && Math.hypot(tree.x - x, tree.z - z) < tree.radius + 11)) continue;
          countrySpots.push({
            id: `${country.countryId}-${kind}-spot-${countrySpots.length + 1}`,
            countryId: country.countryId,
            x,
            z,
            rotationY: Math.atan2(sample.tangent.x, sample.tangent.z),
          });
        }
      }
    }
    spots[country.countryId] = countrySpots;
  });
  return spots;
}

export function assignRoadsideSpots(
  world: WorldLayout,
  requests: readonly HospitalPlacementRequest[],
  kind: "ambulance" | "fire",
  buildings: readonly LayoutBuilding[] = [],
  trees: readonly LayoutTree[] = []
): Map<string, RoadsideSpot> {
  const spots = generateRoadsideSpots(world, kind, buildings, trees);
  const placements = new Map<string, RoadsideSpot>();
  const used = new Set<string>();
  for (const request of [...requests].sort((a, b) => a.id.localeCompare(b.id))) {
    const available = (spots[request.countryId] ?? []).filter((spot) => !used.has(spot.id));
    const spot = [...available].sort((a, b) =>
      Math.hypot(a.x - request.x, a.z - request.z) - Math.hypot(b.x - request.x, b.z - request.z)
    )[0];
    if (!spot) continue;
    placements.set(request.id, spot);
    used.add(spot.id);
  }
  return placements;
}

export interface WorldLayoutValidation {
  ok: boolean;
  issues: string[];
  stats: {
    countries: number;
    roads: number;
    lakes: number;
    forests: number;
    hospitalPads: number;
    shelterPads: number;
    buildings: number;
    trees: number;
    trafficRoutes: number;
    minimumHospitalRoadClearance: number;
    minimumShelterRoadClearance: number;
    minimumBuildingRoadClearance: number;
    minimumTrafficRoadClearance: number;
  };
}

export function validateWorldLayout(
  world: WorldLayout,
  buildings: readonly LayoutBuilding[],
  trees: readonly LayoutTree[]
): WorldLayoutValidation {
  const issues: string[] = [];
  const hubs = Object.values(world.countries).map((country) => country.hub);
  const primaryRoads = world.roads.filter((road) => road.kind !== "access");
  let minimumHospitalRoadClearance = Number.POSITIVE_INFINITY;
  let minimumShelterRoadClearance = Number.POSITIVE_INFINITY;
  let minimumBuildingRoadClearance = Number.POSITIVE_INFINITY;
  let minimumTrafficRoadClearance = Number.POSITIVE_INFINITY;

  for (const country of Object.values(world.countries)) {
    for (const pad of country.hospitalPads) {
      const clearance = roadNetworkClearance(pad.x, pad.z, primaryRoads, [country.hub])
        - WORLD_LAYOUT.hospitalRadius;
      minimumHospitalRoadClearance = Math.min(minimumHospitalRoadClearance, clearance);
      if (clearance < WORLD_LAYOUT.hospitalMargin - 0.01) issues.push(`${pad.id} lacks hospital road clearance.`);
      if (boundaryClearance(pad, country.boundary) < WORLD_LAYOUT.hospitalRadius + 30) issues.push(`${pad.id} leaves its country.`);
      if (country.lakes.some((lake) => signedShapeClearance(pad, lake) < WORLD_LAYOUT.hospitalRadius + 18)) issues.push(`${pad.id} overlaps a lake.`);
      for (const road of world.roads) {
        if (road.kind !== "access" || road.id === pad.accessRoad.id) continue;
        const accessClearance = distanceToPolyline(pad, road.points) - road.width / 2;
        if (accessClearance < WORLD_LAYOUT.hospitalRadius + 6) {
          issues.push(`${pad.id} is crossed by ${road.id}.`);
        }
      }
    }
    for (const pad of country.shelterPads) {
      const clearance = roadNetworkClearance(pad.x, pad.z, primaryRoads, [country.hub])
        - WORLD_LAYOUT.shelterRadius;
      minimumShelterRoadClearance = Math.min(minimumShelterRoadClearance, clearance);
      if (clearance < WORLD_LAYOUT.shelterMargin - 0.01) issues.push(`${pad.id} lacks shelter road clearance.`);
      if (boundaryClearance(pad, country.boundary) < WORLD_LAYOUT.shelterRadius + 26) issues.push(`${pad.id} leaves its country.`);
      if (country.lakes.some((lake) => signedShapeClearance(pad, lake) < WORLD_LAYOUT.shelterRadius + 16)) issues.push(`${pad.id} overlaps a lake.`);
      for (const road of world.roads) {
        if (road.kind !== "access" || road.id === pad.accessRoad.id) continue;
        const accessClearance = distanceToPolyline(pad, road.points) - road.width / 2;
        if (accessClearance < WORLD_LAYOUT.shelterRadius + 6) issues.push(`${pad.id} is crossed by ${road.id}.`);
      }
    }
    const countryBuildings = buildings.filter((building) => building.countryId === country.countryId);
    for (const building of countryBuildings) {
      const extents = buildingExtents(building);
      const clearance = roadNetworkClearance(building.x, building.z, country.collisionRoads, [country.hub]) - extents.radius;
      minimumBuildingRoadClearance = Math.min(minimumBuildingRoadClearance, clearance);
      if (!buildingPoseClear(world, country, building)) issues.push(`${building.id} overlaps a reserved area.`);
    }
    for (let i = 0; i < countryBuildings.length; i += 1) {
      for (let j = i + 1; j < countryBuildings.length; j += 1) {
        if (buildingsOverlap(countryBuildings[i], countryBuildings[j])) {
          issues.push(`Buildings overlap: ${countryBuildings[i].id}, ${countryBuildings[j].id}.`);
        }
      }
    }
  }

  for (const tree of trees) {
    const country = world.countries[tree.countryId];
    if (!country || !treePoseClear(world, country, buildings, tree.x, tree.z, tree.radius)) {
      issues.push(`${tree.id} overlaps a road, building, hospital, or lake.`);
    }
  }

  for (let routeIndex = 0; routeIndex < world.trafficRoutes.length; routeIndex += 1) {
    const route = world.trafficRoutes[routeIndex];
    for (let sampleIndex = 0; sampleIndex <= 240; sampleIndex += 1) {
      const sample = sampleTrafficPath(route, route.total * sampleIndex / 240);
      const clearance = roadNetworkClearance(sample.x, sample.z, world.roads, hubs);
      minimumTrafficRoadClearance = Math.min(minimumTrafficRoadClearance, clearance);
      if (!pointOnRoadNetwork(sample.x, sample.z, world.roads, hubs, 0.75)) {
        issues.push(`Traffic route ${routeIndex} leaves the road network at sample ${sampleIndex}.`);
        break;
      }
    }
  }

  return {
    ok: issues.length === 0,
    issues: issues.slice(0, 100),
    stats: {
      countries: Object.keys(world.countries).length,
      roads: world.roads.length,
      lakes: Object.values(world.countries).reduce((total, country) => total + country.lakes.length, 0),
      forests: Object.values(world.countries).reduce((total, country) => total + country.forests.length, 0),
      hospitalPads: Object.values(world.countries).reduce((total, country) => total + country.hospitalPads.length, 0),
      shelterPads: Object.values(world.countries).reduce((total, country) => total + country.shelterPads.length, 0),
      buildings: buildings.length,
      trees: trees.length,
      trafficRoutes: world.trafficRoutes.length,
      minimumHospitalRoadClearance: Number.isFinite(minimumHospitalRoadClearance) ? minimumHospitalRoadClearance : 0,
      minimumShelterRoadClearance: Number.isFinite(minimumShelterRoadClearance) ? minimumShelterRoadClearance : 0,
      minimumBuildingRoadClearance: Number.isFinite(minimumBuildingRoadClearance) ? minimumBuildingRoadClearance : 0,
      minimumTrafficRoadClearance: Number.isFinite(minimumTrafficRoadClearance) ? minimumTrafficRoadClearance : 0,
    },
  };
}
