import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { COUNTRY_FLAT_ANCHORS, type WorldLayout } from "./worldLayout.ts";

interface AmbientBirdsProps {
  world: WorldLayout;
  quality: "high" | "low";
  prefersReducedMotion: boolean;
  dayMode: boolean;
}

interface Habitat {
  id: string;
  x: number;
  z: number;
  rx: number;
  rz: number;
  rotation: number;
}

interface Flock {
  x: number;
  z: number;
  rx: number;
  rz: number;
  rotation: number;
  cosRotation: number;
  sinRotation: number;
  altitude: number;
  phase: number;
  speed: number;
}

interface BirdFlight {
  seed: number;
  x: number;
  z: number;
  rx: number;
  rz: number;
  cosRotation: number;
  sinRotation: number;
  altitude: number;
  phase: number;
  speed: number;
  bobAmplitude: number;
  bobPhase: number;
  scale: number;
  flapSpeed: number;
  flapPhase: number;
}

const TAU = Math.PI * 2;
const FLOCK_COUNT = 8;
const BIRDS_PER_FLOCK = 4;
const REDUCED_MOTION_TIME = 7.5;
const FALLBACK_COUNTRY_IDS = Object.keys(COUNTRY_FLAT_ANCHORS).sort();

const DAY_BODY_COLORS = ["#27323a", "#3d464b", "#554b40"] as const;
const DAY_WING_COLORS = ["#3b4850", "#505a60", "#686057"] as const;
const NIGHT_BODY_COLORS = ["#cbd5e1", "#dde5ea", "#b8c4cf"] as const;
const NIGHT_WING_COLORS = ["#e2e8f0", "#eef4f6", "#cbd5e1"] as const;

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let value = Math.imul(state ^ (state >>> 15), 1 | state);
    value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function range(random: () => number, min: number, max: number): number {
  return min + random() * (max - min);
}

function createBodyGeometry(): THREE.BufferGeometry {
  const radialSegments = 8;
  const rings: ReadonlyArray<readonly [number, number, number]> = [
    [-3.1, 0.08, 0.08],
    [-2.2, 0.28, 0.22],
    [-1.2, 0.62, 0.5],
    [0, 0.78, 0.62],
    [1.25, 0.65, 0.55],
    [2.05, 0.48, 0.43],
    [2.65, 0.38, 0.34],
    [3.15, 0.05, 0.05],
  ];
  const positions: number[] = [];
  const indices: number[] = [];

  for (const [z, radiusX, radiusY] of rings) {
    for (let segment = 0; segment < radialSegments; segment += 1) {
      const angle = segment / radialSegments * TAU;
      positions.push(Math.cos(angle) * radiusX, Math.sin(angle) * radiusY, z);
    }
  }

  for (let ring = 0; ring < rings.length - 1; ring += 1) {
    for (let segment = 0; segment < radialSegments; segment += 1) {
      const next = (segment + 1) % radialSegments;
      const a = ring * radialSegments + segment;
      const b = ring * radialSegments + next;
      const c = (ring + 1) * radialSegments + segment;
      const d = (ring + 1) * radialSegments + next;
      indices.push(a, b, c, b, d, c);
    }
  }

  const tailCenter = positions.length / 3;
  positions.push(0, 0, rings[0][0]);
  const headCenter = positions.length / 3;
  const headZ = rings[rings.length - 1][0];
  positions.push(0, 0, headZ);
  const headRing = (rings.length - 1) * radialSegments;
  for (let segment = 0; segment < radialSegments; segment += 1) {
    const next = (segment + 1) % radialSegments;
    indices.push(tailCenter, next, segment);
    indices.push(headCenter, headRing + segment, headRing + next);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  return geometry;
}

/** A swept, tapered wing extending along local +X; the left instance mirrors it. */
function createWingGeometry(): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute([
      0, 0, 0.8,
      0, 0, -0.75,
      4.8, 0.05, 0.25,
      10, 0, -1.25,
      8.8, 0, -2.15,
      3.5, 0, -1.35,
    ], 3)
  );
  geometry.setIndex([0, 2, 1, 2, 5, 1, 2, 4, 5, 2, 3, 4]);
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  return geometry;
}

