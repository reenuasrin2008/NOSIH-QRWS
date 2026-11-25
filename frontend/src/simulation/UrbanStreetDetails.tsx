import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import type { ReactNode, RefObject } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

export interface UrbanStreetAnchor {
  x: number;
  z: number;
  radius?: number;
  ground?: string;
  name?: string;
}

export interface UrbanStreetDetailsProps {
  /** Country anchors are injected so this module never imports the diorama scene. */
  anchors: Record<string, UrbanStreetAnchor>;
  quality?: "high" | "low";
  timeOfDay?: "day" | "golden" | "night";
  /** Top surface of the diorama sidewalks. */
  baseY?: number;
  seed?: number;
}

interface Placement {
  x: number;
  y: number;
  z: number;
  yaw: number;
  sx: number;
  sy: number;
  sz: number;
}

interface StreetLayout {
  sidewalks: Placement[];
  streetlightPoles: Placement[];
  streetlightBulbs: Placement[];
  signalFrames: Placement[];
  signalRed: Placement[];
  signalAmber: Placement[];
  signalGreen: Placement[];
  benches: Placement[];
  hydrants: Placement[];
  planters: Placement[];
  bins: Placement[];
  barriers: Placement[];
  busFrames: Placement[];
  busGlass: Placement[];
  billboardFrames: Placement[];
  smallSignFrames: Placement[];
  signPanels: [Placement[], Placement[], Placement[]];
  covers: Placement[];
  bollards: Placement[];
  tactilePads: Placement[];
}

interface GeometryPart {
  geometry: THREE.BufferGeometry;
  color: THREE.ColorRepresentation;
  position?: [number, number, number];
  rotation?: [number, number, number];
  scale?: [number, number, number];
}

interface EdgeState {
  anchorIndex: number;
  anchor: UrbanStreetAnchor;
  edgeIndex: number;
  axis: "x" | "z";
  side: -1 | 1;
  occupied: Array<[number, number]>;
}

const DEFAULT_BASE_Y = 0.8;
const ROAD_HALF_WIDTH = 19;
const HUB_RADIUS = 72;
const CROSSWALKS = [-280, -34, 34, 280];

function hash(...values: number[]): number {
  const value = Math.sin(values.reduce((sum, item, index) => sum + item * (index + 1), 0) * 12.9898 + 78.233) * 43758.5453;
  return value - Math.floor(value);
}

function mergedGeometry(parts: GeometryPart[]): THREE.BufferGeometry {
  const prepared = parts.map((part) => {
    const geometry = part.geometry.index ? part.geometry.toNonIndexed() : part.geometry.clone();
    if (part.rotation) {
      geometry.rotateX(part.rotation[0]);
      geometry.rotateY(part.rotation[1]);
      geometry.rotateZ(part.rotation[2]);
    }
    if (part.scale) geometry.scale(...part.scale);
    if (part.position) geometry.translate(...part.position);

    const color = new THREE.Color(part.color);
    const colors = new Float32Array(geometry.attributes.position.count * 3);
    for (let i = 0; i < geometry.attributes.position.count; i += 1) {
      colors[i * 3] = color.r;
      colors[i * 3 + 1] = color.g;
      colors[i * 3 + 2] = color.b;
    }
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    part.geometry.dispose();
    return geometry;
  });

  const result = mergeGeometries(prepared, false);
  prepared.forEach((geometry) => geometry.dispose());
  if (!result) throw new Error("UrbanStreetDetails: failed to merge instanced geometry.");
  result.computeBoundingSphere();
  return result;
}

function box(size: [number, number, number], color: THREE.ColorRepresentation, position: [number, number, number]): GeometryPart {
  return { geometry: new THREE.BoxGeometry(...size), color, position };
}

function cylinder(
  radii: [number, number],
  height: number,
  segments: number,
  color: THREE.ColorRepresentation,
  position: [number, number, number],
  rotation?: [number, number, number]
): GeometryPart {
  return { geometry: new THREE.CylinderGeometry(...radii, height, segments), color, position, rotation };
}

