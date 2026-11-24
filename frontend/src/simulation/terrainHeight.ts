/**
 * Shared deterministic 3D terrain elevation & slope engine.
 * Guarantees that terrain mesh vertices, buildings, hospitals, shelters,
 * trees, roads, ambulances, pedestrians, and floodwater all share the exact
 * same continuous 3D surface elevation y(x, z) — zero flat planes.
 */

function hash2(x: number, y: number): number {
  const n = Math.sin(x * 127.1 + y * 311.7) * 43758.5453123;
  return n - Math.floor(n);
}

function valueNoise(x: number, y: number): number {
  const xi = Math.floor(x);
  const yi = Math.floor(y);
  const xf = x - xi;
  const yf = y - yi;
  const u = xf * xf * (3 - 2 * xf);
  const v = yf * yf * (3 - 2 * yf);
  const a = hash2(xi, yi);
  const b = hash2(xi + 1, yi);
  const c = hash2(xi, yi + 1);
  const d = hash2(xi + 1, yi + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}

function fbm(x: number, y: number, octaves = 4): number {
  let val = 0;
  let amp = 0.5;
  let freq = 1.0;
  for (let i = 0; i < octaves; i++) {
    val += amp * valueNoise(x * freq, y * freq);
    freq *= 2.03;
    amp *= 0.5;
  }
  return val;
}

export function getTerrainHeight(x: number, z: number, archetype: string): number {
  const low = archetype.toLowerCase();
  // Normalized coordinates around center (0, 0), world spans roughly [-600, 600]
  const nx = x * 0.0042;
  const nz = z * 0.0042;
  const distFromCenter = Math.hypot(x, z);
  const baseNoise = fbm(nx + 10.2, nz + 7.4, 5);
  const detailNoise = fbm(nx * 2.8 + 3.1, nz * 2.8 + 5.9, 3);

  if (low.includes("mountain")) {
    // Alpine valley in center rising into steep rugged snow-capped ridges
    const ridge = Math.abs(baseNoise - 0.5) * 2.0;
    const bowl = Math.pow(Math.min(1.4, distFromCenter / 420), 1.6) * 145;
    return -4 + ridge * 78 + detailNoise * 24 + bowl;
  }

  if (low.includes("river")) {
    // Winding carved river channel running east-west through gentle floodplain hills
    const riverCenterZ = Math.sin(x * 0.0065) * 110;
    const distRiver = Math.abs(z - riverCenterZ);
    const channelCut = Math.max(0, 1 - distRiver / 72);
    const floodplain = baseNoise * 36 + detailNoise * 9 + Math.pow(distFromCenter / 560, 1.5) * 42;
    return floodplain - channelCut * 28;
  }

  if (low.includes("coastal")) {
    // Eastern ocean basin sloping up to sandy beach, terraced coastal city, and western hills
    const coastLineX = 180 + Math.sin(z * 0.008) * 55;
    const slopeCoast = (coastLineX - x) * 0.14;
    if (x > coastLineX) {
      return Math.max(-24, slopeCoast - detailNoise * 4);
    }
    return Math.max(1.5, Math.min(28, slopeCoast * 0.65) + baseNoise * 34 + detailNoise * 8);
  }

  if (low.includes("arid")) {
    // Wind-sculpted sand dunes + stepped flat-top desert mesas
    const dunes = Math.sin(x * 0.014 + z * 0.008) * 7.5 + baseNoise * 28;
    const rawMesa = fbm(nx * 1.4 + 21.0, nz * 1.4 + 13.0, 3);
    const mesa = rawMesa > 0.62 ? Math.min(72, (rawMesa - 0.62) * 320) : 0;
    return 2 + dunes + mesa;
  }

  if (low.includes("forest")) {
    // Rolling highland hills & forested ravines
    const hills = baseNoise * 68 + detailNoise * 18;
    const outerRise = Math.pow(distFromCenter / 580, 1.4) * 55;
    return -2 + hills + outerRise;
  }

  if (low.includes("agricultural")) {
    // Gentle terraced farmland hills with shallow irrigation stream
    const streamZ = Math.cos(x * 0.005) * 90;
    const streamCut = Math.max(0, 1 - Math.abs(z - streamZ) / 38) * 12;
    return 4 + baseNoise * 26 + detailNoise * 6 - streamCut;
  }

  // Dense Urban Industrial: graded terraces + riverfront canal + surrounding ridges
  const canalCut = Math.max(0, 1 - Math.abs(z + 140) / 48) * 16;
  return 5 + Math.floor(baseNoise * 5) * 4.5 + detailNoise * 8 + Math.pow(distFromCenter / 620, 1.5) * 32 - canalCut;
}

export function getTerrainSlope(x: number, z: number, archetype: string): number {
  const eps = 4.0;
  const hx = getTerrainHeight(x + eps, z, archetype) - getTerrainHeight(x - eps, z, archetype);
  const hz = getTerrainHeight(x, z + eps, archetype) - getTerrainHeight(x, z - eps, archetype);
  return Math.hypot(hx, hz) / (2 * eps);
}

export function getWaterLevel(archetype: string, floodBoostMeters = 0): number {
  const low = archetype.toLowerCase();
  if (low.includes("coastal")) return 0.5 + floodBoostMeters;
  if (low.includes("river")) return 2.5 + floodBoostMeters;
  if (low.includes("mountain")) return -1.5 + floodBoostMeters;
  return -2.0 + floodBoostMeters;
}
