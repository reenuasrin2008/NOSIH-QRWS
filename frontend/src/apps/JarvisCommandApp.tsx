import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Cpu,
  Edit3,
  LayoutPanelLeft,
  Map as MapIcon,
  Maximize2,
  Mic,
  MicOff,
  Radio,
  Search,
  Send,
  ShieldAlert,
  Sliders,
  Sparkles,
  Square,
  Terminal,
  Volume2,
  VolumeX,
  Wrench,
  X,
} from "lucide-react";
import { TacticalFlatWorldMap } from "../components/map/TacticalFlatWorldMap";
import { JarvisNeuralCore3D } from "../components/jarvis/JarvisNeuralCore3D";
import { connectGlobalWebSocket, globalApi } from "../shared/globalApi";
import type {
  ApprovalItem,
  GlobalOverview,
  JarvisReply,
  ProviderStatusPayload,
} from "../shared/globalTypes";

const QUICK_COMMANDS = [
  "Analyze the situation in Country 3",
  "View Country 1 and find the best drones to reach the hospital",
  "Prepare a complete rescue plan for Country 3",
  "Can another country provide additional ambulances?",
  "Compare conventional vs hybrid counterfactual worlds",
  "Prepare an 8-drone medical delivery swarm in grid formation",
];

type DockTab = "logs" | "command" | "tools" | "approvals" | "voice" | null;

interface HealthInvariants {
  approvalGated: boolean;
  zeroDatabase: boolean;
  toolCount: number | null;
}

interface LatencyStats {
  count: number;
  p50Ms: number;
  p95Ms: number;
  p99Ms: number;
}

const WAVEFORM_BAR_COUNT = 28;

function formatFrontendCommandChip(cmd: Record<string, any>): string {
  const action = cmd.action || cmd.command || cmd.type || "ui.command";
  const target =
    cmd.target_id ||
    cmd.country_id ||
    cmd.parameters?.country_id ||
    cmd.parameters?.target_id ||
    cmd.parameters?.drone_id ||
    cmd.parameters?.hospital_id ||
    "";
  return target ? `${action} → ${target} ✓` : `${action} ✓`;
}