function makeTactileGeometry(high: boolean): THREE.BufferGeometry {
  const parts: GeometryPart[] = [box([1.45, 0.035, 3.25], "#d8a92f", [0, 0.015, 0])];
  const rows = high ? 3 : 2;
  const columns = high ? 9 : 5;
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      parts.push(
        cylinder(
          [0.07, 0.075],
          0.045,
          high ? 8 : 6,
          "#f4cc58",
          [
            ((row + 0.5) / rows - 0.5) * 1.25,
            0.055,
            ((column + 0.5) / columns - 0.5) * 2.95,
          ]
        )
      );
    }
  }
  return mergedGeometry(parts);
}

function makeStreetGeometries(high: boolean) {
  const radial = high ? 12 : 6;
  const sidewalk = mergedGeometry([
    box([1, 0.18, 4.8], "#c8cdd1", [0, -0.09, 0]),
    box([1, 0.28, 0.34], "#e2e3df", [0, 0.02, -2.34]),
  ]);

  const streetlightPole = mergedGeometry([
    cylinder([0.2, 0.27], 9, radial, "#343d45", [0, 4.5, 0]),
    cylinder([0.38, 0.48], 0.35, radial, "#414a50", [0, 0.175, 0]),
    box([3.1, 0.16, 0.16], "#343d45", [1.55, 8.85, 0]),
    box([0.9, 0.24, 0.58], "#343d45", [3.05, 8.67, 0]),
  ]);
  const streetlightBulb = new THREE.SphereGeometry(0.31, high ? 12 : 6, high ? 8 : 4);
  streetlightBulb.scale(1.45, 0.48, 1);
  streetlightBulb.translate(3.05, 8.49, 0);

  const signalFrameParts: GeometryPart[] = [
    cylinder([0.18, 0.26], 7.6, radial, "#303a40", [0, 3.8, 0]),
    cylinder([0.38, 0.46], 0.3, radial, "#303a40", [0, 0.15, 0]),
    box([4.2, 0.18, 0.18], "#303a40", [2.1, 7.5, 0]),
    box([0.7, 1.9, 0.72], "#252d31", [4.2, 6.85, 0]),
  ];
  [7.35, 6.85, 6.35].forEach((height) => {
    signalFrameParts.push(box([0.8, 0.12, 0.88], "#252d31", [4.2, height + 0.33, 0.36]));
  });
  const signalFrame = mergedGeometry(signalFrameParts);
  const signalLens = new THREE.CylinderGeometry(0.22, 0.22, 0.075, high ? 14 : 7);
  signalLens.rotateX(Math.PI / 2);

  const benchParts: GeometryPart[] = [];
  for (let i = 0; i < 4; i += 1) {
    benchParts.push(box([3.25, 0.12, 0.17], "#9a653f", [0, 0.74, -0.3 + i * 0.2]));
    benchParts.push(box([3.25, 0.17, 0.12], "#a66d43", [0, 1.05 + i * 0.22, 0.38]));
  }
  [-1.32, 1.32].forEach((x) => {
    [-0.27, 0.27].forEach((z) => benchParts.push(box([0.14, 0.72, 0.14], "#354047", [x, 0.36, z])));
    benchParts.push(box([0.13, 0.13, 0.72], "#354047", [x, 1.03, 0.02]));
  });
  const bench = mergedGeometry(benchParts);

  const hydrant = mergedGeometry([
    cylinder([0.39, 0.46], 1.08, radial, "#bd3d35", [0, 0.66, 0]),
    cylinder([0.54, 0.59], 0.16, radial, "#9f302b", [0, 0.08, 0]),
    cylinder([0.15, 0.18], 0.2, radial, "#d9c9a2", [0, 1.28, 0]),
    cylinder([0.16, 0.16], 0.58, radial, "#bd3d35", [0.48, 0.83, 0], [0, 0, Math.PI / 2]),
    cylinder([0.16, 0.16], 0.58, radial, "#bd3d35", [-0.48, 0.83, 0], [0, 0, Math.PI / 2]),
    {
      geometry: new THREE.SphereGeometry(0.4, high ? 14 : 7, high ? 8 : 4, 0, Math.PI * 2, 0, Math.PI / 2),
      color: "#cf493d",
      position: [0, 1.19, 0],
    },
  ]);

  const planter = mergedGeometry([
    box([2.1, 0.72, 1.2], "#a87553", [0, 0.36, 0]),
    box([2.25, 0.15, 1.35], "#c2916c", [0, 0.75, 0]),
    box([1.92, 0.08, 1.08], "#4b4033", [0, 0.83, 0]),
    {
      geometry: new THREE.DodecahedronGeometry(0.75, 0),
      color: "#477b45",
      position: [0, 1.28, 0],
      scale: [1.35, 0.8, 0.95],
    },
    {
      geometry: new THREE.DodecahedronGeometry(0.48, 0),
      color: "#5d9151",
      position: [0.55, 1.18, 0.12],
      scale: [1, 0.78, 1],
    },
  ]);

  const binParts: GeometryPart[] = [
    cylinder([0.41, 0.49], 1.22, radial, "#344f47", [0, 0.66, 0]),
    cylinder([0.51, 0.51], 0.14, radial, "#233c35", [0, 1.34, 0]),
    box([0.4, 0.1, 0.13], "#233c35", [0, 1.48, 0]),
    box([0.34, 0.3, 0.025], "#d7ddd4", [0, 0.83, -0.475]),
  ];
  for (let i = 0; i < 10; i += 1) {
    const angle = (i / 10) * Math.PI * 2;
    binParts.push(
      box([0.045, 0.92, 0.04], "#416258", [Math.sin(angle) * 0.465, 0.68, Math.cos(angle) * 0.465])
    );
  }
  const bin = mergedGeometry(binParts);

  const barrier = mergedGeometry([
    box([4, 0.18, 0.92], "#d97725", [0, 0.09, 0]),
    box([3.82, 0.62, 0.58], "#e88a31", [0, 0.49, 0]),
    box([3.3, 0.36, 0.36], "#e88a31", [0, 0.98, 0]),
    box([0.65, 0.27, 0.035], "#f4f1df", [-1.15, 0.59, 0.405]),
    box([0.65, 0.27, 0.035], "#f4f1df", [1.15, 0.59, 0.405]),
    box([0.5, 0.08, 1.02], "#3d4345", [-1.45, 0.04, 0]),
    box([0.5, 0.08, 1.02], "#3d4345", [1.45, 0.04, 0]),
  ]);

  const busFrameParts: GeometryPart[] = [
    box([6.4, 0.22, 3.6], "#287b91", [0, 3.72, 0]),
    box([5.7, 2.75, 0.1], "#315761", [0, 1.86, 1.43]),
    box([3.4, 0.14, 0.72], "#6e5139", [0, 0.78, 0.82]),
    box([3.4, 0.65, 0.12], "#6e5139", [0, 1.14, 1.13]),
    cylinder([0.075, 0.1], 3.8, radial, "#58646a", [3.25, 1.9, -1.28]),
    box([0.92, 0.72, 0.12], "#287b91", [3.25, 3.55, -1.28]),
  ];
  [-2.72, 2.72].forEach((x) => {
    [-1.45, 1.45].forEach((z) => busFrameParts.push(box([0.14, 3.6, 0.14], "#536168", [x, 1.8, z])));
  });
  const busFrame = mergedGeometry(busFrameParts);
  const busGlass = mergedGeometry([
    box([5.45, 2.62, 0.035], "#a8d9e5", [0, 1.91, 1.36]),
    box([0.035, 2.62, 2.72], "#a8d9e5", [-2.65, 1.91, 0]),
    box([0.035, 2.62, 2.72], "#a8d9e5", [2.65, 1.91, 0]),
  ]);

  const billboardFrame = mergedGeometry([
    cylinder([0.16, 0.23], 5.3, radial, "#4b5358", [-2.75, 2.65, 0.08]),
    cylinder([0.16, 0.23], 5.3, radial, "#4b5358", [2.75, 2.65, 0.08]),
    box([7.5, 3.5, 0.24], "#3b454b", [0, 5.2, 0]),
  ]);
  const smallSignFrame = mergedGeometry([
    cylinder([0.08, 0.12], 2.55, radial, "#69747a", [0, 1.275, 0]),
    box([1.68, 1.12, 0.13], "#465259", [0, 2.78, 0]),
  ]);
  const signPanel = new THREE.PlaneGeometry(1, 1);
  signPanel.rotateY(Math.PI);

  const cover = mergedGeometry([
    cylinder([0.55, 0.55], 0.035, high ? 18 : 9, "#686f70", [0, 0.018, 0]),
    {
      geometry: new THREE.TorusGeometry(0.43, 0.025, high ? 6 : 3, high ? 18 : 9),
      color: "#8a9090",
      position: [0, 0.043, 0],
      rotation: [Math.PI / 2, 0, 0],
    },
  ]);

  const bollard = mergedGeometry([
    cylinder([0.16, 0.22], 1.08, radial, "#3e484d", [0, 0.54, 0]),
    cylinder([0.28, 0.31], 0.1, radial, "#3e484d", [0, 0.05, 0]),
    cylinder([0.185, 0.2], 0.18, radial, "#e6e4d7", [0, 0.78, 0]),
    {
      geometry: new THREE.SphereGeometry(0.18, high ? 10 : 5, high ? 6 : 3),
      color: "#3e484d",
      position: [0, 1.08, 0],
    },
  ]);

  const tactilePad = makeTactileGeometry(high);

  return {
    sidewalk,
    streetlightPole,
    streetlightBulb,
    signalFrame,
    signalLens,
    bench,
    hydrant,
    planter,
    bin,
    barrier,
    busFrame,
    busGlass,
    billboardFrame,
    smallSignFrame,
    signPanel,
    cover,
    bollard,
    tactilePad,
  };
}

