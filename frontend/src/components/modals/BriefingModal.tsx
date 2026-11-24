import React from "react";
import { X, Compass } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";

export const BriefingModal: React.FC = () => {
  const open = useSimStore((s) => s.showBriefingModal);
  const setOpen = useSimStore((s) => s.setShowBriefingModal);
  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/75 flex items-center justify-center z-50 font-mono text-xs">
      <div className="w-[620px] bg-[#11161f] border border-[#2d3748] p-5 space-y-4">
        <div className="flex justify-between items-center border-b border-[#242c3a] pb-2.5">
          <div className="flex items-center gap-2 font-semibold text-zinc-100 tracking-wider">
            <Compass className="w-4 h-4 text-zinc-300" /> MISSION BRIEFING — QUANTUM RESCUE LAB
          </div>
          <button onClick={() => setOpen(false)} className="text-zinc-400 hover:text-zinc-100"><X className="w-4 h-4" /></button>
        </div>

        <div className="space-y-3 text-[11px] text-zinc-300 leading-relaxed">
          <div className="p-2.5 bg-[#0b0e14] border border-[#242c3a]">
            <div className="text-[10px] text-zinc-500 uppercase mb-1">Core Research Objective</div>
            Coordinate 30 heterogeneous autonomous drones across 50 dynamically prioritized disaster-response missions in a 4×4 km urban digital twin while minimizing rescue time, energy consumption, deadline violations, and operational risk.
          </div>

          <div className="p-2.5 bg-[#0b0e14] border border-[#242c3a]">
            <div className="text-[10px] text-zinc-500 uppercase mb-1">Closed-Loop Execution Pipeline</div>
            <div className="text-zinc-100 font-semibold tracking-wide">
              OBSERVE → CALCULATE → SIMULATE → OPTIMIZE → DEPLOY → MONITOR → REPLAN
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {[
              ["1. GREEDY BASELINE", "Nearest-eligible assignment + 3D A* navigation. Fast conventional baseline."],
              ["2. CLASSICAL OR-TOOLS", "Fleet-wide CP-SAT constrained optimization + CVRPTW stop sequencing."],
              ["3. QUANTUM QAOA", "Real Qiskit Aer / statevector QAOA on reduced 4–8 qubit critical QUBO subproblems + classical repair."],
              ["4. HYBRID ENGINE", "Combines classical feasibility with QAOA candidate refinement; strictly retains the better validated plan."],
            ].map(([title, desc]) => (
              <div key={title} className="p-2 bg-[#0b0e14] border border-[#242c3a]">
                <div className="font-semibold text-zinc-100 text-[10px]">{title}</div>
                <div className="text-zinc-400 text-[10px] mt-0.5">{desc}</div>
              </div>
            ))}
          </div>

          <div className="text-[10px] text-zinc-400">
            Fairness Guarantee: Pressing <span className="text-zinc-100 font-semibold">RUN ALL STRATEGIES</span> deep-clones the exact seeded world into 4 isolated backend instances. Injected tasks, drone destruction events, and fire expansions broadcast at the exact same logical simulation timestamp.
          </div>
        </div>
      </div>
    </div>
  );
};
