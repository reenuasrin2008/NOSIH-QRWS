import React from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Crosshair, Eye, Home, X } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";
import { api } from "../../api/client";

export const DroneContextHUD: React.FC = () => {
  const activeState = useSimStore((s) => s.activeState);
  const selectedDroneId = useSimStore((s) => s.selectedDroneId);
  const selectDrone = useSimStore((s) => s.selectDrone);
  const setCameraMode = useSimStore((s) => s.setCameraMode);
  const setCameraFocusPoint = useSimStore((s) => s.setCameraFocusPoint);
  const setPlacementMode = useSimStore((s) => s.setPlacementMode);
  const setShowFailureModal = useSimStore((s) => s.setShowFailureModal);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setToast = useSimStore((s) => s.setToast);

  if (!activeState || !selectedDroneId) return null;
  const drones = activeState.drones;
  const idx = drones.findIndex((d) => d.id === selectedDroneId);
  if (idx === -1) return null;
  const drone = drones[idx];

  const cycle = (dir: -1 | 1) => {
    const next = drones[(idx + dir + drones.length) % drones.length];
    selectDrone(next.id);
    setCameraFocusPoint(next.position);
  };

  return (
    <div className="absolute bottom-12 left-1/2 -translate-x-1/2 z-20 bg-[#11161f]/95 border border-[#2d3748] px-2.5 py-1.5 font-mono text-[11px] flex items-center gap-2 shadow-xl tabular-nums">
      <div className="flex items-center gap-1 pr-2 border-r border-[#242c3a]">
        <button onClick={() => cycle(-1)} className="p-0.5 text-zinc-400 hover:text-zinc-100" title="Previous Drone ([)">
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        <span className="font-bold text-zinc-100">{drone.id}</span>
        <button onClick={() => cycle(1)} className="p-0.5 text-zinc-400 hover:text-zinc-100" title="Next Drone (])">
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
        <span className="text-[10px] text-zinc-400 ml-1">{drone.status}</span>
        <span className={`text-[10px] ml-1 ${drone.battery_percent < 25 ? "text-red-400" : "text-emerald-400"}`}>
          {drone.battery_percent.toFixed(0)}%
        </span>
      </div>

      <button
        onClick={() => { setCameraFocusPoint(drone.position); setCameraMode("follow"); }}
        className="px-2 py-1 bg-[#171d28] hover:bg-[#222c3c] border border-[#2d3748] text-zinc-200 flex items-center gap-1"
      >
        <Eye className="w-3 h-3" /> FOLLOW
      </button>
      <button
        onClick={() => setPlacementMode("set_waypoint")}
        className="px-2 py-1 bg-[#171d28] hover:bg-[#222c3c] border border-[#2d3748] text-zinc-200 flex items-center gap-1"
      >
        <Crosshair className="w-3 h-3" /> WAYPOINT
      </button>
      <button
        onClick={async () => { applyServerPayload(await api.returnToBase(drone.id)); setToast(`${drone.id} returning to base.`); }}
        className="px-2 py-1 bg-[#171d28] hover:bg-[#222c3c] border border-[#2d3748] text-zinc-200 flex items-center gap-1"
      >
        <Home className="w-3 h-3" /> RTB
      </button>
      <button
        onClick={() => setShowFailureModal(true)}
        className="px-2 py-1 bg-red-950/75 hover:bg-red-900 border border-red-800 text-red-200 font-semibold flex items-center gap-1"
      >
        <AlertTriangle className="w-3 h-3" /> FAIL / DESTROY
      </button>
      <button onClick={() => selectDrone(null)} className="p-0.5 text-zinc-400 hover:text-zinc-100" title="Deselect (Esc)">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};
