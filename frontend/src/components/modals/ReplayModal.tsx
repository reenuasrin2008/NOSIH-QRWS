import React, { useEffect, useState } from "react";
import { Play, Pause, X } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";
import { api } from "../../api/client";

export const ReplayModal: React.FC = () => {
  const open = useSimStore((s) => s.showReplayModal);
  const setOpen = useSimStore((s) => s.setShowReplayModal);
  const [frames, setFrames] = useState<Array<{ t: number; drones: Record<string, { pos: [number, number, number]; status: string; bat: number }>; tasks: Record<string, string> }>>([]);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (open) {
      api.getReplay().then((res) => { setFrames(res.frames || []); setIdx(0); setPlaying(false); });
    }
  }, [open]);

  useEffect(() => {
    if (!playing || frames.length === 0) return;
    const timer = setInterval(() => {
      setIdx((prev) => (prev + 1 < frames.length ? prev + 1 : 0));
    }, 350);
    return () => clearInterval(timer);
  }, [playing, frames]);

  if (!open) return null;
  const current = frames[idx];

  return (
    <div className="fixed inset-0 bg-black/75 flex items-center justify-center z-50 font-mono text-xs">
      <div className="w-[540px] bg-[#11161f] border border-[#2d3748] p-4 space-y-3">
        <div className="flex justify-between items-center border-b border-[#242c3a] pb-2">
          <span className="font-semibold text-zinc-100">RECORDED EXPERIMENT REPLAY ({frames.length} FRAMES)</span>
          <button onClick={() => setOpen(false)} className="text-zinc-400 hover:text-zinc-100"><X className="w-4 h-4" /></button>
        </div>

        {current ? (
          <>
            <div className="flex items-center justify-between text-[11px] text-zinc-300">
              <span>FRAME {idx + 1} / {frames.length}</span>
              <span>SIM TIME: T+{current.t.toFixed(0)}s</span>
              <span>COMPLETED: {Object.values(current.tasks).filter((s) => s === "completed").length}</span>
            </div>
            {/* Deterministic 2D Tactical Radar Reconstruction */}
            <svg viewBox="0 0 4000 4000" className="w-full h-64 bg-[#0b0e14] border border-[#242c3a]">
              {Object.entries(current.drones).map(([did, d]) => (
                <g key={did} transform={`translate(${d.pos[0]}, ${d.pos[2]})`}>
                  <circle r="38" fill={d.status === "DESTROYED" ? "#dc2626" : "#3b82f6"} />
                  <text x="14" y="4" fill="#cbd5e1" fontSize="75">{did}</text>
                </g>
              ))}
            </svg>
            <div className="flex items-center gap-2">
              <button onClick={() => setPlaying(!playing)} className="px-3 py-1 bg-zinc-100 text-zinc-950 font-semibold flex items-center gap-1">
                {playing ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />} {playing ? "PAUSE" : "PLAY"}
              </button>
              <input type="range" min={0} max={Math.max(0, frames.length - 1)} value={idx} onChange={(e) => setIdx(parseInt(e.target.value))} className="flex-1 accent-zinc-200" />
            </div>
          </>
        ) : (
          <div className="p-6 text-center text-zinc-400">No recorded replay frames yet. Run the simulation for at least 5 seconds first.</div>
        )}
      </div>
    </div>
  );
};
