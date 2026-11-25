import React, { useEffect, useMemo, useRef } from "react";
import { Line } from "@react-three/drei";
import * as THREE from "three";
import type { LayoutLake, OrganicShape, WorldLayout } from "./worldLayout.ts";
import { buildRibbonGeometry, buildShapeGeometry, scaleShapePoints } from "./worldGeometry.ts";

interface NaturalEnvironmentProps {
  world: WorldLayout;
  dayMode: boolean;
  quality: "high" | "low";
}

interface ShoreDetail {
  x: number;
  z: number;
  height: number;
  radius: number;
  rotationY: number;
  color: THREE.Color;
}

const noRaycast = () => null;

const OrganicMesh: React.FC<{
  shape: OrganicShape;
  y: number;
  color: string;
  roughness?: number;
  metalness?: number;
}> = ({ shape, y, color, roughness = 0.92, metalness = 0 }) => {
  const geometry = useMemo(() => buildShapeGeometry(shape.points, y), [shape, y]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh geometry={geometry} receiveShadow raycast={noRaycast}>
      <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
    </mesh>
  );
};

const ParkPath: React.FC<{ shape: OrganicShape & { path: Array<{ x: number; z: number }> }; dayMode: boolean }> = ({ shape, dayMode }) => {
  const geometry = useMemo(() => buildRibbonGeometry(shape.path, 8, 0.43), [shape]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return (
    <mesh geometry={geometry} receiveShadow raycast={noRaycast}>
      <meshStandardMaterial color={dayMode ? "#d8c7a6" : "#514b3e"} roughness={0.95} />
    </mesh>
  );
};

const Lake: React.FC<{ lake: LayoutLake; dayMode: boolean }> = ({ lake, dayMode }) => {
  const shore = useMemo(
    () => scaleShapePoints(lake.points, lake, lake.kind === "park" ? 1.16 : 1.1),
    [lake]
  );
  const ripples = useMemo(() => {
    const cos = Math.cos(lake.rotation);
    const sin = Math.sin(lake.rotation);
    return [-0.42, -0.05, 0.34].map((offset, rippleIndex) => {
      const points: Array<[number, number, number]> = [];
      for (let i = 0; i <= 18; i += 1) {
        const u = i / 18;
        const localX = (u * 2 - 1) * lake.rx * (0.28 + rippleIndex * 0.035);
        const localZ = offset * lake.rz + Math.sin(u * Math.PI * 2) * 2.8;
        points.push([
          lake.x + localX * cos - localZ * sin,
          lake.kind === "park" ? 0.71 : 0.51,
          lake.z + localX * sin + localZ * cos,
        ]);
      }
      return points;
    });
  }, [lake]);

  return (
    <group>
      <OrganicMesh
        shape={{ ...lake, points: shore }}
        y={lake.kind === "park" ? 0.59 : 0.39}
        color={dayMode ? "#c9bfa5" : "#4a4d45"}
      />
      <OrganicMesh
        shape={lake}
        y={lake.kind === "park" ? 0.65 : 0.45}
        color={dayMode ? "#389fc5" : "#173f59"}
        roughness={0.16}
        metalness={0.22}
      />
      {ripples.map((points, index) => (
        <Line
          key={index}
          points={points}
          color={dayMode ? "#c8f2ff" : "#6ba6bd"}
          lineWidth={0.75}
          transparent
          opacity={dayMode ? 0.32 : 0.18}
          raycast={noRaycast}
        />
      ))}
    </group>
  );
};

export const NaturalEnvironment: React.FC<NaturalEnvironmentProps> = ({ world, dayMode, quality }) => {
  const reedRef = useRef<THREE.InstancedMesh>(null);
  const rockRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const lakes = useMemo(
    () => Object.values(world.countries).flatMap((country) => [...country.lakes, country.park.lake]),
    [world]
  );

  const shoreDetails = useMemo(() => {
    const reeds: ShoreDetail[] = [];
    const rocks: ShoreDetail[] = [];
    lakes.forEach((lake, lakeIndex) => {
      const pointStep = quality === "high" ? 5 : 9;
      for (let i = 0; i < lake.points.length; i += pointStep) {
        const point = lake.points[i];
        const next = lake.points[(i + 1) % lake.points.length];
        const dx = next.x - point.x;
        const dz = next.z - point.z;
        const length = Math.hypot(dx, dz) || 1;
        const outwardX = dx / length;
        const outwardZ = dz / length;
        const reedCount = quality === "high" ? 3 : 1;
        for (let j = 0; j < reedCount; j += 1) {
          const offset = (j - (reedCount - 1) / 2) * 2.4;
          reeds.push({
            x: point.x + outwardX * offset,
            z: point.z + outwardZ * offset,
            height: 3.5 + ((i * 7 + j * 3 + lakeIndex) % 5) * 0.8,
            radius: 0.32 + ((i + j) % 3) * 0.1,
            rotationY: (i * 0.71 + j) % Math.PI,
            color: new THREE.Color(["#6f8f3d", "#8aa653", "#557a35"][(i + j) % 3]),
          });
        }
        if (i % (pointStep * 2) === 0) {
          const size = 2.4 + ((i + lakeIndex) % 4) * 0.75;
          rocks.push({
            x: point.x - outwardX * 2,
            z: point.z - outwardZ * 2,
            height: size * 0.7,
            radius: size,
            rotationY: i * 0.37,
            color: new THREE.Color(["#9d9a8e", "#b7b1a3", "#85877e"][(i + lakeIndex) % 3]),
          });
        }
      }
    });
    return { reeds, rocks };
  }, [lakes, quality]);

  useEffect(() => {
    if (reedRef.current) {
      shoreDetails.reeds.forEach((reed, index) => {
        dummy.position.set(reed.x, 0.45 + reed.height / 2, reed.z);
        dummy.rotation.set(0, reed.rotationY, 0);
        dummy.scale.set(reed.radius, reed.height, reed.radius);
        dummy.updateMatrix();
        reedRef.current!.setMatrixAt(index, dummy.matrix);
        reedRef.current!.setColorAt(index, reed.color);
      });
      reedRef.current.instanceMatrix.needsUpdate = true;
      if (reedRef.current.instanceColor) reedRef.current.instanceColor.needsUpdate = true;
    }
    if (rockRef.current) {
      shoreDetails.rocks.forEach((rock, index) => {
        dummy.position.set(rock.x, 0.42 + rock.height / 2, rock.z);
        dummy.rotation.set(0.12, rock.rotationY, 0.08);
        dummy.scale.set(rock.radius * 1.25, rock.height, rock.radius);
        dummy.updateMatrix();
        rockRef.current!.setMatrixAt(index, dummy.matrix);
        rockRef.current!.setColorAt(index, rock.color);
      });
      rockRef.current.instanceMatrix.needsUpdate = true;
      if (rockRef.current.instanceColor) rockRef.current.instanceColor.needsUpdate = true;
    }
  }, [shoreDetails, dummy]);

  return (
    <group>
      {Object.values(world.countries).flatMap((country) =>
        country.groundPatches.map((patch) => (
          <OrganicMesh key={patch.id} shape={patch} y={0.27} color={dayMode ? patch.color : "#26362d"} />
        ))
      )}
      {Object.values(world.countries).flatMap((country) =>
        country.forests.map((forest) => (
          <OrganicMesh key={forest.id} shape={forest} y={0.3} color={dayMode ? forest.floorColor : "#17291e"} />
        ))
      )}
      {Object.values(world.countries).map((country) => (
        <React.Fragment key={country.countryId}>
          <OrganicMesh
            shape={country.park}
            y={0.34}
            color={dayMode ? "#78b861" : "#203d27"}
          />
          <ParkPath shape={country.park} dayMode={dayMode} />
        </React.Fragment>
      ))}
      {lakes.map((lake) => <Lake key={lake.id} lake={lake} dayMode={dayMode} />)}
      <instancedMesh
        ref={reedRef}
        args={[undefined, undefined, shoreDetails.reeds.length]}
        receiveShadow
        raycast={noRaycast}
      >
        <coneGeometry args={[1, 1, 5]} />
        <meshStandardMaterial roughness={0.9} />
      </instancedMesh>
      <instancedMesh
        ref={rockRef}
        args={[undefined, undefined, shoreDetails.rocks.length]}
        receiveShadow
        raycast={noRaycast}
      >
        <dodecahedronGeometry args={[1, 0]} />
        <meshStandardMaterial roughness={0.96} />
      </instancedMesh>
    </group>
  );
};
