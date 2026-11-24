import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle, BarChart3, BookOpen, CloudRain, Cpu, Crosshair, Database,
  Download, ExternalLink, Eye, Flame, History, Home, ListChecks, Play, Plus,
  Radio, RefreshCw, ShieldAlert, Shuffle, Sliders, Sun, Trophy, Video, Wind
} from "lucide-react";
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip } from "recharts";
import { useSimStore } from "../state/simulationStore";
import { api } from "../api/client";
import { StrategyType } from "../types/simulation";
import { KpiRibbon } from "../components/layout/KpiRibbon";
import { DemoGuideBar } from "../components/layout/DemoGuideBar";
import { BottomPanel } from "../components/layout/BottomPanel";
import { GimbalPreview } from "../components/panels/GimbalPreview";
import { QuantumCharts } from "../components/panels/QuantumCharts";
import { StationStatusPanel } from "../components/panels/StationStatusPanel";
import { FailureInjectionModal } from "../components/modals/FailureInjectionModal";
import { ExperimentHistoryModal } from "../components/modals/ExperimentHistoryModal";
import { SettingsModal } from "../components/modals/SettingsModal";
import { ShortcutsModal } from "../components/modals/ShortcutsModal";
import { BriefingModal } from "../components/modals/BriefingModal";
import { ReplayModal } from "../components/modals/ReplayModal";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";