function createSignTexture(variant: number): THREE.CanvasTexture | null {
  if (typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const context = canvas.getContext("2d");
  if (!context) return null;

  const palettes = [
    ["#123c54", "#56c5d8", "#f4fbff"],
    ["#234d3d", "#78bd82", "#f3faef"],
    ["#7d332c", "#e5a04c", "#fff6e7"],
  ];
  const [background, accent, foreground] = palettes[variant];
  const gradient = context.createLinearGradient(0, 0, 512, 512);
  gradient.addColorStop(0, background);
  gradient.addColorStop(1, "#17242d");
  context.fillStyle = gradient;
  context.fillRect(0, 0, 512, 512);
  context.fillStyle = accent;
  context.fillRect(0, 0, 512, 18);
  context.fillRect(28, 44, 72, 8);
  context.fillStyle = foreground;
  context.globalAlpha = 0.76;
  context.font = "bold 24px Arial, sans-serif";
  context.fillText("NOSIH CITY SERVICES", 28, 92);
  context.globalAlpha = 1;
  context.font = "900 78px Arial, sans-serif";
  context.fillText(variant === 0 ? "MAIN" : variant === 1 ? "CITY" : "READY", 28, 205);
  context.fillText(variant === 0 ? "STREET" : variant === 1 ? "TRANSIT" : "TO HELP", 28, 292);
  context.fillStyle = accent;
  context.fillRect(28, 334, 456, 5);

  if (variant === 2) {
    context.fillStyle = foreground;
    context.fillRect(64, 382, 112, 30);
    context.fillRect(105, 341, 30, 112);
  } else {
    context.strokeStyle = foreground;
    context.lineWidth = 13;
    context.lineCap = "square";
    context.beginPath();
    context.moveTo(54, 410);
    context.lineTo(454, 410);
    context.moveTo(394, 350);
    context.lineTo(454, 410);
    context.lineTo(394, 470);
    context.stroke();
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

function emptyLayout(): StreetLayout {
  return {
    sidewalks: [],
    streetlightPoles: [],
    streetlightBulbs: [],
    signalFrames: [],
    signalRed: [],
    signalAmber: [],
    signalGreen: [],
    benches: [],
    hydrants: [],
    planters: [],
    bins: [],
    barriers: [],
    busFrames: [],
    busGlass: [],
    billboardFrames: [],
    smallSignFrames: [],
    signPanels: [[], [], []],
    covers: [],
    bollards: [],
    tactilePads: [],
  };
}

function roadFacingYaw(axis: "x" | "z", side: -1 | 1): number {
  return axis === "x" ? side * Math.PI / 2 : side > 0 ? Math.PI : 0;
}

function edgePosition(edge: EdgeState, along: number, lateral: number): [number, number] {
  return edge.axis === "x"
    ? [edge.anchor.x + along, edge.anchor.z + edge.side * lateral]
    : [edge.anchor.x + edge.side * lateral, edge.anchor.z + along];
}

function makePlacement(
  x: number,
  z: number,
  baseY: number,
  yaw = 0,
  sx = 1,
  sy = 1,
  sz = 1
): Placement {
  return { x, y: baseY, z, yaw, sx, sy, sz };
}

function offsetPlacement(
  source: Placement,
  localX: number,
  localY: number,
  localZ: number,
  sx = source.sx,
  sy = source.sy,
  sz = source.sz
): Placement {
  const cosine = Math.cos(source.yaw);
  const sine = Math.sin(source.yaw);
  return {
    x: source.x + localX * cosine + localZ * sine,
    y: source.y + localY,
    z: source.z - localX * sine + localZ * cosine,
    yaw: source.yaw,
    sx,
    sy,
    sz,
  };
}

function canPlace(edge: EdgeState, along: number, halfLength: number): boolean {
  return !edge.occupied.some(([start, end]) => along + halfLength > start && along - halfLength < end);
}

function reserve(edge: EdgeState, along: number, halfLength: number): void {
  edge.occupied.push([along - halfLength, along + halfLength]);
}

function buildStreetLayout(
  anchors: Record<string, UrbanStreetAnchor>,
  high: boolean,
  seed: number,
  baseY: number
): StreetLayout {
  const layout = emptyLayout();
  const anchorEntries = Object.entries(anchors)
    .filter(([, anchor]) => Number.isFinite(anchor.x) && Number.isFinite(anchor.z))
    .sort(([a], [b]) => a.localeCompare(b));
  const sidewalkStep = high ? 12 : 20;
  const lightSpacing = high ? 76 : 126;
  const furnitureSpacing = high ? 58 : 94;
  const bollardSpacing = high ? 42 : 84;

  anchorEntries.forEach(([, anchor], anchorIndex) => {
    const edges: EdgeState[] = [];
    (["x", "z"] as const).forEach((axis) => {
      ([-1, 1] as const).forEach((side) => {
        const edge: EdgeState = { anchorIndex, anchor, edgeIndex: edges.length, axis, side, occupied: [] };
        // Keep the roundabout, all four zebra crossings, and their curb ramps clear.
        reserve(edge, 0, 86);
        CROSSWALKS.forEach((crossing) => reserve(edge, crossing, 10));
        edges.push(edge);
      });
    });

    edges.forEach((edge) => {
      const random = (...values: number[]) => hash(seed, anchorIndex, edge.edgeIndex, ...values);
      const lateral = 22;
      const roadYaw = roadFacingYaw(edge.axis, edge.side);
      const alongYaw = roadYaw - Math.PI / 2;
      const sidewalkYaw = edge.axis === "x" ? (edge.side > 0 ? 0 : Math.PI) : (edge.side > 0 ? Math.PI / 2 : -Math.PI / 2);

      // Raised paving ribbons and curb segments follow the full +/-700 m traffic loops.
      for (let along = -810; along <= 810; along += sidewalkStep) {
        if (Math.abs(along) < 86 || CROSSWALKS.some((crossing) => Math.abs(along - crossing) < 10)) continue;
        const center = THREE.MathUtils.clamp(along, -812, 812);
        const [x, z] = edgePosition(edge, center, lateral);
        layout.sidewalks.push(makePlacement(x, z, baseY, sidewalkYaw, sidewalkStep - 0.16));
      }

      // Two curb-mounted signal heads per boulevard edge, outside the active roundabout.
      [-80, 80].forEach((along) => {
        const [x, z] = edgePosition(edge, along, 24);
        const frame = makePlacement(x, z, baseY, roadYaw);
        layout.signalFrames.push(frame);
        layout.signalRed.push(offsetPlacement(frame, 4.2, 7.35, 0.405));
        layout.signalAmber.push(offsetPlacement(frame, 4.2, 6.85, 0.405));
        layout.signalGreen.push(offsetPlacement(frame, 4.2, 6.35, 0.405));
        reserve(edge, along, 1.5);
      });

      const busStops = high ? [-480, 480] : [edge.edgeIndex % 2 === 0 ? -480 : 480];
      busStops.forEach((along, stopIndex) => {
        const [x, z] = edgePosition(edge, along, 22);
        const frame = makePlacement(x, z, baseY, alongYaw);
        layout.busFrames.push(frame);
        layout.busGlass.push(frame);
        layout.signPanels[(anchorIndex + stopIndex) % 3].push(
          offsetPlacement(frame, 3.25, 3.55, -1.36, 0.8, 0.6, 1)
        );
        reserve(edge, along, 5);
      });

      const billboardPositions = high ? [-650, -330, 330, 650] : [-500, 500];
      billboardPositions.forEach((along, boardIndex) => {
        const [x, z] = edgePosition(edge, along + (random(31, boardIndex) - 0.5) * 8, 22.6);
        const frame = makePlacement(x, z, baseY, alongYaw);
        layout.billboardFrames.push(frame);
        layout.signPanels[(anchorIndex + boardIndex + edge.edgeIndex) % 3].push(
          offsetPlacement(frame, 0, 5.2, -0.135, 7.12, 3.12, 1)
        );
        reserve(edge, along, 5.2);
      });

      const barrierRuns = high ? [-590, -150, 150, 590] : [-160, 560];
      barrierRuns.forEach((along) => {
        for (let i = 0; i < 3; i += 1) {
          const [x, z] = edgePosition(edge, along + i * 4.15, 22.7);
          layout.barriers.push(makePlacement(x, z, baseY, alongYaw));
        }
        reserve(edge, along + 4.15, 7.2);
      });

      for (let i = 0, along = -748; along <= 748; i += 1, along += lightSpacing) {
        const position = along + (random(11, i) - 0.5) * 12;
        if (!canPlace(edge, position, 0.85)) continue;
        const [x, z] = edgePosition(edge, position, 23.4);
        const frame = makePlacement(x, z, baseY, roadYaw);
        layout.streetlightPoles.push(frame);
        layout.streetlightBulbs.push(frame);
        reserve(edge, position, 0.85);
      }

      for (let i = 0, along = -716; along <= 716; i += 1, along += furnitureSpacing) {
        const position = along + (random(23, i) - 0.5) * 14;
        const kind = Math.floor(random(37, i) * 4);
        const halfLength = kind === 0 ? 2.05 : kind === 2 ? 1.35 : 0.8;
        if (!canPlace(edge, position, halfLength)) continue;
        const furnitureLateral = kind === 0 ? 22.7 : kind === 2 ? 22.45 : 22.6;
        const [x, z] = edgePosition(edge, position, furnitureLateral);
        const yaw = kind === 0 ? alongYaw : random(41, i) * Math.PI;
        if (kind === 0) layout.benches.push(makePlacement(x, z, baseY, yaw));
        else if (kind === 1) layout.hydrants.push(makePlacement(x, z, baseY, yaw));
        else if (kind === 2) layout.planters.push(makePlacement(x, z, baseY, yaw));
        else layout.bins.push(makePlacement(x, z, baseY, yaw));
        reserve(edge, position, halfLength);
      }

      for (let i = 0, along = -700; along <= 700; i += 1, along += high ? 220 : 350) {
        const position = along + (random(53, i) - 0.5) * 20;
        if (!canPlace(edge, position, 1.25)) continue;
        const [x, z] = edgePosition(edge, position, 22.7);
        const frame = makePlacement(x, z, baseY, alongYaw);
        layout.smallSignFrames.push(frame);
        layout.signPanels[Math.floor(random(59, i) * 3)].push(
          offsetPlacement(frame, 0, 2.78, -0.075, 1.46, 0.9, 1)
        );
        reserve(edge, position, 1.25);
      }

      for (let i = 0, along = -795; along <= 795; i += 1, along += bollardSpacing) {
        const position = along + (random(67, i) - 0.5) * 9;
        if (!canPlace(edge, position, 0.36)) continue;
        const [x, z] = edgePosition(edge, position, 23.65);
        layout.bollards.push(makePlacement(x, z, baseY, random(71, i) * Math.PI));
        reserve(edge, position, 0.36);
      }

      for (let i = 0, along = -740; along <= 740; i += 1, along += high ? 128 : 210) {
        const position = along + (random(83, i) - 0.5) * 36;
        if (!canPlace(edge, position, 0.7)) continue;
        const [x, z] = edgePosition(edge, position, 20.85 + random(89, i) * 1.3);
        layout.covers.push(makePlacement(x, z, baseY + 0.015, random(97, i) * Math.PI));
        reserve(edge, position, 0.7);
      }

      CROSSWALKS.forEach((crossing) => {
        // The +/-34 m markings sit inside the roundabout and must stay unobstructed.
        if (Math.abs(crossing) < 86) return;
        [-1, 1].forEach((direction) => {
          const [x, z] = edgePosition(edge, crossing + direction * 7.1, 21.7);
          layout.tactilePads.push(makePlacement(x, z, baseY + 0.01, sidewalkYaw));
        });
      });
    });

    // Low bollards outline the hub plaza but leave both active boulevard arms open.
    const hubBollardCount = high ? 56 : 28;
    for (let i = 0; i < hubBollardCount; i += 1) {
      const angle = (i / hubBollardCount) * Math.PI * 2 + hash(seed, anchorIndex, 101) * 0.2;
      const x = anchor.x + Math.cos(angle) * 84;
      const z = anchor.z + Math.sin(angle) * 84;
      if (Math.abs(x - anchor.x) < ROAD_HALF_WIDTH + 5 || Math.abs(z - anchor.z) < ROAD_HALF_WIDTH + 5) continue;
      if (Math.hypot(x - anchor.x, z - anchor.z) < HUB_RADIUS + 9) continue;
      layout.bollards.push(makePlacement(x, z, baseY, angle));
    }
  });

  return layout;
}

function useInstanceMatrices(
  ref: RefObject<THREE.InstancedMesh>,
  placements: Placement[]
): void {
  const dummy = useMemo(() => new THREE.Object3D(), []);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    placements.forEach((placement, index) => {
      dummy.position.set(placement.x, placement.y, placement.z);
      dummy.rotation.set(0, placement.yaw, 0);
      dummy.scale.set(placement.sx, placement.sy, placement.sz);
      dummy.updateMatrix();
      mesh.setMatrixAt(index, dummy.matrix);
    });
    mesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);
    mesh.instanceMatrix.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [dummy, placements, ref]);
}

interface InstanceBatchProps {
  geometry: THREE.BufferGeometry;
  placements: Placement[];
  children?: ReactNode;
  castShadow?: boolean;
  receiveShadow?: boolean;
}

const InstanceBatch: React.FC<InstanceBatchProps> = ({
  geometry,
  placements,
  children,
  castShadow = false,
  receiveShadow = false,
}) => {
  const ref = useRef<THREE.InstancedMesh>(null);
  useInstanceMatrices(ref, placements);
  if (placements.length === 0) return null;
  return (
    <instancedMesh
      ref={ref}
      args={[geometry, undefined, placements.length]}
      castShadow={castShadow}
      receiveShadow={receiveShadow}
    >
      {children}
    </instancedMesh>
  );
};

interface SignalLensBatchProps {
  geometry: THREE.BufferGeometry;
  placements: Placement[];
  kind: 0 | 1 | 2;
}

const SignalLensBatch: React.FC<SignalLensBatchProps> = ({ geometry, placements, kind }) => {
  const ref = useRef<THREE.InstancedMesh>(null);
  const lastStep = useRef(-1);
  const colors = useMemo(
    () => ({
      red: new THREE.Color().setRGB(2.4, 0.055, 0.035),
      amber: new THREE.Color().setRGB(2.5, 1.05, 0.035),
      green: new THREE.Color().setRGB(0.08, 2.15, 0.24),
      dimRed: new THREE.Color("#471b1b"),
      dimAmber: new THREE.Color("#493a17"),
      dimGreen: new THREE.Color("#163c2a"),
    }),
    []
  );
  useInstanceMatrices(ref, placements);

  useFrame(({ clock }) => {
    const mesh = ref.current;
    if (!mesh) return;
    const step = Math.floor(clock.elapsedTime / 3.8);
    if (step === lastStep.current) return;
    lastStep.current = step;
    placements.forEach((_, index) => {
      const phase = (step + index % 2) % 3;
      const active = [colors.red, colors.amber, colors.green][phase];
      const dim = [colors.dimRed, colors.dimAmber, colors.dimGreen][phase];
      mesh.setColorAt(index, phase === kind ? active : dim);
    });
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  });

  if (placements.length === 0) return null;
  return (
    <instancedMesh ref={ref} args={[geometry, undefined, placements.length]}>
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
};

/**
 * Dense, deterministic GTA-style street furniture for the seven country dioramas.
 * All repeated pieces are instanced; no anchors are imported from the parent scene.
 */
export const UrbanStreetDetails: React.FC<UrbanStreetDetailsProps> = ({
  anchors,
  quality = "high",
  timeOfDay = "day",
  baseY = DEFAULT_BASE_Y,
  seed = 0,
}) => {
  const high = quality === "high";
  const night = timeOfDay === "night";
  const safeBaseY = Number.isFinite(baseY) ? baseY : DEFAULT_BASE_Y;
  const safeSeed = Number.isFinite(seed) ? seed : 0;
  const layout = useMemo(
    () => buildStreetLayout(anchors, high, safeSeed, safeBaseY),
    [anchors, high, safeBaseY, safeSeed]
  );
  const geometry = useMemo(() => makeStreetGeometries(high), [high]);
  const textures = useMemo(() => [0, 1, 2].map(createSignTexture), []);

  useEffect(() => {
    return () => {
      Object.values(geometry).forEach((resource) => resource.dispose());
    };
  }, [geometry]);

  useEffect(() => {
    return () => {
      textures.forEach((texture) => texture?.dispose());
    };
  }, [textures]);

  return (
    <group name="urban-street-details">
      <InstanceBatch geometry={geometry.sidewalk} placements={layout.sidewalks} receiveShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.94} />
      </InstanceBatch>

      <InstanceBatch geometry={geometry.streetlightPole} placements={layout.streetlightPoles} castShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.58} metalness={0.52} />
      </InstanceBatch>
      <InstanceBatch geometry={geometry.streetlightBulb} placements={layout.streetlightBulbs}>
        <meshStandardMaterial
          color={night ? "#ffd58a" : "#fff0c2"}
          emissive={night ? "#ffd58a" : "#fff0c2"}
          emissiveIntensity={night ? 3.8 : 0.22}
          roughness={0.32}
          toneMapped={false}
        />
      </InstanceBatch>

      <InstanceBatch geometry={geometry.signalFrame} placements={layout.signalFrames} castShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.62} metalness={0.42} />
      </InstanceBatch>
      <SignalLensBatch geometry={geometry.signalLens} placements={layout.signalRed} kind={0} />
      <SignalLensBatch geometry={geometry.signalLens} placements={layout.signalAmber} kind={1} />
      <SignalLensBatch geometry={geometry.signalLens} placements={layout.signalGreen} kind={2} />

      <InstanceBatch geometry={geometry.bench} placements={layout.benches} castShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.86} />
      </InstanceBatch>
      <InstanceBatch geometry={geometry.hydrant} placements={layout.hydrants} castShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.66} metalness={0.12} />
      </InstanceBatch>
      <InstanceBatch geometry={geometry.planter} placements={layout.planters} castShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.92} />
      </InstanceBatch>
      <InstanceBatch geometry={geometry.bin} placements={layout.bins} castShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.74} metalness={0.16} />
      </InstanceBatch>
      <InstanceBatch geometry={geometry.barrier} placements={layout.barriers} castShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.78} />
      </InstanceBatch>

      <InstanceBatch geometry={geometry.busFrame} placements={layout.busFrames} castShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.66} metalness={0.28} />
      </InstanceBatch>
      <InstanceBatch geometry={geometry.busGlass} placements={layout.busGlass}>
        <meshPhysicalMaterial
          color="#a8d9e5"
          transparent
          opacity={high ? 0.24 : 0.3}
          roughness={0.16}
          metalness={0.08}
          depthWrite={false}
          side={THREE.DoubleSide}
        />
      </InstanceBatch>

      <InstanceBatch geometry={geometry.billboardFrame} placements={layout.billboardFrames} castShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.64} metalness={0.38} />
      </InstanceBatch>
      <InstanceBatch geometry={geometry.smallSignFrame} placements={layout.smallSignFrames} castShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.64} metalness={0.38} />
      </InstanceBatch>
      {textures.map((texture, index) => (
        <InstanceBatch key={index} geometry={geometry.signPanel} placements={layout.signPanels[index]}>
          <meshStandardMaterial
            map={texture}
            emissiveMap={texture}
            emissive="#ffffff"
            emissiveIntensity={night ? 0.42 : 0.035}
            roughness={0.8}
            metalness={0.02}
          />
        </InstanceBatch>
      ))}

      <InstanceBatch geometry={geometry.cover} placements={layout.covers} receiveShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.72} metalness={0.55} />
      </InstanceBatch>
      <InstanceBatch geometry={geometry.bollard} placements={layout.bollards} castShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.68} metalness={0.24} />
      </InstanceBatch>
      <InstanceBatch geometry={geometry.tactilePad} placements={layout.tactilePads} receiveShadow={high}>
        <meshStandardMaterial vertexColors roughness={0.9} />
      </InstanceBatch>
    </group>
  );
};
