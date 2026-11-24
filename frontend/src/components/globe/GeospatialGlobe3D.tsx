import React, { useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, Line, OrbitControls, Stars } from "@react-three/drei";
import * as THREE from "three";
import type { CountrySummary, DisasterEvent, GeoPoint } from "../../shared/globalTypes";
import { createRealisticPlanetTextures } from "./planetTextures";

const GLOBE_RADIUS = 2.45;

function latLonToVec3(lat: number, lon: number, radius = GLOBE_RADIUS): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  const x = -radius * Math.sin(phi) * Math.cos(theta);
  const z = radius * Math.sin(phi) * Math.sin(theta);
  const y = radius * Math.cos(phi);
  return new THREE.Vector3(x, y, z);
}

const ATMOSPHERE_VERTEX = `
  varying vec3 vNormal;
  void main() {
    vNormal = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const ATMOSPHERE_FRAGMENT = `
  varying vec3 vNormal;
  void main() {
    float intensity = pow(0.66 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 3.2);
    gl_FragColor = vec4(0.32, 0.68, 1.0, 1.0) * intensity * 1.15;
  }
`;

const STATE_RING_COLORS: Record<string, string> = {
  IDLE: "#3B82F6",
  LISTENING: "#14B8A6",
  THINKING: "#60A5FA",
  QUERYING: "#38BDF8",
  OPTIMIZING: "#818CF8",
  AWAITING_APPROVAL: "#F59E0B",
  EXECUTING: "#22C55E",
  SUCCESS: "#22C55E",
  WARNING: "#F59E0B",
  ERROR: "#EF4444",
};

interface GlobeSceneProps {
  countries: CountrySummary[];
  disasters: DisasterEvent[];
  selectedCountryId: string;
  onSelectCountry?: (countryId: string) => void;
  candidateRoutes?: Array<{ route_id: string; feasible: boolean; waypoints: GeoPoint[] }>;
  jarvisState?: string;
  showLabels?: boolean;
}

const CameraFocusRig: React.FC<{ targetLat?: number; targetLon?: number }> = ({ targetLat, targetLon }) => {
  const { camera } = useThree();
  const desiredPos = useMemo(() => {
    if (targetLat === undefined || targetLon === undefined) return null;
    return latLonToVec3(targetLat, targetLon, 5.4);
  }, [targetLat, targetLon]);

  useFrame((_, delta) => {
    if (desiredPos) {
      camera.position.lerp(desiredPos, Math.min(1, delta * 2.2));
      camera.lookAt(0, 0, 0);
    }
  });
  return null;
};

const GlobeCore: React.FC<GlobeSceneProps> = ({
  countries,
  disasters,
  selectedCountryId,
  onSelectCountry,
  candidateRoutes = [],
  jarvisState = "IDLE",
  showLabels = true,
}) => {
  const cloudsRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const cycloneRef = useRef<THREE.Group>(null);

  const textures = useMemo(() => createRealisticPlanetTextures(), []);

  const atmosphereMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: ATMOSPHERE_VERTEX,
        fragmentShader: ATMOSPHERE_FRAGMENT,
        blending: THREE.AdditiveBlending,
        side: THREE.BackSide,
        transparent: true,
        depthWrite: false,
      }),
    []
  );

  const selectedCountry = countries.find((c) => c.country_id === selectedCountryId);

  useFrame((_, delta) => {
    if (cloudsRef.current) {
      cloudsRef.current.rotation.y += delta * 0.012;
    }
    if (ringRef.current) {
      ringRef.current.rotation.z += delta * 0.09;
    }
    if (cycloneRef.current) {
      cycloneRef.current.children.forEach((child) => {
        child.rotation.z += delta * 1.4;
      });
    }
  });

  const ringColor = STATE_RING_COLORS[jarvisState] || "#3B82F6";

  return (
    <group>
      {/* Realistic Solar Illumination */}
      <ambientLight intensity={0.42} color="#dbeafe" />
      <directionalLight position={[10, 6, 8]} intensity={2.2} color="#fff7ed" />
      <directionalLight position={[-8, -5, -6]} intensity={0.35} color="#3b82f6" />

      <Stars radius={45} depth={30} count={1600} factor={2.5} saturation={0.1} fade speed={0.4} />

      <CameraFocusRig targetLat={selectedCountry?.center.lat} targetLon={selectedCountry?.center.lon} />

      {/* Subtle Aerospace Orbital Telemetry Ring */}
      <mesh ref={ringRef} rotation={[Math.PI / 2.25, 0.14, 0]}>
        <ringGeometry args={[GLOBE_RADIUS + 0.42, GLOBE_RADIUS + 0.44, 128]} />
        <meshBasicMaterial color={ringColor} transparent opacity={0.45} side={THREE.DoubleSide} />
      </mesh>

      {/* Realistic Earth-like Planet Surface with Continents, Elevation Bump & Specular Oceans */}
      <mesh>
        <sphereGeometry args={[GLOBE_RADIUS, 96, 96]} />
        <meshStandardMaterial
          map={textures.albedoMap}
          bumpMap={textures.bumpMap}
          bumpScale={0.075}
          roughnessMap={textures.roughnessMap}
          roughness={1.0}
          metalness={0.08}
        />
      </mesh>

      {/* Dynamic Moving Cloud Deck */}
      <mesh ref={cloudsRef}>
        <sphereGeometry args={[GLOBE_RADIUS + 0.032, 64, 64]} />
        <meshStandardMaterial
          map={textures.cloudsMap}
          transparent
          opacity={0.72}
          depthWrite={false}
          roughness={0.95}
        />
      </mesh>

      {/* Rayleigh Atmospheric Limb Halo */}
      <mesh material={atmosphereMat}>
        <sphereGeometry args={[GLOBE_RADIUS * 1.075, 64, 64]} />
      </mesh>

      {/* 7 Countries: Real Lat/Lon Boundaries + Capital Pin Markers */}
      {countries.map((c) => {
        const isSelected = c.country_id === selectedCountryId;
        const pos = latLonToVec3(c.center.lat, c.center.lon, GLOBE_RADIUS + 0.055);
        const boundaryPts = c.boundary.map((pt) => latLonToVec3(pt.lat, pt.lon, GLOBE_RADIUS + 0.038));
        if (boundaryPts.length > 0) boundaryPts.push(boundaryPts[0]);

        return (
          <group key={c.country_id}>
            {boundaryPts.length > 2 && (
              <Line
                points={boundaryPts}
                color={isSelected ? "#F8FAFC" : "#CBD5E1"}
                lineWidth={isSelected ? 2.2 : 1.0}
                transparent
                opacity={isSelected ? 0.95 : 0.45}
              />
            )}
            <mesh
              position={pos}
              onClick={(e) => {
                e.stopPropagation();
                onSelectCountry?.(c.country_id);
              }}
            >
              <sphereGeometry args={[isSelected ? 0.068 : 0.048, 16, 16]} />
              <meshStandardMaterial
                color={c.active_disasters > 0 ? "#EF4444" : isSelected ? "#38BDF8" : "#F8FAFC"}
                emissive={c.active_disasters > 0 ? "#DC2626" : isSelected ? "#0284C7" : "#000000"}
                emissiveIntensity={0.85}
              />
            </mesh>
            {showLabels && (
              <Html position={pos} distanceFactor={7.2} style={{ pointerEvents: "none" }}>
                <div
                  className={`px-1.5 py-0.5 rounded text-[10px] font-mono whitespace-nowrap border shadow-sm ${
                    isSelected
                      ? "bg-slate-950/90 border-sky-400 text-sky-100"
                      : "bg-slate-950/75 border-slate-700/80 text-slate-200"
                  }`}
                >
                  {c.flag_code} · {c.name}
                  {c.active_disasters > 0 ? " [ALERT]" : ""}
                </div>
              </Html>
            )}
          </group>
        );
      })}

      {/* Active Disasters: Swirling Cyclone Vortex / Flood Pulse / Fire Glow */}
      <group ref={cycloneRef}>
        {disasters
          .filter((d) => d.status === "ACTIVE")
          .map((d) => {
            const dPos = latLonToVec3(d.origin.lat, d.origin.lon, GLOBE_RADIUS + 0.065);
            const lookQuat = new THREE.Quaternion().setFromUnitVectors(
              new THREE.Vector3(0, 0, 1),
              dPos.clone().normalize()
            );
            const color =
              d.disaster_type === "CYCLONE" ? "#E2E8F0" : d.disaster_type === "FLOOD" ? "#38BDF8" : "#F97316";
            return (
              <mesh key={d.event_id} position={dPos} quaternion={lookQuat}>
                <ringGeometry args={[0.045, 0.14, 32]} />
                <meshBasicMaterial color={color} transparent opacity={0.75} side={THREE.DoubleSide} />
              </mesh>
            );
          })}
      </group>

      {/* 3D Candidate Drone Routes from Backend Geometry */}
      {candidateRoutes.slice(0, 8).map((rc) => {
        const pts = rc.waypoints.map((w) => latLonToVec3(w.lat, w.lon, GLOBE_RADIUS + 0.085));
        if (pts.length < 2) return null;
        return (
          <Line
            key={rc.route_id}
            points={pts}
            color={rc.feasible ? "#22C55E" : "#EF4444"}
            lineWidth={rc.feasible ? 2.2 : 1.0}
            transparent
            opacity={rc.feasible ? 0.92 : 0.45}
          />
        );
      })}

      <OrbitControls enablePan={false} minDistance={3.3} maxDistance={9.5} />
    </group>
  );
};

export const GeospatialGlobe3D: React.FC<GlobeSceneProps> = (props) => {
  return (
    <div className="w-full h-full bg-[#040810] relative">
      <Canvas camera={{ position: [0, 1.8, 6.1], fov: 42 }} gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping }}>
        <GlobeCore {...props} />
      </Canvas>
    </div>
  );
};
