import * as THREE from "three";
import type { LayoutPoint } from "./worldLayout.ts";

/** Flat, upward-facing geometry for an organic X/Z polygon. */
export function buildShapeGeometry(points: readonly LayoutPoint[], y = 0): THREE.BufferGeometry {
  const shape = new THREE.Shape();
  shape.moveTo(points[0].x, -points[0].z);
  for (let i = 1; i < points.length; i += 1) shape.lineTo(points[i].x, -points[i].z);
  shape.closePath();
  const geometry = new THREE.ShapeGeometry(shape);
  geometry.rotateX(-Math.PI / 2);
  geometry.translate(0, y, 0);
  geometry.computeVertexNormals();
  return geometry;
}

export function scaleShapePoints(
  points: readonly LayoutPoint[],
  center: LayoutPoint,
  scaleX: number,
  scaleY = scaleX
): LayoutPoint[] {
  return points.map((point) => ({
    x: center.x + (point.x - center.x) * scaleX,
    z: center.z + (point.z - center.z) * scaleY,
  }));
}

/** Smooth road/path ribbon with length-based UVs for asphalt and paving textures. */
export function buildRibbonGeometry(
  points: readonly LayoutPoint[],
  width: number,
  y = 0,
  closed = false
): THREE.BufferGeometry {
  const positions: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];
  const cumulative = [0];
  for (let i = 1; i < points.length; i += 1) {
    cumulative.push(cumulative[i - 1] + Math.hypot(points[i].x - points[i - 1].x, points[i].z - points[i - 1].z));
  }

  points.forEach((point, index) => {
    const previous = points[closed ? (index - 1 + points.length) % points.length : Math.max(0, index - 1)];
    const next = points[closed ? (index + 1) % points.length : Math.min(points.length - 1, index + 1)];
    const dx = next.x - previous.x;
    const dz = next.z - previous.z;
    const length = Math.hypot(dx, dz) || 1;
    const normalX = -dz / length;
    const normalZ = dx / length;
    positions.push(
      point.x + normalX * width / 2, y, point.z + normalZ * width / 2,
      point.x - normalX * width / 2, y, point.z - normalZ * width / 2
    );
    uvs.push(0, cumulative[index] / 70, 1, cumulative[index] / 70);
  });

  const rowSize = 2;
  const segmentCount = closed ? points.length : points.length - 1;
  for (let i = 0; i < segmentCount; i += 1) {
    const next = (i + 1) % points.length;
    const current = i * rowSize;
    const following = next * rowSize;
    indices.push(current, following, current + 1);
    indices.push(current + 1, following, following + 1);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}
