/**
 * Deterministic, renderer-agnostic city detail generation.
 *
 * Coordinates are world X/Z metres. Buildings occupy fixed grid parcels, so
 * footprints cannot overlap. The existing central park at anchor + (215, 215)
 * is deliberately not emitted again; it is reserved as empty space here.
 */

export interface CityDetailAnchor {
  readonly x: number;
  readonly z: number;
  readonly radius?: number;
  readonly ground?: string;
}

export type BuildingCategory =
  | "apartment"
  | "house"
  | "office"
  | "hotel"
  | "retail"
  | "civic"
  | "warehouse";

export type RoofKind = "flat" | "gable" | "hip" | "mansard" | "sawtooth";

export interface RoofDetail {
  kind: RoofKind;
  color: string;
  rise: number;
  hvacUnits: number;
  waterTank: boolean;
  solarPanels: boolean;
  antennaHeight: number;
}

export interface CityBuilding {
  id: string;
  x: number;
  z: number;
  width: number;
  depth: number;
  height: number;
  baseY: number;
  floors: number;
  category: BuildingCategory;
  color: string;
  trimColor: string;
  windowColor: string;
  roof: RoofDetail;
}

export interface ParkTree {
  x: number;
  z: number;
  height: number;
  radius: number;
  color: string;
}

export interface CityPark {
  id: string;
  kind: "pocket";
  x: number;
  z: number;
  width: number;
  depth: number;
  y: number;
  color: string;
  pathColor: string;
  trees: ParkTree[];
}

export interface SidewalkLot {
  id: string;
  buildingId: string;
  x: number;
  z: number;
  width: number;
  depth: number;
  y: number;
  color: string;
}

export interface ParkedCar {
  id: string;
  x: number;
  z: number;
  width: number;
  depth: number;
  height: number;
  baseY: number;
  /** Radians; generator emits only quarter turns (0 or PI / 2). */
  rotationY: number;
  color: string;
}

export interface ParkingLot {
  id: string;
  carId: string;
  x: number;
  z: number;
  width: number;
  depth: number;
  y: number;
  color: string;
}

export interface CityDetails {
  countryId: string;
  seed: string;
  anchor: CityDetailAnchor;
  buildings: CityBuilding[];
  parks: CityPark[];
  sidewalkLots: SidewalkLot[];
  parkedCars: ParkedCar[];
  parkingLots: ParkingLot[];
}

export interface CityDetailValidation {
  ok: boolean;
  buildingCount: number;
  minimumBuildings: number;
  maximumBuildings: number;
  minimumRoadClearance: number | null;
  minimumBuildingGap: number | null;
  minimumParkClearance: number | null;
  minimumRiverClearance: number | null;
  issues: string[];
}

export const CITY_DETAIL_LAYOUT = {
  gridSize: 27,
  cellSize: 80,
  cityRadius: 960,
  roadHalfWidth: 45,
  roadMargin: 4,
  centralParkX: 215,
  centralParkZ: 215,
  centralParkRadius: 155,
  riverXMin: -1750,
  riverXMax: 4800,
  riverClearance: 115,
  minimumBuildings: 180,
  maximumBuildings: 250,
  pocketParkCount: 4,
  sidewalkPadding: 5,
} as const;

/** Matches the Veridia centerline used by DioramaOpenWorld3D.tsx. */
export function veridiaRiverZ(x: number): number {
  return 210 + Math.sin(x * 0.00145) * 195 + Math.cos(x * 0.00072 + 0.6) * 95;
}

interface Profile {
  palettes: readonly string[];
  roofs: readonly string[];
  categories: readonly BuildingCategory[];
  height: readonly [number, number];
  towerChance: number;
}

