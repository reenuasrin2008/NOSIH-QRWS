import React, { useEffect, useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { HazardZone, WeatherState } from "../types/simulation";
import { useSimStore } from "../state/simulationStore";
import { createFireSpriteTexture, createSmokeSpriteTexture, createWaterRippleTexture } from "./textures";

const FirePlume: React.FC<{
  hz: HazardZone;
  windRad: number;
  windSpeed: number;
  fireTex: THREE.CanvasTexture;
  smokeTex: THREE.CanvasTexture;
}> = ({ hz, windRad, windSpeed, fireTex, smokeTex }) => {
  const smokeRef = useRef<THREE.Points>(null);
  const flameRef = useRef<THREE.Points>(null);
  const sparkRef = useRef<THREE.Points>(null);
  const fireLightRef = useRef<THREE.PointLight>(null);
  const coreMeshRef = useRef<THREE.Mesh>(null);

  const smokeCount = 120;
  const flameCount = 85;
  const sparkCount = 90;

  const smokeInit = useMemo(() => {
    const arr = new Float32Array(smokeCount * 3);
    for (let i = 0; i < smokeCount; i++) {
      const a = Math.random() * Math.PI * 2;
      const r = Math.random() * hz.radius * 0.42;
      arr[i * 3] = Math.cos(a) * r;
      arr[i * 3 + 1] = 18 + Math.random() * 190;
      arr[i * 3 + 2] = Math.sin(a) * r;
    }
    return arr;
  }, [hz.radius]);

  const flameInit = useMemo(() => {
    const arr = new Float32Array(flameCount * 3);
    for (let i = 0; i < flameCount; i++) {
      const a = Math.random() * Math.PI * 2;
      const r = Math.random() * hz.radius * 0.45;
      arr[i * 3] = Math.cos(a) * r;
      arr[i * 3 + 1] = Math.random() * 58;
      arr[i * 3 + 2] = Math.sin(a) * r;
    }
    return arr;
  }, [hz.radius]);

  const sparkInit = useMemo(() => {
    const arr = new Float32Array(sparkCount * 3);
    for (let i = 0; i < sparkCount; i++) {
      const a = Math.random() * Math.PI * 2;
      const r = Math.random() * hz.radius * 0.5;
      arr[i * 3] = Math.cos(a) * r;
      arr[i * 3 + 1] = Math.random() * 110;
      arr[i * 3 + 2] = Math.sin(a) * r;
    }
    return arr;
  }, [hz.radius]);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const wx = Math.cos(windRad) * windSpeed;
    const wz = Math.sin(windRad) * windSpeed;

    // Flickering firelight illumination on nearby skyscrapers
    if (fireLightRef.current) {
      fireLightRef.current.intensity = 28000 + Math.sin(t * 11.3 + hz.x) * 7500 + Math.cos(t * 23.1) * 3500;
    }
    if (coreMeshRef.current) {
      const s = 0.92 + Math.sin(t * 13.0 + hz.z) * 0.1;
      coreMeshRef.current.scale.set(s, 0.85 + Math.cos(t * 15.0) * 0.2, s);
    }

    // 1. Rising turbulent flame tongues
    if (flameRef.current) {
      const pos = flameRef.current.geometry.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < pos.count; i++) {
        let y = pos.getY(i) + delta * (26 + (i % 5) * 4);
        let x = pos.getX(i) + (wx * 0.45 + Math.sin(t * 5 + i) * 3.5) * delta;
        let z = pos.getZ(i) + (wz * 0.45 + Math.cos(t * 4.5 + i) * 3.5) * delta;
        if (y > 62) {
          const a = Math.random() * Math.PI * 2;
          const r = Math.random() * hz.radius * 0.4;
          y = 2;
          x = Math.cos(a) * r;
          z = Math.sin(a) * r;
        }
        pos.setXYZ(i, x, y, z);
      }
      pos.needsUpdate = true;
    }

    // 2. Fast-rising glowing embers / sparks swirling in wind
    if (sparkRef.current) {
      const pos = sparkRef.current.geometry.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < pos.count; i++) {
        let y = pos.getY(i) + delta * (38 + (i % 7) * 5);
        let x = pos.getX(i) + (wx * 1.9 + Math.sin(t * 8 + i * 2) * 8) * delta;
        let z = pos.getZ(i) + (wz * 1.9 + Math.cos(t * 7 + i * 2) * 8) * delta;
        if (y > 125) {
          const a = Math.random() * Math.PI * 2;
          const r = Math.random() * hz.radius * 0.36;
          y = 4;
          x = Math.cos(a) * r;
          z = Math.sin(a) * r;
        }
        pos.setXYZ(i, x, y, z);
      }
      pos.needsUpdate = true;
    }

    // 3. Tall billowing dark smoke column drifting with wind
    if (smokeRef.current) {
      const pos = smokeRef.current.geometry.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < pos.count; i++) {
        let y = pos.getY(i) + delta * (19 + (i % 4) * 3);
        let x = pos.getX(i) + wx * 1.8 * delta;
        let z = pos.getZ(i) + wz * 1.8 * delta;
        if (y > 210) {
          const a = Math.random() * Math.PI * 2;
          const r = Math.random() * hz.radius * 0.35;
          y = 24;
          x = Math.cos(a) * r;
          z = Math.sin(a) * r;
        }
        pos.setXYZ(i, x, y, z);
      }
      pos.needsUpdate = true;
    }
  });

  return (
    <group position={[hz.x, 0, hz.z]}>
      <pointLight ref={fireLightRef} position={[0, 48, 0]} color="#ff7315" intensity={28000} distance={620} decay={2} />

      {/* Scorched Charred Ground Footprint + Glowing Lava-Hot Center */}
      <mesh position={[0, 0.55, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[hz.radius, 40]} />
        <meshBasicMaterial color="#1c1412" transparent opacity={0.62} />
      </mesh>
      <mesh position={[0, 0.68, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[hz.radius * 0.55, 32]} />
        <meshBasicMaterial color={[2.2, 0.55, 0.12]} transparent opacity={0.45} toneMapped={false} />
      </mesh>

      {/* Pulsing Inner Flame Core */}
      <mesh ref={coreMeshRef} position={[0, 12, 0]}>
        <coneGeometry args={[hz.radius * 0.32, 34, 10]} />
        <meshBasicMaterial color={[2.8, 1.35, 0.35]} transparent opacity={0.52} toneMapped={false} />
      </mesh>

      {/* Volumetric Rising Flame Tongues (Additive HDR Bloom) */}
      <points ref={flameRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={flameCount} array={flameInit} itemSize={3} />
        </bufferGeometry>
        <pointsMaterial
          map={fireTex}
          color={[2.6, 1.2, 0.35]}
          size={58}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </points>

      {/* Bright Rising Sparks / Embers */}
      <points ref={sparkRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={sparkCount} array={sparkInit} itemSize={3} />
        </bufferGeometry>
        <pointsMaterial
          map={fireTex}
          color={[3.2, 1.8, 0.5]}
          size={11}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </points>

      {/* Billowing Dark Volumetric Smoke Column */}
      <points ref={smokeRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={smokeCount} array={smokeInit} itemSize={3} />
        </bufferGeometry>
        <pointsMaterial
          map={smokeTex}
          size={105}
          transparent
          opacity={0.64}
          depthWrite={false}
        />
      </points>
    </group>
  );
};

export const EnvironmentalEffects: React.FC<{ hazards: HazardZone[]; weather: WeatherState; worldSize?: number }> = ({
  hazards, weather, worldSize = 4000,
}) => {
  const showHazards = useSimStore((s) => s.showHazards);
  const enableFire = useSimStore((s) => s.enableFire);
  const enableFlood = useSimStore((s) => s.enableFlood);
  const enableWind = useSimStore((s) => s.enableWind);

  const rainRef = useRef<THREE.Points>(null);
  const windRef = useRef<THREE.Points>(null);
  const lightningRef = useRef<THREE.DirectionalLight>(null);

  const floodTex = useMemo(() => createWaterRippleTexture(), []);
  const fireTex = useMemo(() => createFireSpriteTexture(), []);
  const smokeTex = useMemo(() => createSmokeSpriteTexture(), []);
  const windRad = (weather.wind_direction_deg * Math.PI) / 180;

  useEffect(() => () => {
    floodTex.dispose();
    fireTex.dispose();
    smokeTex.dispose();
  }, [floodTex, fireTex, smokeTex]);

  const rainPositions = useMemo(() => {
    const arr = new Float32Array(1400 * 3);
    for (let i = 0; i < 1400; i++) {
      arr[i * 3] = Math.random() * worldSize;
      arr[i * 3 + 1] = Math.random() * 340;
      arr[i * 3 + 2] = Math.random() * worldSize;
    }
    return arr;
  }, [worldSize]);

  const windPositions = useMemo(() => {
    const arr = new Float32Array(260 * 3);
    for (let i = 0; i < 260; i++) {
      arr[i * 3] = Math.random() * worldSize;
      arr[i * 3 + 1] = 40 + Math.random() * 140;
      arr[i * 3 + 2] = Math.random() * worldSize;
    }
    return arr;
  }, [worldSize]);

  useFrame((state, delta) => {
    const wx = Math.cos(windRad) * weather.wind_speed_mps;
    const wz = Math.sin(windRad) * weather.wind_speed_mps;
    floodTex.offset.x += delta * 0.04;

    if (lightningRef.current) {
      if (weather.condition === "storm") {
        const pulse = Math.sin(state.clock.elapsedTime * 1.9) * Math.sin(state.clock.elapsedTime * 13.7);
        lightningRef.current.intensity = pulse > 0.94 ? 5.5 : 0.0;
      } else {
        lightningRef.current.intensity = 0.0;
      }
    }

    if (rainRef.current && weather.rain_intensity > 0.1) {
      const pos = rainRef.current.geometry.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < pos.count; i++) {
        let x = pos.getX(i) + wx * delta * 4.2;
        let y = pos.getY(i) - delta * (120 + weather.rain_intensity * 110);
        let z = pos.getZ(i) + wz * delta * 4.2;
        if (y < 0) y = 340;
        if (x > worldSize) x = 0; if (x < 0) x = worldSize;
        if (z > worldSize) z = 0; if (z < 0) z = worldSize;
        pos.setXYZ(i, x, y, z);
      }
      pos.needsUpdate = true;
    }

    if (windRef.current && enableWind && weather.wind_speed_mps > 1.0) {
      const pos = windRef.current.geometry.attributes.position as THREE.BufferAttribute;
      for (let i = 0; i < pos.count; i++) {
        let x = pos.getX(i) + wx * delta * 7.5;
        let z = pos.getZ(i) + wz * delta * 7.5;
        if (x > worldSize) x = 0; if (x < 0) x = worldSize;
        if (z > worldSize) z = 0; if (z < 0) z = worldSize;
        pos.setX(i, x);
        pos.setZ(i, z);
      }
      pos.needsUpdate = true;
    }
  });

  if (!showHazards) return null;

  return (
    <group>
      <directionalLight ref={lightningRef} position={[2200, 1400, 1800]} color="#dbeafe" intensity={0} />

      {enableFlood &&
        hazards.filter((h) => h.active && h.kind === "flood").map((hz) => (
          <group key={hz.id} position={[hz.x, 1.35, hz.z]}>
            <mesh rotation={[-Math.PI / 2, 0, 0]}>
              <circleGeometry args={[hz.radius, 44]} />
              <meshStandardMaterial map={floodTex} color="#2563eb" transparent opacity={0.42} roughness={0.14} metalness={0.56} />
            </mesh>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.12, 0]}>
              <ringGeometry args={[hz.radius - 3.5, hz.radius, 44]} />
              <meshBasicMaterial color="#93c5fd" transparent opacity={0.45} side={THREE.DoubleSide} />
            </mesh>
          </group>
        ))}

      {enableFire &&
        hazards.filter((h) => h.active && h.kind === "fire").map((hz) => (
          <FirePlume key={hz.id} hz={hz} windRad={windRad} windSpeed={weather.wind_speed_mps} fireTex={fireTex} smokeTex={smokeTex} />
        ))}

      {hazards.filter((h) => h.active && (h.kind === "no_fly" || h.kind === "blocked_area")).map((hz) => (
        <group key={hz.id} position={[hz.x, 0, hz.z]}>
          <mesh position={[0, 75, 0]}>
            <cylinderGeometry args={[hz.radius, hz.radius, 150, 32, 1, true]} />
            <meshBasicMaterial color="#dc2626" transparent opacity={0.09} side={THREE.DoubleSide} />
          </mesh>
          <mesh position={[0, 0.8, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[hz.radius - 3, hz.radius, 36]} />
            <meshBasicMaterial color="#dc2626" side={THREE.DoubleSide} />
          </mesh>
        </group>
      ))}

      {weather.rain_intensity > 0.1 && (
        <points ref={rainRef}>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" count={1400} array={rainPositions} itemSize={3} />
          </bufferGeometry>
          <pointsMaterial color="#cbd5e1" size={1.6} transparent opacity={0.38 * weather.rain_intensity} />
        </points>
      )}

      {enableWind && (
        <points ref={windRef}>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" count={260} array={windPositions} itemSize={3} />
          </bufferGeometry>
          <pointsMaterial color="#94a3b8" size={2.6} transparent opacity={0.22} />
        </points>
      )}
    </group>
  );
};
