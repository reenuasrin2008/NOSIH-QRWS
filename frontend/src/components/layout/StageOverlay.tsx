import React from "react";
import { Maximize2 } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";
import { StrategyType } from "../../types/simulation";
import { api } from "../../api/client";

export const StageOverlay: React.FC = () => {
  const stageMode = useSimStore((s) => s.stageMode);
  const setStageMode = useSimStore((s) => s.setStageMode);
  const leaderboard = useSimStore((s) => s.leaderboard);
  const activeView = useSimStore((s) => s.activeView);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);

  if (!stageMode) return null;

  return (
    <div className="absolute top-14 right-3 z-20 w-64 bg-[#11161f]/92 border border-[#2d3748] p-2.5 font-mono text-[11px] tabular-nums shadow-2xl space-y-2">
      <div className="flex items-center justify-between border-b border-[#242c3a] pb-1.5">
        <span className="text-[10px] font-semibold text-zinc-200 tracking-wider">LIVE BENCHMARK RANKING</span>
        <button
          onClick={() => setStageMode(false)}
          className="text-[9px] px-1.5 py-0.5 bg-[#171d28] border border-[#2d3748] text-zinc-300 hover:text-white flex items-center gap-1"
        >
          <Maximize2 className="w-2.5 h-2.5" /> EXIT STAGE
        </button>
      </div>
      <div className="space-y-1.5">
        {leaderboard.map((row) => {
          const isCurrent = row.strategy === activeView;
          return (
            <button
              key={row.strategy}
              onClick={async () => applyServerPayload(await api.switchView(row.strategy as StrategyType))}
              className={`w-full text-left p-1.5 border transition ${
                isCurrent ? "bg-[#1a2230] border-zinc-300" : "bg-[#0b0e14]/80 border-[#242c3a] hover:border-zinc-500"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-zinc-100 uppercase">#{row.rank} {row.strategy}</span>
                <span className="font-bold text-zinc-100">{row.score.toFixed(1)}</span>
              </div>
              <div className="w-full h-1 bg-[#171d28] mt-1">
                <div className={`h-full ${row.rank === 1 ? "bg-emerald-500" : "bg-zinc-400"}`} style={{ width: `${Math.min(100, row.score)}%` }} />
              </div>
              <div className="flex justify-between text-[9px] text-zinc-400 mt-1">
                <span>DONE: {row.missions_completed}</span>
                <span>{row.total_energy_wh.toFixed(0)} Wh</span>
                <span>REC: {row.tasks_recovered}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
