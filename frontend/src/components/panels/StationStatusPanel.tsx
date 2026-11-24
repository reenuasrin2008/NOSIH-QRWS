import React from "react";
import { Station } from "../../types/simulation";

interface Props {
  stations: Station[];
  utilization?: Record<string, { occupied: number; capacity: number; queued: number }>;
}

export const StationStatusPanel: React.FC<Props> = ({ stations, utilization }) => {
  if (!stations.length) return null;
  return (
    <div className="p-2 bg-[#0b0e14] border border-[#242c3a] space-y-1.5">
      <div className="text-[10px] text-zinc-400 uppercase tracking-wider">Charging Hubs & Hospitals</div>
      {stations.map((st) => {
        const u = utilization?.[st.id] || { occupied: 0, capacity: st.capacity, queued: 0 };
        const pct = Math.min(100, Math.round((u.occupied / Math.max(1, u.capacity)) * 100));
        return (
          <div key={st.id} className="text-[10px] space-y-0.5">
            <div className="flex justify-between text-zinc-300">
              <span className="truncate max-w-[175px]">{st.name}</span>
              <span className={st.active ? "text-zinc-400" : "text-red-400"}>
                {st.active ? `${u.occupied}/${u.capacity} pads${u.queued ? ` (+${u.queued}Q)` : ""}` : "OFFLINE"}
              </span>
            </div>
            <div className="h-1 bg-[#171d28] border border-[#242c3a]">
              <div className={`h-full ${pct > 80 ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
};
