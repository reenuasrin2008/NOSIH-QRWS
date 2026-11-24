import React, { useEffect, useState } from "react";
import { X, Play, Database } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";
import { api } from "../../api/client";

interface SavedExp {
  run_id: string;
  scenario_id: string;
  seed: number;
  strategy: string;
  status: string;
  sim_time_s: number;
  score: number;
  created_at: string;
}

export const ExperimentHistoryModal: React.FC = () => {
  const open = useSimStore((s) => s.showHistoryModal);
  const setOpen = useSimStore((s) => s.setShowHistoryModal);
  const startReplay3D = useSimStore((s) => s.startReplay3D);
  const setToast = useSimStore((s) => s.setToast);
  const [rows, setRows] = useState<SavedExp[]>([]);

  useEffect(() => {
    if (open) {
      api.listExperiments().then(setRows).catch(() => setRows([]));
    }
  }, [open]);

  if (!open) return null;

  const load3DReplay = async (runId: string) => {
    const rep = await api.getSavedReplay(runId);
    if (!rep.frames || rep.frames.length === 0) {
      setToast("Saved run has no recorded replay frames.");
      return;
    }
    startReplay3D(runId, rep.frames);
    setOpen(false);
    setToast(`Loaded ${runId} into 3D Experiment Replay (${rep.frames.length} frames).`);
  };

  return (
    <div className="fixed inset-0 bg-black/75 flex items-center justify-center z-50 font-mono text-xs">
      <div className="w-[640px] bg-[#11161f] border border-[#2d3748] p-4 space-y-3">
        <div className="flex justify-between items-center border-b border-[#242c3a] pb-2">
          <div className="flex items-center gap-2 font-semibold text-zinc-100">
            <Database className="w-4 h-4 text-zinc-400" /> SAVED EXPERIMENT ARCHIVE (SQLITE)
          </div>
          <button onClick={() => setOpen(false)} className="text-zinc-400 hover:text-zinc-100"><X className="w-4 h-4" /></button>
        </div>

        {rows.length === 0 ? (
          <div className="p-6 text-center text-zinc-400">
            No saved experiments yet. Run a simulation and click EXPORT ZIP to persist a run to SQLite.
          </div>
        ) : (
          <div className="max-h-72 overflow-y-auto border border-[#242c3a] bg-[#0b0e14]">
            <table className="w-full text-left text-[11px]">
              <thead className="bg-[#171d28] text-zinc-400 border-b border-[#242c3a]">
                <tr>
                  <th className="p-2">RUN ID</th>
                  <th className="p-2">STRATEGY</th>
                  <th className="p-2">SEED</th>
                  <th className="p-2 text-right">SIM TIME</th>
                  <th className="p-2 text-right">SCORE</th>
                  <th className="p-2 text-right">ACTION</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.run_id} className="border-b border-[#1c2331]">
                    <td className="p-2 text-zinc-100 font-semibold">{r.run_id}</td>
                    <td className="p-2 uppercase text-zinc-300">{r.strategy}</td>
                    <td className="p-2 text-zinc-400">{r.seed}</td>
                    <td className="p-2 text-right text-zinc-300">{r.sim_time_s.toFixed(0)}s</td>
                    <td className="p-2 text-right font-bold text-emerald-400">{r.score.toFixed(1)}</td>
                    <td className="p-2 text-right">
                      <button
                        onClick={() => load3DReplay(r.run_id)}
                        className="px-2 py-0.5 bg-zinc-100 text-zinc-950 font-semibold inline-flex items-center gap-1"
                      >
                        <Play className="w-3 h-3 fill-current" /> 3D REPLAY
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