function createFlocks(world: WorldLayout): Flock[] {
  const countryIds = Object.keys(world.countries).sort();
  const ids = countryIds.length > 0 ? countryIds : FALLBACK_COUNTRY_IDS;
  const flocks: Flock[] = [];

  for (let flockIndex = 0; flockIndex < FLOCK_COUNT; flockIndex += 1) {
    const countryId = ids[flockIndex % ids.length];
    const country = world.countries[countryId];
    const anchor = country?.anchor ?? COUNTRY_FLAT_ANCHORS[countryId];
    const habitats: Habitat[] = [];
    const lakes = country?.lakes ?? [];
    const forests = country?.forests ?? [];
    const habitatCount = Math.max(lakes.length, forests.length);

    // Interleaving keeps both lake and forest flocks represented in the first pass.
    for (let index = 0; index < habitatCount; index += 1) {
      const lake = lakes[index];
      if (lake) habitats.push(lake);
      const forest = forests[index];
      if (forest) habitats.push(forest);
    }

    if (habitats.length === 0) {
      const angle = flockIndex * 2.399963229728653;
      const fallbackAnchor = anchor ?? { x: 0, z: 0, radius: 1200 };
      habitats.push({
        id: `${countryId}-ambient-fallback`,
        x: fallbackAnchor.x + Math.cos(angle) * fallbackAnchor.radius * 0.55,
        z: fallbackAnchor.z + Math.sin(angle) * fallbackAnchor.radius * 0.55,
        rx: 180,
        rz: 120,
        rotation: angle,
      });
    }

    const habitat = habitats[Math.floor(flockIndex / ids.length) % habitats.length];
    const random = mulberry32(0x6a09e667 ^ Math.imul(flockIndex + 1, 0x9e3779b1));
    const rotation = habitat.rotation + range(random, -0.45, 0.45);
    flocks.push({
      x: habitat.x + range(random, -0.08, 0.08) * habitat.rx,
      z: habitat.z + range(random, -0.08, 0.08) * habitat.rz,
      rx: THREE.MathUtils.clamp(habitat.rx * range(random, 0.38, 0.58), 80, 210),
      rz: THREE.MathUtils.clamp(habitat.rz * range(random, 0.38, 0.58), 60, 155),
      rotation,
      cosRotation: Math.cos(rotation),
      sinRotation: Math.sin(rotation),
      altitude: range(random, 105, 175),
      phase: random() * TAU,
      speed: range(random, 0.1, 0.17) * (random() < 0.5 ? -1 : 1),
    });
  }

  return flocks;
}

function createFlights(world: WorldLayout, quality: "high" | "low"): BirdFlight[] {
  const flocks = createFlocks(world);
  const flights: BirdFlight[] = [];
  const birdsPerFlock = quality === "high" ? BIRDS_PER_FLOCK : BIRDS_PER_FLOCK / 2;

  flocks.forEach((flock, flockIndex) => {
    for (let slot = 0; slot < birdsPerFlock; slot += 1) {
      const seed = (
        0xbb67ae85
        ^ Math.imul(flockIndex + 1, 0x9e3779b1)
        ^ Math.imul(slot + 1, 0x85ebca6b)
      ) >>> 0;
      const random = mulberry32(seed);
      flights.push({
        seed,
        x: flock.x + range(random, -14, 14),
        z: flock.z + range(random, -14, 14),
        rx: flock.rx * range(random, 0.9, 1.1),
        rz: flock.rz * range(random, 0.9, 1.1),
        cosRotation: flock.cosRotation,
        sinRotation: flock.sinRotation,
        altitude: flock.altitude + (slot - 1.5) * 6 + range(random, -7, 7),
        phase: flock.phase + slot * 0.18 + range(random, -0.045, 0.045),
        speed: flock.speed * range(random, 0.96, 1.04),
        bobAmplitude: range(random, 3.5, 8),
        bobPhase: random() * TAU,
        scale: range(random, 0.82, 1.12),
        flapSpeed: range(random, 8, 11),
        flapPhase: random() * TAU,
      });
    }
  });

  return flights;
}

