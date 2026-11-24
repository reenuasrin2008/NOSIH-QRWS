import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Film,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  SkipForward,
  X,
} from "lucide-react";
import type { GlobalOverview } from "../shared/globalTypes";

interface CinematicAct {
  id: number;
  title: string;
  durationSec: number;
  caption: string;
}

interface KpiSnapshot {
  activeDisasters: number;
  deployedDrones: number;
  avgReadiness: number;
  worldVersion: number;
}

const ACTS: readonly CinematicAct[] = [
  {
    id: 1,
    title: "Continental Overview",
    durationSec: 8,
    caption: "7 nations · 98 drones · 1,000,000 residents — live digital twin online.",
  },
  {
    id: 2,
    title: "Cyclone Formation",
    durationSec: 15,
    caption: "Sir, a Category 4 cyclone is forming over Veridia Basin.",
  },
  {
    id: 3,
    title: "Autonomous Swarm Deployment",
    durationSec: 20,
    caption: "Deploying autonomous search swarm — flight corridors and recovery arcs locked.",
  },
  {
    id: 4,
    title: "Hospital Surge & Dispatch",
    durationSec: 15,
    caption: "Hospital surge detected — dispatching ambulances from nearest staging bays.",
  },
  {
    id: 5,
    title: "Cross-Border Mutual Aid",
    durationSec: 15,
    caption: "Mutual aid corridor authorized — transferring reserve fleet from Ferros to Veridia.",
  },
  {
    id: 6,
    title: "Continental Pull-Back",
    durationSec: 12,
    caption: "All corridors stabilized. Rescue complete, Sir.",
  },
  {
    id: 7,
    title: "Before / After KPI Ribbon",
    durationSec: 5,
    caption: "Mission telemetry verified — before & after continental KPI comparison.",
  },
] as const;

const TOTAL_DURATION_SEC = ACTS.reduce((acc, a) => acc + a.durationSec, 0);
const TICK_INTERVAL_MS = 100;

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

