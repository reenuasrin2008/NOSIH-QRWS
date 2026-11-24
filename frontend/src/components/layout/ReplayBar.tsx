import React, { useEffect, useState } from "react";
import { Play, Pause, X } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";

export const ReplayBar: React.FC = () => {
  const active = useSimStore((s) => s.replay3DActive);
  const runId = useSimStore((s) => s.replay3DRunId);
  const frames = useSimStore((s) => s.replay3DFrames);
  const idx = useSimStore((s) => s.replay3DIndex);
  const setIdx = useSimStore((s) => s.setReplay3DIndex);
  const stop = useSimStore((s) => s.stopReplay3D);
  const [playing, setPlaying] = useState(true);

  useEffect(() => {
    if (!active || !playing || frames.length === 0) return;
    const timer = setInterval(() => {
      setIdx((idx + 1) % frames.length);
    }, 320);
    return () => clearInterval(timer);
  }, [active, playing, frames.length, idx, setIdx]);

  if (!active || frames.length === 0) return null;
  const cur = frames[idx] || frames[0];

  return (
    <div className="absolute bottom-12 left-1/2 -translate-x-1/2 z-30 w-[560px] bg-[#11161f]/95 border border-amber-500 px-3 py-2 font-mono text-xs flex items-center gap-3 shadow-xl">
      <span className="px-1.5 py-0.5 bg-amber-600 text-zinc-950 font-bold text-[10px]">3D REPLAY</span>
      <span className="text-zinc-300 text-[11px]">{runId} · T+{cur.t.toFixed(0)}s</span>
      <button onClick={() => setPlaying(!playing)} className="px-2 py-1 bg-zinc-100 text-zinc-950 font-semibold flex items-center gap-1">
        {playing ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
      </button>
      <input
        type="range"
        min={0}
        max={Math.max(0, frames.length - 1)}
        value={idx}
        onChange={(e) => setIdx(parseInt(e.target.value))}
        className="flex-1 accent-amber-500"
      />
      <button onClick={stop} className="p-1 text-zinc-400 hover:text-zinc-100" title="Exit 3D Replay">
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};