function ignoreRaycast(): void {
  // Ambient birds must not intercept country selection or map clicks.
}

export function AmbientBirds({
  world,
  quality,
  prefersReducedMotion,
  dayMode,
}: AmbientBirdsProps) {
  const count = quality === "high" ? 32 : 16;
  const flights = useMemo(() => createFlights(world, quality), [world, quality]);
  const bodyGeometry = useMemo(createBodyGeometry, []);
  const wingGeometry = useMemo(createWingGeometry, []);
  const bodyMaterial = useMemo(() => new THREE.MeshStandardMaterial({
    color: "#ffffff",
    roughness: 0.86,
    metalness: 0,
    flatShading: true,
  }), []);
  const wingMaterial = useMemo(() => new THREE.MeshStandardMaterial({
    color: "#ffffff",
    roughness: 0.9,
    metalness: 0,
    side: THREE.DoubleSide,
    flatShading: true,
  }), []);

  const bodyRef = useRef<THREE.InstancedMesh>(null);
  const leftWingRef = useRef<THREE.InstancedMesh>(null);
  const rightWingRef = useRef<THREE.InstancedMesh>(null);
  const scratch = useMemo(() => ({
    bodyMatrix: new THREE.Matrix4(),
    wingLocalMatrix: new THREE.Matrix4(),
    wingWorldMatrix: new THREE.Matrix4(),
    position: new THREE.Vector3(),
    quaternion: new THREE.Quaternion(),
    euler: new THREE.Euler(0, 0, 0, "YXZ"),
    scale: new THREE.Vector3(),
    wingPosition: new THREE.Vector3(),
    wingQuaternion: new THREE.Quaternion(),
    wingEuler: new THREE.Euler(),
    wingScale: new THREE.Vector3(),
    color: new THREE.Color(),
  }), []);

  const writeMatrices = useCallback((time: number) => {
    const bodies = bodyRef.current;
    const leftWings = leftWingRef.current;
    const rightWings = rightWingRef.current;
    if (!bodies || !leftWings || !rightWings) return;

    for (let index = 0; index < flights.length; index += 1) {
      const bird = flights[index];
      const angle = bird.phase + time * bird.speed;
      const cosAngle = Math.cos(angle);
      const sinAngle = Math.sin(angle);
      const localX = bird.rx * cosAngle;
      const localZ = bird.rz * sinAngle;
      const localDx = -bird.rx * sinAngle;
      const localDz = bird.rz * cosAngle;
      const dx = localDx * bird.cosRotation + localDz * bird.sinRotation;
      const dz = -localDx * bird.sinRotation + localDz * bird.cosRotation;
      const ddx = -bird.rx * cosAngle * bird.cosRotation
        - bird.rz * sinAngle * bird.sinRotation;
      const ddz = bird.rx * cosAngle * bird.sinRotation
        - bird.rz * sinAngle * bird.cosRotation;
      const horizontalSpeedSquared = dx * dx + dz * dz;
      const horizontalSpeed = Math.sqrt(horizontalSpeedSquared) * Math.abs(bird.speed);
      const bobAngle = angle * 2 + bird.bobPhase;
      const dy = Math.cos(bobAngle) * 2 * bird.bobAmplitude * bird.speed;
      const turnRate = horizontalSpeedSquared > 1e-6
        ? bird.speed * (dz * ddx - dx * ddz) / horizontalSpeedSquared
        : 0;

      scratch.position.set(
        bird.x + localX * bird.cosRotation + localZ * bird.sinRotation,
        bird.altitude + Math.sin(bobAngle) * bird.bobAmplitude,
        bird.z - localX * bird.sinRotation + localZ * bird.cosRotation
      );
      scratch.euler.set(
        THREE.MathUtils.clamp(-Math.atan2(dy, horizontalSpeed), -0.12, 0.12),
        Math.atan2(dx, dz),
        THREE.MathUtils.clamp(-turnRate * 1.6, -0.26, 0.26),
        "YXZ"
      );
      scratch.quaternion.setFromEuler(scratch.euler);
      scratch.scale.setScalar(bird.scale);
      scratch.bodyMatrix.compose(scratch.position, scratch.quaternion, scratch.scale);
      bodies.setMatrixAt(index, scratch.bodyMatrix);

      const flap = Math.sin(time * bird.flapSpeed + bird.flapPhase) * 0.62 + 0.08;
      for (let side = -1; side <= 1; side += 2) {
        scratch.wingPosition.set(side * 0.42, 0.03, 0);
        scratch.wingEuler.set(0, 0, side * flap, "XYZ");
        scratch.wingQuaternion.setFromEuler(scratch.wingEuler);
        scratch.wingScale.set(side, 1, 1);
        scratch.wingLocalMatrix.compose(
          scratch.wingPosition,
          scratch.wingQuaternion,
          scratch.wingScale
        );
        scratch.wingWorldMatrix.multiplyMatrices(scratch.bodyMatrix, scratch.wingLocalMatrix);
        if (side < 0) leftWings.setMatrixAt(index, scratch.wingWorldMatrix);
        else rightWings.setMatrixAt(index, scratch.wingWorldMatrix);
      }
    }

    bodies.instanceMatrix.needsUpdate = true;
    leftWings.instanceMatrix.needsUpdate = true;
    rightWings.instanceMatrix.needsUpdate = true;
  }, [flights, scratch]);

  useLayoutEffect(() => {
    const bodies = bodyRef.current;
    const leftWings = leftWingRef.current;
    const rightWings = rightWingRef.current;
    if (!bodies || !leftWings || !rightWings) return;
    const bodyPalette = dayMode ? DAY_BODY_COLORS : NIGHT_BODY_COLORS;
    const wingPalette = dayMode ? DAY_WING_COLORS : NIGHT_WING_COLORS;

    for (let index = 0; index < flights.length; index += 1) {
      const colorIndex = flights[index].seed % bodyPalette.length;
      bodies.setColorAt(index, scratch.color.set(bodyPalette[colorIndex]));
      leftWings.setColorAt(index, scratch.color.set(wingPalette[colorIndex]));
      rightWings.setColorAt(index, scratch.color.set(wingPalette[colorIndex]));
    }
    if (bodies.instanceColor) bodies.instanceColor.needsUpdate = true;
    if (leftWings.instanceColor) leftWings.instanceColor.needsUpdate = true;
    if (rightWings.instanceColor) rightWings.instanceColor.needsUpdate = true;
  }, [dayMode, flights, scratch]);

  useLayoutEffect(() => {
    const usage = prefersReducedMotion ? THREE.StaticDrawUsage : THREE.DynamicDrawUsage;
    bodyRef.current?.instanceMatrix.setUsage(usage);
    leftWingRef.current?.instanceMatrix.setUsage(usage);
    rightWingRef.current?.instanceMatrix.setUsage(usage);
    writeMatrices(prefersReducedMotion ? REDUCED_MOTION_TIME : 0);
  }, [prefersReducedMotion, writeMatrices]);

  useEffect(() => () => {
    bodyGeometry.dispose();
    wingGeometry.dispose();
    bodyMaterial.dispose();
    wingMaterial.dispose();
  }, [bodyGeometry, wingGeometry, bodyMaterial, wingMaterial]);

  useFrame((state) => {
    if (!prefersReducedMotion) writeMatrices(state.clock.elapsedTime);
  });

  return (
    <group name="ambient-birds">
      <instancedMesh
        ref={bodyRef}
        args={[bodyGeometry, bodyMaterial, count]}
        frustumCulled={false}
        raycast={ignoreRaycast}
      />
      <instancedMesh
        ref={leftWingRef}
        args={[wingGeometry, wingMaterial, count]}
        frustumCulled={false}
        raycast={ignoreRaycast}
      />
      <instancedMesh
        ref={rightWingRef}
        args={[wingGeometry, wingMaterial, count]}
        frustumCulled={false}
        raycast={ignoreRaycast}
      />
    </group>
  );
}
