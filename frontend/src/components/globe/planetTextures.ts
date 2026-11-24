import * as THREE from "three";

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

function fbm(x: number, y: number, octaves = 5): number {
  let val = 0;
  let amp = 0.5;
  let freq = 1.0;
  for (let i = 0; i < octaves; i++) {
    val += amp * valueNoise(x * freq, y * freq);
    freq *= 2.02;
    amp *= 0.5;
  }
  return val;
}

export interface PlanetPBRTextures {
  albedoMap: THREE.CanvasTexture;
  bumpMap: THREE.CanvasTexture;
  roughnessMap: THREE.CanvasTexture;
  cloudsMap: THREE.CanvasTexture;
}

/**
 * Generates realistic Earth-like procedural PBR planetary textures (continents, shallow shelves,
 * forests, plains, deserts, alpine snow peaks, specular oceans, elevation bump, and cloud deck).
 */
export function createRealisticPlanetTextures(): PlanetPBRTextures {
  const w = 1024;
  const h = 512;

  const albedoCanvas = document.createElement("canvas");
  albedoCanvas.width = w;
  albedoCanvas.height = h;
  const aCtx = albedoCanvas.getContext("2d")!;
  const aImg = aCtx.createImageData(w, h);

  const bumpCanvas = document.createElement("canvas");
  bumpCanvas.width = w;
  bumpCanvas.height = h;
  const bCtx = bumpCanvas.getContext("2d")!;
  const bImg = bCtx.createImageData(w, h);

  const roughCanvas = document.createElement("canvas");
  roughCanvas.width = w;
  roughCanvas.height = h;
  const rCtx = roughCanvas.getContext("2d")!;
  const rImg = rCtx.createImageData(w, h);

  const cloudCanvas = document.createElement("canvas");
  cloudCanvas.width = w;
  cloudCanvas.height = h;
  const cCtx = cloudCanvas.getContext("2d")!;
  const cImg = cCtx.createImageData(w, h);

  // Landmass anchors around our 7 countries + global continents so all 7 nations sit on rich terrain
  const continentCenters = [
    { lat: 19.5, lon: 79.0, rad: 22.0, weight: 0.42 }, // Main 7-Nation Subcontinent
    { lat: 38.0, lon: -100.0, rad: 30.0, weight: 0.36 },
    { lat: -15.0, lon: -60.0, rad: 24.0, weight: 0.34 },
    { lat: 48.0, lon: 20.0, rad: 28.0, weight: 0.35 },
    { lat: 5.0, lon: 22.0, rad: 28.0, weight: 0.36 },
    { lat: 35.0, lon: 105.0, rad: 32.0, weight: 0.36 },
    { lat: -25.0, lon: 135.0, rad: 18.0, weight: 0.32 },
  ];

  for (let y = 0; y < h; y++) {
    const v = y / h;
    const lat = 90 - v * 180;
    const absLat = Math.abs(lat);
    for (let x = 0; x < w; x++) {
      const u = x / w;
      const lon = u * 360 - 180;
      const idx = (y * w + x) * 4;

      // Seamless spherical-ish domain warping
      const nx = Math.cos(u * Math.PI * 2) * 2.2 + 4.0;
      const ny = Math.sin(u * Math.PI * 2) * 2.2 + 4.0;
      const nz = v * 4.4;
      let elev = fbm(nx + nz * 0.7, ny + nz * 1.1, 5) * 0.72 + fbm(u * 12, v * 6, 4) * 0.28;

      for (const cc of continentCenters) {
        const dlat = lat - cc.lat;
        let dlon = lon - cc.lon;
        if (dlon > 180) dlon -= 360;
        if (dlon < -180) dlon += 360;
        const d = Math.hypot(dlat, dlon * 0.85);
        if (d < cc.rad * 1.6) {
          elev += cc.weight * Math.max(0, 1 - d / (cc.rad * 1.6));
        }
      }

      const moisture = fbm(u * 10 + 11.3, v * 5 + 3.7, 4);
      const seaLevel = 0.56;

      let r = 12, g = 42, b = 82;
      let bump = 0;
      let rough = 58; // Glossy ocean water

      if (absLat > 74 + elev * 8) {
        // Polar ice cap
        r = 228; g = 236; b = 244;
        bump = 135;
        rough = 195;
      } else if (elev < seaLevel) {
        // Deep ocean -> shallow turquoise continental shelf
        const depth = Math.min(1, (seaLevel - elev) / 0.28);
        r = Math.round(28 * (1 - depth) + 9 * depth);
        g = Math.round(115 * (1 - depth) + 34 * depth);
        b = Math.round(145 * (1 - depth) + 74 * depth);
        bump = 10;
        rough = 52;
      } else {
        // Land biomes
        const landH = Math.min(1, (elev - seaLevel) / 0.45);
        bump = Math.round(90 + landH * 165);
        rough = 222; // Matte terrain

        if (landH < 0.045) {
          // Sandy coastline / river delta
          r = 196; g = 182; b = 142;
        } else if (landH > 0.68) {
          // Alpine snow & granite peaks
          r = 212; g = 216; b = 222;
        } else if (landH > 0.48) {
          // Rocky highlands
          r = 122; g = 114; b = 104;
        } else if (moisture < 0.36 && absLat < 38) {
          // Arid steppe & desert
          r = 184; g = 152; b = 106;
        } else if (moisture > 0.58) {
          // Lush dense forest
          r = 44; g = 96; b = 52;
        } else {
          // Agricultural plains & temperate hills
          r = 92; g = 132; b = 72;
        }
      }

      aImg.data[idx] = r;
      aImg.data[idx + 1] = g;
      aImg.data[idx + 2] = b;
      aImg.data[idx + 3] = 255;

      bImg.data[idx] = bump;
      bImg.data[idx + 1] = bump;
      bImg.data[idx + 2] = bump;
      bImg.data[idx + 3] = 255;

      rImg.data[idx] = rough;
      rImg.data[idx + 1] = rough;
      rImg.data[idx + 2] = rough;
      rImg.data[idx + 3] = 255;

      // Procedural swirling clouds
      const cn = fbm(u * 9 + Math.sin(v * 6) * 0.4, v * 5 + 19.2, 5);
      const cloudAlpha = cn > 0.57 ? Math.min(220, Math.round(((cn - 0.57) / 0.35) * 235)) : 0;
      cImg.data[idx] = 244;
      cImg.data[idx + 1] = 248;
      cImg.data[idx + 2] = 255;
      cImg.data[idx + 3] = cloudAlpha;
    }
  }

  aCtx.putImageData(aImg, 0, 0);
  bCtx.putImageData(bImg, 0, 0);
  rCtx.putImageData(rImg, 0, 0);
  cCtx.putImageData(cImg, 0, 0);

  const albedoMap = new THREE.CanvasTexture(albedoCanvas);
  albedoMap.colorSpace = THREE.SRGBColorSpace;
  albedoMap.anisotropy = 8;

  const bumpMap = new THREE.CanvasTexture(bumpCanvas);
  const roughnessMap = new THREE.CanvasTexture(roughCanvas);
  const cloudsMap = new THREE.CanvasTexture(cloudCanvas);
  cloudsMap.colorSpace = THREE.SRGBColorSpace;

  return { albedoMap, bumpMap, roughnessMap, cloudsMap };
}
