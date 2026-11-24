import React, { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Environment, Lightformer } from "@react-three/drei";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import * as THREE from "three";
import { City } from "./City";
import { LivingWorldProps } from "./LivingWorldProps";
import { CountryBiomeLandscape } from "./CountryBiomeLandscape";
import { LivingPopulation3D } from "./LivingPopulation3D";
import { DroneFleet } from "./DroneFleet";
import { RescueMarkers } from "./RescueMarkers";
import { FlightPaths } from "./FlightPaths";
import { RecoveryArcs } from "./RecoveryArcs";
import { EnvironmentalEffects } from "./EnvironmentalEffects";
import { CameraController } from "./CameraController";
import { PlacementController } from "./PlacementController";
import { SkyAtmosphere } from "./SkyAtmosphere";
import { TacticalCompassHUD } from "./TacticalCompassHUD";
import { TacticalMinimap } from "./TacticalMinimap";
import { ReplayBar } from "../components/layout/ReplayBar";
import { DroneContextHUD } from "../components/layout/DroneContextHUD";
import { RecoveryBanner } from "../components/layout/RecoveryBanner";
import { StageOverlay } from "../components/layout/StageOverlay";
import { useSimStore } from "../state/simulationStore";
import { StrategyType } from "../types/simulation";
import { api } from "../api/client";

const FpsTracker: React.FC = () => {
  const setFps = useSimStore((s) => s.setFps);
  const frames = useRef(0);
  const last = useRef(performance.now());
  useFrame(() => {
    frames.current += 1;
    const now = performance.now();
    if (now - last.current >= 1000) {
      setFps(frames.current);
      frames.current = 0;
      last.current = now;
    }
  });
  return null;
};

interface SceneProps {
  countryArchetype?: string;
  countryName?: string;
  hasActiveDisaster?: boolean;
}

