import * as THREE from "three";

function seededNoise(i: number): number {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453123;
  return x - Math.floor(x);
}

/** Realistic architectural facade texture: glass curtain-wall towers or concrete/stucco apartments. */
export function createBuildingFacadeTexture(variant: "commercial" | "residential", dayMode: boolean): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d")!;

  if (variant === "commercial") {
    ctx.fillStyle = dayMode ? "#4c5c6e" : "#1f2733";
    ctx.fillRect(0, 0, 512, 512);

    const cols = 8;
    const rows = 14;
    const cw = 512 / cols;
    const ch = 512 / rows;

    for (let r = 0; r < rows; r++) {
      ctx.fillStyle = dayMode ? "#3b4754" : "#151b24";
      ctx.fillRect(0, r * ch, 512, 6);

      for (let c = 0; c < cols; c++) {
        const n = seededNoise(r * 41 + c * 19 + 7);
        const lit = !dayMode && n > 0.56;
        if (lit) {
          ctx.fillStyle = n > 0.84 ? "#f2d6a2" : "#b8cde0";
        } else if (dayMode) {
          const g = ctx.createLinearGradient(0, r * ch + 6, 0, (r + 1) * ch - 3);
          g.addColorStop(0, n > 0.5 ? "#7a9bb8" : "#6282a1");
          g.addColorStop(1, "#3d556e");
          ctx.fillStyle = g;
        } else {
          ctx.fillStyle = "#16202e";
        }
        ctx.fillRect(c * cw + 4, r * ch + 7, cw - 8, ch - 10);
      }
    }
  } else {
    ctx.fillStyle = dayMode ? "#a89f94" : "#3a3f4a";
    ctx.fillRect(0, 0, 512, 512);

    for (let i = 0; i < 1800; i++) {
      const x = seededNoise(i * 3) * 512;
      const y = seededNoise(i * 3 + 1) * 512;
      ctx.fillStyle = i % 2 === 0 ? "rgba(255,255,255,0.035)" : "rgba(0,0,0,0.045)";
      ctx.fillRect(x, y, 4, 4);
    }

    const cols = 6;
    const rows = 12;
    const cw = 512 / cols;
    const ch = 512 / rows;

    for (let r = 0; r < rows; r++) {
      ctx.fillStyle = dayMode ? "#8a8278" : "#2b303a";
      ctx.fillRect(0, r * ch, 512, 5);

      for (let c = 0; c < cols; c++) {
        const n = seededNoise(r * 29 + c * 13 + 101);
        const lit = !dayMode && n > 0.62;
        ctx.fillStyle = dayMode ? "#4e535c" : "#1b2029";
        ctx.fillRect(c * cw + 12, r * ch + 10, cw - 24, ch - 18);
        ctx.fillStyle = lit ? (n > 0.85 ? "#f5cf8e" : "#dbe7f2") : (dayMode ? "#425366" : "#151a22");
        ctx.fillRect(c * cw + 15, r * ch + 13, cw - 30, ch - 24);
        ctx.fillStyle = dayMode ? "#6b7280" : "#2d3440";
        ctx.fillRect(c * cw + 10, (r + 1) * ch - 9, cw - 20, 4);
      }
    }
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 8;
  return tex;
}

/**
 * Paired PBR Roughness Map for commercial glass skyscrapers:
 * Glass panes = dark (roughness ~0.12 -> crisp sky reflections),
 * Concrete spandrels/mullions = bright (roughness ~0.88 -> matte stone).
 */
export function createCommercialRoughnessMap(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = "#e0e0e0"; // matte mullions
  ctx.fillRect(0, 0, 256, 256);

  const cols = 8;
  const rows = 14;
  const cw = 256 / cols;
  const ch = 256 / rows;

  ctx.fillStyle = "#1f1f1f"; // glossy glass panes
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      ctx.fillRect(c * cw + 2, r * ch + 3.5, cw - 4, ch - 5);
    }
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

