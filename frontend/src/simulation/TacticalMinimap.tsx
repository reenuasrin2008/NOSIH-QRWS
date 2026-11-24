import React from "react";
import { ActiveSimState, CityEnvironment } from "../types/simulation";
import { useSimStore } from "../state/simulationStore";

export const TacticalMinimap: React.FC<{ city: CityEnvironment; state: ActiveSimState }> = ({ city, state }) => {
  const setCameraFocusPoint = useSimStore((s) => s.setCameraFocusPoint);
  const selectedDroneId = useSimStore((s) => s.selectedDroneId);
  const W = city.world_size || 4000;

  const activeDrones = state.drones.filter((d) => !["DESTROYED", "DAMAGED", "COMMUNICATION_LOST"].includes(d.status)).length;
  const fleetHealthPct = Math.round((activeDrones / Math.max(1, state.drones.length)) * 100);
  const avgBatPct = Math.round(state.drones.reduce((acc, d) => acc + d.battery_percent, 0) / Math.max(1, state.drones.length));
  const completedPct = Math.round((state.tasks.filter((t) => t.status === "completed").length / Math.max(1, state.tasks.length)) * 100);

  const handleMapClick = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width;
    const nz = (e.clientY - rect.top) / rect.height;
    const wx = Math.round(Math.max(80, Math.min(W - 80, nx * W)));
    const wz = Math.round(Math.max(80, Math.min(W - 80, nz * W)));
    setCameraFocusPoint([wx, 20, wz]);
  };

  return (
    <div className="absolute bottom-4 left-4 z-20 select-none">
      {/* Classic GTA V Rectangular Radar Frame */}
      <div className="bg-black/80 p-1 border-2 border-black shadow-[0_8px_28px_rgba(0,0,0,0.75)]">
        <div className="relative">
          {/* North Badge */}
          <div className="absolute top-1 left-1/2 -translate-x-1/2 z-10 px-1.5 py-0 bg-black/90 text-[10px] font-bold text-white tracking-widest border border-white/25 pointer-events-none">
            N
          </div>

          <svg
            viewBox={`0 0 ${W} ${W}`}
            onClick={handleMapClick}
            className="w-56 h-36 bg-[#1b222a] cursor-crosshair block"
            preserveAspectRatio="xMidYMid slice"
          >
            {/* River Water */}
            <rect x={0} y={city.river_z - city.river_width / 2} width={W} height={city.river_width} fill="#254d73" />

            {/* Arterial Highways */}
            {city.roads.map((r) => (
              <line
                key={r.id}
                x1={r.start[0]}
                y1={r.start[1]}
                x2={r.end[0]}
                y2={r.end[1]}
                stroke={r.blocked ? "#dc2626" : "#4b5563"}
                strokeWidth={r.width * 0.9}
              />
            ))}

            {/* Hazard Zones */}
            {state.hazards.filter((h) => h.active).map((h) => (
              <circle
                key={h.id}
                cx={h.x}
                cy={h.z}
                r={h.radius}
                fill={h.kind === "flood" ? "#2563eb" : h.kind === "fire" ? "#ea580c" : "#ef4444"}
                fillOpacity={h.kind === "no_fly" ? 0.18 : 0.35}
                stroke={h.kind === "no_fly" ? "#ef4444" : "none"}
                strokeWidth={22}
              />
            ))}

            {/* Rescue Objective Blips */}
            {state.tasks.map((t) => (
              <rect
                key={t.id}
                x={t.location[0] - 32}
                y={t.location[2] - 32}
                width={64}
                height={64}
                fill={t.status === "completed" ? "#22c55e" : t.priority === "critical" ? "#ef4444" : "#facc15"}
                opacity={t.status === "completed" ? 0.45 : 0.95}
              />
            ))}

            {/* 30 Live Drone Blips */}
            {state.drones.map((d) => {
              const isSel = d.id === selectedDroneId;
              const fill = d.status === "DESTROYED" ? "#ef4444" : isSel ? "#ffffff" : "#38bdf8";
              return (
                <circle
                  key={d.id}
                  cx={d.position[0]}
                  cy={d.position[2]}
                  r={isSel ? 85 : 46}
                  fill={fill}
                  stroke="#000000"
                  strokeWidth={20}
                />
              );
            })}
          </svg>
        </div>

        {/* GTA-Style 3-Segment Status Bars directly under Minimap: Fleet Health (Green), Battery (Blue), Mission Progress (Gold) */}
        <div className="grid grid-cols-3 gap-1 mt-1">
          <div className="h-2 bg-zinc-900 overflow-hidden" title={`Fleet Readiness: ${fleetHealthPct}%`}>
            <div className="h-full bg-[#4ade80] transition-all duration-300" style={{ width: `${fleetHealthPct}%` }} />
          </div>
          <div className="h-2 bg-zinc-900 overflow-hidden" title={`Avg Fleet Battery: ${avgBatPct}%`}>
            <div className="h-full bg-[#38bdf8] transition-all duration-300" style={{ width: `${avgBatPct}%` }} />
          </div>
          <div className="h-2 bg-zinc-900 overflow-hidden" title={`Missions Completed: ${completedPct}%`}>
            <div className="h-full bg-[#facc15] transition-all duration-300" style={{ width: `${completedPct}%` }} />
          </div>
        </div>
      </div>
    </div>
  );
};
