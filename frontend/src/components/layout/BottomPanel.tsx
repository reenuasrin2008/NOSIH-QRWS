import React, { useState } from "react";
import { Play, Pause, RotateCcw, StepForward, ChevronDown, ChevronUp } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";
import { api } from "../../api/client";

const SPEEDS = [0.5, 1, 2, 4, 8];
const FILTERS = ["all", "drone", "task", "solver", "failure", "replanning", "environment", "system"];

export const BottomPanel: React.FC = () => {
  const [expanded, setExpanded] = useState(true);
  const activeState = useSimStore((s) => s.activeState);
  const eventFilter = useSimStore((s) => s.eventFilter);
  const setEventFilter = useSimStore((s) => s.setEventFilter);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);

  const isRunning = activeState?.status === "RUNNING";
  const speed = activeState?.speed_multiplier ?? 1;
  const events = (activeState?.events || []).filter((e) => eventFilter === "all" || e.category === eventFilter).slice().reverse();

  return (
    <footer className="bg-[#0e0e0e] border-t border-[#262626] font-mono text-xs shrink-0">
      {/* Control Strip */}
      <div className="h-10 px-3 flex items-center justify-between border-b border-[#1f1f1f]">
        <div className="flex items-center gap-1.5">
          {!isRunning ? (
            <button onClick={async () => applyServerPayload(await api.startSim())} className="px-2.5 py-1 bg-zinc-100 text-zinc-950 font-semibold flex items-center gap-1">
              <Play className="w-3 h-3 fill-current" /> START
            </button>
          ) : (
            <button onClick={async () => applyServerPayload(await api.pauseSim())} className="px-2.5 py-1 bg-neutral-300 text-zinc-950 font-semibold flex items-center gap-1">
              <Pause className="w-3 h-3 fill-current" /> PAUSE
            </button>
          )}
          <button onClick={async () => applyServerPayload(await api.stepSim())} className="px-2 py-1 bg-[#171717] border border-[#333333] text-zinc-200 flex items-center gap-1">
            <StepForward className="w-3 h-3" /> STEP
          </button>
          <button onClick={async () => applyServerPayload(await api.resetSim())} className="px-2 py-1 bg-[#171717] border border-[#333333] text-zinc-200 flex items-center gap-1">
            <RotateCcw className="w-3 h-3" /> RESET
          </button>

          <div className="ml-2 flex items-center border border-[#262626] bg-[#050505]">
            {SPEEDS.map((sp) => (
              <button
                key={sp}
                onClick={async () => { await api.setSpeed(sp); applyServerPayload(await api.getScenario()); }}
                className={`px-2 py-1 text-[10px] ${speed === sp ? "bg-zinc-200 text-zinc-950 font-bold" : "text-zinc-400 hover:text-zinc-100"}`}
              >
                {sp}x
              </button>
            ))}
          </div>
        </div>

        {/* Event Filter Pills */}
        <div className="flex items-center gap-1">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setEventFilter(f)}
              className={`px-2 py-0.5 text-[10px] uppercase border ${
                eventFilter === f ? "bg-zinc-200 text-zinc-950 border-zinc-200 font-semibold" : "bg-[#050505] text-zinc-400 border-[#262626]"
              }`}
            >
              {f}
            </button>
          ))}
          <button onClick={() => setExpanded(!expanded)} className="ml-2 p-1 text-zinc-400 hover:text-zinc-100">
            {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Live Event Console */}
      {expanded && (
        <div className="h-28 overflow-y-auto px-3 py-1.5 bg-[#050505] space-y-0.5 text-[11px]">
          {events.map((ev) => (
            <div key={ev.id} className="flex items-center gap-2 leading-snug">
              <span className="text-zinc-500 shrink-0">[T+{ev.sim_time_s.toFixed(0).padStart(4, "0")}s]</span>
              <span className={`uppercase text-[10px] w-20 shrink-0 ${
                ev.category === "failure" ? "text-neutral-300 font-semibold"
                : ev.category === "replanning" ? "text-neutral-300"
                : ev.category === "solver" ? "text-neutral-300"
                : ev.category === "task" ? "text-neutral-200"
                : "text-zinc-400"
              }`}>
                {ev.category}
              </span>
              <span className="text-zinc-200 truncate">{ev.message}</span>
            </div>
          ))}
        </div>
      )}
    </footer>
  );
};
