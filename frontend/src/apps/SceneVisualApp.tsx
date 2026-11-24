import React, { useEffect } from "react";
import { ExternalLink, Radio, Sun, Moon } from "lucide-react";
import { api } from "../api/client";
import { Scene } from "../simulation/Scene";
import { AddTargetModal } from "../components/modals/AddTargetModal";
import { FailureInjectionModal } from "../components/modals/FailureInjectionModal";
import { ShortcutsModal } from "../components/modals/ShortcutsModal";
import { useSimStore } from "../state/simulationStore";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";

interface SceneVisualProps {
  countryArchetype?: string;
  countryName?: string;
  hasActiveDisaster?: boolean;
}

export const SceneVisualApp: React.FC<SceneVisualProps> = ({ countryArchetype, countryName, hasActiveDisaster }) => {
  const connected = useSimStore((s) => s.connected);
  const fps = useSimStore((s) => s.fps);
  const activeState = useSimStore((s) => s.activeState);
  const leaderboard = useSimStore((s) => s.leaderboard);
  const toast = useSimStore((s) => s.toast);
  const setToast = useSimStore((s) => s.setToast);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const dayMode = activeState?.weather.day_mode ?? true;

  useKeyboardShortcuts();

  useEffect(() => {
    document.title = "QUANTUM RESCUE — 3D Open-World Visual (:5173)";
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3800);
    return () => clearTimeout(t);
  }, [toast, setToast]);

  const tasks = activeState?.tasks || [];
  const completed = tasks.filter((t) => t.status === "completed").length;
  const status = activeState?.status || "READY";
  const leader = leaderboard[0];

  const formatClock = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  };

  return (
    <div className="h-screen w-screen relative bg-[#090d14] text-zinc-100 overflow-hidden">
      {/* 100% Full-Bleed Open-World 3D Metropolis */}
      <Scene countryArchetype={countryArchetype} countryName={countryName} hasActiveDisaster={hasActiveDisaster} />

      {/* Subtle Cinematic Edge Vignette for Depth */}
      <div
        className="pointer-events-none absolute inset-0 z-10"
        style={{ background: "radial-gradient(circle at center, transparent 62%, rgba(5, 8, 14, 0.52) 100%)" }}
      />

      {/* GTA-Style Top-Right Crisp Open-World Telemetry Stack */}
      <div className="absolute top-14 right-4 z-20 text-right select-none pointer-events-none drop-shadow-[0_2px_6px_rgba(0,0,0,0.9)]">
        <div
          className="text-3xl font-extrabold tracking-wide text-emerald-400 leading-none tabular-nums"
          style={{ fontFamily: "'Barlow Condensed', sans-serif" }}
        >
          {completed} / {tasks.length} RESCUED
        </div>
        <div
          className="text-lg font-bold tracking-wider text-white uppercase mt-0.5 tabular-nums"
          style={{ fontFamily: "'Barlow Condensed', sans-serif" }}
        >
          {leader ? `#1 ${leader.strategy} · ${leader.score.toFixed(1)}` : "STANDBY"} · T+{formatClock(activeState?.sim_time_s || 0)}
        </div>
        <div className="mt-1 flex items-center justify-end gap-2 font-mono text-[10px]">
          <span className="px-1.5 py-0.5 bg-black/70 border border-white/15 text-zinc-200 flex items-center gap-1">
            <Radio className={`w-2.5 h-2.5 ${connected ? "text-emerald-400" : "text-red-400"}`} />
            {status} · {fps} FPS
          </span>
          <button
            onClick={async () => { const r = await api.injectEnvEvent("toggle_day_night"); applyServerPayload(r.state); }}
            className="pointer-events-auto px-2 py-0.5 bg-black/80 hover:bg-white hover:text-black border border-white/25 text-zinc-200 flex items-center gap-1 transition"
            title="Toggle Day / Night Lighting"
          >
            {dayMode ? <Moon className="w-2.5 h-2.5" /> : <Sun className="w-2.5 h-2.5" />}
            {dayMode ? "NIGHT" : "DAY"}
          </button>
          <a
            href="http://localhost:5174"
            target="_blank"
            rel="noreferrer"
            className="pointer-events-auto px-2 py-0.5 bg-black/80 hover:bg-white hover:text-black border border-white/25 text-zinc-200 flex items-center gap-1 transition"
          >
            CONTROL (:5174) <ExternalLink className="w-2.5 h-2.5" />
          </a>
        </div>
      </div>

      {toast && (
        <div className="ops-pill absolute bottom-20 left-1/2 -translate-x-1/2 z-30 px-4 py-1.5 text-zinc-100 text-xs font-mono">
          {toast}
        </div>
      )}

      <AddTargetModal />
      <FailureInjectionModal />
      <ShortcutsModal />
    </div>
  );
};
