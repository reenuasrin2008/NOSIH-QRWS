import React, { useMemo, useRef } from "react";
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
  uniform vec3 uMidColor;
  uniform vec3 uHorizonColor;
  uniform vec3 uGroundColor;
  varying vec3 vWorldPos;
  void main() {
    float h = normalize(vWorldPos - vec3(2000.0, 0.0, 2000.0)).y;
    vec3 col;
    if (h >= 0.0) {
      vec3 lower = mix(uHorizonColor, uMidColor, smoothstep(0.0, 0.22, h));
      col = mix(lower, uTopColor, smoothstep(0.18, 0.72, h));
    } else {
      col = mix(uHorizonColor, uGroundColor, clamp(-h * 4.5, 0.0, 1.0));
    }
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
          uTopColor: { value: new THREE.Color(dayMode ? "#1b5fa8" : "#050914") },
          uMidColor: { value: new THREE.Color(dayMode ? "#5aa5d8" : "#111b2e") },
          uHorizonColor: { value: new THREE.Color(dayMode ? "#f5cfa0" : "#1f2a40") },
          uGroundColor: { value: new THREE.Color(dayMode ? "#7f94a3" : "#090d16") },
        },
      }),
    [dayMode]
  );

  // High-altitude airy sunlit cumulus clouds (spread naturally across the sky)
  const cloudClusters = useMemo(
    () =>
      Array.from({ length: 18 }, (_, i) => ({
        x: ((i * 733) % worldSize),
        y: 680 + (i % 4) * 75,
        z: ((i * 919) % worldSize),
        scale: 1.15 + (i % 4) * 0.4,
      })),
    [worldSize]
  );

  useFrame((_, delta) => {
    if (!cloudsRef.current) return;
    const rad = (windDeg * Math.PI) / 180;
    const dx = Math.cos(rad) * windSpeed * delta * 1.1;
    const dz = Math.sin(rad) * windSpeed * delta * 1.1;
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

      {/* Los Santos Golden-Hour Sun / Moon Corona */}
      <group position={[half + 1850, dayMode ? 1450 : 1800, half - 1950]}>
        <mesh>
          <sphereGeometry args={[dayMode ? 105 : 54, 16, 16]} />
          <meshBasicMaterial color={dayMode ? "#fffbeb" : "#e2e8f0"} />
        </mesh>
        <mesh>
          <sphereGeometry args={[dayMode ? 240 : 95, 16, 16]} />
          <meshBasicMaterial color={dayMode ? "#fde68a" : "#93c5fd"} transparent opacity={dayMode ? 0.22 : 0.1} />
        </mesh>
      </group>

      {/* Soft High-Altitude Sunlit Clouds */}
      <group ref={cloudsRef}>
        {cloudClusters.map((c, idx) => (
          <group key={idx} position={[c.x, c.y, c.z]} scale={[c.scale * 1.4, c.scale * 0.28, c.scale]}>
            <mesh position={[0, 0, 0]}>
              <icosahedronGeometry args={[62, 2]} />
              <meshStandardMaterial color={dayMode ? "#fff7ed" : "#1e293b"} roughness={1} transparent opacity={dayMode ? 0.24 : 0.14} depthWrite={false} />
            </mesh>
            <mesh position={[58, -6, 14]}>
              <icosahedronGeometry args={[48, 2]} />
              <meshStandardMaterial color={dayMode ? "#ffedd5" : "#1b2434"} roughness={1} transparent opacity={dayMode ? 0.2 : 0.12} depthWrite={false} />
            </mesh>
            <mesh position={[-54, -8, -12]}>
              <icosahedronGeometry args={[44, 2]} />
              <meshStandardMaterial color={dayMode ? "#fef3c7" : "#1b2434"} roughness={1} transparent opacity={dayMode ? 0.18 : 0.11} depthWrite={false} />
            </mesh>
          </group>
        ))}
      </group>
    </group>
  );
};