function formatClock(totalSeconds: number): string {
  const clamped = Math.max(0, Math.floor(totalSeconds));
  const mins = Math.floor(clamped / 60);
  const secs = clamped % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function extractKpiSnapshot(overview: GlobalOverview): KpiSnapshot {
  const countries = Array.isArray(overview.countries) ? overview.countries : [];
  const avgReadiness =
    countries.length > 0
      ? countries.reduce((sum, c) => sum + (Number(c.readiness_score) || 0), 0) / countries.length
      : 0;
  return {
    activeDisasters: overview.totals?.active_disasters ?? 0,
    deployedDrones: overview.totals?.drones_active ?? 0,
    avgReadiness: Number(avgReadiness.toFixed(1)),
    worldVersion: overview.clock?.world_version ?? 0,
  };
}

async function fetchJson<T>(
  url: string,
  init: RequestInit,
  signal: AbortSignal
): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
    signal,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status} on ${url}`);
  }
  return (await res.json()) as T;
}

async function callAiTool(
  toolName: string,
  args: Record<string, unknown>,
  signal: AbortSignal
): Promise<Record<string, unknown>> {
  const data = await fetchJson<Record<string, unknown>>(
    `/api/ai/tools/${toolName}`,
    { method: "POST", body: JSON.stringify(args) },
    signal
  );
  const resultObj =
    data.result && typeof data.result === "object"
      ? (data.result as Record<string, unknown>)
      : null;
  if (data.status === "ERROR" || resultObj?.status === "ERROR" || data.error) {
    const errMsg =
      (typeof data.error === "string" && data.error) ||
      (typeof resultObj?.error === "string" && resultObj.error) ||
      `Tool ${toolName} returned ERROR`;
    throw new Error(errMsg);
  }
  return data;
}

function extractApprovalId(payload: Record<string, unknown>): string | null {
  if (typeof payload.approval_id === "string" && payload.approval_id) {
    return payload.approval_id;
  }
  const resultObj =
    payload.result && typeof payload.result === "object"
      ? (payload.result as Record<string, unknown>)
      : null;
  if (resultObj && typeof resultObj.approval_id === "string" && resultObj.approval_id) {
    return resultObj.approval_id;
  }
  return null;
}

async function approveOperation(
  approvalId: string,
  signal: AbortSignal
): Promise<Record<string, unknown>> {
  return fetchJson<Record<string, unknown>>(
    `/api/approvals/${approvalId}/approve`,
    { method: "POST", body: JSON.stringify({ auto_execute: true }) },
    signal
  );
}

async function fetchWorldOverview(signal: AbortSignal): Promise<GlobalOverview> {
  return fetchJson<GlobalOverview>("/api/world/overview", { method: "GET" }, signal);
}

async function sendJarvisBrief(
  message: string,
  signal: AbortSignal
): Promise<Record<string, unknown>> {
  return fetchJson<Record<string, unknown>>(
    "/api/ai/chat",
    {
      method: "POST",
      body: JSON.stringify({ message, session_id: "cinematic-directors-cut" }),
    },
    signal
  );
}

export const CinematicDirector: React.FC = () => {
  const isQueryEnabled = useMemo(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("cinematic") === "1";
  }, []);

  const [exited, setExited] = useState(false);
  const [actIndex, setActIndex] = useState(0);
  const [runEpoch, setRunEpoch] = useState(0);
  const [paused, setPaused] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [actElapsedMs, setActElapsedMs] = useState(0);
  const [busy, setBusy] = useState(false);
  const [actionStatus, setActionStatus] = useState<string>("Initializing cinematic telemetry...");
  const [inlineError, setInlineError] = useState<string | null>(null);
  const [beforeKpis, setBeforeKpis] = useState<KpiSnapshot | null>(null);
  const [afterKpis, setAfterKpis] = useState<KpiSnapshot | null>(null);

  const isMountedRef = useRef(true);
  const activeAbortRef = useRef<AbortController | null>(null);
  const actElapsedRef = useRef(0);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      activeAbortRef.current?.abort();
      activeAbortRef.current = null;
    };
  }, []);

  const currentAct = ACTS[actIndex] ?? ACTS[0];
  const isActive = isQueryEnabled && !exited;

  // Act execution effect with dedicated AbortController per act / restart
  useEffect(() => {
    if (!isActive) return;

    activeAbortRef.current?.abort();
    const ac = new AbortController();
    activeAbortRef.current = ac;
    const { signal } = ac;

    const executeAct = async () => {
      if (!isMountedRef.current) return;
      setBusy(true);
      setInlineError(null);

      try {
        switch (actIndex) {
          case 0: {
            setActionStatus("Capturing baseline KPIs & framing global overview...");
            const [overview] = await Promise.all([
              fetchWorldOverview(signal),
              callAiTool("view_global_world", {}, signal),
            ]);
            if (!isMountedRef.current || signal.aborted) return;
            setBeforeKpis(extractKpiSnapshot(overview));
            setActionStatus("view_global_world ✓ · baseline snapshot locked");
            break;
          }

          case 1: {
            setActionStatus("Focusing Veridia Basin (COUNTRY-03) & staging Category 4 cyclone...");
            await callAiTool("view_country", { country_id: "COUNTRY-03" }, signal);
            const prep = await callAiTool(
              "prepare_disaster_event",
              {
                country_id: "COUNTRY-03",
                disaster_type: "CYCLONE",
                severity: 0.88,
                radius_km: 14.0,
              },
              signal
            );
            const approvalId = extractApprovalId(prep);
            if (!approvalId) {
              throw new Error("Cyclone staging did not return an approval_id.");
            }
            if (!isMountedRef.current || signal.aborted) return;
            setActionStatus(`Approving ${approvalId} (Category 4 Cyclone · COUNTRY-03)...`);
            await approveOperation(approvalId, signal);
            if (!isMountedRef.current || signal.aborted) return;
            setActionStatus(`Cyclone live (${approvalId}) · J.A.R.V.I.S. threat brief running...`);
            await sendJarvisBrief(
              "Analyze the Category 4 cyclone impact in Country 3",
              signal
            );
            if (!isMountedRef.current || signal.aborted) return;
            setActionStatus(`Cyclone active (${approvalId}) · JARVIS threat brief ✓`);
            break;
          }

          case 2: {
            setActionStatus("Staging 8-drone SURVIVOR_SEARCH swarm for COUNTRY-03...");
            const prep = await callAiTool(
              "prepare_swarm_operation",
              {
                country_id: "COUNTRY-03",
                mode: "SURVIVOR_SEARCH",
                drone_count: 8,
                formation: "SEARCH_GRID",
              },
              signal
            );
            const approvalId = extractApprovalId(prep);
            if (!approvalId) {
              throw new Error("Swarm staging did not return an approval_id.");
            }
            if (!isMountedRef.current || signal.aborted) return;
            setActionStatus(`Approving swarm deployment ${approvalId}...`);
            await approveOperation(approvalId, signal);
            if (!isMountedRef.current || signal.aborted) return;
            setActionStatus(`8-drone SURVIVOR_SEARCH swarm deployed (${approvalId}) ✓`);
            break;
          }

          case 3: {
            setActionStatus("Checking Veridia hospital surge & staging ambulance dispatch...");
            const [hospStatus, ambPrep] = await Promise.all([
              callAiTool("get_hospital_status", { country_id: "COUNTRY-03" }, signal),
              callAiTool(
                "prepare_ambulance_dispatch",
                { country_id: "COUNTRY-03", count: 6 },
                signal
              ),
            ]);
            const approvalId = extractApprovalId(ambPrep);
            if (!approvalId) {
              throw new Error("Ambulance dispatch did not return an approval_id.");
            }
            if (!isMountedRef.current || signal.aborted) return;
            setActionStatus(`Approving ambulance dispatch ${approvalId}...`);
            await approveOperation(approvalId, signal);
            const hospResult =
              hospStatus.result && typeof hospStatus.result === "object"
                ? (hospStatus.result as Record<string, unknown>)
                : null;
            const totalHosps =
              typeof hospResult?.total_hospitals === "number"
                ? hospResult.total_hospitals
                : null;
            if (!isMountedRef.current || signal.aborted) return;
            setActionStatus(
              totalHosps !== null
                ? `${totalHosps} hospitals scanned · 6 ambulances dispatched (${approvalId}) ✓`
                : `Hospital surge checked · 6 ambulances dispatched (${approvalId}) ✓`
            );
            break;
          }

          case 4: {
            setActionStatus("Authorizing mutual aid corridor Ferros (COUNTRY-04) → Veridia (COUNTRY-03)...");
            const prep = await callAiTool(
              "prepare_cross_country_aid",
              {
                country_id: "COUNTRY-03",
                donor_country_id: "COUNTRY-04",
                resource_type: "ambulances",
                quantity: 6,
              },
              signal
            );
            const approvalId = extractApprovalId(prep);
            if (!approvalId) {
              throw new Error("Mutual aid proposal did not return an approval_id.");
            }
            if (!isMountedRef.current || signal.aborted) return;
            setActionStatus(`Approving mutual aid transfer ${approvalId}...`);
            await approveOperation(approvalId, signal);
            if (!isMountedRef.current || signal.aborted) return;
            setActionStatus(`Mutual aid transfer COUNTRY-04 → COUNTRY-03 approved (${approvalId}) ✓`);
            break;
          }

          case 5: {
            setActionStatus("Returning camera to continental overview...");
            await Promise.all([
              callAiTool("view_global_world", {}, signal),
              sendJarvisBrief(
                "Summarize continental stabilization status across all 7 nations.",
                signal
              ),
            ]);
            if (!isMountedRef.current || signal.aborted) return;
            setActionStatus("view_global_world ✓ · all corridors stabilized");
            break;
          }

          case 6: {
            setActionStatus("Fetching final /api/world/overview for before/after KPI ribbon...");
            const overview = await fetchWorldOverview(signal);
            if (!isMountedRef.current || signal.aborted) return;
            setAfterKpis(extractKpiSnapshot(overview));
            setActionStatus("Before / After KPI telemetry synchronized ✓");
            break;
          }

          default:
            break;
        }
      } catch (err: unknown) {
        if (isAbortError(err) || signal.aborted || !isMountedRef.current) return;
        const msg = err instanceof Error ? err.message : "Act execution failed.";
        setInlineError(`Act ${actIndex + 1}: ${msg}`);
        setActionStatus("Act encountered an API error — use Skip or Restart to continue.");
      } finally {
        if (isMountedRef.current && !signal.aborted) {
          setBusy(false);
        }
      }
    };

    void executeAct();

    return () => {
      ac.abort();
    };
  }, [isActive, actIndex, runEpoch]);

  // Smooth act countdown timer (StrictMode-safe: no nested setState inside updater)
  useEffect(() => {
    if (!isActive || paused || completed) return;

    const durationMs = currentAct.durationSec * 1000;
    const timer = window.setInterval(() => {
      const next = actElapsedRef.current + TICK_INTERVAL_MS;
      if (next >= durationMs) {
        if (actIndex < ACTS.length - 1) {
          actElapsedRef.current = 0;
          setActElapsedMs(0);
          setActIndex((idx) => idx + 1);
        } else {
          actElapsedRef.current = durationMs;
          setActElapsedMs(durationMs);
          setCompleted(true);
        }
      } else {
        actElapsedRef.current = next;
        setActElapsedMs(next);
      }
    }, TICK_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [isActive, paused, completed, actIndex, currentAct.durationSec]);

  const handleTogglePause = useCallback(() => {
    if (completed) return;
    setPaused((p) => !p);
  }, [completed]);

  const handleSkipNext = useCallback(() => {
    if (actIndex < ACTS.length - 1) {
      actElapsedRef.current = 0;
      setActIndex((idx) => idx + 1);
      setActElapsedMs(0);
      setInlineError(null);
    } else {
      const dur = currentAct.durationSec * 1000;
      actElapsedRef.current = dur;
      setCompleted(true);
      setActElapsedMs(dur);
    }
  }, [actIndex, currentAct.durationSec]);

  const handleRestart = useCallback(() => {
    activeAbortRef.current?.abort();
    actElapsedRef.current = 0;
    setActIndex(0);
    setActElapsedMs(0);
    setPaused(false);
    setCompleted(false);
    setInlineError(null);
    setBeforeKpis(null);
    setAfterKpis(null);
    setActionStatus("Restarting 90-second Director's Cut...");
    setRunEpoch((e) => e + 1);
  }, []);

  const handleExit = useCallback(() => {
    activeAbortRef.current?.abort();
    setExited(true);
  }, []);

  if (!isActive) return null;

  const priorElapsedSec = ACTS.slice(0, actIndex).reduce((sum, a) => sum + a.durationSec, 0);
  const totalElapsedSec = Math.min(
    TOTAL_DURATION_SEC,
    priorElapsedSec + actElapsedMs / 1000
  );
  const actProgressPct = Math.min(
    100,
    (actElapsedMs / Math.max(1, currentAct.durationSec * 1000)) * 100
  );

  const showKpiRibbon = actIndex === ACTS.length - 1 || completed;

  return (
    <div
      className="fixed inset-0 z-[70] pointer-events-none flex flex-col justify-between font-sans select-none"
      role="region"
      aria-label="Cinematic Director's Cut Overlay"
    >
      {/* Top Letterbox HUD Bar */}
      <div className="pointer-events-auto w-full bg-[#050505]/92 backdrop-blur-xl border-b border-white/15 px-4 py-2.5 shadow-2xl">
        <div className="max-w-6xl mx-auto space-y-2">
          {/* Top Row: Act Title + Timer + Controls */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2.5 min-w-0">
              <span className="px-2 py-0.5 rounded bg-[#FAFAFA] text-[#050505] text-[10px] font-mono font-bold tracking-widest uppercase flex items-center gap-1 shrink-0">
                <Film className="w-3 h-3" />
                DIRECTOR&apos;S CUT
              </span>
              <span className="text-xs font-mono text-[#A1A1AA] shrink-0">
                ACT {currentAct.id}/{ACTS.length}
              </span>
              <span className="text-xs sm:text-sm font-semibold tracking-wide text-[#FAFAFA] truncate">
                {currentAct.title}
              </span>
              {busy && <Loader2 className="w-3.5 h-3.5 animate-spin text-[#A1A1AA] shrink-0" />}
              {completed && (
                <span className="px-2 py-0.5 rounded bg-[#16181C] border border-white/25 text-[10px] font-mono text-[#FAFAFA] flex items-center gap-1 shrink-0">
                  <CheckCircle2 className="w-3 h-3" /> COMPLETE
                </span>
              )}
            </div>

            <div className="flex items-center gap-1.5 text-[11px] font-mono">
              <span className="px-2 py-1 rounded bg-[#0F1012] border border-[#2A2D34] text-[#E4E4E7] tabular-nums">
                {formatClock(totalElapsedSec)} / {formatClock(TOTAL_DURATION_SEC)}
              </span>

              <button
                onClick={handleTogglePause}
                disabled={completed}
                className="px-2.5 py-1 rounded bg-[#16181C] hover:bg-[#23262C] disabled:opacity-40 border border-[#2A2D34] text-[#FAFAFA] flex items-center gap-1 transition-colors"
                title={paused ? "Resume playback" : "Pause playback"}
              >
                {paused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
                <span className="hidden sm:inline">{paused ? "Resume" : "Pause"}</span>
              </button>

              <button
                onClick={handleSkipNext}
                disabled={completed}
                className="px-2.5 py-1 rounded bg-[#16181C] hover:bg-[#23262C] disabled:opacity-40 border border-[#2A2D34] text-[#FAFAFA] flex items-center gap-1 transition-colors"
                title="Skip to next act"
              >
                <SkipForward className="w-3 h-3" />
                <span className="hidden sm:inline">Next Act</span>
              </button>

              <button
                onClick={handleRestart}
                className="px-2.5 py-1 rounded bg-[#16181C] hover:bg-[#23262C] border border-[#2A2D34] text-[#FAFAFA] flex items-center gap-1 transition-colors"
                title="Restart 90-second sequence"
              >
                <RotateCcw className="w-3 h-3" />
                <span className="hidden sm:inline">Restart</span>
              </button>

              <button
                onClick={handleExit}
                className="px-2.5 py-1 rounded bg-[#0F1012] hover:bg-[#FAFAFA] hover:text-[#050505] border border-[#2A2D34] text-[#A1A1AA] flex items-center gap-1 transition-colors"
                title="Exit cinematic mode"
              >
                <X className="w-3 h-3" />
                <span className="hidden sm:inline">Exit</span>
              </button>
            </div>
          </div>

          {/* 7-Act Segmented Progress Bar */}
          <div className="grid grid-cols-7 gap-1.5" aria-label="Act progress">
            {ACTS.map((act, idx) => {
              const fillPct =
                idx < actIndex || completed
                  ? 100
                  : idx === actIndex
                  ? actProgressPct
                  : 0;
              return (
                <div key={act.id} className="space-y-1">
                  <div className="h-1 w-full rounded-full bg-[#1E2026] overflow-hidden">
                    <div
                      className="h-full bg-[#FAFAFA] transition-[width] duration-100 ease-linear"
                      style={{ width: `${fillPct}%` }}
                    />
                  </div>
                  <div
                    className={`text-[9px] font-mono truncate ${
                      idx === actIndex
                        ? "text-[#FAFAFA] font-semibold"
                        : idx < actIndex
                        ? "text-[#A1A1AA]"
                        : "text-[#52525B]"
                    }`}
                  >
                    {act.id}. {act.title}
                  </div>
                </div>
              );
            })}
          </div>

          {inlineError && (
            <div
              role="alert"
              className="px-2.5 py-1 rounded bg-[#16181C] border border-white/25 text-[11px] font-mono text-[#E4E4E7] flex items-center justify-between gap-2"
            >
              <span className="flex items-center gap-1.5 truncate">
                <AlertTriangle className="w-3.5 h-3.5 text-[#FAFAFA] shrink-0" />
                <span className="truncate">{inlineError}</span>
              </span>
              <button
                onClick={() => setInlineError(null)}
                className="text-[#A1A1AA] hover:text-[#FAFAFA] shrink-0"
                aria-label="Dismiss error"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Letterbox Area: Optional Before/After KPI Ribbon + Stark Narrator Subtitle Bar */}
      <div className="pointer-events-auto w-full flex flex-col items-center">
        {showKpiRibbon && (
          <div className="w-full max-w-5xl mx-auto px-4 pb-3">
            <div className="rounded-xl bg-[#0B0C0E]/95 backdrop-blur-xl border border-white/20 shadow-2xl px-4 py-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono tracking-[0.18em] uppercase text-[#A1A1AA]">
                  BEFORE / AFTER CONTINENTAL KPI RIBBON
                </span>
                <span className="text-[10px] font-mono text-[#71717A]">
                  LIVE /api/world/overview
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 font-mono">
                <div className="p-2.5 rounded-lg bg-[#050505] border border-[#2A2D34]">
                  <div className="text-[10px] text-[#A1A1AA] uppercase">Active Disasters</div>
                  <div className="mt-1 text-sm text-[#FAFAFA] font-semibold">
                    {beforeKpis ? beforeKpis.activeDisasters : "—"}
                    <span className="mx-1.5 text-[#71717A]">→</span>
                    {afterKpis ? afterKpis.activeDisasters : "…"}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-[#050505] border border-[#2A2D34]">
                  <div className="text-[10px] text-[#A1A1AA] uppercase">Deployed Drones</div>
                  <div className="mt-1 text-sm text-[#FAFAFA] font-semibold">
                    {beforeKpis ? beforeKpis.deployedDrones : "—"}
                    <span className="mx-1.5 text-[#71717A]">→</span>
                    {afterKpis ? afterKpis.deployedDrones : "…"}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-[#050505] border border-[#2A2D34]">
                  <div className="text-[10px] text-[#A1A1AA] uppercase">Avg Readiness</div>
                  <div className="mt-1 text-sm text-[#FAFAFA] font-semibold">
                    {beforeKpis ? `${beforeKpis.avgReadiness.toFixed(1)}%` : "—"}
                    <span className="mx-1.5 text-[#71717A]">→</span>
                    {afterKpis ? `${afterKpis.avgReadiness.toFixed(1)}%` : "…"}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-[#050505] border border-[#2A2D34]">
                  <div className="text-[10px] text-[#A1A1AA] uppercase">World Version</div>
                  <div className="mt-1 text-sm text-[#FAFAFA] font-semibold">
                    {beforeKpis ? `v${beforeKpis.worldVersion}` : "—"}
                    <span className="mx-1.5 text-[#71717A]">→</span>
                    {afterKpis ? `v${afterKpis.worldVersion}` : "…"}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Stark-Style Narrator Subtitle Bar */}
        <div className="w-full bg-[#050505]/92 backdrop-blur-xl border-t border-white/15 px-4 py-3 shadow-2xl">
          <div className="max-w-4xl mx-auto text-center space-y-1">
            <p className="text-sm sm:text-base font-medium tracking-wide text-[#FAFAFA]">
              &ldquo;{currentAct.caption}&rdquo;
            </p>
            <div className="text-[10px] font-mono text-[#A1A1AA] tracking-wider uppercase truncate">
              {paused ? "PAUSED · " : ""}
              {actionStatus}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
