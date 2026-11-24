import React, { useEffect, useState } from "react";
import { X, Sliders } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";
import { api } from "../../api/client";

export const SettingsModal: React.FC = () => {
  const open = useSimStore((s) => s.showSettingsModal);
  const setOpen = useSimStore((s) => s.setShowSettingsModal);
  const setToast = useSimStore((s) => s.setToast);

  const [weights, setWeights] = useState({
    w_rescue_time: 0.25,
    w_energy: 0.15,
    w_risk: 0.15,
    w_deadline_violations: 0.20,
    w_uncompleted: 0.25,
  });
  const [qaoa, setQaoa] = useState({
    qaoa_max_qubits: 8,
    qaoa_layers: 2,
    qaoa_shots: 512,
  });

  useEffect(() => {
    if (open) {
      api.getConfig().then((cfg) => {
        if (cfg.weights) setWeights(cfg.weights as typeof weights);
        if (cfg.qaoa) setQaoa(cfg.qaoa as typeof qaoa);
      }).catch(() => {});
    }
  }, [open]);

  if (!open) return null;

  const save = async () => {
    await api.updateConfig({ ...weights, ...qaoa });
    setOpen(false);
    setToast("Scoring weights and QAOA circuit parameters updated.");
  };

  return (
    <div className="fixed inset-0 bg-black/75 flex items-center justify-center z-50 font-mono text-xs">
      <div className="w-[460px] bg-[#11161f] border border-[#2d3748] p-4 space-y-3">
        <div className="flex justify-between items-center border-b border-[#242c3a] pb-2">
          <div className="flex items-center gap-2 font-semibold text-zinc-100">
            <Sliders className="w-4 h-4 text-zinc-400" /> LAB PARAMETER TUNING
          </div>
          <button onClick={() => setOpen(false)} className="text-zinc-400 hover:text-zinc-100"><X className="w-4 h-4" /></button>
        </div>

        <div className="space-y-2">
          <div className="text-[10px] text-zinc-400 uppercase">Leaderboard Objective Weights</div>
          {(Object.keys(weights) as Array<keyof typeof weights>).map((k) => (
            <div key={k} className="flex items-center justify-between gap-3">
              <span className="text-[11px] text-zinc-300 w-44">{k}</span>
              <input
                type="range"
                min="0"
                max="0.5"
                step="0.05"
                value={weights[k]}
                onChange={(e) => setWeights({ ...weights, [k]: parseFloat(e.target.value) })}
                className="flex-1 accent-zinc-200"
              />
              <span className="w-10 text-right text-zinc-200">{weights[k].toFixed(2)}</span>
            </div>
          ))}
        </div>

        <div className="space-y-2 pt-2 border-t border-[#242c3a]">
          <div className="text-[10px] text-zinc-400 uppercase">QAOA Quantum-Circuit Parameters</div>
          <div className="grid grid-cols-3 gap-2">
            <label>
              <span className="text-[10px] text-zinc-400">MAX QUBITS (4-10)</span>
              <input type="number" min={4} max={10} value={qaoa.qaoa_max_qubits} onChange={(e) => setQaoa({ ...qaoa, qaoa_max_qubits: parseInt(e.target.value) || 8 })} className="mt-0.5 w-full bg-[#0b0e14] border border-[#242c3a] px-2 py-1 text-zinc-100" />
            </label>
            <label>
              <span className="text-[10px] text-zinc-400">LAYERS (p)</span>
              <input type="number" min={1} max={4} value={qaoa.qaoa_layers} onChange={(e) => setQaoa({ ...qaoa, qaoa_layers: parseInt(e.target.value) || 2 })} className="mt-0.5 w-full bg-[#0b0e14] border border-[#242c3a] px-2 py-1 text-zinc-100" />
            </label>
            <label>
              <span className="text-[10px] text-zinc-400">SHOTS</span>
              <input type="number" min={128} max={2048} step={128} value={qaoa.qaoa_shots} onChange={(e) => setQaoa({ ...qaoa, qaoa_shots: parseInt(e.target.value) || 512 })} className="mt-0.5 w-full bg-[#0b0e14] border border-[#242c3a] px-2 py-1 text-zinc-100" />
            </label>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2 border-t border-[#242c3a]">
          <button onClick={() => setOpen(false)} className="px-3 py-1.5 bg-[#171d28] border border-[#2d3748] text-zinc-300">CANCEL</button>
          <button onClick={save} className="px-3 py-1.5 bg-zinc-100 text-zinc-950 font-semibold">APPLY PARAMETERS</button>
        </div>
      </div>
    </div>
  );
};
