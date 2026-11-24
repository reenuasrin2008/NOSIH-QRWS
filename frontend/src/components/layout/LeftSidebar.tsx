import React, { useState } from "react";
import { Plus, Crosshair, Flame, CloudRain, Wind, ShieldAlert, Sun, Shuffle, ChevronLeft, ChevronRight } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";
import { api } from "../../api/client";

export const LeftSidebar: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [section, setSection] = useState<"env" | "fleet" | "tasks">("fleet");
  const [cityDensity, setCityDensity] = useState(1.0);
  const [buildingDensity, setBuildingDensity] = useState(1.0);
  const [fleetQuery, setFleetQuery] = useState("");
  const [fleetClassFilter, setFleetClassFilter] = useState("all");
  const [taskQuery, setTaskQuery] = useState("");
  const [taskPrioFilter, setTaskPrioFilter] = useState("all");

  const activeState = useSimStore((s) => s.activeState);
  const selectedDroneId = useSimStore((s) => s.selectedDroneId);
  const selectedTaskId = useSimStore((s) => s.selectedTaskId);
  const selectDrone = useSimStore((s) => s.selectDrone);
  const selectTask = useSimStore((s) => s.selectTask);
  const setCameraFocusPoint = useSimStore((s) => s.setCameraFocusPoint);
  const setPlacementMode = useSimStore((s) => s.setPlacementMode);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setToast = useSimStore((s) => s.setToast);

  const showRoads = useSimStore((s) => s.showRoads);
  const showBuildings = useSimStore((s) => s.showBuildings);
  const showHazards = useSimStore((s) => s.showHazards);
  const showRoutes = useSimStore((s) => s.showRoutes);
  const enableFire = useSimStore((s) => s.enableFire);
  const enableFlood = useSimStore((s) => s.enableFlood);
  const toggleLayer = useSimStore((s) => s.toggleLayer);

  const triggerEnvEvent = async (kind: string, label: string) => {
    const res = await api.injectEnvEvent(kind);
    applyServerPayload(res.state);
    setToast(label);
  };

  const regenerateCity = async (randomSeed: boolean) => {
    const seed = randomSeed ? Math.floor(10000000 + Math.random() * 89999999) : (activeState?.seed || 20261121);
    const data = await api.generateScenario({ seed, city_density: cityDensity, building_density: buildingDensity });
    applyServerPayload(data);
    setToast(`City generated (seed ${seed})`);
  };

  if (collapsed) {
    return (
      <div className="w-9 bg-[#11161f] border-r border-[#242c3a] flex flex-col items-center py-2 shrink-0">
        <button onClick={() => setCollapsed(false)} className="p-1 text-zinc-400 hover:text-zinc-100">
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    );
  }

  const drones = activeState?.drones || [];
  const tasks = activeState?.tasks || [];
  const filteredDrones = drones.filter((d) => (fleetClassFilter === "all" || d.drone_type === fleetClassFilter) && (d.id.toLowerCase().includes(fleetQuery.toLowerCase()) || d.status.toLowerCase().includes(fleetQuery.toLowerCase())));
  const filteredTasks = tasks.filter((t) => (taskPrioFilter === "all" || t.priority === taskPrioFilter) && (t.id.toLowerCase().includes(taskQuery.toLowerCase()) || t.task_type.toLowerCase().includes(taskQuery.toLowerCase())));

  return (
    <aside className="w-72 bg-[#11161f] border-r border-[#242c3a] flex flex-col shrink-0 text-xs">
      {/* Header & Collapse */}
      <div className="h-9 px-2.5 border-b border-[#242c3a] flex items-center justify-between font-mono">
        <span className="text-[11px] font-semibold text-zinc-300 tracking-wider">ENVIRONMENT & FLEET</span>
        <button onClick={() => setCollapsed(true)} className="p-1 text-zinc-400 hover:text-zinc-100">
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Primary Interactive Action Buttons */}
      <div className="p-2 border-b border-[#242c3a] grid grid-cols-2 gap-1.5 font-mono text-[11px]">
        <button
          onClick={() => setPlacementMode("add_target")}
          className="px-2 py-1.5 bg-red-950/60 hover:bg-red-900/70 border border-red-800 text-red-200 flex items-center justify-center gap-1 font-medium"
        >
          <Plus className="w-3.5 h-3.5" /> ADD TARGET
        </button>
        <button
          onClick={() => {
            if (!selectedDroneId) { setToast("Select a drone first to set a custom destination."); return; }
            setPlacementMode("set_waypoint");
          }}
          className="px-2 py-1.5 bg-[#171d28] hover:bg-[#202938] border border-[#2d3748] text-zinc-200 flex items-center justify-center gap-1"
        >
          <Crosshair className="w-3.5 h-3.5" /> WAYPOINT
        </button>
      </div>

      {/* Section Tabs */}
      <div className="grid grid-cols-3 border-b border-[#242c3a] font-mono text-[10px]">
        {(["env", "fleet", "tasks"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setSection(t)}
            className={`py-2 uppercase border-b-2 transition ${
              section === t ? "border-zinc-100 text-zinc-100 bg-[#171d28]" : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {t === "env" ? "ENV" : t === "fleet" ? `FLEET (${drones.length})` : `TASKS (${tasks.length})`}
          </button>
        ))}
      </div>

      {/* Section Body */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {section === "env" && (
          <div className="space-y-3 font-mono text-[11px]">
            <div className="p-2 bg-[#0b0e14] border border-[#242c3a] space-y-2">
              <div className="text-[10px] text-zinc-400 uppercase">City Generation</div>
              <div>
                <div className="flex justify-between text-[10px] text-zinc-400"><span>CITY DENSITY</span><span>{cityDensity.toFixed(1)}x</span></div>
                <input type="range" min="0.5" max="1.3" step="0.1" value={cityDensity} onChange={(e) => setCityDensity(parseFloat(e.target.value))} className="w-full accent-zinc-300" />
              </div>
              <div>
                <div className="flex justify-between text-[10px] text-zinc-400"><span>BUILDING DENSITY</span><span>{buildingDensity.toFixed(1)}x</span></div>
                <input type="range" min="0.5" max="1.3" step="0.1" value={buildingDensity} onChange={(e) => setBuildingDensity(parseFloat(e.target.value))} className="w-full accent-zinc-300" />
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                <button onClick={() => regenerateCity(false)} className="py-1 bg-[#171d28] border border-[#2d3748] text-zinc-200 hover:bg-[#1f2837]">REBUILD</button>
                <button onClick={() => regenerateCity(true)} className="py-1 bg-[#171d28] border border-[#2d3748] text-zinc-200 hover:bg-[#1f2837] flex items-center justify-center gap-1">
                  <Shuffle className="w-3 h-3" /> RANDOMIZE
                </button>
              </div>
            </div>

            <div className="p-2 bg-[#0b0e14] border border-[#242c3a] space-y-1.5">
              <div className="text-[10px] text-zinc-400 uppercase mb-1">Visibility Layers</div>
              {[
                ["showRoads", "Roads & Bridges", showRoads],
                ["showBuildings", "Urban Buildings", showBuildings],
                ["showHazards", "Danger & No-Fly Zones", showHazards],
                ["showRoutes", "3D Flight Paths", showRoutes],
                ["enableFire", "Fire & Smoke Effects", enableFire],
                ["enableFlood", "Flood Districts", enableFlood],
              ].map(([key, label, val]) => (
                <label key={key as string} className="flex items-center justify-between text-zinc-300 cursor-pointer">
                  <span>{label as string}</span>
                  <input type="checkbox" checked={val as boolean} onChange={() => toggleLayer(key as "showRoads")} className="accent-zinc-200" />
                </label>
              ))}
            </div>

            <div className="p-2 bg-[#0b0e14] border border-[#242c3a] space-y-1.5">
              <div className="text-[10px] text-zinc-400 uppercase mb-1">Event Injection Toolbox</div>
              <button onClick={() => triggerEnvEvent("expand_fire", "Fire zone expanded — checking affected routes.")} className="w-full py-1.5 px-2 bg-[#171d28] hover:bg-[#1f2837] border border-[#2d3748] text-left flex items-center gap-2 text-amber-300">
                <Flame className="w-3.5 h-3.5" /> Expand Fire Zone
              </button>
              <button onClick={() => triggerEnvEvent("new_fire", "New fire zone erupted.")} className="w-full py-1.5 px-2 bg-[#171d28] hover:bg-[#1f2837] border border-[#2d3748] text-left flex items-center gap-2 text-red-300">
                <Flame className="w-3.5 h-3.5" /> Spawn New Fire
              </button>
              <button onClick={() => triggerEnvEvent("new_flood", "New flood zone introduced.")} className="w-full py-1.5 px-2 bg-[#171d28] hover:bg-[#1f2837] border border-[#2d3748] text-left flex items-center gap-2 text-blue-300">
                <CloudRain className="w-3.5 h-3.5" /> Introduce Flooding
              </button>
              <button onClick={() => triggerEnvEvent("close_airspace", "Airspace closed — rerouting active drones.")} className="w-full py-1.5 px-2 bg-[#171d28] hover:bg-[#1f2837] border border-[#2d3748] text-left flex items-center gap-2 text-red-400">
                <ShieldAlert className="w-3.5 h-3.5" /> Close Airspace Region
              </button>
              <button onClick={() => triggerEnvEvent("increase_wind", "Wind speed increased.")} className="w-full py-1.5 px-2 bg-[#171d28] hover:bg-[#1f2837] border border-[#2d3748] text-left flex items-center gap-2 text-zinc-200">
                <Wind className="w-3.5 h-3.5" /> Increase Wind Speed
              </button>
              <button onClick={() => triggerEnvEvent("heavy_rain", "Heavy rainstorm active.")} className="w-full py-1.5 px-2 bg-[#171d28] hover:bg-[#1f2837] border border-[#2d3748] text-left flex items-center gap-2 text-zinc-200">
                <CloudRain className="w-3.5 h-3.5" /> Trigger Heavy Rain
              </button>
              <button onClick={() => triggerEnvEvent("toggle_day_night", "Day/Night lighting toggled.")} className="w-full py-1.5 px-2 bg-[#171d28] hover:bg-[#1f2837] border border-[#2d3748] text-left flex items-center gap-2 text-zinc-200">
                <Sun className="w-3.5 h-3.5" /> Toggle Day / Night
              </button>
            </div>
          </div>
        )}

        {section === "fleet" && (
          <div className="space-y-1.5 font-mono">
            <div className="flex gap-1">
              <input value={fleetQuery} onChange={(e) => setFleetQuery(e.target.value)} placeholder="Search ID/status..." className="flex-1 bg-[#0b0e14] border border-[#242c3a] px-1.5 py-1 text-[10px] text-zinc-100" />
              <select value={fleetClassFilter} onChange={(e) => setFleetClassFilter(e.target.value)} className="bg-[#0b0e14] border border-[#242c3a] px-1 py-1 text-[10px] text-zinc-200">
                <option value="all">ALL</option>
                <option value="surveillance">SURV</option>
                <option value="medical">MED</option>
                <option value="heavy_lift">HEAVY</option>
                <option value="search_rescue">S&R</option>
              </select>
            </div>
            {filteredDrones.map((d) => {
              const selected = d.id === selectedDroneId;
              const isDead = d.status === "DESTROYED" || d.status === "DAMAGED";
              return (
                <button
                  key={d.id}
                  onClick={() => { selectDrone(d.id); setCameraFocusPoint(d.position); }}
                  className={`w-full p-2 text-left border transition ${
                    selected
                      ? "bg-[#1a2230] border-zinc-300"
                      : isDead
                      ? "bg-red-950/25 border-red-900/60 hover:border-red-700"
                      : "bg-[#0b0e14] border-[#242c3a] hover:border-zinc-600"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-zinc-100">{d.id} <span className="text-[10px] text-zinc-400 font-normal uppercase">{d.drone_type.replace("_", " ")}</span></span>
                    <span className={`text-[10px] ${d.battery_percent < 25 ? "text-red-400" : "text-emerald-400"}`}>{d.battery_percent.toFixed(0)}%</span>
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-zinc-400 mt-0.5">
                    <span className={isDead ? "text-red-400 font-semibold" : "text-zinc-300"}>{d.status}</span>
                    <span>{d.active_task_id || "IDLE"} · ({d.position[0].toFixed(0)},{d.position[2].toFixed(0)})</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {section === "tasks" && (
          <div className="space-y-1.5 font-mono">
            <div className="flex gap-1">
              <input value={taskQuery} onChange={(e) => setTaskQuery(e.target.value)} placeholder="Search task..." className="flex-1 bg-[#0b0e14] border border-[#242c3a] px-1.5 py-1 text-[10px] text-zinc-100" />
              <select value={taskPrioFilter} onChange={(e) => setTaskPrioFilter(e.target.value)} className="bg-[#0b0e14] border border-[#242c3a] px-1 py-1 text-[10px] text-zinc-200">
                <option value="all">ALL</option>
                <option value="critical">CRIT</option>
                <option value="high">HIGH</option>
                <option value="medium">MED</option>
                <option value="low">LOW</option>
              </select>
            </div>
            {filteredTasks.map((t) => {
              const selected = t.id === selectedTaskId;
              const pColor =
                t.priority === "critical" ? "text-red-400"
                : t.priority === "high" ? "text-amber-400"
                : t.priority === "medium" ? "text-yellow-400"
                : "text-blue-400";
              return (
                <button
                  key={t.id}
                  onClick={() => { selectTask(t.id); setCameraFocusPoint(t.location); }}
                  className={`w-full p-2 text-left border transition ${
                    selected ? "bg-[#1a2230] border-zinc-300" : "bg-[#0b0e14] border-[#242c3a] hover:border-zinc-600"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-zinc-100">{t.id} <span className={`text-[10px] uppercase ${pColor}`}>{t.priority}</span></span>
                    <span className={`text-[10px] uppercase ${t.status === "completed" ? "text-emerald-400" : "text-zinc-400"}`}>{t.status}</span>
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-zinc-400 mt-0.5">
                    <span className="truncate max-w-[140px]">{t.task_type.replace("_", " ")}</span>
                    <span>{t.assigned_drone_id || "NONE"} · DL {t.deadline_seconds.toFixed(0)}s</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
};
