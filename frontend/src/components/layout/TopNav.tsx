import React from "react";
import { Download, Play, Radio, RefreshCw, History, Database, Sliders, ListChecks, Maximize2, BookOpen } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";
import { api } from "../../api/client";

export const TopNav: React.FC = () => {
  const connected = useSimStore((s) => s.connected);
  const fps = useSimStore((s) => s.fps);
  const city = useSimStore((s) => s.city);
  const activeState = useSimStore((s) => s.activeState);
  const activeView = useSimStore((s) => s.activeView);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setShowReplayModal = useSimStore((s) => s.setShowReplayModal);
  const setShowHistoryModal = useSimStore((s) => s.setShowHistoryModal);
  const setShowSettingsModal = useSimStore((s) => s.setShowSettingsModal);
  const setShowShortcutsModal = useSimStore((s) => s.setShowShortcutsModal);
  const showDemoBar = useSimStore((s) => s.showDemoBar);
  const setShowDemoBar = useSimStore((s) => s.setShowDemoBar);
  const stageMode = useSimStore((s) => s.stageMode);
  const setStageMode = useSimStore((s) => s.setStageMode);
  const setShowBriefingModal = useSimStore((s) => s.setShowBriefingModal);
  const startReplay3D = useSimStore((s) => s.startReplay3D);
  const setToast = useSimStore((s) => s.setToast);

  const handleRunAll = async () => {
    setToast("Launching 4 isolated strategy benchmarks...");
    const data = await api.startBenchmark();
    applyServerPayload(data);
    setToast("Benchmark Arena running: Greedy, Classical OR-Tools, QAOA, Hybrid.");
  };

  const handleInit = async () => {
    const data = await api.resetSim();
    applyServerPayload(data);
    setToast("Scenario CHENNAI_FLOOD_001 initialized.");
  };

  const handleExportZip = async () => {
    await api.saveExperiment();
    window.open(api.exportZipUrl(), "_blank");
    setToast("Exporting complete experiment ZIP package...");
  };

  const formatClock = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  };

  const status = activeState?.status || "READY";
  const statusColor =
    status === "RUNNING" ? "text-emerald-400 border-emerald-700 bg-emerald-950/50"
    : status === "PAUSED" ? "text-amber-400 border-amber-700 bg-amber-950/50"
    : status === "COMPLETED" ? "text-blue-400 border-blue-700 bg-blue-950/50"
    : status === "ERROR" ? "text-red-400 border-red-700 bg-red-950/50"
    : "text-zinc-300 border-zinc-700 bg-zinc-900";

  return (
    <header className="h-12 bg-[#11161f] border-b border-[#242c3a] px-3 flex items-center justify-between text-xs font-mono tabular-nums shrink-0">
      {/* Left: Brand & Scenario */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 pr-3 border-r border-[#242c3a]">
          <div className="w-6 h-6 bg-zinc-100 text-zinc-950 flex items-center justify-center font-bold text-[11px]">QR</div>
          <div>
            <div className="font-semibold tracking-wider text-zinc-100 leading-none">QUANTUM RESCUE</div>
            <div className="text-[10px] text-zinc-400 leading-none mt-0.5">AUTONOMOUS FLEET LAB</div>
          </div>
        </div>
        <div className="hidden xl:flex items-center gap-2 text-[11px]">
          <span className="text-zinc-400">SCENARIO:</span>
          <span className="text-zinc-100 font-medium">{city?.scenario_id || "CHENNAI_FLOOD_001"}</span>
          <span className="text-zinc-600">|</span>
          <span className="text-zinc-400">SEED:</span>
          <span className="text-zinc-200">{activeState?.seed || 20261121}</span>
        </div>
      </div>

      {/* Center: Status, Clock, Strategy */}
      <div className="flex items-center gap-2">
        <span className={`px-2 py-0.5 border text-[10px] font-semibold tracking-wider ${statusColor}`}>{status}</span>
        <div className="px-2.5 py-0.5 bg-[#0b0e14] border border-[#242c3a] text-zinc-100">
          T+{formatClock(activeState?.sim_time_s || 0)}
        </div>
        <div className="px-2 py-0.5 bg-[#0b0e14] border border-[#242c3a] text-zinc-300 uppercase">
          MODE: {activeView}
        </div>
        <button
          onClick={handleInit}
          className="px-2.5 py-1 bg-[#171d28] hover:bg-[#1f2735] border border-[#2d3748] text-zinc-200 flex items-center gap-1.5"
        >
          <RefreshCw className="w-3 h-3" /> INIT ENV
        </button>
        <button
          onClick={handleRunAll}
          className="px-3 py-1 bg-zinc-100 hover:bg-white text-zinc-950 font-semibold flex items-center gap-1.5"
        >
          <Play className="w-3 h-3 fill-current" /> RUN ALL STRATEGIES
        </button>
      </div>

      {/* Right: Connection, FPS, Replay, Export */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5 px-2 py-0.5 bg-[#0b0e14] border border-[#242c3a] text-[10px]">
          <Radio className={`w-3 h-3 ${connected ? "text-emerald-500" : "text-red-500"}`} />
          <span className={connected ? "text-emerald-400" : "text-red-400"}>{connected ? "LINK OK" : "OFFLINE"}</span>
          <span className="text-zinc-600">|</span>
          <span className="text-zinc-300">{fps} FPS</span>
        </div>
        <button
          onClick={async () => {
            const rep = await api.getReplay();
            if (rep.frames && rep.frames.length > 0) { startReplay3D(rep.run_id, rep.frames); setToast("3D Replay active in viewport."); }
            else { setShowReplayModal(true); }
          }}
          className="px-2 py-1 bg-[#171d28] hover:bg-[#1f2735] border border-[#2d3748] text-zinc-200 flex items-center gap-1"
          title="3D Experiment Replay"
        >
          <History className="w-3.5 h-3.5" /> 3D REPLAY
        </button>
        <button
          onClick={() => setStageMode(!stageMode)}
          className={`px-2 py-1 border flex items-center gap-1 ${stageMode ? "bg-zinc-100 text-zinc-950 border-zinc-100 font-semibold" : "bg-[#171d28] hover:bg-[#1f2735] border-[#2d3748] text-zinc-200"}`}
          title="Toggle Presentation Stage Mode (P)"
        >
          <Maximize2 className="w-3.5 h-3.5" /> STAGE
        </button>
        <button
          onClick={() => setShowBriefingModal(true)}
          className="px-2 py-1 bg-[#171d28] hover:bg-[#1f2735] border border-[#2d3748] text-zinc-200 flex items-center gap-1"
          title="Mission Briefing & Architecture"
        >
          <BookOpen className="w-3.5 h-3.5" /> BRIEF
        </button>
        <button
          onClick={() => setShowDemoBar(!showDemoBar)}
          className="px-2 py-1 bg-[#171d28] hover:bg-[#1f2735] border border-[#2d3748] text-zinc-200 flex items-center gap-1"
          title="Toggle Guided Demo Bar"
        >
          <ListChecks className="w-3.5 h-3.5" /> DEMO
        </button>
        <button
          onClick={() => setShowSettingsModal(true)}
          className="px-2 py-1 bg-[#171d28] hover:bg-[#1f2735] border border-[#2d3748] text-zinc-200 flex items-center gap-1"
          title="Scoring & QAOA Settings"
        >
          <Sliders className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => setShowShortcutsModal(true)}
          className="px-2 py-1 bg-[#171d28] hover:bg-[#1f2735] border border-[#2d3748] text-zinc-200 font-bold"
          title="Keyboard Controls (?)"
        >
          ?
        </button>
        <button
          onClick={() => setShowHistoryModal(true)}
          className="px-2 py-1 bg-[#171d28] hover:bg-[#1f2735] border border-[#2d3748] text-zinc-200 flex items-center gap-1"
          title="Saved SQLite Experiments"
        >
          <Database className="w-3.5 h-3.5" /> ARCHIVE
        </button>
        <button
          onClick={handleExportZip}
          className="px-2.5 py-1 bg-[#171d28] hover:bg-[#1f2735] border border-[#2d3748] text-zinc-100 flex items-center gap-1.5"
        >
          <Download className="w-3.5 h-3.5" /> EXPORT ZIP
        </button>
      </div>
    </header>
  );
};
