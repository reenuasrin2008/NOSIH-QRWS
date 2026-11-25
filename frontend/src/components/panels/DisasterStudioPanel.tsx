import React, { useEffect, useState } from "react";
import {
  Activity, Flame, Pause, Play, Plus, RotateCcw, Shuffle, Square, Trash2, TrendingDown, TrendingUp, Zap
} from "lucide-react";
import { api } from "../../api/client";
import { DisasterPreset, DisasterType } from "../../types/simulation";
import { useSimStore } from "../../state/simulationStore";

export const DisasterStudioPanel: React.FC = () => {
  const activeState = useSimStore((s) => s.activeState);
  const setToast = useSimStore((s) => s.setToast);

  const [dtype, setDtype] = useState<DisasterType>("flood");
  const [x, setX] = useState(1850);
  const [z, setZ] = useState(2100);
  const [severity, setSeverity] = useState(0.8);
  const [radius, setRadius] = useState(320);
  const [speed, setSpeed] = useState(1.2);
  const [duration, setDuration] = useState(900);
  const [startDelay, setStartDelay] = useState(0);
  const [presets, setPresets] = useState<DisasterPreset[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listDisasterPresets().then(setPresets).catch(() => {});
  }, []);

  const disasters = activeState?.disasters || [];
  const survivors = activeState?.survivors || [];
  const damageSummary = activeState?.building_damage_summary;
  const affectedBuildingsCount = damageSummary?.total_damaged ?? 0;
  const affectedRoadsCount = disasters.reduce((acc, d) => acc + (d.affected_roads?.length || 0), 0);
  const activeTasksCount = (activeState?.tasks || []).filter((t) => t.status === "assigned" || t.status === "in_progress").length;

  const handleMapClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const nx = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const nz = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    setX(Math.round(nx * 4000));
    setZ(Math.round(nz * 4000));
  };

  const runAction = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true);
    try {
      await fn();
      setToast(msg);
    } catch (err) {
      setToast(`Error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-12 gap-3 h-full min-h-0 font-mono text-[11px] tabular-nums">
      {/* Left: Creation Controls & Interactive 4x4km Coordinate Picker */}
      <div className="col-span-5 bg-[#050505] border border-[#262626] p-2.5 space-y-2 overflow-y-auto">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold text-neutral-300 uppercase flex items-center gap-1.5">
            <Flame className="w-3.5 h-3.5" /> DISASTER STUDIO
          </span>
          <button
            disabled={busy}
            onClick={() => runAction(() => api.triggerRandomDisaster(), "Random multi-hazard scenario triggered.")}
            className="px-2 py-0.5 bg-[#171717] hover:bg-[#262626] border border-[#333333] text-[10px] text-zinc-200 flex items-center gap-1"
          >
            <Shuffle className="w-3 h-3" /> RANDOM
          </button>
        </div>

        <div className="grid grid-cols-3 gap-1">
          {(["flood", "earthquake", "fire", "cyclone", "building_collapse", "landslide"] as DisasterType[]).map((t) => (
            <button
              key={t}
              onClick={() => setDtype(t)}
              className={`py-1 px-1 text-[9px] uppercase border ${
                dtype === t ? "bg-white/15 border-white text-white font-semibold" : "bg-[#0e0e0e] border-[#262626] text-zinc-400"
              }`}
            >
              {t.replace("_", " ")}
            </button>
          ))}
        </div>

        {/* Clickable 4x4 km Coordinate Picker */}
        <div>
          <div className="flex justify-between text-[9px] text-zinc-400 mb-1">
            <span>CLICK MAP TO PICK EPICENTRE</span>
            <span className="text-neutral-200">({x}m, {z}m)</span>
          </div>
          <div
            onClick={handleMapClick}
            className="relative w-full h-28 bg-[#080808] border border-[#333333] cursor-crosshair overflow-hidden"
          >
            <div className="absolute inset-x-0 top-1/2 h-2 bg-neutral-800 -translate-y-1/2" />
            {disasters.map((d) => (
              <div
                key={d.event_id}
                style={{
                  left: `${(d.epicentre.x / 4000) * 100}%`,
                  top: `${(d.epicentre.z / 4000) * 100}%`,
                  width: `${Math.max(8, (d.affected_radius / 4000) * 100)}%`,
                  height: `${Math.max(8, (d.affected_radius / 4000) * 100)}%`,
                }}
                className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/70 bg-white/15 pointer-events-none"
              />
            ))}
            <div
              style={{ left: `${(x / 4000) * 100}%`, top: `${(z / 4000) * 100}%` }}
              className="absolute w-2.5 h-2.5 -translate-x-1/2 -translate-y-1/2 bg-amber-400 border border-white rounded-full pointer-events-none"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-[10px]">
          <label>
            <span className="text-zinc-400 block">SEVERITY ({severity.toFixed(2)})</span>
            <input type="range" min="0.1" max="1.0" step="0.05" value={severity} onChange={(e) => setSeverity(parseFloat(e.target.value))} className="w-full accent-white" />
          </label>
          <label>
            <span className="text-zinc-400 block">RADIUS ({radius}m)</span>
            <input type="range" min="80" max="900" step="20" value={radius} onChange={(e) => setRadius(parseInt(e.target.value, 10))} className="w-full accent-white" />
          </label>
          <label>
            <span className="text-zinc-400 block">SPEED ({speed.toFixed(1)}x)</span>
            <input type="range" min="0.2" max="3.0" step="0.2" value={speed} onChange={(e) => setSpeed(parseFloat(e.target.value))} className="w-full accent-white" />
          </label>
          <label>
            <span className="text-zinc-400 block">DURATION ({duration}s)</span>
            <input type="range" min="120" max="2400" step="60" value={duration} onChange={(e) => setDuration(parseInt(e.target.value, 10))} className="w-full accent-white" />
          </label>
        </div>

        <div className="flex items-center gap-2 text-[10px]">
          <span className="text-zinc-400">DELAY (s):</span>
          <input
            type="number"
            min={0}
            max={300}
            value={startDelay}
            onChange={(e) => setStartDelay(Math.max(0, parseInt(e.target.value || "0", 10)))}
            className="w-16 bg-[#0e0e0e] border border-[#262626] px-1.5 py-0.5 text-zinc-100"
          />
          <button
            disabled={busy}
            onClick={() =>
              runAction(
                () =>
                  api.createDisaster({
                    type: dtype,
                    x,
                    z,
                    severity,
                    affected_radius: radius,
                    duration,
                    propagation_speed: speed,
                    start_delay: startDelay,
                    auto_start: startDelay === 0,
                  }),
                `Created ${dtype.toUpperCase()} at (${x}, ${z}).`
              )
            }
            className="flex-1 py-1.5 bg-white hover:bg-neutral-200 text-zinc-950 font-bold flex items-center justify-center gap-1"
          >
            <Plus className="w-3.5 h-3.5" /> CREATE DISASTER
          </button>
        </div>

        {presets.length > 0 && (
          <div className="pt-1 border-t border-[#262626] space-y-1">
            <div className="text-[9px] text-zinc-400 uppercase">Multi-Hazard Presets</div>
            <div className="grid grid-cols-2 gap-1">
              {presets.map((p) => (
                <button
                  key={p.preset_id}
                  disabled={busy}
                  onClick={() => runAction(() => api.loadDisasterPreset(p.preset_id), `Loaded preset: ${p.name}`)}
                  className="p-1.5 bg-[#0e0e0e] hover:bg-[#171717] border border-[#262626] text-left text-[9px] text-zinc-200 truncate"
                  title={p.description}
                >
                  {p.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Right: Impact Counters & Active Disaster Lifecycle Controls */}
      <div className="col-span-7 flex flex-col gap-2 min-h-0">
        <div className="grid grid-cols-4 gap-1.5 text-[10px]">
          <div className="p-2 bg-[#050505] border border-[#262626]">
            <div className="text-zinc-500 text-[9px]">AFFECTED BLDGS</div>
            <div className="text-neutral-200 font-bold text-sm">{affectedBuildingsCount}</div>
          </div>
          <div className="p-2 bg-[#050505] border border-[#262626]">
            <div className="text-zinc-500 text-[9px]">AFFECTED ROADS</div>
            <div className="text-neutral-300 font-bold text-sm">{affectedRoadsCount}</div>
          </div>
          <div className="p-2 bg-[#050505] border border-[#262626]">
            <div className="text-zinc-500 text-[9px]">SIM SURVIVORS</div>
            <div className="text-neutral-300 font-bold text-sm">{survivors.length}</div>
          </div>
          <div className="p-2 bg-[#050505] border border-[#262626]">
            <div className="text-zinc-500 text-[9px]">ACTIVE RESCUES</div>
            <div className="text-neutral-200 font-bold text-sm">{activeTasksCount}</div>
          </div>
        </div>

        <div className="flex-1 bg-[#050505] border border-[#262626] p-2 overflow-y-auto space-y-1.5">
          <div className="text-[10px] text-zinc-400 uppercase flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-neutral-300" /> ACTIVE HAZARDS ({disasters.length})
          </div>
          {disasters.length === 0 ? (
            <div className="p-4 text-center text-zinc-500 text-[10px]">
              No active disasters. Pick an epicentre on the map or launch a preset scenario.
            </div>
          ) : (
            disasters.map((d) => (
              <div key={d.event_id} className="p-2 bg-[#0e0e0e] border border-[#262626] space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-zinc-100">{d.event_id}</span>
                    <span className="px-1.5 py-0.5 bg-neutral-900 border border-neutral-600 text-neutral-200 uppercase text-[9px]">
                      {d.type.replace("_", " ")}
                    </span>
                    <span className="text-[9px] text-neutral-200">{d.status}</span>
                  </div>
                  <span className="text-[10px] text-zinc-400">
                    SEV {d.severity.toFixed(2)} · R={d.affected_radius}m · SUR={d.related_survivors.length}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1 text-[9px]">
                  <button onClick={() => runAction(() => api.startDisaster(d.event_id), `Started ${d.event_id}`)} className="px-1.5 py-0.5 bg-[#171717] border border-[#333333] text-white flex items-center gap-0.5"><Play className="w-2.5 h-2.5" /> START</button>
                  <button onClick={() => runAction(() => api.pauseDisaster(d.event_id), `Paused ${d.event_id}`)} className="px-1.5 py-0.5 bg-[#171717] border border-[#333333] text-zinc-200 flex items-center gap-0.5"><Pause className="w-2.5 h-2.5" /> PAUSE</button>
                  <button onClick={() => runAction(() => api.resumeDisaster(d.event_id), `Resumed ${d.event_id}`)} className="px-1.5 py-0.5 bg-[#171717] border border-[#333333] text-neutral-200">RESUME</button>
                  <button onClick={() => runAction(() => api.stopDisaster(d.event_id), `Stopped ${d.event_id}`)} className="px-1.5 py-0.5 bg-[#171717] border border-[#333333] text-zinc-300 flex items-center gap-0.5"><Square className="w-2.5 h-2.5" /> STOP</button>
                  <button onClick={() => runAction(() => api.resetDisaster(d.event_id), `Reset ${d.event_id}`)} className="px-1.5 py-0.5 bg-[#171717] border border-[#333333] text-zinc-300 flex items-center gap-0.5"><RotateCcw className="w-2.5 h-2.5" /> RESET</button>
                  <button onClick={() => runAction(() => api.adjustDisasterSeverity(d.event_id, 0.15), `Increased severity of ${d.event_id}`)} className="px-1.5 py-0.5 bg-[#171717] border border-[#333333] text-neutral-200 flex items-center gap-0.5"><TrendingUp className="w-2.5 h-2.5" /> +SEV</button>
                  <button onClick={() => runAction(() => api.adjustDisasterSeverity(d.event_id, -0.15), `Decreased severity of ${d.event_id}`)} className="px-1.5 py-0.5 bg-[#171717] border border-[#333333] text-neutral-200 flex items-center gap-0.5"><TrendingDown className="w-2.5 h-2.5" /> -SEV</button>
                  {d.type === "earthquake" && (
                    <button onClick={() => runAction(() => api.triggerAftershock(d.event_id), `Aftershock triggered on ${d.event_id}`)} className="px-1.5 py-0.5 bg-neutral-900 border border-neutral-500 text-white flex items-center gap-0.5"><Zap className="w-2.5 h-2.5" /> AFTERSHOCK</button>
                  )}
                  <button onClick={() => runAction(() => api.removeDisaster(d.event_id), `Removed ${d.event_id}`)} className="px-1.5 py-0.5 bg-neutral-900 border border-neutral-500 text-neutral-200 flex items-center gap-0.5"><Trash2 className="w-2.5 h-2.5" /> REMOVE</button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