export const ControlPanelApp: React.FC = () => {
  const connected = useSimStore((s) => s.connected);
  const city = useSimStore((s) => s.city);
  const activeState = useSimStore((s) => s.activeState);
  const activeView = useSimStore((s) => s.activeView);
  const leaderboard = useSimStore((s) => s.leaderboard);
  const leaderboardSort = useSimStore((s) => s.leaderboardSort);
  const setLeaderboardSort = useSimStore((s) => s.setLeaderboardSort);
  const selectedDroneId = useSimStore((s) => s.selectedDroneId);
  const selectedTaskId = useSimStore((s) => s.selectedTaskId);
  const selectDrone = useSimStore((s) => s.selectDrone);
  const selectTask = useSimStore((s) => s.selectTask);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setShowFailureModal = useSimStore((s) => s.setShowFailureModal);
  const setShowHistoryModal = useSimStore((s) => s.setShowHistoryModal);
  const setShowSettingsModal = useSimStore((s) => s.setShowSettingsModal);
  const setShowShortcutsModal = useSimStore((s) => s.setShowShortcutsModal);
  const setShowBriefingModal = useSimStore((s) => s.setShowBriefingModal);
  const showDemoBar = useSimStore((s) => s.showDemoBar);
  const setShowDemoBar = useSimStore((s) => s.setShowDemoBar);
  const toast = useSimStore((s) => s.toast);
  const setToast = useSimStore((s) => s.setToast);

  const showRoads = useSimStore((s) => s.showRoads);
  const showBuildings = useSimStore((s) => s.showBuildings);
  const showHazards = useSimStore((s) => s.showHazards);
  const showRoutes = useSimStore((s) => s.showRoutes);
  const showGhostRoutes = useSimStore((s) => s.showGhostRoutes);
  const enableFire = useSimStore((s) => s.enableFire);
  const enableFlood = useSimStore((s) => s.enableFlood);
  const toggleLayer = useSimStore((s) => s.toggleLayer);

  const [leftTab, setLeftTab] = useState<"fleet" | "tasks" | "env">("fleet");
  const [centerTab, setCenterTab] = useState<"analytics" | "quantum" | "remote">("analytics");
  const [fleetQuery, setFleetQuery] = useState("");
  const [fleetClassFilter, setFleetClassFilter] = useState("all");
  const [taskQuery, setTaskQuery] = useState("");
  const [taskPrioFilter, setTaskPrioFilter] = useState("all");
  const [cityDensity, setCityDensity] = useState(1.0);
  const [buildingDensity, setBuildingDensity] = useState(1.0);

  useKeyboardShortcuts();

  useEffect(() => {
    document.title = "QUANTUM RESCUE — Mission Control Panel (:5174)";
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3800);
    return () => clearTimeout(t);
  }, [toast, setToast]);

  const drones = activeState?.drones || [];
  const tasks = activeState?.tasks || [];
  const analytics = activeState?.analytics || [];
  const qMetrics = activeState?.quantum_metrics;
  const selectedDrone = drones.find((d) => d.id === selectedDroneId) || drones[0];

  const sortedLeaderboard = useMemo(() => {
    const arr = [...leaderboard];
    if (leaderboardSort === "energy") return arr.sort((a, b) => a.total_energy_wh - b.total_energy_wh);
    if (leaderboardSort === "rescue_time") return arr.sort((a, b) => a.avg_response_time_s - b.avg_response_time_s);
    if (leaderboardSort === "risk") return arr.sort((a, b) => a.operational_risk - b.operational_risk);
    if (leaderboardSort === "completed") return arr.sort((a, b) => b.missions_completed - a.missions_completed);
    if (leaderboardSort === "runtime") return arr.sort((a, b) => a.solver_runtime_ms - b.solver_runtime_ms);
    return arr;
  }, [leaderboard, leaderboardSort]);

  const filteredDrones = drones.filter(
    (d) =>
      (fleetClassFilter === "all" || d.drone_type === fleetClassFilter) &&
      (d.id.toLowerCase().includes(fleetQuery.toLowerCase()) || d.status.toLowerCase().includes(fleetQuery.toLowerCase()))
  );
  const filteredTasks = tasks.filter(
    (t) =>
      (taskPrioFilter === "all" || t.priority === taskPrioFilter) &&
      (t.id.toLowerCase().includes(taskQuery.toLowerCase()) || t.task_type.toLowerCase().includes(taskQuery.toLowerCase()))
  );

  // Synced Remote Actions -> immediately update the 3D Visual Server (:5173)
  const syncSelectDrone = (id: string, pos: [number, number, number]) => {
    selectDrone(id);
    api.syncUi("select_drone", { id });
    api.syncUi("focus_point", { point: pos });
  };

  const syncSelectTask = (id: string, pos: [number, number, number]) => {
    selectTask(id);
    api.syncUi("select_task", { id });
    api.syncUi("focus_point", { point: pos });
  };

  const syncLayer = (key: "showRoads" | "showBuildings" | "showHazards" | "showRoutes" | "showGhostRoutes" | "enableFire" | "enableFlood") => {
    toggleLayer(key);
    api.syncUi("toggle_layer", { key });
  };

  const syncCamera = (mode: string) => {
    api.syncUi("camera_mode", { mode });
    setToast(`3D Scene camera switched to ${mode.toUpperCase()}.`);
  };

  const syncFocus = (point: [number, number, number], label: string) => {
    api.syncUi("focus_point", { point });
    setToast(`3D Scene camera gliding to ${label}.`);
  };

  const handleRunAll = async () => {
    setToast("Launching 4 isolated strategy benchmarks...");
    const data = await api.startBenchmark();
    applyServerPayload(data);
    api.syncUi("critical_alert", {
      alert: {
        title: "4-STRATEGY BENCHMARK LAUNCHED",
        detail: "Greedy, Classical OR-Tools, Quantum QAOA, and Hybrid running on isolated copies of Seed 20261121.",
        kind: "info",
      },
    });
  };

  const triggerEnvEvent = async (kind: string, label: string) => {
    const res = await api.injectEnvEvent(kind);
    applyServerPayload(res.state);
    setToast(label);
    if (kind === "expand_fire" || kind === "new_fire" || kind === "close_airspace") {
      api.syncUi("critical_alert", { alert: { title: "HAZARD UPDATED — REROUTING", detail: label, kind: "replan" } });
    }
  };

  const regenerateCity = async (randomSeed: boolean) => {
    const seed = randomSeed ? Math.floor(10000000 + Math.random() * 89999999) : (activeState?.seed || 20261121);
    const data = await api.generateScenario({ seed, city_density: cityDensity, building_density: buildingDensity });
    applyServerPayload(data);
    setToast(`City regenerated on both servers (seed ${seed}).`);
  };

  const status = activeState?.status || "READY";
  const formatClock = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const greedyScore = leaderboard.find((x) => x.strategy === "greedy")?.score ?? null;

  return (
    <div className="h-screen w-screen flex flex-col bg-[#090d14] text-zinc-100 overflow-hidden">
      {/* Top Command Header */}
      <header className="h-12 bg-[#101620] border-b border-[#222c3c] px-3 flex items-center justify-between text-xs font-mono tabular-nums shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 pr-3 border-r border-[#222c3c]">
            <div className="w-6 h-6 bg-zinc-100 text-zinc-950 font-bold text-[11px] flex items-center justify-center">QR</div>
            <div>
              <div className="font-semibold tracking-wider text-zinc-100 leading-none">QUANTUM RESCUE</div>
              <div className="text-[9px] text-zinc-400 leading-none mt-0.5">MISSION CONTROL DECK (:5174)</div>
            </div>
          </div>
          <span className="px-2 py-0.5 bg-[#090d14] border border-[#222c3c] text-[10px] text-emerald-400 flex items-center gap-1.5">
            <Radio className={`w-3 h-3 ${connected ? "text-emerald-400" : "text-red-400"}`} />
            {connected ? "SYNCED WITH 3D VISUAL (:5173)" : "BACKEND OFFLINE"}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 bg-[#090d14] border border-[#222c3c] text-zinc-200 font-semibold">{status}</span>
          <span className="px-2 py-0.5 bg-[#090d14] border border-[#222c3c] text-zinc-100">T+{formatClock(activeState?.sim_time_s || 0)}</span>
          <button
            onClick={async () => { applyServerPayload(await api.resetSim()); setToast("Scenario reset."); }}
            className="px-2.5 py-1 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-zinc-200 flex items-center gap-1"
          >
            <RefreshCw className="w-3 h-3" /> INIT
          </button>
          <button
            onClick={handleRunAll}
            className="px-3 py-1 bg-zinc-100 hover:bg-white text-zinc-950 font-semibold flex items-center gap-1.5"
          >
            <Play className="w-3 h-3 fill-current" /> RUN ALL 4 STRATEGIES
          </button>
        </div>

        <div className="flex items-center gap-1.5">
          <a
            href="http://localhost:5173"
            target="_blank"
            rel="noreferrer"
            className="px-2.5 py-1 bg-blue-950/60 hover:bg-blue-900/70 border border-blue-700/80 text-blue-200 flex items-center gap-1.5 font-semibold"
          >
            <Video className="w-3.5 h-3.5" /> OPEN 3D VISUAL (:5173) <ExternalLink className="w-3 h-3" />
          </a>
          <button onClick={() => setShowDemoBar(!showDemoBar)} className="px-2 py-1 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-zinc-200 flex items-center gap-1">
            <ListChecks className="w-3.5 h-3.5" /> DEMO
          </button>
          <button onClick={() => setShowBriefingModal(true)} className="px-2 py-1 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-zinc-200 flex items-center gap-1">
            <BookOpen className="w-3.5 h-3.5" /> BRIEF
          </button>
          <button onClick={() => setShowSettingsModal(true)} className="px-2 py-1 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-zinc-200" title="Parameters">
            <Sliders className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => setShowHistoryModal(true)} className="px-2 py-1 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-zinc-200" title="SQLite Archive">
            <Database className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={async () => {
              const rep = await api.getReplay();
              if (rep.frames?.length) {
                api.syncUi("start_replay", { runId: rep.run_id, frames: rep.frames });
                setToast("3D Replay triggered on Visual Server (:5173).");
              } else {
                setToast("Run simulation for at least 5s to record replay frames.");
              }
            }}
            className="px-2 py-1 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-zinc-200"
            title="Play 3D Replay on Visual Server"
          >
            <History className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={async () => { await api.saveExperiment(); window.open(api.exportZipUrl(), "_blank"); setToast("Exporting 14-artifact experiment ZIP..."); }}
            className="px-2.5 py-1 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-zinc-100 flex items-center gap-1"
          >
            <Download className="w-3.5 h-3.5" /> ZIP
          </button>
          <button onClick={() => setShowShortcutsModal(true)} className="px-2 py-1 bg-[#161e2c] border border-[#2c384d] text-zinc-200 font-bold">?</button>
        </div>
      </header>

      <KpiRibbon />
      <DemoGuideBar />

      {/* 3-Column Full-Screen Operations Deck */}
      <div className="flex-1 min-h-0 grid grid-cols-12 gap-2.5 p-2.5 overflow-hidden">
        {/* LEFT COLUMN: Fleet / Tasks / Environment Control */}
        <section className="col-span-3 ops-card flex flex-col min-h-0">
          <div className="p-2 border-b border-[#222c3c] grid grid-cols-2 gap-1.5 font-mono text-[10px]">
            <button
              onClick={() => { api.syncUi("placement_mode", { mode: "add_target" }); setToast("Click on 3D Visual (:5173) to place new rescue target."); }}
              className="py-1.5 bg-red-950/60 hover:bg-red-900/70 border border-red-800 text-red-200 font-semibold flex items-center justify-center gap-1"
            >
              <Plus className="w-3 h-3" /> ADD TARGET ON 3D
            </button>
            <button
              onClick={() => {
                if (!selectedDrone) return;
                api.syncUi("select_drone", { id: selectedDrone.id });
                api.syncUi("placement_mode", { mode: "set_waypoint" });
                setToast(`Click on 3D Visual (:5173) to set waypoint for ${selectedDrone.id}.`);
              }}
              className="py-1.5 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-zinc-200 flex items-center justify-center gap-1"
            >
              <Crosshair className="w-3 h-3" /> WAYPOINT ON 3D
            </button>
          </div>

          <div className="grid grid-cols-3 border-b border-[#222c3c] font-mono text-[10px]">
            {(["fleet", "tasks", "env"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setLeftTab(t)}
                className={`py-2 uppercase border-b-2 ${
                  leftTab === t ? "border-zinc-100 text-zinc-100 bg-[#161e2c] font-semibold" : "border-transparent text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {t === "fleet" ? `FLEET (${drones.length})` : t === "tasks" ? `TASKS (${tasks.length})` : "HAZARDS"}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1.5 font-mono text-[11px] tabular-nums">
            {leftTab === "fleet" && (
              <>
                <div className="flex gap-1">
                  <input value={fleetQuery} onChange={(e) => setFleetQuery(e.target.value)} placeholder="Filter drone..." className="flex-1 bg-[#090d14] border border-[#222c3c] px-2 py-1 text-[10px] text-zinc-100" />
                  <select value={fleetClassFilter} onChange={(e) => setFleetClassFilter(e.target.value)} className="bg-[#090d14] border border-[#222c3c] px-1.5 py-1 text-[10px] text-zinc-200">
                    <option value="all">ALL</option>
                    <option value="surveillance">SURV</option>
                    <option value="medical">MED</option>
                    <option value="heavy_lift">HEAVY</option>
                    <option value="search_rescue">S&R</option>
                  </select>
                </div>
                {filteredDrones.map((d) => {
                  const sel = d.id === selectedDrone?.id;
                  const dead = d.status === "DESTROYED" || d.status === "DAMAGED";
                  return (
                    <button
                      key={d.id}
                      onClick={() => syncSelectDrone(d.id, d.position)}
                      className={`w-full p-2 text-left border transition ${
                        sel ? "bg-[#1a2435] border-zinc-200" : dead ? "bg-red-950/25 border-red-900/60" : "bg-[#090d14] border-[#222c3c] hover:border-zinc-600"
                      }`}
                    >
                      <div className="flex justify-between">
                        <span className="font-semibold text-zinc-100">{d.id} <span className="text-[9px] text-zinc-400 uppercase font-normal">{d.drone_type.replace("_", " ")}</span></span>
                        <span className={`text-[10px] ${d.battery_percent < 25 ? "text-red-400" : "text-emerald-400"}`}>{d.battery_percent.toFixed(0)}%</span>
                      </div>
                      <div className="flex justify-between text-[10px] text-zinc-400 mt-0.5">
                        <span className={dead ? "text-red-400 font-semibold" : "text-zinc-300"}>{d.status}</span>
                        <span>{d.active_task_id || "IDLE"} · {d.groundspeed_mps.toFixed(0)}m/s</span>
                      </div>
                    </button>
                  );
                })}
              </>
            )}

            {leftTab === "tasks" && (
              <>
                <div className="flex gap-1">
                  <input value={taskQuery} onChange={(e) => setTaskQuery(e.target.value)} placeholder="Filter task..." className="flex-1 bg-[#090d14] border border-[#222c3c] px-2 py-1 text-[10px] text-zinc-100" />
                  <select value={taskPrioFilter} onChange={(e) => setTaskPrioFilter(e.target.value)} className="bg-[#090d14] border border-[#222c3c] px-1.5 py-1 text-[10px] text-zinc-200">
                    <option value="all">ALL</option>
                    <option value="critical">CRIT</option>
                    <option value="high">HIGH</option>
                    <option value="medium">MED</option>
                    <option value="low">LOW</option>
                  </select>
                </div>
                {filteredTasks.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => syncSelectTask(t.id, t.location)}
                    className={`w-full p-2 text-left border transition ${
                      t.id === selectedTaskId ? "bg-[#1a2435] border-zinc-200" : "bg-[#090d14] border-[#222c3c] hover:border-zinc-600"
                    }`}
                  >
                    <div className="flex justify-between">
                      <span className="font-semibold text-zinc-100">{t.id} <span className={`text-[9px] uppercase ${t.priority === "critical" ? "text-red-400" : t.priority === "high" ? "text-amber-400" : "text-zinc-400"}`}>{t.priority}</span></span>
                      <span className={`text-[10px] uppercase ${t.status === "completed" ? "text-emerald-400" : "text-zinc-400"}`}>{t.status}</span>
                    </div>
                    <div className="flex justify-between text-[10px] text-zinc-400 mt-0.5">
                      <span className="truncate max-w-[140px]">{t.task_type.replace("_", " ")}</span>
                      <span>{t.assigned_drone_id || "NONE"}</span>
                    </div>
                  </button>
                ))}
              </>
            )}

            {leftTab === "env" && (
              <div className="space-y-2.5 text-[11px]">
                <div className="p-2 bg-[#090d14] border border-[#222c3c] space-y-1.5">
                  <div className="text-[10px] text-zinc-400 uppercase">Event Injection Toolbox</div>
                  <button onClick={() => triggerEnvEvent("expand_fire", "Fire zone expanded across all benchmarks.")} className="w-full py-1.5 px-2 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-left flex items-center gap-2 text-amber-300"><Flame className="w-3.5 h-3.5" /> Expand Fire Zone</button>
                  <button onClick={() => triggerEnvEvent("new_fire", "New metropolitan fire zone erupted.")} className="w-full py-1.5 px-2 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-left flex items-center gap-2 text-red-300"><Flame className="w-3.5 h-3.5" /> Spawn New Fire</button>
                  <button onClick={() => triggerEnvEvent("new_flood", "Flood zone expanded.")} className="w-full py-1.5 px-2 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-left flex items-center gap-2 text-blue-300"><CloudRain className="w-3.5 h-3.5" /> Introduce Flooding</button>
                  <button onClick={() => triggerEnvEvent("close_airspace", "Airspace closed — safe detours computed.")} className="w-full py-1.5 px-2 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-left flex items-center gap-2 text-red-400"><ShieldAlert className="w-3.5 h-3.5" /> Close Airspace Region</button>
                  <button onClick={() => triggerEnvEvent("increase_wind", "Wind speed increased.")} className="w-full py-1.5 px-2 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-left flex items-center gap-2 text-zinc-200"><Wind className="w-3.5 h-3.5" /> Increase Wind Speed</button>
                  <button onClick={() => triggerEnvEvent("heavy_rain", "Heavy rainstorm active.")} className="w-full py-1.5 px-2 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-left flex items-center gap-2 text-zinc-200"><CloudRain className="w-3.5 h-3.5" /> Heavy Rainstorm</button>
                  <button onClick={() => triggerEnvEvent("toggle_day_night", "Day/Night lighting toggled on 3D Visual.")} className="w-full py-1.5 px-2 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-left flex items-center gap-2 text-zinc-200"><Sun className="w-3.5 h-3.5" /> Toggle Day / Night</button>
                </div>

                <div className="p-2 bg-[#090d14] border border-[#222c3c] space-y-2">
                  <div className="text-[10px] text-zinc-400 uppercase">4x4 KM City Seed ({city?.seed || 20261121})</div>
                  <div className="flex justify-between text-[10px] text-zinc-400"><span>CITY DENSITY</span><span>{cityDensity.toFixed(1)}x</span></div>
                  <input type="range" min="0.5" max="1.3" step="0.1" value={cityDensity} onChange={(e) => setCityDensity(parseFloat(e.target.value))} className="w-full accent-zinc-200" />
                  <div className="flex justify-between text-[10px] text-zinc-400"><span>BUILDINGS</span><span>{buildingDensity.toFixed(1)}x</span></div>
                  <input type="range" min="0.5" max="1.3" step="0.1" value={buildingDensity} onChange={(e) => setBuildingDensity(parseFloat(e.target.value))} className="w-full accent-zinc-200" />
                  <div className="grid grid-cols-2 gap-1.5">
                    <button onClick={() => regenerateCity(false)} className="py-1 bg-[#161e2c] border border-[#2c384d] text-zinc-200">REBUILD</button>
                    <button onClick={() => regenerateCity(true)} className="py-1 bg-[#161e2c] border border-[#2c384d] text-zinc-200 flex items-center justify-center gap-1"><Shuffle className="w-3 h-3" /> RANDOM</button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* CENTER COLUMN: 4-Strategy Live Benchmark Arena + Analytics / Quantum / Remote */}
        <section className="col-span-6 flex flex-col gap-2.5 min-h-0">
          {/* Top Half: Live 4-Strategy Competition Arena */}
          <div className="ops-card p-3 flex flex-col gap-2.5 font-mono tabular-nums">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-semibold text-zinc-100">
                <Trophy className="w-4 h-4 text-zinc-300" /> LIVE 4-STRATEGY BENCHMARK ARENA
              </div>
              <select
                value={leaderboardSort}
                onChange={(e) => setLeaderboardSort(e.target.value)}
                className="bg-[#090d14] border border-[#222c3c] text-[10px] text-zinc-200 px-2 py-1"
              >
                <option value="score">Sort: Overall Score</option>
                <option value="completed">Sort: Missions Completed</option>
                <option value="rescue_time">Sort: Fastest Response</option>
                <option value="energy">Sort: Lowest Energy</option>
                <option value="risk">Sort: Lowest Risk</option>
                <option value="runtime">Sort: Solver Speed</option>
              </select>
            </div>

            {/* 2x2 Strategy Comparison Cards */}
            <div className="grid grid-cols-2 gap-2">
              {sortedLeaderboard.map((m) => {
                const isLeader = m.rank === 1 && leaderboard.length > 1;
                const isViewing = m.strategy === activeView;
                const delta = greedyScore !== null && m.strategy !== "greedy" ? m.score - greedyScore : null;
                return (
                  <motion.div
                    layout
                    transition={{ duration: 0.25 }}
                    key={m.strategy}
                    className={`p-2.5 bg-[#090d14] border space-y-1.5 ${
                      isViewing ? "border-zinc-200" : isLeader ? "border-emerald-700/80" : "border-[#222c3c]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span className="text-zinc-400 text-[10px]">#{m.rank}</span>
                        <span className="font-bold text-zinc-100 uppercase text-xs">{m.strategy}</span>
                        {isLeader && <span className="px-1 bg-emerald-950 border border-emerald-700 text-emerald-300 text-[9px]">LEADER</span>}
                        {delta !== null && (
                          <span className={`text-[9px] ${delta >= 0 ? "text-emerald-400" : "text-amber-400"}`}>
                            {delta >= 0 ? "+" : ""}{delta.toFixed(1)}
                          </span>
                        )}
                      </div>
                      <button
                        onClick={async () => { applyServerPayload(await api.switchView(m.strategy as StrategyType)); setToast(`3D Visual switched to ${m.strategy.toUpperCase()}.`); }}
                        className={`px-1.5 py-0.5 text-[9px] border ${
                          isViewing ? "bg-zinc-100 text-zinc-950 border-zinc-100 font-bold" : "bg-[#161e2c] border-[#2c384d] text-zinc-300 hover:text-white"
                        }`}
                      >
                        {isViewing ? "ON 3D SCREEN" : "SHOW ON 3D"}
                      </button>
                    </div>
                    <div className="w-full h-1.5 bg-[#161e2c]">
                      <div className={`h-full ${isLeader ? "bg-emerald-500" : "bg-zinc-400"}`} style={{ width: `${Math.min(100, m.score)}%` }} />
                    </div>
                    <div className="grid grid-cols-4 gap-1 text-[10px] text-zinc-400">
                      <div>SCORE <span className="text-zinc-100 font-semibold block">{m.score.toFixed(1)}</span></div>
                      <div>DONE <span className="text-emerald-400 font-semibold block">{m.missions_completed}</span></div>
                      <div>ENERGY <span className="text-zinc-200 block">{m.total_energy_wh.toFixed(0)}Wh</span></div>
                      <div>SOLVER <span className="text-zinc-200 block">{m.solver_runtime_ms.toFixed(0)}ms</span></div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>

          {/* Bottom Half: Tabbed Analytics / Quantum QAOA / 3D Viewport Remote */}
          <div className="ops-card flex-1 min-h-0 flex flex-col">
            <div className="flex border-b border-[#222c3c] font-mono text-[10px]">
              {[
                { id: "analytics", label: "LIVE ANALYTICS", icon: BarChart3 },
                { id: "quantum", label: "QUANTUM QAOA ENGINE", icon: Cpu },
                { id: "remote", label: "3D VISUAL REMOTE (:5173)", icon: Video },
              ].map((t) => {
                const Icon = t.icon;
                return (
                  <button
                    key={t.id}
                    onClick={() => setCenterTab(t.id as typeof centerTab)}
                    className={`px-3 py-2 flex items-center gap-1.5 border-b-2 ${
                      centerTab === t.id ? "border-zinc-100 text-zinc-100 bg-[#161e2c] font-semibold" : "border-transparent text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" /> {t.label}
                  </button>
                );
              })}
            </div>

            <div className="flex-1 overflow-y-auto p-3 font-mono text-[11px] tabular-nums">
              {centerTab === "analytics" && (
                <div className="grid grid-cols-2 gap-3 h-full min-h-[180px]">
                  <div className="p-2.5 bg-[#090d14] border border-[#222c3c] flex flex-col">
                    <div className="text-[10px] text-zinc-400 uppercase mb-1.5">Completed Missions & Fleet Battery (%)</div>
                    <div className="flex-1 min-h-[140px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={analytics}>
                          <XAxis dataKey="t" stroke="#64748b" fontSize={10} />
                          <YAxis stroke="#64748b" fontSize={10} />
                          <Tooltip contentStyle={{ backgroundColor: "#101620", borderColor: "#222c3c", fontSize: 10 }} />
                          <Line type="monotone" dataKey="completed" stroke="#10b981" dot={false} strokeWidth={2} />
                          <Line type="monotone" dataKey="avg_battery_pct" stroke="#3b82f6" dot={false} strokeWidth={1.6} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  <div className="p-2.5 bg-[#090d14] border border-[#222c3c] flex flex-col">
                    <div className="text-[10px] text-zinc-400 uppercase mb-1.5">Strategy Overall Score Comparison</div>
                    <div className="flex-1 min-h-[140px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={leaderboard}>
                          <XAxis dataKey="strategy" stroke="#64748b" fontSize={10} />
                          <YAxis domain={[0, 100]} stroke="#64748b" fontSize={10} />
                          <Tooltip contentStyle={{ backgroundColor: "#101620", borderColor: "#222c3c", fontSize: 10 }} />
                          <Bar dataKey="score" fill="#cbd5e1" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </div>
              )}

              {centerTab === "quantum" && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <div className="p-2 bg-[#090d14] border border-[#222c3c]">
                      <div className="text-[10px] text-amber-400 font-semibold uppercase">
                        {qMetrics?.backend_name || "QAOA — Classical quantum-circuit simulation"}
                      </div>
                      <div className="text-[10px] text-zinc-400 mt-1">
                        Executes real QAOA circuit on reduced critical-task QUBO subproblem (4–8 qubits) with deterministic classical repair.
                      </div>
                    </div>
                    {qMetrics?.executed ? (
                      <div className="grid grid-cols-2 gap-1.5 text-[10px]">
                        {[
                          ["QUBITS", qMetrics.num_qubits],
                          ["DEPTH", qMetrics.circuit_depth],
                          ["LAYERS (p)", qMetrics.qaoa_layers],
                          ["SHOTS", qMetrics.shots],
                          ["EXEC TIME", `${qMetrics.execution_time_ms} ms`],
                          ["BEST BITSTRING", qMetrics.best_bitstring],
                        ].map(([k, v]) => (
                          <div key={k as string} className="p-2 bg-[#090d14] border border-[#222c3c]">
                            <div className="text-zinc-500 text-[9px]">{k as string}</div>
                            <div className="text-zinc-100 font-semibold">{v as string}</div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="p-3 bg-[#090d14] border border-[#222c3c] text-zinc-400">
                        Press RUN ALL 4 STRATEGIES to inspect live QAOA circuit telemetry.
                      </div>
                    )}
                  </div>
                  <div>{qMetrics?.executed && <QuantumCharts q={qMetrics} />}</div>
                </div>
              )}

              {centerTab === "remote" && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-2.5 bg-[#090d14] border border-[#222c3c] space-y-2">
                    <div className="text-[10px] text-zinc-400 uppercase">3D Visual Camera Presets (:5173)</div>
                    <div className="grid grid-cols-2 gap-1.5">
                      {(["orbit", "topdown", "follow", "fpv", "free"] as const).map((m) => (
                        <button key={m} onClick={() => syncCamera(m)} className="py-1.5 bg-[#161e2c] hover:bg-zinc-100 hover:text-zinc-950 border border-[#2c384d] uppercase font-semibold">
                          {m}
                        </button>
                      ))}
                    </div>
                    <div className="text-[10px] text-zinc-400 uppercase pt-1">Metropolitan Landmarks</div>
                    <div className="grid grid-cols-3 gap-1.5">
                      <button onClick={() => syncFocus([2000, 60, 1800], "Downtown Core")} className="py-1.5 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d]">CORE</button>
                      <button onClick={() => syncFocus([2000, 20, 2000], "Adyar River Bridge")} className="py-1.5 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d]">RIVER</button>
                      <button onClick={() => syncFocus([1380, 30, 1420], "Primary Fire Zone")} className="py-1.5 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-amber-300">FIRE</button>
                    </div>
                  </div>

                  <div className="p-2.5 bg-[#090d14] border border-[#222c3c] space-y-1.5">
                    <div className="text-[10px] text-zinc-400 uppercase mb-1">Synced 3D Visibility Layers</div>
                    {[
                      ["showRoads", "Highways & Bridges", showRoads],
                      ["showBuildings", "1,000+ Urban Buildings", showBuildings],
                      ["showHazards", "Hazards & No-Fly Zones", showHazards],
                      ["showRoutes", "3D Spline Flight Paths", showRoutes],
                      ["showGhostRoutes", "Benchmark Ghost Overlay", showGhostRoutes],
                      ["enableFire", "Fire & Smoke Plumes", enableFire],
                      ["enableFlood", "Animated Flood Waters", enableFlood],
                    ].map(([k, lbl, val]) => (
                      <label key={k as string} className="flex items-center justify-between text-zinc-300 cursor-pointer">
                        <span>{lbl as string}</span>
                        <input type="checkbox" checked={val as boolean} onChange={() => syncLayer(k as "showRoads")} className="accent-zinc-100" />
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* RIGHT COLUMN: Selected Drone Avionics, FLIR Gimbal & Station Capacity */}
        <section className="col-span-3 ops-card flex flex-col min-h-0 overflow-y-auto p-2.5 space-y-2.5 font-mono text-[11px] tabular-nums">
          {selectedDrone && (
            <>
              <div className="p-2.5 bg-[#090d14] border border-[#222c3c]">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-zinc-100">{selectedDrone.id}</span>
                  <span className="px-1.5 py-0.5 bg-[#161e2c] border border-[#2c384d] text-[10px] text-zinc-200">{selectedDrone.status}</span>
                </div>
                <div className="text-[10px] text-zinc-400 mt-0.5">{selectedDrone.class_label}</div>
              </div>

              <GimbalPreview drone={selectedDrone} />

              <div className="grid grid-cols-2 gap-1.5">
                <div className="p-2 bg-[#090d14] border border-[#222c3c]">
                  <div className="text-[9px] text-zinc-500">BATTERY</div>
                  <div className={`font-semibold ${selectedDrone.battery_percent < 25 ? "text-red-400" : "text-emerald-400"}`}>
                    {selectedDrone.battery_percent.toFixed(1)}%
                  </div>
                </div>
                <div className="p-2 bg-[#090d14] border border-[#222c3c]">
                  <div className="text-[9px] text-zinc-500">SPEED / ETA</div>
                  <div className="text-zinc-100 font-semibold">{selectedDrone.groundspeed_mps.toFixed(1)}m/s · {selectedDrone.eta_seconds.toFixed(0)}s</div>
                </div>
                <div className="p-2 bg-[#090d14] border border-[#222c3c]">
                  <div className="text-[9px] text-zinc-500">POWER / TEMP</div>
                  <div className="text-zinc-200">{selectedDrone.power_draw_w.toFixed(0)}W · {selectedDrone.battery_temp_c.toFixed(1)}°C</div>
                </div>
                <div className="p-2 bg-[#090d14] border border-[#222c3c]">
                  <div className="text-[9px] text-zinc-500">PAYLOAD</div>
                  <div className="text-zinc-200">{selectedDrone.current_payload_kg}/{selectedDrone.max_payload_kg} kg</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-1.5">
                <button
                  onClick={() => { api.syncUi("select_drone", { id: selectedDrone.id }); syncCamera("follow"); }}
                  className="py-1.5 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-zinc-200 flex items-center justify-center gap-1 text-[10px]"
                >
                  <Eye className="w-3 h-3" /> FOLLOW ON 3D
                </button>
                <button
                  onClick={async () => { applyServerPayload(await api.returnToBase(selectedDrone.id)); setToast(`${selectedDrone.id} ordered to RTB.`); }}
                  className="py-1.5 bg-[#161e2c] hover:bg-[#1e293b] border border-[#2c384d] text-zinc-200 flex items-center justify-center gap-1 text-[10px]"
                >
                  <Home className="w-3 h-3" /> RETURN BASE
                </button>
              </div>
              <button
                onClick={() => setShowFailureModal(true)}
                className="w-full py-2 bg-red-950/75 hover:bg-red-900 border border-red-800 text-red-100 font-semibold flex items-center justify-center gap-1.5 text-[11px]"
              >
                <AlertTriangle className="w-3.5 h-3.5" /> INJECT FAILURE / DESTROY {selectedDrone.id}
              </button>
            </>
          )}

          <StationStatusPanel stations={activeState?.stations || []} utilization={activeState?.station_utilization} />
        </section>
      </div>

      <BottomPanel />

      {toast && (
        <div className="ops-pill fixed bottom-14 left-1/2 -translate-x-1/2 z-50 px-4 py-1.5 text-zinc-100 text-xs font-mono">
          {toast}
        </div>
      )}

      <FailureInjectionModal />
      <ExperimentHistoryModal />
      <SettingsModal />
      <ShortcutsModal />
      <BriefingModal />
      <ReplayModal />
    </div>
  );
};