export const JarvisCommandApp: React.FC = () => {
  const [overview, setOverview] = useState<GlobalOverview | null>(null);
  const [providers, setProviders] = useState<ProviderStatusPayload | null>(null);
  const [allDrones, setAllDrones] = useState<any[]>([]);
  const [allHospitals, setAllHospitals] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [toolLogs, setToolLogs] = useState<any[]>([]);
  const [availableTools, setAvailableTools] = useState<string[]>([]);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [messages, setMessages] = useState<JarvisReply[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedCountryId, setSelectedCountryId] = useState("COUNTRY-03");
  const [candidateRoutes, setCandidateRoutes] = useState<any[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [healthInvariants, setHealthInvariants] = useState<HealthInvariants>({
    approvalGated: true,
    zeroDatabase: true,
    toolCount: null,
  });
  const [latencyStats, setLatencyStats] = useState<LatencyStats>({
    count: 0,
    p50Ms: 0,
    p95Ms: 0,
    p99Ms: 0,
  });

  // Full-Screen 3D Core vs Split Core + Flat Tactical Map
  const [stageMode, setStageMode] = useState<"fullscreen" | "split">("fullscreen");
  // Bottom Pop-Up Dock Drawer
  const [activeDock, setActiveDock] = useState<DockTab>(null);

  // Voice & Web Audio API state
  const [voiceMode, setVoiceMode] = useState<"ptt" | "continuous" | "text">("ptt");
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(true);
  const [voiceRate, setVoiceRate] = useState(1.04);
  const [voiceVolume, setVoiceVolume] = useState(1.0);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoiceName, setSelectedVoiceName] = useState("");
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const [waveformBars, setWaveformBars] = useState<number[]>(
    () => Array.from({ length: WAVEFORM_BAR_COUNT }, () => 0.14)
  );

  // Inline reply interactions: Explain, Modify Approval, Decision status
  const [expandedExplainIds, setExpandedExplainIds] = useState<Record<string, boolean>>({});
  const [explainingId, setExplainingId] = useState<string | null>(null);
  const [editingApprovalId, setEditingApprovalId] = useState<string | null>(null);
  const [modifyDraftJson, setModifyDraftJson] = useState("");
  const [modifyError, setModifyError] = useState<string | null>(null);
  const [approvalStatusMap, setApprovalStatusMap] = useState<Record<string, string>>({});

  // Drawer-local filters
  const [logFilter, setLogFilter] = useState<string>("all");
  const [logQuery, setLogQuery] = useState("");
  const [expandedLogIdx, setExpandedLogIdx] = useState<number | null>(null);
  const [toolSearch, setToolSearch] = useState("");
  const [toolRunResult, setToolRunResult] = useState<{
    tool: string;
    duration_ms?: number;
    output: any;
  } | null>(null);
  const [runningTool, setRunningTool] = useState<string | null>(null);

  const recognitionRef = useRef<any>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const speakWaveRafRef = useRef<number | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const isMountedRef = useRef(true);
  const micSessionIdRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const telemetryAbortRef = useRef<AbortController | null>(null);
  const voiceModeRef = useRef(voiceMode);
  voiceModeRef.current = voiceMode;

  const cleanupAudioPipeline = () => {
    micSessionIdRef.current += 1;
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((tr) => tr.stop());
      micStreamRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    if (isMountedRef.current) {
      setAudioLevel(0);
      setWaveformBars(Array.from({ length: WAVEFORM_BAR_COUNT }, () => 0.14));
    }
  };

  const refreshMeta = () => {
    const signal = abortControllerRef.current?.signal;
    globalApi.getOverview().then((d) => { if (isMountedRef.current) setOverview(d); }).catch(() => {});
    globalApi.getProvidersStatus().then((d) => { if (isMountedRef.current) setProviders(d); }).catch(() => {});
    globalApi.getGlobalDrones().then((r) => { if (isMountedRef.current) setAllDrones(r.drones); }).catch(() => {});
    fetch("/api/hospitals", { signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { if (isMountedRef.current) setAllHospitals(d.hospitals || []); })
      .catch(() => {});
    globalApi.getEvents(50).then((r) => { if (isMountedRef.current) setEvents(r.events); }).catch(() => {});
    globalApi.getAuditLogs().then((r) => { if (isMountedRef.current) setToolLogs(r.tool_logs || []); }).catch(() => {});
    globalApi.getApprovals().then((r) => { if (isMountedRef.current) setApprovals(r.approvals || []); }).catch(() => {});
  };

  const pollHealthAndLatency = () => {
    telemetryAbortRef.current?.abort();
    const ac = new AbortController();
    telemetryAbortRef.current = ac;
    const { signal } = ac;

    fetch("/api/health", { signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: Record<string, any>) => {
        if (!isMountedRef.current || signal.aborted) return;
        const inv = d?.invariants && typeof d.invariants === "object" ? d.invariants : {};
        const rawTools = d?.tool_count ?? d?.tools_count ?? inv?.tool_count ?? null;
        setHealthInvariants({
          approvalGated: Boolean(inv?.approval_gated ?? d?.approval_gated ?? true),
          zeroDatabase: Boolean(inv?.zero_database ?? d?.zero_database ?? true),
          toolCount: typeof rawTools === "number" && Number.isFinite(rawTools) ? rawTools : null,
        });
      })
      .catch(() => {});

    fetch("/api/ai/latency", { signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: Record<string, any>) => {
        if (!isMountedRef.current || signal.aborted) return;
        const rawCount = Number(d?.count ?? d?.sample_count ?? d?.samples ?? d?.total ?? 0);
        const count = Number.isFinite(rawCount) && rawCount > 0 ? Math.floor(rawCount) : 0;
        const p50 = Number(d?.p50_ms ?? d?.p50 ?? 0);
        const p95 = Number(d?.p95_ms ?? d?.p95 ?? 0);
        const p99 = Number(d?.p99_ms ?? d?.p99 ?? 0);
        setLatencyStats({
          count,
          p50Ms: Number.isFinite(p50) ? Math.round(p50) : 0,
          p95Ms: Number.isFinite(p95) ? Math.round(p95) : 0,
          p99Ms: Number.isFinite(p99) ? Math.round(p99) : 0,
        });
      })
      .catch(() => {});
  };

  useEffect(() => {
    isMountedRef.current = true;
    const ac = new AbortController();
    abortControllerRef.current = ac;

    refreshMeta();
    pollHealthAndLatency();
    fetch("/api/ai/tools", { signal: ac.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { if (isMountedRef.current) setAvailableTools(Object.keys(d.tools || {})); })
      .catch(() => {});

    let loadVoices: (() => void) | null = null;
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      loadVoices = () => {
        if (!isMountedRef.current) return;
        const list = window.speechSynthesis.getVoices();
        setVoices(list);
        if (list.length > 0 && !selectedVoiceName) {
          const eng = list.find((v) => v.lang.startsWith("en")) || list[0];
          setSelectedVoiceName(eng.name);
        }
      };
      loadVoices();
      window.speechSynthesis.onvoiceschanged = loadVoices;
    }

    const disconnect = connectGlobalWebSocket("quantum-jarvis", {
      onConnectionChange: (c) => { if (isMountedRef.current) setWsConnected(c); },
      onSnapshot: (snap) => {
        if (!isMountedRef.current) return;
        if (snap.overview) setOverview(snap.overview);
        if (snap.providers) setProviders(snap.providers);
      },
      onWorldEvent: () => refreshMeta(),
    });

    return () => {
      isMountedRef.current = false;
      ac.abort();
      abortControllerRef.current = null;
      telemetryAbortRef.current?.abort();
      telemetryAbortRef.current = null;
      disconnect();
      if (recognitionRef.current) {
        try {
          recognitionRef.current.onresult = null;
          recognitionRef.current.onerror = null;
          recognitionRef.current.onend = null;
          recognitionRef.current.abort?.();
        } catch {
          // ignore already-stopped recognition
        }
        recognitionRef.current = null;
      }
      cleanupAudioPipeline();
      if (speakWaveRafRef.current !== null) {
        cancelAnimationFrame(speakWaveRafRef.current);
        speakWaveRafRef.current = null;
      }
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        if (window.speechSynthesis.onvoiceschanged === loadVoices) {
          window.speechSynthesis.onvoiceschanged = null;
        }
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  // Animate clean silver waveform cadence while JARVIS is speaking (and not listening)
  useEffect(() => {
    if (speaking && !listening) {
      const start = performance.now();
      const step = (now: number) => {
        const t = (now - start) / 1000;
        const bars = Array.from({ length: WAVEFORM_BAR_COUNT }, (_, i) => {
          const centerWeight = 1 - Math.abs(i - WAVEFORM_BAR_COUNT / 2) / (WAVEFORM_BAR_COUNT / 2);
          const wave =
            0.22 +
            (0.35 + centerWeight * 0.4) *
              Math.abs(Math.sin(t * 7.2 + i * 0.45) * Math.cos(t * 3.1 - i * 0.22));
          return Math.min(1, Math.max(0.14, wave));
        });
        setWaveformBars(bars);
        setAudioLevel(0.45 + Math.abs(Math.sin(t * 6.5)) * 0.35);
        speakWaveRafRef.current = requestAnimationFrame(step);
      };
      speakWaveRafRef.current = requestAnimationFrame(step);
      return () => {
        if (speakWaveRafRef.current !== null) {
          cancelAnimationFrame(speakWaveRafRef.current);
          speakWaveRafRef.current = null;
        }
      };
    } else if (!listening) {
      setWaveformBars(Array.from({ length: WAVEFORM_BAR_COUNT }, () => 0.14));
      setAudioLevel(0);
    }
  }, [speaking, listening]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const stopSpeaking = () => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    setSpeaking(false);
  };

  const speakText = (text: string) => {
    if (
      !autoSpeak ||
      voiceMode === "text" ||
      typeof window === "undefined" ||
      !("speechSynthesis" in window)
    ) {
      return;
    }
    stopSpeaking();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = voiceRate;
    u.volume = voiceVolume;
    const chosen = voices.find((v) => v.name === selectedVoiceName);
    if (chosen) u.voice = chosen;
    u.onstart = () => setSpeaking(true);
    u.onend = () => {
      if (!isMountedRef.current) return;
      setSpeaking(false);
      if (voiceModeRef.current === "continuous") startVoiceRecognition();
    };
    u.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(u);
  };

  const sendCommand = async (cmdText?: string) => {
    const query = (cmdText ?? input).trim();
    if (!query || loading) return;
    stopSpeaking();
    setInput("");
    setLoading(true);
    setActiveDock("command");
    try {
      const reply = await globalApi.jarvisChat(query, "command-session-1");
      setMessages((prev) => [...prev, reply]);
      if (reply.context?.active_country_id) {
        setSelectedCountryId(reply.context.active_country_id);
      }
      const routeCard = reply.structured_cards.find((c) => c.type === "route_comparison");
      if (routeCard?.data?.all_candidate_routes) {
        setCandidateRoutes(routeCard.data.all_candidate_routes);
      }
      speakText(reply.spoken_summary);
      refreshMeta();
      pollHealthAndLatency();
    } catch (err: any) {
      setVoiceNotice(err?.message || "Command dispatch failed.");
    } finally {
      setLoading(false);
    }
  };

  const hasExternalLlmKeys = useMemo(() => {
    if (!providers?.providers) return false;
    return Object.values(providers.providers).some((p) => (p?.active_keys ?? 0) > 0);
  }, [providers]);

  const handleExplainReply = async (reply: JarvisReply) => {
    const isAlreadyExpanded = !!expandedExplainIds[reply.reply_id];
    if (!hasExternalLlmKeys) {
      setExpandedExplainIds((prev) => ({ ...prev, [reply.reply_id]: !isAlreadyExpanded }));
      return;
    }

    setExplainingId(reply.reply_id);
    try {
      const res = await fetch("/api/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: reply.user_message,
          session_id: reply.session_id || "command-session-1",
          use_llm_polish: true,
        }),
      });
      if (res.ok) {
        const polished: JarvisReply = await res.json();
        setMessages((prev) =>
          prev.map((m) =>
            m.reply_id === reply.reply_id
              ? {
                  ...m,
                  assistant_message: polished.assistant_message || m.assistant_message,
                  provider: polished.provider || m.provider,
                  model: polished.model || m.model,
                  latency_ms: polished.latency_ms ?? m.latency_ms,
                  structured_cards:
                    polished.structured_cards?.length > 0
                      ? polished.structured_cards
                      : m.structured_cards,
                  execution_trace:
                    polished.execution_trace?.length > 0
                      ? polished.execution_trace
                      : m.execution_trace,
                }
              : m
          )
        );
      }
      setExpandedExplainIds((prev) => ({ ...prev, [reply.reply_id]: true }));
      pollHealthAndLatency();
    } catch {
      setExpandedExplainIds((prev) => ({ ...prev, [reply.reply_id]: !isAlreadyExpanded }));
    } finally {
      setExplainingId(null);
    }
  };

  const startVoiceRecognition = () => {
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec) {
      setVoiceNotice(
        "Browser speech recognition unavailable; type commands or use Chrome/Edge for live mic."
      );
      return;
    }
    setVoiceNotice(null);
    stopSpeaking();
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort?.();
      } catch {
        // ignore prior recognition state
      }
      recognitionRef.current = null;
    }
    cleanupAudioPipeline();
    const sessionId = micSessionIdRef.current;

    const rec = new SpeechRec();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.onstart = () => {
      if (!isMountedRef.current || micSessionIdRef.current !== sessionId) return;
      setListening(true);
      if (navigator.mediaDevices?.getUserMedia) {
        navigator.mediaDevices
          .getUserMedia({ audio: true })
          .then((stream) => {
            if (!isMountedRef.current || micSessionIdRef.current !== sessionId) {
              stream.getTracks().forEach((tr) => tr.stop());
              return;
            }
            micStreamRef.current = stream;
            const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
            const ctx = new AudioCtx();
            audioCtxRef.current = ctx;
            const src = ctx.createMediaStreamSource(stream);
            const analyser = ctx.createAnalyser();
            analyser.fftSize = 128;
            analyser.smoothingTimeConstant = 0.78;
            src.connect(analyser);
            const data = new Uint8Array(analyser.frequencyBinCount);
            const tick = () => {
              if (!isMountedRef.current || micSessionIdRef.current !== sessionId) return;
              analyser.getByteFrequencyData(data);
              const avg = data.reduce((a, b) => a + b, 0) / Math.max(1, data.length);
              setAudioLevel(Math.min(1, avg / 95));
              const step = Math.max(1, Math.floor(data.length / WAVEFORM_BAR_COUNT));
              const bars: number[] = [];
              for (let i = 0; i < WAVEFORM_BAR_COUNT; i++) {
                const v = data[Math.min(data.length - 1, i * step)] / 255;
                bars.push(Math.max(0.14, Math.min(1, v * 1.35)));
              }
              setWaveformBars(bars);
              rafRef.current = requestAnimationFrame(tick);
            };
            tick();
          })
          .catch(() => {});
      }
    };
    rec.onresult = (ev: any) => {
      if (!isMountedRef.current) return;
      const transcript = ev.results?.[0]?.[0]?.transcript;
      if (transcript) sendCommand(transcript);
    };
    rec.onerror = (ev: any) => {
      if (!isMountedRef.current) return;
      setListening(false);
      cleanupAudioPipeline();
      setVoiceNotice(`Voice input status: ${ev.error}`);
    };
    rec.onend = () => {
      if (!isMountedRef.current) return;
      setListening(false);
      cleanupAudioPipeline();
    };
    recognitionRef.current = rec;
    try {
      rec.start();
    } catch (err: any) {
      setListening(false);
      cleanupAudioPipeline();
      setVoiceNotice(err?.message || "Unable to start speech recognition.");
    }
  };

  const toggleVoiceInput = () => {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      cleanupAudioPipeline();
      return;
    }
    startVoiceRecognition();
  };

  const handleApproval = async (approvalId: string, approve: boolean) => {
    try {
      if (approve) {
        await globalApi.approveOperation(approvalId, true);
        setApprovalStatusMap((prev) => ({ ...prev, [approvalId]: "EXECUTED" }));
        speakText(`Operation ${approvalId} approved and executed.`);
      } else {
        await globalApi.rejectOperation(approvalId);
        setApprovalStatusMap((prev) => ({ ...prev, [approvalId]: "REJECTED" }));
        speakText(`Operation ${approvalId} rejected.`);
      }
      if (editingApprovalId === approvalId) {
        setEditingApprovalId(null);
      }
      refreshMeta();
    } catch (err: any) {
      setVoiceNotice(err?.message || `Failed to update approval ${approvalId}`);
    }
  };

  const openModifyApproval = (approval: ApprovalItem) => {
    if (editingApprovalId === approval.approval_id) {
      setEditingApprovalId(null);
      setModifyError(null);
      return;
    }
    setEditingApprovalId(approval.approval_id);
    setModifyDraftJson(JSON.stringify(approval.parameters || {}, null, 2));
    setModifyError(null);
  };

  const submitModifyApproval = async (approvalId: string) => {
    try {
      const parsed = JSON.parse(modifyDraftJson);
      const res = await fetch(`/api/approvals/${approvalId}/modify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates: parsed }),
      });
      if (!res.ok) {
        throw new Error((await res.text()) || `HTTP ${res.status}`);
      }
      const updated: ApprovalItem = await res.json();
      setMessages((prev) =>
        prev.map((m) =>
          m.pending_approval?.approval_id === approvalId
            ? { ...m, pending_approval: updated }
            : m
        )
      );
      setApprovalStatusMap((prev) => ({ ...prev, [approvalId]: "MODIFIED" }));
      setEditingApprovalId(null);
      setModifyError(null);
      refreshMeta();
    } catch (err: any) {
      setModifyError(err?.message || "Invalid JSON parameters");
    }
  };

  const runDirectTool = async (toolName: string) => {
    setRunningTool(toolName);
    try {
      const res = await fetch(`/api/ai/tools/${toolName}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country_id: selectedCountryId }),
        signal: abortControllerRef.current?.signal,
      });
      const rawText = await res.text();
      let data: any = null;
      try {
        data = rawText ? JSON.parse(rawText) : {};
      } catch {
        data = { error: rawText || `HTTP ${res.status}` };
      }
      if (!res.ok) {
        setToolRunResult({
          tool: toolName,
          duration_ms: data?.duration_ms,
          output: { error: data?.error || data?.detail || `HTTP ${res.status}`, ...(typeof data === "object" ? data : {}) },
        });
        return;
      }
      setToolRunResult({
        tool: toolName,
        duration_ms: data.duration_ms,
        output: data.result ?? data,
      });
      refreshMeta();
    } catch (err: any) {
      setToolRunResult({ tool: toolName, output: { error: err?.message || "Tool call failed" } });
    } finally {
      setRunningTool(null);
    }
  };

  const mergedLogs = useMemo(() => {
    const normalizedTools = toolLogs.map((t, i) => ({
      event_id: `TOOL-${i}-${t.timestamp}`,
      timestamp: t.timestamp,
      event_type: t.tool || "ai.tool",
      category: "ai_tool",
      country_id: t.payload?.country_id || t.arguments?.country_id || null,
      duration_ms: t.duration_ms,
      status: t.status,
      summary: t.summary,
      payload: t,
    }));
    const all = [...normalizedTools, ...events];
    all.sort((a, b) => (b.timestamp || "").localeCompare(a.timestamp || ""));
    return all.filter((item) => {
      const cat = (item.category || "simulation").toLowerCase();
      if (logFilter !== "all" && cat !== logFilter) return false;
      if (logQuery.trim()) {
        const hay = `${item.event_type || ""} ${item.summary || ""} ${item.country_id || ""}`.toLowerCase();
        if (!hay.includes(logQuery.toLowerCase())) return false;
      }
      return true;
    });
  }, [events, toolLogs, logFilter, logQuery]);

  const filteredTools = useMemo(() => {
    const q = toolSearch.trim().toLowerCase();
    if (!q) return availableTools;
    return availableTools.filter((t) => t.toLowerCase().includes(q));
  }, [availableTools, toolSearch]);

  const pendingApprovalsCount = useMemo(
    () => approvals.filter((a) => a.status === "PENDING").length,
    [approvals]
  );

  const toggleDock = (tab: Exclude<DockTab, null>) => {
    setActiveDock((cur) => (cur === tab ? null : tab));
  };

  const renderInlineApprovalCard = (approval: ApprovalItem) => {
    const localStatus = approvalStatusMap[approval.approval_id] || approval.status;
    const isFinalized = localStatus === "EXECUTED" || localStatus === "REJECTED";
    const isEditing = editingApprovalId === approval.approval_id;

    return (
      <div className="p-3 rounded-lg bg-[#0F1012] border border-[#2A2D34] space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-3.5 h-3.5 text-[#FAFAFA] shrink-0" />
              <span className="text-xs font-semibold text-[#FAFAFA]">{approval.title}</span>
            </div>
            <div className="text-[11px] text-[#A1A1AA] mt-0.5">{approval.description}</div>
          </div>
          <span className="px-2 py-0.5 rounded bg-[#16181C] border border-[#2A2D34] text-[10px] font-mono text-[#FAFAFA] shrink-0">
            {approval.approval_id} · {localStatus}
          </span>
        </div>

        {approval.parameters && Object.keys(approval.parameters).length > 0 && !isEditing && (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(approval.parameters).map(([k, v]) => (
              <span
                key={k}
                className="px-1.5 py-0.5 rounded bg-[#16181C] border border-[#2A2D34] text-[10px] font-mono text-[#A1A1AA]"
              >
                {k}: <span className="text-[#FAFAFA]">{String(v)}</span>
              </span>
            ))}
          </div>
        )}

        {isEditing && (
          <div className="space-y-1.5">
            <textarea
              value={modifyDraftJson}
              onChange={(e) => setModifyDraftJson(e.target.value)}
              rows={4}
              className="w-full bg-[#050505] border border-[#2A2D34] rounded p-2 text-[11px] font-mono text-[#FAFAFA] focus:outline-none focus:border-white/50"
            />
            {modifyError && <div className="text-[10px] font-mono text-[#A1A1AA]">{modifyError}</div>}
            <div className="flex items-center gap-2">
              <button
                onClick={() => submitModifyApproval(approval.approval_id)}
                className="px-2.5 py-1 rounded text-[11px] font-mono font-semibold bg-[#FAFAFA] text-[#050505] hover:bg-white/90"
              >
                Save Modifications
              </button>
              <button
                onClick={() => setEditingApprovalId(null)}
                className="px-2.5 py-1 rounded text-[11px] font-mono bg-[#16181C] border border-[#2A2D34] text-[#A1A1AA] hover:text-[#FAFAFA]"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {!isFinalized && (
          <div className="flex flex-wrap items-center gap-2 pt-0.5">
            <button
              onClick={() => handleApproval(approval.approval_id, true)}
              className="px-2.5 py-1 rounded text-[11px] font-mono font-semibold bg-[#FAFAFA] hover:bg-white text-[#050505] flex items-center gap-1 transition-colors"
            >
              <Check className="w-3.5 h-3.5" /> Approve & Execute
            </button>
            <button
              onClick={() => openModifyApproval(approval)}
              className="px-2.5 py-1 rounded text-[11px] font-mono bg-[#16181C] hover:bg-[#23262C] border border-[#2A2D34] text-[#FAFAFA] flex items-center gap-1 transition-colors"
            >
              <Edit3 className="w-3 h-3" /> Modify
            </button>
            <button
              onClick={() => handleApproval(approval.approval_id, false)}
              className="px-2.5 py-1 rounded text-[11px] font-mono bg-[#050505] hover:bg-[#16181C] border border-[#2A2D34] text-[#A1A1AA] hover:text-[#FAFAFA] flex items-center gap-1 transition-colors"
            >
              <X className="w-3.5 h-3.5" /> Reject
            </button>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="w-screen h-screen bg-[#050505] text-[#FAFAFA] flex flex-col overflow-hidden font-sans relative select-none">
      {/* Ultra-Sleek Stark Industries Top Command Strip */}
      <header className="h-11 px-4 bg-[#0B0C0E]/90 backdrop-blur-md border-b border-[#2A2D34] flex items-center justify-between shrink-0 z-30">
        <div className="flex items-center gap-3">
          <div className="w-6 h-6 rounded bg-[#16181C] border border-[#2A2D34] flex items-center justify-center">
            <Terminal className="w-3.5 h-3.5 text-[#FAFAFA]" />
          </div>
          <span className="font-semibold text-xs tracking-[0.18em] uppercase text-[#FAFAFA]">
            J.A.R.V.I.S // TACTICAL CORE
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#16181C] text-[#A1A1AA] border border-[#2A2D34]">
            03 · :5175
          </span>
          <span
            className={`text-[10px] font-mono px-2 py-0.5 rounded border flex items-center gap-1.5 ${
              listening
                ? "bg-[#FAFAFA] border-[#FAFAFA] text-[#050505] font-semibold"
                : speaking
                ? "bg-[#16181C] border-white/40 text-[#FAFAFA]"
                : "bg-[#0F1012] border-[#2A2D34] text-[#A1A1AA]"
            }`}
          >
            <Radio className={`w-3 h-3 ${listening ? "animate-pulse" : ""}`} />
            {listening
              ? "MIC LIVE"
              : speaking
              ? "VOICE SYNTH"
              : `VOICE · ${voiceMode.toUpperCase()}`}
          </span>
        </div>

        <div className="flex items-center gap-2 text-[11px] font-mono">
          {providers && (
            <span className="hidden md:inline-flex px-2 py-0.5 rounded bg-[#0F1012] border border-[#2A2D34] text-[#A1A1AA]">
              GEMINI {providers.providers.gemini?.active_keys ?? 0}/3 · GROK{" "}
              {providers.providers.grok?.active_keys ?? 0}/3
            </span>
          )}
          <button
            onClick={() => setStageMode((m) => (m === "fullscreen" ? "split" : "fullscreen"))}
            className="px-2.5 py-1 rounded bg-[#16181C] hover:bg-[#22252B] border border-[#2A2D34] text-[#FAFAFA] flex items-center gap-1.5 transition-colors"
            title="Toggle between Full-Screen 3D JARVIS Core and Split Core + Flat Tactical Map"
          >
            {stageMode === "fullscreen" ? (
              <>
                <LayoutPanelLeft className="w-3.5 h-3.5 text-[#A1A1AA]" />
                <span>Split Core + Map</span>
              </>
            ) : (
              <>
                <Maximize2 className="w-3.5 h-3.5 text-[#A1A1AA]" />
                <span>Full-Screen 3D Core</span>
              </>
            )}
          </button>
          <span
            className={`px-2 py-0.5 rounded border flex items-center gap-1.5 ${
              wsConnected
                ? "bg-[#16181C] border-white/25 text-[#FAFAFA]"
                : "bg-[#0F1012] border-[#2A2D34] text-[#71717A]"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                wsConnected ? "bg-[#FAFAFA]" : "bg-[#52525B]"
              }`}
            />
            {wsConnected ? "LIVE" : "OFFLINE"}
          </span>
        </div>
      </header>

      {/* Main Stage: Full-Bleed 3D JARVIS Core OR Split Core + Flat Tactical Map */}
      <main className="flex-1 relative overflow-hidden flex bg-[#050505]">
        <div
          className={`relative h-full transition-all duration-300 ${
            stageMode === "split" ? "w-1/2 border-r border-[#2A2D34]" : "w-full"
          }`}
        >
          <JarvisNeuralCore3D
            listening={listening}
            speaking={speaking}
            thinking={loading}
            awaitingApproval={pendingApprovalsCount > 0}
            error={Boolean(voiceNotice && /failed|error/i.test(voiceNotice))}
            audioLevel={audioLevel}
            statusLabel={
              listening
                ? "LISTENING · LIVE AUDIO STREAM"
                : speaking
                ? "SPEAKING · TACTICAL BRIEF"
                : loading
                ? "ORCHESTRATING TOOLS"
                : `STANDBY · ${selectedCountryId} · ${availableTools.length || 50} TOOLS READY`
            }
          />
        </div>

        {stageMode === "split" && (
          <div className="w-1/2 h-full relative bg-[#0F1012]">
            <TacticalFlatWorldMap
              countries={overview?.countries || []}
              disasters={overview?.active_disasters || []}
              selectedCountryId={selectedCountryId}
              onSelectCountry={(cid) => {
                setSelectedCountryId(cid);
                sendCommand(`View ${cid}`);
              }}
              drones={allDrones}
              hospitals={allHospitals}
              candidateRoutes={candidateRoutes}
              title="JARVIS GEOPOLITICAL TACTICAL MAP — 7 NATIONS"
            />
          </div>
        )}

        {/* Popped-Up Frosted Obsidian Bottom Drawer Overlay (3D Core remains visible behind/above) */}
        {activeDock !== null && (
          <section className="absolute left-4 right-4 bottom-[84px] z-20 max-w-5xl mx-auto rounded-2xl bg-[#0B0C0E]/95 backdrop-blur-xl border border-white/15 shadow-2xl flex flex-col overflow-hidden max-h-[52vh] select-text">
            {/* Drawer Header */}
            <div className="px-4 py-2 bg-[#0F1012]/90 border-b border-[#2A2D34] flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2 text-[11px] font-mono tracking-wider uppercase text-[#FAFAFA]">
                {activeDock === "command" && (
                  <>
                    <Mic className="w-3.5 h-3.5 text-[#FAFAFA]" />
                    <span>COMMAND & VOICE CONSOLE</span>
                  </>
                )}
                {activeDock === "logs" && (
                  <>
                    <Terminal className="w-3.5 h-3.5 text-[#FAFAFA]" />
                    <span>LIVE INTELLIGENCE & TOOL LOGS ({mergedLogs.length})</span>
                  </>
                )}
                {activeDock === "tools" && (
                  <>
                    <Wrench className="w-3.5 h-3.5 text-[#FAFAFA]" />
                    <span>LIVE BACKEND TOOLS ({availableTools.length || 50})</span>
                  </>
                )}
                {activeDock === "approvals" && (
                  <>
                    <ShieldAlert className="w-3.5 h-3.5 text-[#FAFAFA]" />
                    <span>OPERATOR APPROVALS ({pendingApprovalsCount} PENDING)</span>
                  </>
                )}
                {activeDock === "voice" && (
                  <>
                    <Sliders className="w-3.5 h-3.5 text-[#FAFAFA]" />
                    <span>VOICE & SYNTHESIS CALIBRATION</span>
                  </>
                )}
              </div>

              <button
                onClick={() => setActiveDock(null)}
                className="px-2 py-0.5 rounded bg-[#16181C] hover:bg-[#22252B] border border-[#2A2D34] text-[10px] font-mono text-[#A1A1AA] hover:text-[#FAFAFA] flex items-center gap-1"
                title="Collapse drawer to view full 3D JARVIS Core"
              >
                <ChevronDown className="w-3 h-3" /> Hide
              </button>
            </div>

            {/* DRAWER 1: COMMAND & VOICE */}
            {activeDock === "command" && (
              <div className="flex-1 flex flex-col min-h-0">
                {/* Voice Controls + Real Web Audio API Waveform */}
                <div className="px-4 py-2.5 bg-[#0F1012]/80 border-b border-[#2A2D34] space-y-2 shrink-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={toggleVoiceInput}
                        className={`px-3.5 py-1.5 rounded-lg text-xs font-mono font-semibold flex items-center gap-2 border transition-all ${
                          listening
                            ? "bg-[#FAFAFA] border-[#FAFAFA] text-[#050505] shadow-md"
                            : "bg-[#16181C] hover:bg-[#FAFAFA] hover:text-[#050505] border-white/25 text-[#FAFAFA]"
                        }`}
                      >
                        {listening ? (
                          <MicOff className="w-3.5 h-3.5" />
                        ) : (
                          <Mic className="w-3.5 h-3.5" />
                        )}
                        {listening ? "STOP MIC" : "SPEAK TO JARVIS"}
                      </button>

                      <button
                        onClick={stopSpeaking}
                        disabled={!speaking}
                        className="px-2.5 py-1.5 rounded-lg text-xs font-mono bg-[#16181C] hover:bg-[#23262C] disabled:opacity-35 border border-[#2A2D34] text-[#FAFAFA] flex items-center gap-1.5 transition-colors"
                      >
                        <Square className="w-3 h-3" /> Interrupt
                      </button>

                      <button
                        onClick={() => setAutoSpeak((v) => !v)}
                        className={`px-2.5 py-1.5 rounded-lg text-xs font-mono border flex items-center gap-1.5 transition-colors ${
                          autoSpeak
                            ? "bg-[#FAFAFA] border-[#FAFAFA] text-[#050505] font-semibold"
                            : "bg-[#0F1012] border-[#2A2D34] text-[#A1A1AA]"
                        }`}
                        title="Toggle Auto-Speak Replies"
                      >
                        {autoSpeak ? (
                          <Volume2 className="w-3.5 h-3.5" />
                        ) : (
                          <VolumeX className="w-3.5 h-3.5" />
                        )}
                        Auto-Speak
                      </button>
                    </div>

                    {/* Live Animated White/Silver Audio Waveform Bars */}
                    <div className="h-8 flex-1 min-w-[180px] max-w-[320px] bg-[#050505] rounded-lg border border-[#2A2D34] px-2.5 flex items-center justify-center gap-[3px]">
                      {waveformBars.map((lvl, i) => (
                        <div
                          key={i}
                          className={`w-[3px] rounded-full transition-all duration-75 ${
                            listening
                              ? "bg-[#FAFAFA]"
                              : speaking
                              ? "bg-[#D4D4D8]"
                              : "bg-[#3F3F46]"
                          }`}
                          style={{ height: `${Math.round(lvl * 100)}%` }}
                        />
                      ))}
                    </div>
                  </div>

                  {voiceNotice && (
                    <div className="text-[10px] font-mono text-[#A1A1AA]">{voiceNotice}</div>
                  )}

                  <div className="flex flex-wrap gap-1.5">
                    {QUICK_COMMANDS.slice(0, 4).map((q) => (
                      <button
                        key={q}
                        onClick={() => sendCommand(q)}
                        className="px-2 py-0.5 rounded bg-[#16181C] hover:bg-[#22252B] border border-[#2A2D34] text-[10px] font-mono text-[#A1A1AA] hover:text-[#FAFAFA] truncate max-w-[235px] transition-colors"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Conversation Transcript */}
                <div className="flex-1 overflow-y-auto p-3.5 space-y-3 bg-[#050505]/70 min-h-[160px]">
                  {messages.length === 0 && (
                    <div className="p-3.5 rounded-xl bg-[#0F1012] border border-[#2A2D34] text-xs text-[#A1A1AA]">
                      Press <strong className="text-[#FAFAFA]">SPEAK TO JARVIS</strong> or enter a
                      tactical command below. All{" "}
                      <span className="text-[#FAFAFA] font-mono">
                        {availableTools.length || 50}
                      </span>{" "}
                      grounded backend tools are online.
                    </div>
                  )}

                  {messages.map((m) => {
                    const isExpanded = !!expandedExplainIds[m.reply_id];
                    const isExplaining = explainingId === m.reply_id;
                    return (
                      <div
                        key={m.reply_id}
                        className="rounded-xl bg-[#0F1012] border border-[#2A2D34] p-3.5 space-y-2.5"
                      >
                        {/* Top Header: User Prompt + Latency Badge */}
                        <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono">
                          <span className="text-[#FAFAFA] font-semibold">
                            &gt; {m.user_message}
                          </span>
                          <span className="px-2 py-0.5 rounded bg-[#16181C] border border-[#2A2D34] text-[#A1A1AA]">
                            <span className="text-[#FAFAFA] font-semibold">
                              {m.latency_ms} ms
                            </span>{" "}
                            · {m.provider || m.model || "instant_grounded_orchestrator"}
                          </span>
                        </div>

                        {/* Frontend Command Chips */}
                        {Array.isArray(m.frontend_commands) && m.frontend_commands.length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            {m.frontend_commands.map((cmd, idx) => (
                              <span
                                key={idx}
                                className="px-2 py-0.5 rounded-full bg-[#16181C] border border-white/20 text-[10px] font-mono text-[#FAFAFA]"
                              >
                                {formatFrontendCommandChip(cmd)}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Assistant Message Body */}
                        <div className="text-xs text-[#E4E4E7] whitespace-pre-line leading-relaxed">
                          {m.assistant_message}
                        </div>

                        {/* Inline Approval Card (no modal) */}
                        {m.pending_approval && renderInlineApprovalCard(m.pending_approval)}

                        {/* Footer Action Row: Explain Button */}
                        <div className="flex items-center justify-between pt-1 border-t border-[#2A2D34]/70">
                          <div className="text-[10px] font-mono text-[#71717A]">
                            {m.execution_trace?.length || 0} tool steps ·{" "}
                            {m.structured_cards?.length || 0} telemetry cards
                          </div>
                          <button
                            onClick={() => handleExplainReply(m)}
                            disabled={isExplaining}
                            className="px-2.5 py-1 rounded bg-[#16181C] hover:bg-[#23262C] border border-[#2A2D34] text-[10px] font-mono text-[#FAFAFA] flex items-center gap-1.5 transition-colors"
                          >
                            <Sparkles className="w-3 h-3 text-[#A1A1AA]" />
                            {isExplaining
                              ? "Explaining..."
                              : isExpanded
                              ? "Hide Details"
                              : "Explain"}
                            {isExpanded ? (
                              <ChevronUp className="w-3 h-3 text-[#A1A1AA]" />
                            ) : (
                              <ChevronDown className="w-3 h-3 text-[#A1A1AA]" />
                            )}
                          </button>
                        </div>

                        {/* Expanded Structured Cards & Execution Trace */}
                        {isExpanded && (
                          <div className="space-y-2 pt-1">
                            {m.structured_cards && m.structured_cards.length > 0 ? (
                              m.structured_cards.map((card, cIdx) => (
                                <div
                                  key={cIdx}
                                  className="p-2.5 rounded-lg bg-[#050505] border border-[#2A2D34] space-y-1.5"
                                >
                                  <div className="text-[10px] font-mono uppercase tracking-wider text-[#A1A1AA]">
                                    STRUCTURED CARD · {card.type}
                                  </div>
                                  <pre className="text-[10px] font-mono text-[#E4E4E7] overflow-x-auto max-h-40 whitespace-pre-wrap">
                                    {JSON.stringify(card.data, null, 2)}
                                  </pre>
                                </div>
                              ))
                            ) : (
                              <div className="p-2 rounded bg-[#050505] border border-[#2A2D34] text-[10px] font-mono text-[#A1A1AA]">
                                Grounded directly from live simulation telemetry (no external LLM
                                keys required).
                              </div>
                            )}

                            {m.execution_trace && m.execution_trace.length > 0 && (
                              <div className="p-2.5 rounded-lg bg-[#050505] border border-[#2A2D34] space-y-1">
                                <div className="text-[10px] font-mono uppercase tracking-wider text-[#A1A1AA]">
                                  EXECUTION TRACE
                                </div>
                                {m.execution_trace.map((st, sIdx) => (
                                  <div
                                    key={sIdx}
                                    className="flex items-center justify-between text-[10px] font-mono text-[#E4E4E7]"
                                  >
                                    <span>
                                      {st.tool} — <span className="text-[#A1A1AA]">{st.summary}</span>
                                    </span>
                                    <span className="text-[#A1A1AA] shrink-0 ml-2">
                                      {st.duration_ms} ms
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                  <div ref={chatEndRef} />
                </div>

                {/* Command Input Bar */}
                <div className="p-2.5 bg-[#0F1012] border-t border-[#2A2D34] flex items-center gap-2 shrink-0">
                  <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && sendCommand()}
                    placeholder="Speak or type tactical command to J.A.R.V.I.S..."
                    className="flex-1 bg-[#050505] border border-[#2A2D34] rounded-lg px-3 py-1.5 text-xs text-[#FAFAFA] placeholder:text-[#71717A] focus:outline-none focus:border-white/40"
                  />
                  <button
                    onClick={() => sendCommand()}
                    disabled={loading}
                    className="px-3.5 py-1.5 rounded-lg bg-[#FAFAFA] hover:bg-white disabled:opacity-40 text-[#050505] text-xs font-mono font-semibold flex items-center gap-1.5 transition-colors"
                  >
                    <Send className="w-3.5 h-3.5" /> {loading ? "..." : "Send"}
                  </button>
                </div>
              </div>
            )}

            {/* DRAWER 2: LOGS */}
            {activeDock === "logs" && (
              <div className="flex-1 flex flex-col min-h-0">
                <div className="px-3.5 py-2 bg-[#0F1012] border-b border-[#2A2D34] flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono shrink-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {(["all", "disaster", "ai_tool", "approval", "execution", "recovery"] as const).map(
                      (cat) => (
                        <button
                          key={cat}
                          onClick={() => setLogFilter(cat)}
                          className={`px-2 py-0.5 rounded uppercase text-[10px] border transition-colors ${
                            logFilter === cat
                              ? "bg-[#FAFAFA] border-[#FAFAFA] text-[#050505] font-semibold"
                              : "bg-[#16181C] border-[#2A2D34] text-[#A1A1AA] hover:text-[#FAFAFA]"
                          }`}
                        >
                          {cat.replace("_", " ")}
                        </button>
                      )
                    )}
                  </div>
                  <div className="relative">
                    <Search className="w-3 h-3 text-[#71717A] absolute left-2 top-1.5" />
                    <input
                      value={logQuery}
                      onChange={(e) => setLogQuery(e.target.value)}
                      placeholder="Filter logs..."
                      className="pl-6 pr-2 py-0.5 rounded bg-[#050505] border border-[#2A2D34] text-[11px] text-[#FAFAFA] placeholder:text-[#71717A] w-44 focus:outline-none focus:border-white/40"
                    />
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto divide-y divide-[#2A2D34]/60 font-mono text-[11px] bg-[#050505]/80 min-h-[200px]">
                  {mergedLogs.length === 0 && (
                    <div className="p-4 text-[#71717A]">No matching events recorded yet.</div>
                  )}
                  {mergedLogs.slice(0, 80).map((item, idx) => {
                    const cat = (item.category || "simulation").toLowerCase();
                    const timeStr = (item.timestamp || "").split("T")[1]?.slice(0, 8) || "--:--:--";
                    const isOpen = expandedLogIdx === idx;
                    return (
                      <div
                        key={item.event_id || idx}
                        onClick={() => setExpandedLogIdx(isOpen ? null : idx)}
                        className="px-3.5 py-2 hover:bg-[#16181C]/70 cursor-pointer"
                      >
                        <div className="flex items-center gap-2.5">
                          <span className="text-[#71717A] shrink-0">{timeStr}</span>
                          <span className="px-1.5 py-0.5 rounded text-[9px] uppercase border border-[#2A2D34] bg-[#16181C] text-[#E4E4E7] shrink-0">
                            {cat.replace("_", " ")}
                          </span>
                          <span className="text-[#FAFAFA] font-semibold shrink-0">
                            {item.event_type}
                          </span>
                          {item.country_id && (
                            <span className="text-[#A1A1AA] shrink-0">[{item.country_id}]</span>
                          )}
                          <span className="text-[#A1A1AA] truncate flex-1">
                            {item.summary || ""}
                          </span>
                          {item.duration_ms !== undefined && (
                            <span className="text-[#FAFAFA] shrink-0">{item.duration_ms} ms</span>
                          )}
                        </div>
                        {isOpen && item.payload && (
                          <pre className="mt-2 p-2.5 rounded bg-[#0F1012] border border-[#2A2D34] text-[10px] text-[#E4E4E7] overflow-x-auto max-h-36">
                            {JSON.stringify(item.payload, null, 2)}
                          </pre>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* DRAWER 3: 50 TOOLS */}
            {activeDock === "tools" && (
              <div className="flex-1 flex flex-col min-h-0">
                <div className="px-3.5 py-2 bg-[#0F1012] border-b border-[#2A2D34] flex items-center justify-between gap-2 shrink-0">
                  <div className="relative flex-1 max-w-xs">
                    <Search className="w-3.5 h-3.5 text-[#71717A] absolute left-2.5 top-2" />
                    <input
                      value={toolSearch}
                      onChange={(e) => setToolSearch(e.target.value)}
                      placeholder="Search tools..."
                      className="w-full pl-8 pr-2.5 py-1 rounded bg-[#050505] border border-[#2A2D34] text-xs font-mono text-[#FAFAFA] placeholder:text-[#71717A] focus:outline-none focus:border-white/40"
                    />
                  </div>
                  <span className="text-[10px] font-mono text-[#A1A1AA]">
                    TARGET: <strong className="text-[#FAFAFA]">{selectedCountryId}</strong>
                  </span>
                </div>
                <div className="flex-1 overflow-y-auto p-3.5 bg-[#050505]/80 space-y-3 min-h-[200px]">
                  {toolRunResult && (
                    <div className="p-3 rounded-lg bg-[#0F1012] border border-white/20 space-y-1.5">
                      <div className="flex items-center justify-between text-[10px] font-mono">
                        <span className="text-[#FAFAFA] font-semibold">
                          RESULT · {toolRunResult.tool}
                        </span>
                        <div className="flex items-center gap-2">
                          {toolRunResult.duration_ms !== undefined && (
                            <span className="text-[#A1A1AA]">{toolRunResult.duration_ms} ms</span>
                          )}
                          <button
                            onClick={() => setToolRunResult(null)}
                            className="text-[#A1A1AA] hover:text-[#FAFAFA]"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                      <pre className="text-[10px] font-mono text-[#E4E4E7] overflow-x-auto max-h-36">
                        {JSON.stringify(toolRunResult.output, null, 2)}
                      </pre>
                    </div>
                  )}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                    {filteredTools.map((t) => (
                      <div
                        key={t}
                        className="px-2.5 py-2 rounded-lg bg-[#0F1012] border border-[#2A2D34] flex items-center justify-between gap-2"
                      >
                        <div className="flex items-center gap-1.5 min-w-0">
                          <Cpu className="w-3 h-3 text-[#A1A1AA] shrink-0" />
                          <span className="text-[11px] font-mono text-[#FAFAFA] truncate">{t}</span>
                        </div>
                        <button
                          onClick={() => runDirectTool(t)}
                          disabled={runningTool === t}
                          className="px-2 py-0.5 rounded bg-[#16181C] hover:bg-[#FAFAFA] hover:text-[#050505] border border-[#2A2D34] text-[10px] font-mono text-[#FAFAFA] shrink-0 transition-colors"
                        >
                          {runningTool === t ? "..." : "Run"}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* DRAWER 4: APPROVALS */}
            {activeDock === "approvals" && (
              <div className="flex-1 overflow-y-auto p-3.5 space-y-2.5 bg-[#050505]/80 min-h-[200px]">
                {approvals.length === 0 ? (
                  <div className="p-4 rounded-xl bg-[#0F1012] border border-[#2A2D34] text-xs font-mono text-[#A1A1AA]">
                    No approval proposals queued. Ask J.A.R.V.I.S. to prepare a rescue plan, swarm,
                    or mutual aid transfer.
                  </div>
                ) : (
                  approvals.map((apr) => (
                    <div key={apr.approval_id}>{renderInlineApprovalCard(apr)}</div>
                  ))
                )}
              </div>
            )}

            {/* DRAWER 5: VOICE SETTINGS */}
            {activeDock === "voice" && (
              <div className="p-4 bg-[#050505]/85 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
                <label className="flex flex-col gap-1.5 text-[#A1A1AA]">
                  INPUT MODE
                  <select
                    value={voiceMode}
                    onChange={(e) => setVoiceMode(e.target.value as any)}
                    className="bg-[#0F1012] border border-[#2A2D34] rounded-lg px-2.5 py-1.5 text-[#FAFAFA] focus:outline-none focus:border-white/40"
                  >
                    <option value="ptt">Push-to-Talk</option>
                    <option value="continuous">Continuous Voice Chat</option>
                    <option value="text">Text Only</option>
                  </select>
                </label>

                <label className="flex flex-col gap-1.5 text-[#A1A1AA]">
                  SYNTHESIS VOICE
                  <select
                    value={selectedVoiceName}
                    onChange={(e) => setSelectedVoiceName(e.target.value)}
                    className="bg-[#0F1012] border border-[#2A2D34] rounded-lg px-2.5 py-1.5 text-[#FAFAFA] focus:outline-none focus:border-white/40"
                  >
                    {voices.length === 0 && <option value="">Default System Voice</option>}
                    {voices.map((v) => (
                      <option key={v.name} value={v.name}>
                        {v.name}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="flex flex-col gap-1.5 text-[#A1A1AA]">
                  CADENCE RATE ({voiceRate.toFixed(2)}x)
                  <input
                    type="range"
                    min={0.7}
                    max={1.5}
                    step={0.05}
                    value={voiceRate}
                    onChange={(e) => setVoiceRate(parseFloat(e.target.value))}
                    className="accent-white"
                  />
                </label>

                <label className="flex flex-col gap-1.5 text-[#A1A1AA]">
                  OUTPUT VOLUME ({Math.round(voiceVolume * 100)}%)
                  <input
                    type="range"
                    min={0.1}
                    max={1.0}
                    step={0.1}
                    value={voiceVolume}
                    onChange={(e) => setVoiceVolume(parseFloat(e.target.value))}
                    className="accent-white"
                  />
                </label>
              </div>
            )}
          </section>
        )}

        {/* Bottom Command Dock + Live Invariants & Latency Footer Badge */}
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 z-30 flex flex-col items-center gap-1.5 pointer-events-none max-w-[calc(100vw-1rem)]">
          <div
            aria-label="JARVIS System Invariants and Latency"
            className="pointer-events-auto px-3 py-0.5 rounded-full bg-[#0B0C0E]/90 backdrop-blur-md border border-[#2A2D34] text-[10px] font-mono tracking-wide text-[#A1A1AA] shadow-lg flex items-center gap-1.5 whitespace-nowrap overflow-x-auto max-w-full"
          >
            <span className="text-[#FAFAFA]">
              {healthInvariants.approvalGated ? "✓" : "✗"}
            </span>
            <span>Approval-gated</span>
            <span className="text-[#52525B]">·</span>
            <span className="text-[#FAFAFA]">
              {healthInvariants.zeroDatabase ? "✓" : "✗"}
            </span>
            <span>Zero-database</span>
            <span className="text-[#52525B]">·</span>
            <span className="text-[#FAFAFA]">
              {healthInvariants.toolCount ?? (availableTools.length || 50)} tools
            </span>
            <span className="text-[#52525B]">·</span>
            <span className="text-[#E4E4E7]">
              {latencyStats.count > 0
                ? `p50 ${latencyStats.p50Ms}ms · p95 ${latencyStats.p95Ms}ms · p99 ${latencyStats.p99Ms}ms`
                : "<5ms grounded"}
            </span>
          </div>

          <nav
            aria-label="JARVIS Bottom Command Dock"
            className="pointer-events-auto px-2 py-1.5 rounded-full bg-[#0B0C0E]/95 backdrop-blur-xl border border-white/15 shadow-2xl flex items-center gap-1"
          >
          {(
            [
              { id: "logs", label: "LOGS", icon: Terminal },
              { id: "command", label: "COMMAND & VOICE", icon: Mic },
              {
                id: "tools",
                label: `${availableTools.length || 50} TOOLS`,
                icon: Wrench,
              },
              {
                id: "approvals",
                label:
                  pendingApprovalsCount > 0 ? `APPROVALS (${pendingApprovalsCount})` : "APPROVALS",
                icon: ShieldAlert,
              },
              { id: "voice", label: "VOICE SETTINGS", icon: Sliders },
            ] as const
          ).map((item) => {
            const Icon = item.icon;
            const isActive = activeDock === item.id;
            return (
              <button
                key={item.id}
                onClick={() => toggleDock(item.id)}
                className={`px-3 py-1.5 rounded-full text-[11px] font-mono tracking-wide flex items-center gap-1.5 transition-all whitespace-nowrap ${
                  isActive
                    ? "bg-[#FAFAFA] text-[#050505] font-semibold shadow"
                    : "bg-transparent text-[#A1A1AA] hover:text-[#FAFAFA] hover:bg-[#16181C]"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{item.label}</span>
              </button>
            );
          })}

          <div className="w-px h-5 bg-[#2A2D34] mx-0.5" />

          <button
            onClick={() => setStageMode((m) => (m === "fullscreen" ? "split" : "fullscreen"))}
            className={`px-3 py-1.5 rounded-full text-[11px] font-mono tracking-wide flex items-center gap-1.5 transition-all whitespace-nowrap ${
              stageMode === "split"
                ? "bg-[#FAFAFA] text-[#050505] font-semibold shadow"
                : "bg-transparent text-[#A1A1AA] hover:text-[#FAFAFA] hover:bg-[#16181C]"
            }`}
          >
            <MapIcon className="w-3.5 h-3.5" />
            <span>FLAT MAP</span>
          </button>
          </nav>
        </div>
      </main>
    </div>
  );
};
