import React, { useState } from "react";
import { DroneState } from "../../types/simulation";

export const GimbalPreview: React.FC<{ drone: DroneState }> = ({ drone }) => {
  const [flir, setFlir] = useState(drone.drone_type === "surveillance" || drone.drone_type === "search_rescue");
  const degHdg = Math.round((((drone.heading_rad * 180) / Math.PI) % 360 + 360) % 360);
  const bankDeg = (drone.bank_rad * 180) / Math.PI;
  const pitchOffset = (drone.pitch_rad * 180) / Math.PI * 1.4;
  const isDead = drone.status === "DESTROYED" || drone.status === "COMMUNICATION_LOST";

  return (
    <div className="p-2 bg-[#0b0e14] border border-[#242c3a] space-y-1.5 font-mono">
      <div className="flex items-center justify-between text-[10px]">
        <span className="text-zinc-400">OPTICAL GIMBAL FEED — {drone.id}</span>
        <button
          onClick={() => setFlir(!flir)}
          className={`px-1.5 py-0.5 border text-[9px] ${
            flir ? "bg-amber-950/60 border-amber-700 text-amber-300" : "bg-[#171d28] border-[#2d3748] text-zinc-300"
          }`}
        >
          {flir ? "FLIR THERMAL" : "EO RGB"}
        </button>
      </div>

      <div className={`relative h-28 overflow-hidden border border-[#1d2432] ${flir ? "bg-[#14171c]" : "bg-[#0d141d]"}`}>
        {isDead ? (
          <div className="w-full h-full flex items-center justify-center text-red-400 text-[11px] font-semibold">
            NO VIDEO SIGNAL — {drone.status}
          </div>
        ) : (
          <svg viewBox="0 0 240 110" className="w-full h-full">
            {/* Artificial Horizon Line */}
            <g transform={`translate(120, ${55 + pitchOffset}) rotate(${-bankDeg})`}>
              <line x1="-80" y1="0" x2="-22" y2="0" stroke={flir ? "#fbbf24" : "#94a3b8"} strokeWidth="1" />
              <line x1="22" y1="0" x2="80" y2="0" stroke={flir ? "#fbbf24" : "#94a3b8"} strokeWidth="1" />
              <line x1="-45" y1="-16" x2="45" y2="-16" stroke={flir ? "#fbbf24" : "#64748b"} strokeWidth="0.6" strokeDasharray="3 3" />
              <line x1="-45" y1="16" x2="45" y2="16" stroke={flir ? "#fbbf24" : "#64748b"} strokeWidth="0.6" strokeDasharray="3 3" />
            </g>

            {/* Center Targeting Crosshair */}
            <circle cx="120" cy="55" r="14" fill="none" stroke={flir ? "#f59e0b" : "#cbd5e1"} strokeWidth="0.9" strokeDasharray="4 4" />
            <line x1="112" y1="55" x2="128" y2="55" stroke={flir ? "#f59e0b" : "#f8fafc"} strokeWidth="1" />
            <line x1="120" y1="47" x2="120" y2="63" stroke={flir ? "#f59e0b" : "#f8fafc"} strokeWidth="1" />

            {/* HUD Corner Readouts */}
            <text x="8" y="14" fill={flir ? "#fcd34d" : "#cbd5e1"} fontSize="8">HDG {String(degHdg).padStart(3, "0")}°</text>
            <text x="172" y="14" fill={flir ? "#fcd34d" : "#cbd5e1"} fontSize="8">ALT {drone.position[1].toFixed(0)}m</text>
            <text x="8" y="102" fill={flir ? "#fcd34d" : "#cbd5e1"} fontSize="8">GS {drone.groundspeed_mps.toFixed(1)}m/s</text>
            <text x="152" y="102" fill={flir ? "#fcd34d" : "#cbd5e1"} fontSize="8">TGT {drone.active_task_id || "SCAN"}</text>
          </svg>
        )}
      </div>
    </div>
  );
};