export const Scene: React.FC<SceneProps> = ({ countryArchetype = "River Basin", countryName = "Veridia Basin", hasActiveDisaster = false }) => {
  const city = useSimStore((s) => s.city);
  const activeState = useSimStore((s) => s.activeState);
  const ghostRoutes = useSimStore((s) => s.ghostRoutes);
  const placementMode = useSimStore((s) => s.placementMode);
  const cameraMode = useSimStore((s) => s.cameraMode);
  const setCameraMode = useSimStore((s) => s.setCameraMode);
  const setCameraFocusPoint = useSimStore((s) => s.setCameraFocusPoint);
  const mode = useSimStore((s) => s.mode);
  const activeView = useSimStore((s) => s.activeView);
  const showGhostRoutes = useSimStore((s) => s.showGhostRoutes);
  const toggleLayer = useSimStore((s) => s.toggleLayer);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const dayMode = activeState?.weather.day_mode ?? true;
  const worldSize = city?.world_size || 4000;
  const replay3DActive = useSimStore((s) => s.replay3DActive);
  const replay3DFrames = useSimStore((s) => s.replay3DFrames);
  const replay3DIndex = useSimStore((s) => s.replay3DIndex);
  const effectiveDrones = React.useMemo(() => {
    if (!activeState) return [];
    if (!replay3DActive || !replay3DFrames[replay3DIndex]) return activeState.drones;
    const f = replay3DFrames[replay3DIndex];
    return activeState.drones.map((d) => f.drones[d.id] ? { ...d, position: f.drones[d.id].pos, status: f.drones[d.id].status, battery_percent: f.drones[d.id].bat, heading_rad: f.drones[d.id].hdg } : d);
  }, [activeState, replay3DActive, replay3DFrames, replay3DIndex]);
  const effectiveTasks = React.useMemo(() => {
    if (!activeState) return [];
    if (!replay3DActive || !replay3DFrames[replay3DIndex]) return activeState.tasks;
    const f = replay3DFrames[replay3DIndex];
    return activeState.tasks.map((t) => f.tasks[t.id] ? { ...t, status: f.tasks[t.id] } : t);
  }, [activeState, replay3DActive, replay3DFrames, replay3DIndex]);

  const switchStrategyView = async (strat: StrategyType) => {
    const data = await api.switchView(strat);
    applyServerPayload(data);
  };

  return (
    <div className="relative w-full h-full bg-[#0b0e14]">
      <Canvas
        shadows
        camera={{ position: [560, 920, 3450], fov: 46, near: 5, far: 14000 }}
        gl={{
          antialias: true,
          powerPreference: "high-performance",
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: dayMode ? 1.08 : 0.95,
        }}
      >
        <color attach="background" args={[dayMode ? "#8fa3b8" : "#0b0f17"]} />
        <fogExp2 attach="fog" args={[dayMode ? "#8fa3b8" : "#0b0f17", dayMode ? 0.00016 : 0.00022]} />

        <ambientLight intensity={dayMode ? 0.72 : 0.36} />
        <directionalLight
          position={[1400, 1900, 1100]}
          intensity={dayMode ? 1.85 : 1.05}
          color={dayMode ? "#fff6e5" : "#cbd5e1"}
          castShadow
          shadow-mapSize-width={2048}
          shadow-mapSize-height={2048}
          shadow-camera-left={-2200}
          shadow-camera-right={2200}
          shadow-camera-top={2200}
          shadow-camera-bottom={-2200}
          shadow-camera-far={5500}
        />
        <hemisphereLight args={[dayMode ? "#dbeafe" : "#475569", dayMode ? "#4b5563" : "#11161f", dayMode ? 0.68 : 0.38]} />
        {/* Warm/Cool Opposite Rim Fill Light so shadowed skyscraper faces retain architectural depth */}
        <directionalLight position={[-1200, 900, -1000]} intensity={dayMode ? 0.55 : 0.35} color={dayMode ? "#bae6fd" : "#3b82f6"} />

        {/* Procedural Studio/Sky Environment Map for Realistic Glass, Water & Carbon-Fiber Reflections */}
        <Environment resolution={256} frames={1}>
          <Lightformer form="ring" intensity={dayMode ? 2.2 : 0.8} position={[0, 12, 0]} rotation={[Math.PI / 2, 0, 0]} scale={24} color={dayMode ? "#fff4dc" : "#64748b"} />
          <Lightformer form="rect" intensity={dayMode ? 1.8 : 0.5} position={[14, 6, -12]} scale={[20, 8, 1]} color={dayMode ? "#fde68a" : "#38bdf8"} />
          <Lightformer form="rect" intensity={dayMode ? 0.9 : 0.3} position={[-14, 4, 12]} scale={[20, 8, 1]} color={dayMode ? "#93c5fd" : "#1e293b"} />
        </Environment>

        {city && activeState && (
          <>
            <SkyAtmosphere dayMode={dayMode} windSpeed={activeState.weather.wind_speed_mps} windDeg={activeState.weather.wind_direction_deg} worldSize={worldSize} />
            <City city={city} stations={activeState.stations} dayMode={dayMode} />
            <CountryBiomeLandscape archetype={countryArchetype} countryName={countryName} worldSize={worldSize} dayMode={dayMode} />
            <LivingWorldProps worldSize={worldSize} riverZ={city.river_z} dayMode={dayMode} windSpeed={activeState.weather.wind_speed_mps} windDeg={activeState.weather.wind_direction_deg} />
            <LivingPopulation3D worldSize={worldSize} hasActiveDisaster={hasActiveDisaster} dayMode={dayMode} />
            <EnvironmentalEffects hazards={activeState.hazards} weather={activeState.weather} worldSize={worldSize} />
            <DroneFleet drones={effectiveDrones} dayMode={dayMode} windSpeed={activeState.weather.wind_speed_mps} />
            <RescueMarkers tasks={effectiveTasks} />
            <FlightPaths drones={effectiveDrones} ghostRoutes={ghostRoutes} />
            <RecoveryArcs arcs={activeState.recovery_arcs || []} drones={effectiveDrones} />
            <CameraController drones={effectiveDrones} worldSize={worldSize} />
            <PlacementController worldSize={worldSize} />
          </>
        )}
        <FpsTracker />
        {/* Selective Post-Processing Bloom: triggers ONLY on HDR light sources (fire cores, sirens, beacons, nav lights) */}
        <EffectComposer multisampling={4}>
          <Bloom luminanceThreshold={1.1} mipmapBlur intensity={0.62} radius={0.55} />
        </EffectComposer>
      </Canvas>

      {activeState && <TacticalCompassHUD state={activeState} />}
      {city && activeState && <TacticalMinimap city={city} state={activeState} />}
      <ReplayBar />
      <DroneContextHUD />
      <RecoveryBanner />
      <StageOverlay />

      {mode === "benchmark" && (
        <div className="absolute top-3 left-3 flex items-center gap-1 bg-[#11161f]/95 border border-[#242c3a] p-1 text-[11px] font-mono">
          <span className="px-2 text-zinc-400 uppercase">VIEW:</span>
          {(["greedy", "classical", "quantum", "hybrid"] as StrategyType[]).map((st) => (
            <button
              key={st}
              onClick={() => switchStrategyView(st)}
              className={`px-2 py-1 uppercase border transition ${
                activeView === st
                  ? "bg-zinc-100 text-zinc-950 border-zinc-100 font-semibold"
                  : "bg-[#0b0e14] text-zinc-400 border-[#242c3a] hover:text-zinc-100"
              }`}
            >
              {st}
            </button>
          ))}
          <button
            onClick={() => toggleLayer("showGhostRoutes")}
            className={`ml-1 px-2 py-1 uppercase border ${
              showGhostRoutes ? "bg-amber-600/20 text-amber-300 border-amber-500/50" : "bg-[#0b0e14] text-zinc-400 border-[#242c3a]"
            }`}
          >
            OVERLAY
          </button>
        </div>
      )}

      {placementMode !== "none" && (
        <div className="absolute top-14 left-1/2 -translate-x-1/2 px-4 py-1.5 bg-[#11161f] border border-amber-500 text-amber-200 text-xs font-mono">
          {placementMode === "add_target"
            ? "PLACEMENT ACTIVE — Click anywhere on the city ground to create a rescue target."
            : "WAYPOINT ACTIVE — Click anywhere on the city ground to redirect selected drone."}
        </div>
      )}

      <div className="absolute top-3 right-3 flex items-center gap-1 bg-[#11161f]/95 border border-[#242c3a] p-1 text-[10px] font-mono">
        <button onClick={() => setCameraFocusPoint([2000, 60, 1800])} className="px-1.5 py-1 uppercase border bg-[#0b0e14] text-zinc-400 border-[#242c3a] hover:text-zinc-100">CORE</button>
        <button onClick={() => setCameraFocusPoint([2000, 20, 2000])} className="px-1.5 py-1 uppercase border bg-[#0b0e14] text-zinc-400 border-[#242c3a] hover:text-zinc-100">RIVER</button>
        <button onClick={() => setCameraFocusPoint([1380, 30, 1420])} className="px-1.5 py-1 uppercase border bg-[#0b0e14] text-amber-400 border-[#242c3a] hover:text-amber-200">FIRE</button>
        <span className="text-zinc-700 mx-0.5">|</span>
        {(["orbit", "topdown", "follow", "fpv", "free"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setCameraMode(m)}
            className={`px-2 py-1 uppercase border transition ${
              cameraMode === m
                ? "bg-zinc-100 text-zinc-950 border-zinc-100 font-semibold"
                : "bg-[#0b0e14] text-zinc-400 border-[#242c3a] hover:text-zinc-100"
            }`}
          >
            {m}
          </button>
        ))}
      </div>
    </div>
  );
};