const PROFILES: Record<string, Profile> = {
  "COUNTRY-01": {
    palettes: ["#ffd166", "#ef8354", "#6ecbd5", "#f7a8b8", "#f4f1de", "#8ecae6"],
    roofs: ["#e76f51", "#457b9d", "#f4a261"],
    categories: ["apartment", "office", "hotel", "retail"],
    height: [28, 118],
    towerChance: 0.3,
  },
  "COUNTRY-02": {
    palettes: ["#c7ccd4", "#9fb3c8", "#d9c7a2", "#b0a8b9", "#e4dfd4", "#7f9e9e"],
    roofs: ["#52616b", "#6d597a", "#8d99ae"],
    categories: ["house", "apartment", "civic", "office"],
    height: [18, 82],
    towerChance: 0.14,
  },
  "COUNTRY-03": {
    palettes: ["#80cbc4", "#ffcc80", "#90caf9", "#f48fb1", "#e6ee9c", "#b39ddb"],
    roofs: ["#455a64", "#00796b", "#6d4c41"],
    categories: ["office", "apartment", "retail", "civic"],
    height: [26, 132],
    towerChance: 0.34,
  },
  "COUNTRY-04": {
    palettes: ["#f4d35e", "#ee964b", "#a7c957", "#f7ede2", "#d4a373", "#84a59d"],
    roofs: ["#bc6c25", "#606c38", "#8a5a44"],
    categories: ["house", "retail", "civic", "apartment"],
    height: [12, 48],
    towerChance: 0.04,
  },
  "COUNTRY-05": {
    palettes: ["#94a3b8", "#cbd5e1", "#d4a373", "#7f8c8d", "#b8b08d", "#78909c"],
    roofs: ["#455a64", "#546e7a", "#6d6e71"],
    categories: ["warehouse", "retail", "office", "apartment"],
    height: [10, 54],
    towerChance: 0.08,
  },
  "COUNTRY-06": {
    palettes: ["#e6a15c", "#f4c95d", "#c97b63", "#f0dfc2", "#b08968", "#9c6644"],
    roofs: ["#7f5539", "#a44a3f", "#606c38"],
    categories: ["house", "retail", "civic", "apartment"],
    height: [12, 58],
    towerChance: 0.06,
  },
  "COUNTRY-07": {
    palettes: ["#95d5b2", "#f28482", "#f6bd60", "#84a59d", "#b8c0ff", "#d8f3dc"],
    roofs: ["#2a9d8f", "#6d4c41", "#457b9d"],
    categories: ["house", "apartment", "civic", "retail"],
    height: [14, 72],
    towerChance: 0.1,
  },
};

const FALLBACK_PROFILE = PROFILES["COUNTRY-03"];
const TRIMS = ["#f8fafc", "#263238", "#e7c9a9", "#b0bec5", "#fff3cd"] as const;
const WINDOWS = ["#80deea", "#b3e5fc", "#fff59d", "#dcedc8", "#e1bee7"] as const;
const CAR_COLORS = [
  "#ef5350", "#42a5f5", "#ffee58", "#66bb6a", "#ab47bc", "#ff7043",
  "#eceff1", "#263238", "#26c6da", "#8d6e63",
] as const;
const TREE_COLORS = ["#2e7d32", "#43a047", "#558b2f", "#7cb342", "#1b5e20"] as const;
const PARK_COLORS = ["#81c784", "#aed581", "#66bb6a", "#9ccc65"] as const;
const POCKET_PARK_OFFSETS = [
  [-320, -320], [320, -320], [-320, 320], [320, 320],
  [0, -400], [400, 0], [-400, 0], [0, 400],
  [-480, -160], [480, -160], [-480, 160], [480, 160],
  [-160, -480], [160, -480], [-160, 480], [160, 480],
] as const;

const q = (value: number): number => Math.round(value * 1000) / 1000;
const pick = <T,>(items: readonly T[], random: () => number): T =>
  items[Math.floor(random() * items.length) % items.length];

