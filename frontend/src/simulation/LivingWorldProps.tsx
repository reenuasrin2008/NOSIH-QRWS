import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

interface Props {
  worldSize: number;
  riverZ: number;
  dayMode: boolean;
  windSpeed: number;
  windDeg: number;
}

export const LivingWorldProps: React.FC<Props> = ({ worldSize, riverZ, dayMode, windSpeed, windDeg }) => {
  const birdsRef = useRef<THREE.Group>(null);
  const boatsRef = useRef<THREE.Group>(null);
  const palmsRef = useRef<THREE.Group>(null);
  const craneTrolleysRef = useRef<THREE.Group>(null);
  const signalsRef = useRef<THREE.Group>(null);

  const birdSeeds = useMemo(
    () =>
      Array.from({ length: 16 }, (_, i) => ({
        cx: 2000 + ((i % 4) - 1.5) * 750,
        cz: riverZ + ((i % 3) - 1) * 420,
        radius: 130 + (i % 5) * 48,
        alt: 95 + (i % 4) * 34,
        speed: 0.24 + (i % 4) * 0.06,
        phase: i * 1.15,
      })),
    [riverZ]
  );

  const beachPalms = useMemo(
    () => Array.from({ length: 34 }, (_, i) => [worldSize + 70 + (i % 3) * 26, 180 + i * 112] as [number, number]),
    [worldSize]
  );

  const signalIntersections = useMemo(
    () => [
      [800, 800], [1600, 800], [2400, 800], [3200, 800],
      [800, 1600], [1600, 1600], [2400, 1600], [3200, 1600],
      [800, 2400], [1600, 2400], [2400, 2400], [3200, 2400],
    ] as [number, number][],
    []
  );

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const windRad = (windDeg * Math.PI) / 180;
    const swayAmp = Math.min(0.18, 0.025 + windSpeed * 0.0085);

    // 1. Flocking coastal seabirds with smooth flapping wings
    if (birdsRef.current) {
      birdsRef.current.children.forEach((bird, idx) => {
        const s = birdSeeds[idx];
        const ang = t * s.speed + s.phase;
        bird.position.set(
          s.cx + Math.cos(ang) * s.radius,
          s.alt + Math.sin(t * 1.4 + s.phase) * 7.5,
          s.cz + Math.sin(ang) * s.radius
        );
        bird.rotation.y = -ang;
        const flap = Math.sin(t * 7.5 + s.phase * 2.0) * 0.48;
        const leftWing = bird.children[1];
        const rightWing = bird.children[2];
        if (leftWing) leftWing.rotation.z = flap;
        if (rightWing) rightWing.rotation.z = -flap;
      });
    }

    // 2. River Rescue Patrol Boats + Eastern Coastal Freighter
    if (boatsRef.current) {
      const b0 = boatsRef.current.children[0]; // River rescue boat eastbound
      if (b0) {
        b0.position.x = ((t * 28 + 300) % (worldSize - 300)) + 150;
        b0.position.y = 1.6 + Math.sin(t * 2.6) * 0.35;
        b0.rotation.z = Math.sin(t * 2.1) * 0.04;
      }
      const b1 = boatsRef.current.children[1]; // River rescue boat westbound
      if (b1) {
        b1.position.x = worldSize - 150 - ((t * 22 + 1200) % (worldSize - 300));
        b1.position.y = 1.6 + Math.cos(t * 2.4) * 0.35;
        b1.rotation.z = Math.cos(t * 2.0) * 0.04;
      }
      const ship = boatsRef.current.children[2]; // Offshore container ship
      if (ship) {
        ship.position.z = ((t * 16 + 400) % (worldSize + 400)) - 200;
        ship.position.y = 3.2 + Math.sin(t * 1.1) * 0.45;
      }
    }

    // 3. Wind-swaying coastal palms driven by live weather wind speed & direction
    if (palmsRef.current) {
      const wx = Math.cos(windRad);
      const wz = Math.sin(windRad);
      palmsRef.current.children.forEach((palm, idx) => {
        const gust = Math.sin(t * (1.8 + windSpeed * 0.09) + idx * 0.7) * swayAmp;
        palm.rotation.z = -wx * (swayAmp * 0.7 + gust);
        palm.rotation.x = wz * (swayAmp * 0.7 + gust);
      });
    }

    // 4. East Port Harbor Crane Trolley & Hoist Motion
    if (craneTrolleysRef.current) {
      craneTrolleysRef.current.children.forEach((trolley, idx) => {
        trolley.position.x = -20 + Math.sin(t * 0.38 + idx * 1.9) * 38;
        const hook = trolley.children[1];
        if (hook) {
          hook.position.y = -24 + Math.cos(t * 0.45 + idx) * 14;
        }
      });
    }

    // 5. Arterial Intersection Traffic Lights (Green -> Amber -> Red cycle)
    if (signalsRef.current) {
      const cycle = Math.floor(t * 0.25) % 4;
      signalsRef.current.children.forEach((gantry, idx) => {
        const phase = (cycle + (idx % 2) * 2) % 4;
        const bulb = gantry.children[1] as THREE.Mesh | undefined;
        if (bulb) {
          const mat = bulb.material as THREE.MeshBasicMaterial;
          if (phase === 0 || phase === 1) mat.color.setRGB(0.2, 2.2, 0.45);
          else if (phase === 2) mat.color.setRGB(2.4, 1.5, 0.15);
          else mat.color.setRGB(2.5, 0.2, 0.2);
        }
      });
    }
  });

  return (
    <group>
      {/* 1. Flocking Coastal Seabirds */}
      <group ref={birdsRef}>
        {birdSeeds.map((_, idx) => (
          <group key={idx}>
            <mesh><coneGeometry args={[1.1, 4.2, 5]} /><meshStandardMaterial color="#f8fafc" roughness={0.6} /></mesh>
            <mesh position={[-3.2, 0.2, 0]}><boxGeometry args={[6.0, 0.22, 1.6]} /><meshStandardMaterial color="#e2e8f0" /></mesh>
            <mesh position={[3.2, 0.2, 0]}><boxGeometry args={[6.0, 0.22, 1.6]} /><meshStandardMaterial color="#e2e8f0" /></mesh>
          </group>
        ))}
      </group>

      {/* 2. River Rescue Patrol Boats & Coastal Cargo Ship with Foam Wake Trails */}
      <group ref={boatsRef}>
        {/* Eastbound River Rescue Boat */}
        <group position={[600, 1.6, riverZ - 28]}>
          <mesh castShadow><boxGeometry args={[28, 4.5, 10]} /><meshStandardMaterial color="#f8fafc" roughness={0.35} /></mesh>
          <mesh position={[-2, 4.2, 0]}><boxGeometry args={[11, 4.2, 7.5]} /><meshStandardMaterial color="#dc2626" roughness={0.4} /></mesh>
          <mesh position={[-24, -0.8, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[26, 9]} />
            <meshBasicMaterial color="#e2e8f0" transparent opacity={0.38} />
          </mesh>
        </group>

        {/* Westbound Coast Guard Boat */}
        <group position={[2800, 1.6, riverZ + 28]} rotation={[0, Math.PI, 0]}>
          <mesh castShadow><boxGeometry args={[26, 4.2, 9.5]} /><meshStandardMaterial color="#e2e8f0" roughness={0.35} /></mesh>
          <mesh position={[-1, 4.0, 0]}><boxGeometry args={[10, 4.0, 7]} /><meshStandardMaterial color="#1d4ed8" roughness={0.4} /></mesh>
          <mesh position={[-22, -0.8, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[24, 8.5]} />
            <meshBasicMaterial color="#e2e8f0" transparent opacity={0.35} />
          </mesh>
        </group>

        {/* Offshore Coastal Cargo Freighter */}
        <group position={[worldSize + 520, 3.2, 1600]}>
          <mesh castShadow><boxGeometry args={[42, 14, 155]} /><meshStandardMaterial color="#334155" roughness={0.7} /></mesh>
          <mesh position={[0, 14, -46]} castShadow><boxGeometry args={[32, 20, 26]} /><meshStandardMaterial color="#f1f5f9" roughness={0.5} /></mesh>
          <mesh position={[0, 11, 14]} castShadow><boxGeometry args={[34, 12, 78]} /><meshStandardMaterial color="#b45309" roughness={0.75} /></mesh>
          <mesh position={[0, -2.1, -110]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[34, 85]} />
            <meshBasicMaterial color="#f1f5f9" transparent opacity={0.32} />
          </mesh>
        </group>
      </group>

      {/* 3. Wind-Swaying Coastal Marina Palm Trees */}
      <group ref={palmsRef}>
        {beachPalms.map(([px, pz], idx) => (
          <group key={idx} position={[px, 0, pz]}>
            <mesh position={[0, 11, 0]}>
              <cylinderGeometry args={[0.7, 1.35, 22, 6]} />
              <meshStandardMaterial color="#5c4330" roughness={0.95} />
            </mesh>
            <mesh position={[0.6, 22, 0.4]}>
              <dodecahedronGeometry args={[6.8, 0]} />
              <meshStandardMaterial color={dayMode ? "#2f6b3a" : "#1a3b23"} roughness={0.85} />
            </mesh>
          </group>
        ))}
      </group>

      {/* 4. Animated East Port Harbor Crane Trolleys & Hoists */}
      <group ref={craneTrolleysRef} position={[3580, 91, 1450]}>
        {[0, 180, 360].map((oz, idx) => (
          <group key={idx} position={[-20, 0, oz]}>
            <mesh><boxGeometry args={[12, 6, 12]} /><meshStandardMaterial color="#eab308" roughness={0.5} /></mesh>
            <group position={[0, -24, 0]}>
              <mesh position={[0, 12, 0]}><cylinderGeometry args={[0.35, 0.35, 24, 4]} /><meshBasicMaterial color="#cbd5e1" /></mesh>
              <mesh><boxGeometry args={[20, 9, 10]} /><meshStandardMaterial color={idx % 2 === 0 ? "#1d4ed8" : "#15803d"} roughness={0.7} /></mesh>
            </group>
          </group>
        ))}
      </group>

      {/* 5. Arterial Intersection Cycling Traffic Signals */}
      <group ref={signalsRef}>
        {signalIntersections.map(([ix, iz], idx) => (
          <group key={idx} position={[ix + 21, 0, iz + 21]}>
            <mesh position={[0, 10, 0]}><cylinderGeometry args={[0.45, 0.55, 20, 6]} /><meshStandardMaterial color="#334155" metalness={0.6} /></mesh>
            <mesh position={[-3.5, 19.2, 0]}>
              <sphereGeometry args={[1.45, 8, 8]} />
              <meshBasicMaterial color={[0.2, 2.2, 0.45]} toneMapped={false} />
            </mesh>
          </group>
        ))}
      </group>
    </group>
  );
};
