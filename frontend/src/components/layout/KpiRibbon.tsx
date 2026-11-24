import React from "react";
import { useSimStore } from "../../state/simulationStore";

export const KpiRibbon: React.FC = () => {
  const activeState = useSimStore((s) => s.activeState);
  const leaderboard = useSimStore((s) => s.leaderboard);
  if (!activeState) return null;

  const tasks = activeState.tasks;
  const drones = activeState.drones;
  const completed = tasks.filter((t) => t.status === "completed").length;
  const pct = tasks.length ? Math.round((completed / tasks.length) * 100) : 0;

  const activeDrones = drones.filter((d) => !["DESTROYED", "DAMAGED", "COMMUNICATION_LOST"].includes(d.status)).length;
  const lostDrones = drones.length - activeDrones;

  const leader = leaderboard[0];
  const greedy = leaderboard.find((m) => m.strategy === "greedy");
  const deltaVsGreedy = leader && greedy && leader.strategy !== "greedy" ? leader.score - greedy.score : null;

  const metrics = activeState.metrics;
  const q = activeState.quantum_metrics;

  return (
    <div className="h-10 bg-[#0d121a] border-b border-[#242c3a] px-3 flex items-center justify-between gap-4 font-mono text-[11px] tabular-nums shrink-0 overflow-x-auto">
      {/* KPI 1: Missions */}
      <div className="flex items-center gap-2.5 min-w-[175px]">
        <div>
          <div className="text-[9px] text-zinc-500 uppercase leading-none">MISSIONS RESOLVED</div>
          <div className="text-zinc-100 font-semibold leading-tight mt-0.5">
            {completed}/{tasks.length} <span className="text-emerald-400">({pct}%)</span>
          </div>
        </div>
        <div className="w-16 h-1.5 bg-[#171d28] border border-[#242c3a]">
          <div className="h-full bg-emerald-500 transition-all duration-300" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* KPI 2: Leading Strategy */}
      <div className="flex items-center gap-2 pl-3 border-l border-[#242c3a] min-w-[180px]">
        <div>
          <div className="text-[9px] text-zinc-500 uppercase leading-none">BENCHMARK LEADER</div>
          <div className="text-zinc-100 font-semibold leading-tight mt-0.5 uppercase">
            {leader ? `${leader.strategy} · ${leader.score.toFixed(1)}` : "STANDBY"}
            {deltaVsGreedy !== null && (
              <span className={`ml-1.5 text-[10px] ${deltaVsGreedy >= 0 ? "text-emerald-400" : "text-amber-400"}`}>
                {deltaVsGreedy >= 0 ? "+" : ""}{deltaVsGreedy.toFixed(1)} vs GREEDY
              </span>
            )}
          </div>
        </div>
      </div>

      {/* KPI 3: Fleet Readiness */}
      <div className="flex items-center gap-2 pl-3 border-l border-[#242c3a] min-w-[130px]">
        <div>
          <div className="text-[9px] text-zinc-500 uppercase leading-none">FLEET READINESS</div>
          <div className="text-zinc-100 font-semibold leading-tight mt-0.5">
            {activeDrones}/{drones.length} OK
            {lostDrones > 0 && <span className="ml-1.5 text-red-400">({lostDrones} LOST)</span>}
          </div>
        </div>
      </div>

      {/* KPI 4: Failure Recovery */}
      <div className="flex items-center gap-2 pl-3 border-l border-[#242c3a] min-w-[140px]">
        <div>
          <div className="text-[9px] text-zinc-500 uppercase leading-none">AUTO-RECOVERY</div>
          <div className="text-zinc-100 font-semibold leading-tight mt-0.5">
            {metrics.tasks_recovered} TASKS <span className="text-emerald-400">({metrics.recovery_rate_pct}%)</span>
          </div>
        </div>
      </div>

      {/* KPI 5: Quantum Engine */}
      <div className="flex items-center gap-2 pl-3 border-l border-[#242c3a] min-w-[170px]">
        <div>
          <div className="text-[9px] text-zinc-500 uppercase leading-none">QAOA CIRCUIT ENGINE</div>
          <div className="text-zinc-200 font-semibold leading-tight mt-0.5">
            {q && q.executed
              ? `${q.num_qubits}q · p=${q.qaoa_layers} · ${q.execution_time_ms.toFixed(0)}ms`
              : "READY (4–8 QUBITS)"}
          </div>
        </div>
      </div>
    </div>
  );
};
