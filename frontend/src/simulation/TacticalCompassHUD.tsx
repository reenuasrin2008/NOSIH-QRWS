import React from "react";
import { ActiveSimState } from "../types/simulation";

export const TacticalCompassHUD: React.FC<{ state: ActiveSimState }> = ({ state }) => {
  const airborne = state.drones.filter((d) => ["IN_FLIGHT", "TAKING_OFF", "RETURNING", "DELIVERING"].includes(d.status)).length;
  return (
    <div className="absolute bottom-4 right-4 z-20 text-right pointer-events-none select-none drop-shadow-[0_2px_6px_rgba(0,0,0,0.9)]">
      <div
        className="text-2xl font-extrabold tracking-wider text-white uppercase leading-none"
        style={{ fontFamily: "'Barlow Condensed', sans-serif" }}
      >
        CHENNAI METRO
      </div>
      <div
        className="text-sm font-bold tracking-widest text-amber-400 uppercase mt-0.5"
        style={{ fontFamily: "'Barlow Condensed', sans-serif" }}
      >
        ADYAR RIVER CORRIDOR · 4×4 KM
      </div>
      <div className="text-[10px] font-mono tabular-nums text-zinc-200 mt-1 bg-black/60 px-2 py-0.5 inline-block border border-white/15">
        AIRBORNE {airborne}/30 · WIND {state.weather.wind_speed_mps.toFixed(1)}m/s · WASD PAN · ?: KEYS
      </div>
    </div>
  );
};