function hashSeed(text: string): number {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function mulberry32(seed: number): () => number {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let value = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function normalizeSeed(seed: number | string): string {
  return typeof seed === "number" && Number.isFinite(seed) ? String(seed) : String(seed ?? 0);
}

function profileFor(countryId: string): Profile {
  return PROFILES[countryId] ?? FALLBACK_PROFILE;
}

/** Conservative signed clearance from a box to the winding river corridor. */
function riverMargin(
  x: number,
  z: number,
  width: number,
  depth: number,
  anchorX: number,
  anchorZ: number,
): number | null {
  const worldX = anchorX + x;
  if (worldX < CITY_DETAIL_LAYOUT.riverXMin || worldX > CITY_DETAIL_LAYOUT.riverXMax) return null;
  // The extra term covers the centerline slope across the entire footprint.
  return Math.abs(anchorZ + z - veridiaRiverZ(worldX))
    - depth / 2
    - (width / 2) * 0.36
    - CITY_DETAIL_LAYOUT.riverClearance;
}

function isParcelClear(
  x: number,
  z: number,
  width: number,
  depth: number,
  anchor: CityDetailAnchor,
  cityRadius: number,
): boolean {
  const halfW = width / 2;
  const halfD = depth / 2;
  const roadEdge = CITY_DETAIL_LAYOUT.roadHalfWidth + CITY_DETAIL_LAYOUT.roadMargin;
  if (Math.abs(x) - halfW < roadEdge || Math.abs(z) - halfD < roadEdge) return false;

  const parkDistance = Math.hypot(
    x - CITY_DETAIL_LAYOUT.centralParkX,
    z - CITY_DETAIL_LAYOUT.centralParkZ,
  );
  if (parkDistance - Math.hypot(halfW, halfD) < CITY_DETAIL_LAYOUT.centralParkRadius + 5) return false;

  const riverGap = riverMargin(x, z, width, depth, anchor.x, anchor.z);
  if (riverGap !== null && riverGap < 0) return false;

  const cornerX = Math.abs(x) + halfW;
  const cornerZ = Math.abs(z) + halfD;
  return Math.hypot(cornerX, cornerZ) <= cityRadius;
}

function makePocketPark(
  id: string,
  x: number,
  z: number,
  random: () => number,
): CityPark {
  const width = 54;
  const depth = 54;
  const trees: ParkTree[] = [];
  for (let ring = 0; ring < 2; ring++) {
    const count = ring === 0 ? 8 : 4;
    const radius = ring === 0 ? 18 : 7;
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2 + ring * 0.38;
      trees.push({
        x: q(x + Math.cos(angle) * radius),
        z: q(z + Math.sin(angle) * radius),
        height: q(7 + random() * 7),
        radius: q(2.8 + random() * 1.8),
        color: pick(TREE_COLORS, random),
      });
    }
  }
  return {
    id,
    kind: "pocket",
    x,
    z,
    width,
    depth,
    y: 0.4,
    color: pick(PARK_COLORS, random),
    pathColor: "#e5d5bc",
    trees,
  };
}

function makeBuilding(
  id: string,
  localX: number,
  localZ: number,
  anchor: CityDetailAnchor,
  profile: Profile,
  cellSeed: number,
): CityBuilding {
  const random = mulberry32(cellSeed);
  const radius = Math.hypot(localX, localZ);
  let category = pick(profile.categories, random);
  if (radius < 260 && random() < profile.towerChance) {
    category = profile.categories.includes("office") ? "office" : category;
  }

  const industrial = category === "warehouse";
  const house = category === "house";
  const width = q(industrial ? 38 + random() * 12 : house ? 22 + random() * 10 : 27 + random() * 21);
  const depth = q(industrial ? 30 + random() * 14 : house ? 21 + random() * 11 : 25 + random() * 19);
  const downtown = Math.max(0, 1 - radius / 520);
  const height = q(
    (profile.height[0] + random() * (profile.height[1] - profile.height[0]))
    * (0.5 + downtown * 0.5),
  );
  const roll = random();
  const roofKind: RoofKind = industrial
    ? (roll < 0.45 ? "sawtooth" : "flat")
    : house
      ? (roll < 0.5 ? "gable" : roll < 0.8 ? "hip" : "flat")
      : roll < 0.58 ? "flat" : roll < 0.78 ? "mansard" : "hip";

  return {
    id,
    x: q(anchor.x + localX),
    z: q(anchor.z + localZ),
    width,
    depth,
    height,
    baseY: 0.5,
    floors: Math.max(2, Math.round(height / 3.4)),
    category,
    color: pick(profile.palettes, random),
    trimColor: pick(TRIMS, random),
    windowColor: pick(WINDOWS, random),
    roof: {
      kind: roofKind,
      color: pick(profile.roofs, random),
      rise: q(roofKind === "flat" ? 0.8 : 2.5 + random() * 4),
      hvacUnits: height > 35 ? 1 + Math.floor(random() * 4) : random() < 0.3 ? 1 : 0,
      waterTank: height > 45 && random() < 0.3,
      solarPanels: random() < 0.28,
      antennaHeight: height > 95 && random() < 0.35 ? q(5 + random() * 12) : 0,
    },
  };
}

interface Parcel {
  gridX: number;
  gridZ: number;
  x: number;
  z: number;
}

interface Box {
  x: number;
  z: number;
  width: number;
  depth: number;
}

function boxesOverlap(a: Box, b: Box): boolean {
  return Math.abs(a.x - b.x) < (a.width + b.width) / 2 - 0.001
    && Math.abs(a.z - b.z) < (a.depth + b.depth) / 2 - 0.001;
}

/** Generate one country's dense urban blocks from an anchor and stable seed. */
export function generateCityDetails(
  anchor: CityDetailAnchor,
  countryId: string,
  seed: number | string = 0,
): CityDetails {
  if (!Number.isFinite(anchor.x) || !Number.isFinite(anchor.z)) {
    throw new TypeError("generateCityDetails requires a finite anchor.x and anchor.z");
  }

  const normalizedSeed = normalizeSeed(seed);
  const rootSeed = hashSeed(`${countryId}|${normalizedSeed}`);
  const random = mulberry32(rootSeed);
  const profile = profileFor(countryId);
  const cityRadius = Math.min(CITY_DETAIL_LAYOUT.cityRadius, (anchor.radius ?? 1350) * 0.6);
  const parcels: Parcel[] = [];
  const half = Math.floor(CITY_DETAIL_LAYOUT.gridSize / 2);

  for (let gridZ = -half; gridZ <= half; gridZ++) {
    for (let gridX = -half; gridX <= half; gridX++) {
      const x = gridX * CITY_DETAIL_LAYOUT.cellSize;
      const z = gridZ * CITY_DETAIL_LAYOUT.cellSize;
      if (Math.hypot(x, z) > cityRadius) continue;
      // Fixed 80 m parcels leave internal streets and guarantee separation.
      // Reserve for the largest building plus its 5 m sidewalk on every side.
      if (isParcelClear(x, z, 60, 54, anchor, cityRadius)) parcels.push({ gridX, gridZ, x, z });
    }
  }

  // Reserve four well-spaced pocket parks before filling building parcels.
  const preferredOffsets = POCKET_PARK_OFFSETS
    .map((offset) => ({ offset, rank: random() }))
    .sort((a, b) => a.rank - b.rank)
    .map(({ offset }) => offset);
  const parks: CityPark[] = [];
  const reserved = new Set<string>();
  for (const [x, z] of preferredOffsets) {
    if (parks.length >= CITY_DETAIL_LAYOUT.pocketParkCount) break;
    if (Math.hypot(x, z) > cityRadius) continue;
    if (!isParcelClear(x, z, 58, 58, anchor, cityRadius)) continue;
    if (parks.some((park) => Math.hypot(park.x - anchor.x - x, park.z - anchor.z - z) < 240)) continue;
    const gridX = x / CITY_DETAIL_LAYOUT.cellSize;
    const gridZ = z / CITY_DETAIL_LAYOUT.cellSize;
    const key = `${gridX},${gridZ}`;
    if (reserved.has(key)) continue;
    reserved.add(key);
    parks.push(makePocketPark(
      `${countryId}-park-${parks.length + 1}`,
      q(anchor.x + x),
      q(anchor.z + z),
      mulberry32(hashSeed(`${rootSeed}|park|${key}`)),
    ));
  }

  let buildingParcels = parcels.filter((parcel) => !reserved.has(`${parcel.gridX},${parcel.gridZ}`));
  // Deterministic edge thinning only if an unusually large anchor exceeds the cap.
  if (buildingParcels.length > CITY_DETAIL_LAYOUT.maximumBuildings) {
    buildingParcels = buildingParcels
      .map((parcel) => ({
        parcel,
        rank: Math.hypot(parcel.x, parcel.z)
          + random() * 90
          + Math.abs(parcel.gridX) * 0.01
          + Math.abs(parcel.gridZ) * 0.01,
      }))
      .sort((a, b) => a.rank - b.rank)
      .slice(0, CITY_DETAIL_LAYOUT.maximumBuildings)
      .map(({ parcel }) => parcel);
  }

  const buildings: CityBuilding[] = [];
  const sidewalkLots: SidewalkLot[] = [];
  for (const parcel of buildingParcels) {
    const id = `${countryId}-building-${parcel.gridX + half}-${parcel.gridZ + half}`;
    const cellSeed = hashSeed(`${rootSeed}|cell|${parcel.gridX}|${parcel.gridZ}`);
    const building = makeBuilding(
      id, parcel.x, parcel.z, anchor, profile, cellSeed,
    );
    buildings.push(building);
    sidewalkLots.push({
      id: `${id}-sidewalk`,
      buildingId: id,
      x: building.x,
      z: building.z,
      width: q(building.width + CITY_DETAIL_LAYOUT.sidewalkPadding * 2),
      depth: q(building.depth + CITY_DETAIL_LAYOUT.sidewalkPadding * 2),
      y: 0.4,
      color: "#d7dce2",
    });
  }

  const occupied: Box[] = [...sidewalkLots, ...parks];
  const parkedCars: ParkedCar[] = [];
  const parkingLots: ParkingLot[] = [];
  for (const building of buildings) {
    if (random() >= 0.48) continue;
    const localX = building.x - anchor.x;
    const localZ = building.z - anchor.z;
    const gridX = Math.round(localX / CITY_DETAIL_LAYOUT.cellSize);
    const gridZ = Math.round(localZ / CITY_DETAIL_LAYOUT.cellSize);
    const canParkVertical = Math.abs(gridX) > 1;
    const canParkHorizontal = Math.abs(gridZ) > 1;
    if (!canParkVertical && !canParkHorizontal) continue;

    const vertical = canParkVertical && (!canParkHorizontal || random() < 0.5);
    const lane = vertical
      ? localX - Math.sign(localX) * CITY_DETAIL_LAYOUT.cellSize / 2
      : localZ - Math.sign(localZ) * CITY_DETAIL_LAYOUT.cellSize / 2;
    const along = (vertical ? localZ : localX) + (random() - 0.5) * 24;
    const localCarX = vertical ? lane : along;
    const localCarZ = vertical ? along : lane;
    const rotationY = vertical ? 0 : Math.PI / 2;
    const width = vertical ? 2.8 : 5.8;
    const depth = vertical ? 5.8 : 2.8;
    const carBox: Box = { x: q(anchor.x + localCarX), z: q(anchor.z + localCarZ), width, depth };
    const lotBox: Box = { ...carBox, width: width + 1.6, depth: depth + 1.6 };
    if (!isParcelClear(localCarX, localCarZ, lotBox.width, lotBox.depth, anchor, cityRadius + 45)) continue;
    if (occupied.some((box) => boxesOverlap(lotBox, box))) continue;

    const id = `${building.id}-car`;
    parkedCars.push({
      id,
      ...carBox,
      height: 1.6,
      baseY: 0.72,
      rotationY,
      color: pick(CAR_COLORS, random),
    });
    parkingLots.push({
      id: `${id}-bay`,
      carId: id,
      ...lotBox,
      y: 0.67,
      color: "#64748b",
    });
    occupied.push(lotBox);
  }

  return {
    countryId,
    seed: normalizedSeed,
    anchor: { x: anchor.x, z: anchor.z, radius: anchor.radius, ground: anchor.ground },
    buildings,
    parks,
    sidewalkLots,
    parkedCars,
    parkingLots,
  };
}

function boxGap(a: Box, b: Box): number {
  const gapX = Math.max(
    Math.abs(a.x - b.x) - (a.width + b.width) / 2,
    0,
  );
  const gapZ = Math.max(
    Math.abs(a.z - b.z) - (a.depth + b.depth) / 2,
    0,
  );
  return Math.hypot(gapX, gapZ);
}

/** Validate counts, grid separation, boulevards, central park, and river clearance. */
export function validateCityDetails(
  details: CityDetails,
  options: { minimumBuildings?: number; maximumBuildings?: number } = {},
): CityDetailValidation {
  const minimumBuildings = options.minimumBuildings ?? CITY_DETAIL_LAYOUT.minimumBuildings;
  const maximumBuildings = options.maximumBuildings ?? CITY_DETAIL_LAYOUT.maximumBuildings;
  const issues: string[] = [];
  let minimumRoadClearance: number | null = null;
  let minimumBuildingGap: number | null = null;
  let minimumParkClearance: number | null = null;
  let minimumRiverClearance: number | null = null;

  if (details.buildings.length < minimumBuildings || details.buildings.length > maximumBuildings) {
    issues.push(`Building count ${details.buildings.length} is outside ${minimumBuildings}-${maximumBuildings}.`);
  }

  const allBoxes: Array<Box & { id: string }> = [
    ...details.buildings,
    ...details.parks,
    ...details.sidewalkLots,
    ...details.parkedCars,
    ...details.parkingLots,
  ];
  const updateMinimum = (current: number | null, value: number | null): number | null =>
    value === null ? current : current === null ? value : Math.min(current, value);

  for (const box of allBoxes) {
    if (![box.x, box.z, box.width, box.depth].every(Number.isFinite)
      || box.width <= 0 || box.depth <= 0) {
      issues.push(`${box.id} has invalid coordinates or dimensions.`);
      continue;
    }
    const localX = box.x - details.anchor.x;
    const localZ = box.z - details.anchor.z;
    const roadClearance = Math.min(
      Math.abs(localX) - box.width / 2,
      Math.abs(localZ) - box.depth / 2,
    );
    minimumRoadClearance = updateMinimum(minimumRoadClearance, roadClearance);
    if (roadClearance < CITY_DETAIL_LAYOUT.roadHalfWidth - 0.001) {
      issues.push(`${box.id} intrudes into a central boulevard.`);
    }

    const parkClearance = Math.hypot(
      localX - CITY_DETAIL_LAYOUT.centralParkX,
      localZ - CITY_DETAIL_LAYOUT.centralParkZ,
    ) - Math.hypot(box.width / 2, box.depth / 2)
      - CITY_DETAIL_LAYOUT.centralParkRadius;
    minimumParkClearance = updateMinimum(minimumParkClearance, parkClearance);
    if (parkClearance < -0.001) issues.push(`${box.id} intrudes into the central park.`);

    const riverGap = riverMargin(localX, localZ, box.width, box.depth, details.anchor.x, details.anchor.z);
    minimumRiverClearance = updateMinimum(minimumRiverClearance, riverGap);
    if (riverGap !== null && riverGap < -0.001) {
      issues.push(`${box.id} intrudes into the Veridia river corridor.`);
    }
  }
  for (const building of details.buildings) {
    if (!Number.isFinite(building.height) || building.height <= 0) {
      issues.push(`${building.id} has an invalid height.`);
    }
  }

  for (let i = 0; i < details.buildings.length; i++) {
    for (let j = i + 1; j < details.buildings.length; j++) {
      const a = details.buildings[i];
      const b = details.buildings[j];
      const gap = boxGap(a, b);
      if (boxesOverlap(a, b)) issues.push(`Buildings overlap: ${a.id}, ${b.id}.`);
      else minimumBuildingGap = updateMinimum(minimumBuildingGap, gap);
    }
  }

  if (details.sidewalkLots.length !== details.buildings.length) {
    issues.push("Each building must have exactly one sidewalk lot.");
  }
  if (details.parkingLots.length !== details.parkedCars.length) {
    issues.push("Each parked car must have exactly one parking bay.");
  }
  for (let i = 0; i < details.parks.length; i++) {
    for (let j = i + 1; j < details.parks.length; j++) {
      if (boxesOverlap(details.parks[i], details.parks[j])) issues.push("Pocket parks overlap.");
    }
    for (const building of details.buildings) {
      if (boxesOverlap(details.parks[i], building)) issues.push(`Park ${details.parks[i].id} overlaps a building.`);
    }
  }
  for (let i = 0; i < details.parkedCars.length; i++) {
    for (let j = i + 1; j < details.parkedCars.length; j++) {
      if (boxesOverlap(details.parkedCars[i], details.parkedCars[j])) issues.push("Parked cars overlap.");
    }
    for (const building of details.buildings) {
      if (boxesOverlap(details.parkedCars[i], building)) issues.push(`Car ${details.parkedCars[i].id} overlaps a building.`);
    }
  }

  return {
    ok: issues.length === 0,
    buildingCount: details.buildings.length,
    minimumBuildings,
    maximumBuildings,
    minimumRoadClearance: q(minimumRoadClearance ?? 0),
    minimumBuildingGap: q(minimumBuildingGap ?? 0),
    minimumParkClearance: q(minimumParkClearance ?? 0),
    minimumRiverClearance: minimumRiverClearance === null ? null : q(minimumRiverClearance),
    issues,
  };
}