/** Paired PBR Bump Map for residential recessed windows & floor ledges. */
export function createResidentialBumpMap(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = "#b0b0b0";
  ctx.fillRect(0, 0, 256, 256);

  const cols = 6;
  const rows = 12;
  const cw = 256 / cols;
  const ch = 256 / rows;

  for (let r = 0; r < rows; r++) {
    ctx.fillStyle = "#ffffff"; // raised floor slab ledge
    ctx.fillRect(0, r * ch, 256, 3);
    ctx.fillStyle = "#202020"; // recessed window cavity
    for (let c = 0; c < cols; c++) {
      ctx.fillRect(c * cw + 6, r * ch + 5, cw - 12, ch - 9);
    }
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

/** Realistic 4-lane open-world asphalt with double-yellow centerline, dashed white lanes & sidewalks. */
export function createAsphaltTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = "#5c626b";
  ctx.fillRect(0, 0, 512, 512);
  ctx.fillStyle = "#484e57";
  for (let y = 0; y < 512; y += 32) {
    ctx.fillRect(0, y, 42, 2);
    ctx.fillRect(470, y, 42, 2);
  }

  ctx.fillStyle = "#22262c";
  ctx.fillRect(42, 0, 428, 512);

  for (let i = 0; i < 4500; i++) {
    const x = 44 + seededNoise(i * 3) * 424;
    const y = seededNoise(i * 3 + 1) * 512;
    const v = 26 + Math.floor(seededNoise(i * 3 + 2) * 22);
    ctx.fillStyle = `rgb(${v},${v + 1},${v + 3})`;
    ctx.fillRect(x, y, 2, 2);
  }

  ctx.fillStyle = "#d4a024";
  ctx.fillRect(249, 0, 4, 512);
  ctx.fillRect(259, 0, 4, 512);

  ctx.fillStyle = "#d1d5db";
  for (let y = 16; y < 512; y += 64) {
    ctx.fillRect(146, y, 5, 34);
    ctx.fillRect(361, y, 5, 34);
  }

  ctx.fillStyle = "#9ca3af";
  ctx.fillRect(52, 0, 3, 512);
  ctx.fillRect(457, 0, 3, 512);

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(1, 28);
  tex.anisotropy = 8;
  return tex;
}

/** Realistic urban ground/concrete/grass patchwork texture. */
export function createTerrainTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#252b26";
  ctx.fillRect(0, 0, 512, 512);

  for (let i = 0; i < 5500; i++) {
    const x = seededNoise(i * 5) * 512;
    const y = seededNoise(i * 5 + 1) * 512;
    const w = 2 + seededNoise(i * 5 + 2) * 6;
    ctx.fillStyle = i % 3 === 0 ? "rgba(120,130,115,0.06)" : "rgba(18,22,26,0.09)";
    ctx.fillRect(x, y, w, w);
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(20, 20);
  return tex;
}

/** Seamless procedural water wave/ripple texture for animated river & ocean currents. */
export function createWaterRippleTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = "#143552";
  ctx.fillRect(0, 0, 256, 256);

  for (let i = 0; i < 500; i++) {
    const x = seededNoise(i * 7) * 256;
    const y = seededNoise(i * 7 + 1) * 256;
    const w = 14 + seededNoise(i * 7 + 2) * 34;
    const h = 1.5 + seededNoise(i * 7 + 3) * 2.5;
    ctx.fillStyle = i % 3 === 0 ? "rgba(186, 224, 255, 0.18)" : "rgba(6, 18, 32, 0.24)";
    ctx.fillRect(x, y, w, h);
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(22, 3);
  tex.anisotropy = 4;
  return tex;
}

/** Soft volumetric radial sprite for billowing smoke plumes (no square point pixels). */
export function createSmokeSpriteTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext("2d")!;
  const grad = ctx.createRadialGradient(64, 64, 6, 64, 64, 60);
  grad.addColorStop(0, "rgba(45, 48, 54, 0.85)");
  grad.addColorStop(0.45, "rgba(38, 40, 46, 0.45)");
  grad.addColorStop(1, "rgba(24, 24, 28, 0.0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(canvas);
}

/** Soft volumetric radial sprite for glowing fire cores & embers. */
export function createFireSpriteTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext("2d")!;
  const grad = ctx.createRadialGradient(64, 64, 4, 64, 64, 58);
  grad.addColorStop(0, "rgba(255, 244, 200, 1.0)");
  grad.addColorStop(0.32, "rgba(255, 138, 28, 0.88)");
  grad.addColorStop(0.7, "rgba(220, 48, 16, 0.35)");
  grad.addColorStop(1, "rgba(180, 20, 0, 0.0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(canvas);
}
