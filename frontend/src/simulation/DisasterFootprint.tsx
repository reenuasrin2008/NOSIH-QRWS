import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { CountrySummary, DisasterEvent } from "../shared/globalTypes";

export interface DisasterFootprintProps {
  disasters: DisasterEvent[];
  countryById: Record<string, CountrySummary | undefined>;
  geoToFlatWorld: (
    lat: number,
    lon: number,
    country: CountrySummary | undefined
  ) => [number, number];
}

function getSemanticHazardColor(disasterType: string): string {
  const t = (disasterType || "").toUpperCase();
  if (t.includes("CYCLONE") || t.includes("STORM") || t.includes("WIND")) {
    return "#f59e0b";
  }
  if (t.includes("FLOOD") || t.includes("TSUNAMI")) {
    return "#0284c7";
  }
  if (t.includes("FIRE") || t.includes("WILDFIRE")) {
    return "#ea580c";
  }
  return "#ea580c";
}

interface FootprintItemProps {
  x: number;
  z: number;
  baseRadius: number;
  color: string;
  isFire: boolean;
  phaseOffset: number;
}

const FootprintItem: React.FC<FootprintItemProps> = ({
  x,
  z,
  baseRadius,
  color,
  isFire,
  phaseOffset,
}) => {
  const outerRingRef = useRef<THREE.Mesh>(null);
  const outerMatRef = useRef<THREE.MeshBasicMaterial>(null);
  const innerRingRef = useRef<THREE.Mesh>(null);
  const innerMatRef = useRef<THREE.MeshBasicMaterial>(null);
  const discMatRef = useRef<THREE.MeshBasicMaterial>(null);
  const fireLightRef = useRef<THREE.PointLight>(null);

  useFrame((state) => {
    const t = state.clock.elapsedTime;

    // Expanding pulse cycle for outer hazard ring (no setState inside useFrame)
    const pulseA = (t * 0.55 + phaseOffset) % 1;
    const scaleA = 0.72 + pulseA * 0.48;
    if (outerRingRef.current) {
      outerRingRef.current.scale.set(scaleA, scaleA, 1);
    }
    if (outerMatRef.current) {
      outerMatRef.current.opacity = (1 - pulseA) * 0.72;
    }

    // Secondary staggered pulse ring
    const pulseB = (t * 0.55 + phaseOffset + 0.5) % 1;
    const scaleB = 0.58 + pulseB * 0.52;
    if (innerRingRef.current) {
      innerRingRef.current.scale.set(scaleB, scaleB, 1);
    }
    if (innerMatRef.current) {
      innerMatRef.current.opacity = (1 - pulseB) * 0.55;
    }

    // Gentle breathing opacity on the translucent hazard disc
    if (discMatRef.current) {
      discMatRef.current.opacity = 0.13 + Math.sin(t * 2.1 + phaseOffset * 6.28) * 0.04;
    }

    // Warm flickering pointLight for active fires
    if (isFire && fireLightRef.current) {
      const flicker =
        Math.sin(t * 11.3 + phaseOffset * 10) * 0.35 +
        Math.sin(t * 23.7 + phaseOffset * 4) * 0.22 +
        Math.cos(t * 6.4) * 0.18;
      fireLightRef.current.intensity = Math.max(1.2, 2.8 + flicker * 1.4);
    }
  });

  const ringInner = Math.max(12, baseRadius * 0.88);
  const ringOuter = baseRadius;

  return (
    <group position={[x, 0, z]}>
      {/* Subtle translucent hazard disc */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 2.6, 0]}>
        <circleGeometry args={[baseRadius * 0.94, 48]} />
        <meshBasicMaterial
          ref={discMatRef}
          color={color}
          transparent
          opacity={0.14}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* Primary pulsing RingGeometry */}
      <mesh ref={outerRingRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, 3.1, 0]}>
        <ringGeometry args={[ringInner, ringOuter, 64]} />
        <meshBasicMaterial
          ref={outerMatRef}
          color={color}
          transparent
          opacity={0.65}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* Staggered secondary pulsing RingGeometry */}
      <mesh ref={innerRingRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, 3.3, 0]}>
        <ringGeometry args={[baseRadius * 0.62, baseRadius * 0.72, 48]} />
        <meshBasicMaterial
          ref={innerMatRef}
          color={color}
          transparent
          opacity={0.48}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* Warm flickering pointLight for active fires */}
      {isFire && (
        <pointLight
          ref={fireLightRef}
          position={[0, 72, 0]}
          color="#ff7a1a"
          intensity={2.8}
          distance={Math.max(420, baseRadius * 2.4)}
          decay={1.5}
        />
      )}
    </group>
  );
};

/**
 * Renders animated pulsing RingGeometry + translucent hazard discs at each
 * active disaster origin scaled by severity * radius_km, plus a warm flickering
 * pointLight for active fires. Zero setState inside useFrame.
 */
export const DisasterFootprint: React.FC<DisasterFootprintProps> = ({
  disasters,
  countryById,
  geoToFlatWorld,
}) => {
  const activeFootprints = useMemo(() => {
    return disasters
      .filter((d) => d.status === "ACTIVE")
      .map((ev, idx) => {
        const [x, z] = geoToFlatWorld(
          ev.origin.lat,
          ev.origin.lon,
          countryById[ev.country_id]
        );
        const severity = Math.max(0.2, ev.severity || 0.5);
        const radiusKm = Math.max(2, ev.radius_km || 6);
        const baseRadius = THREE.MathUtils.clamp(severity * radiusKm * 36, 95, 680);
        const color = getSemanticHazardColor(ev.disaster_type);
        const isFire = (ev.disaster_type || "").toUpperCase().includes("FIRE");

        return {
          eventId: ev.event_id,
          x,
          z,
          baseRadius,
          color,
          isFire,
          phaseOffset: (idx * 0.27) % 1,
        };
      });
  }, [disasters, countryById, geoToFlatWorld]);

  return (
    <group name="disaster-footprints">
      {activeFootprints.map((fp) => (
        <FootprintItem
          key={fp.eventId}
          x={fp.x}
          z={fp.z}
          baseRadius={fp.baseRadius}
          color={fp.color}
          isFire={fp.isFire}
          phaseOffset={fp.phaseOffset}
        />
      ))}
    </group>
  );
};
