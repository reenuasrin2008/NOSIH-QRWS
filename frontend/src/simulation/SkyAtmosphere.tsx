import React, { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

const SKY_VERTEX = `
  varying vec3 vWorldPos;
  void main() {
    vec4 wp = modelMatrix * vec4(position, 1.0);
    vWorldPos = wp.xyz;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }
`;

const SKY_FRAGMENT = `
  uniform vec3 uTopColor;
  uniform vec3 uHorizonColor;
  uniform vec3 uGroundColor;
  varying vec3 vWorldPos;
  void main() {
    float h = normalize(vWorldPos - vec3(2000.0, 0.0, 2000.0)).y;
    vec3 col = h >= 0.0
      ? mix(uHorizonColor, uTopColor, pow(clamp(h, 0.0, 1.0), 0.5))
      : mix(uHorizonColor, uGroundColor, clamp(-h * 4.0, 0.0, 1.0));
    gl_FragColor = vec4(col, 1.0);
  }
`;

export const SkyAtmosphere: React.FC<{ dayMode: boolean; windSpeed: number; windDeg: number; worldSize: number }> = ({
  dayMode, windSpeed, windDeg, worldSize,
}) => {
  const cloudsRef = useRef<THREE.Group>(null);
  const half = worldSize / 2;

  const skyMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: SKY_VERTEX,
        fragmentShader: SKY_FRAGMENT,
        side: THREE.BackSide,
        depthWrite: false,
        uniforms: {
          uTopColor: { value: new THREE.Color(dayMode ? "#2d63a3" : "#070c17") },
          uHorizonColor: { value: new THREE.Color(dayMode ? "#e4d2bc" : "#1a2538") },
          uGroundColor: { value: new THREE.Color(dayMode ? "#7f8c96" : "#0a0f18") },
        },
      }),
    [dayMode]
  );

  useEffect(() => {
    return () => {
      skyMat.dispose();
    };
  }, [skyMat]);

  // Multi-puff organic cloud clusters instead of flat boxes
  const cloudClusters = useMemo(
    () =>
      Array.from({ length: 24 }, (_, i) => ({
        x: ((i * 613) % worldSize),
        y: 440 + (i % 5) * 48,
        z: ((i * 857) % worldSize),
        scale: 1.0 + (i % 4) * 0.35,
      })),
    [worldSize]
  );

  useFrame((_, delta) => {
    if (!cloudsRef.current) return;
    const rad = (windDeg * Math.PI) / 180;
    const dx = Math.cos(rad) * windSpeed * delta * 1.4;
    const dz = Math.sin(rad) * windSpeed * delta * 1.4;
    cloudsRef.current.children.forEach((c) => {
      c.position.x = (c.position.x + dx + worldSize) % worldSize;
      c.position.z = (c.position.z + dz + worldSize) % worldSize;
    });
  });

  return (
    <group>
      <mesh position={[half, 0, half]} material={skyMat}>
        <sphereGeometry args={[worldSize * 2.25, 32, 20]} />
      </mesh>

      {/* Sun / Moon Core + Atmospheric Halo */}
      <group position={[half + 1750, dayMode ? 1850 : 1800, half - 1950]}>
        <mesh>
          <sphereGeometry args={[dayMode ? 95 : 54, 16, 16]} />
          <meshBasicMaterial color={dayMode ? "#fff6d6" : "#e2e8f0"} />
        </mesh>
        <mesh>
          <sphereGeometry args={[dayMode ? 175 : 95, 16, 16]} />
          <meshBasicMaterial color={dayMode ? "#fde68a" : "#93c5fd"} transparent opacity={dayMode ? 0.16 : 0.1} />
        </mesh>
      </group>

      {/* Organic Multi-Puff Drifting Clouds */}
      <group ref={cloudsRef}>
        {cloudClusters.map((c, idx) => (
          <group key={idx} position={[c.x, c.y, c.z]} scale={[c.scale, c.scale * 0.42, c.scale]}>
            <mesh position={[0, 0, 0]}>
              <dodecahedronGeometry args={[68, 1]} />
              <meshStandardMaterial color={dayMode ? "#f5efe6" : "#1e293b"} roughness={1} transparent opacity={dayMode ? 0.42 : 0.22} />
            </mesh>
            <mesh position={[55, -8, 18]}>
              <dodecahedronGeometry args={[52, 1]} />
              <meshStandardMaterial color={dayMode ? "#efe8de" : "#1b2434"} roughness={1} transparent opacity={dayMode ? 0.38 : 0.2} />
            </mesh>
            <mesh position={[-52, -10, -14]}>
              <dodecahedronGeometry args={[48, 1]} />
              <meshStandardMaterial color={dayMode ? "#efe8de" : "#1b2434"} roughness={1} transparent opacity={dayMode ? 0.36 : 0.18} />
            </mesh>
          </group>
        ))}
      </group>
    </group>
  );
};
