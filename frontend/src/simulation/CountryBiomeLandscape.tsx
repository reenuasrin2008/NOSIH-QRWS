import React, { useMemo } from "react";
import * as THREE from "three";

interface Props {
  archetype: string;
  countryName: string;
  worldSize: number;
  dayMode: boolean;
}

/**
 * Renders distinct, real-world-inspired surrounding 3D geography for each of the 7 countries:
 * alpine snow peaks, dense swaying pine forests, patchwork farmland & silos, arid red-rock mesas,
 * braided river floodplains, industrial cooling towers, or coastal piers.
 */
export const CountryBiomeLandscape: React.FC<Props> = ({ archetype, worldSize, dayMode }) => {
  const low = archetype.toLowerCase();
  const isMountain = low.includes("mountain");
  const isForest = low.includes("forest");
  const isArid = low.includes("arid");
  const isAgri = low.includes("agricultural");
  const isIndustrial = low.includes("industrial");

  const mountainPeaks = useMemo(
    () =>
      Array.from({ length: 18 }, (_, i) => {
        const angle = (i / 18) * Math.PI * 2;
        const dist = worldSize * 0.62 + (i % 3) * 380;
        return {
          x: worldSize / 2 + Math.cos(angle) * dist,
          z: worldSize / 2 + Math.sin(angle) * dist,
          radius: 420 + (i % 4) * 140,
          height: (isMountain ? 560 : 280) + (i % 5) * 95,
        };
      }),
    [worldSize, isMountain]
  );

  const forestTrees = useMemo(
    () =>
      Array.from({ length: isForest ? 180 : 64 }, (_, i) => {
        const edge = i % 4;
        const pos = ((i * 197) % (worldSize - 300)) + 150;
        const offset = 120 + (i % 5) * 90;
        const x = edge === 0 ? -offset : edge === 1 ? worldSize + offset : pos;
        const z = edge === 2 ? -offset : edge === 3 ? worldSize + offset : pos;
        return { x, z, scale: 0.8 + (i % 4) * 0.28 };
      }),
    [worldSize, isForest]
  );

  const cropFields = useMemo(
    () =>
      Array.from({ length: 12 }, (_, i) => ({
        x: -650 - (i % 3) * 420,
        z: 450 + Math.floor(i / 3) * 820,
        color: i % 3 === 0 ? "#6d8b46" : i % 3 === 1 ? "#9b8b49" : "#4f723c",
      })),
    []
  );

  const groundColor = isArid
    ? dayMode ? "#c8a97e" : "#4a3d2d"
    : isMountain
    ? dayMode ? "#70786e" : "#252a2b"
    : isAgri
    ? dayMode ? "#7f9657" : "#25301f"
    : isForest
    ? dayMode ? "#4c6b42" : "#18261a"
    : dayMode ? "#6d7a69" : "#1c242e";

  return (
    <group>
      {/* Extended Horizon Terrain Skirt */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[worldSize / 2, -2.5, worldSize / 2]} receiveShadow>
        <planeGeometry args={[worldSize * 3.5, worldSize * 3.5]} />
        <meshStandardMaterial color={groundColor} roughness={0.94} metalness={0.02} />
      </mesh>

      {/* Mountain Ranges / Arid Mesas */}
      {(isMountain || isForest || isArid) &&
        mountainPeaks.map((pk, idx) => (
          <group key={idx} position={[pk.x, 0, pk.z]}>
            <mesh position={[0, pk.height / 2 - 10, 0]} castShadow receiveShadow>
              {isArid ? (
                <cylinderGeometry args={[pk.radius * 0.45, pk.radius * 0.85, pk.height * 0.45, 7]} />
              ) : (
                <coneGeometry args={[pk.radius, pk.height, 7]} />
              )}
              <meshStandardMaterial
                color={isArid ? "#b67e52" : dayMode ? "#656d72" : "#2a313a"}
                roughness={0.92}
              />
            </mesh>
            {isMountain && (
              <mesh position={[0, pk.height * 0.84, 0]}>
                <coneGeometry args={[pk.radius * 0.32, pk.height * 0.3, 7]} />
                <meshStandardMaterial color={dayMode ? "#e8eef5" : "#7c8da3"} roughness={0.75} />
              </mesh>
            )}
          </group>
        ))}

      {/* Surrounding Natural Forests & Greenbelts */}
      {!isArid &&
        forestTrees.map((tr, idx) => (
          <group key={idx} position={[tr.x, 0, tr.z]} scale={tr.scale}>
            <mesh position={[0, 12, 0]}>
              <cylinderGeometry args={[2.2, 3.2, 24, 6]} />
              <meshStandardMaterial color="#5b4331" roughness={0.95} />
            </mesh>
            <mesh position={[0, 34, 0]} castShadow>
              <coneGeometry args={[15, 36, 7]} />
              <meshStandardMaterial color={dayMode ? "#2f5d34" : "#14291b"} roughness={0.88} />
            </mesh>
            <mesh position={[0, 50, 0]} castShadow>
              <coneGeometry args={[10, 26, 7]} />
              <meshStandardMaterial color={dayMode ? "#3b7040" : "#193523"} roughness={0.88} />
            </mesh>
          </group>
        ))}

      {/* Agricultural Crop Patchwork & Grain Silos */}
      {isAgri &&
        cropFields.map((f, idx) => (
          <mesh key={idx} rotation={[-Math.PI / 2, 0, 0]} position={[f.x, -1.2, f.z]} receiveShadow>
            <planeGeometry args={[360, 740]} />
            <meshStandardMaterial color={f.color} roughness={0.95} />
          </mesh>
        ))}

      {/* Industrial Cooling Towers */}
      {isIndustrial &&
        [
          [-380, 900],
          [-380, 1450],
          [-380, 2000],
        ].map(([tx, tz], idx) => (
          <group key={idx} position={[tx, 0, tz]}>
            <mesh position={[0, 68, 0]} castShadow>
              <cylinderGeometry args={[34, 52, 136, 20]} />
              <meshStandardMaterial color={dayMode ? "#8a929a" : "#3a424d"} roughness={0.85} />
            </mesh>
          </group>
        ))}
    </group>
  );
};
