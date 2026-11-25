import React, { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle2, Clock, Download, ExternalLink, Mic, MicOff, Pause, Play,
  Radio, RefreshCw, Send, ShieldAlert, SlidersHorizontal, Square,
  Volume2, VolumeX, X, XCircle
} from "lucide-react";
import { useSimStore } from "../state/simulationStore";
import { api } from "../api/client";
import { Jarvis3DCore, JarvisState } from "../components/panels/Jarvis3DCore";
import {
  agentApi,
  AgentRuntimeStatus,
  createAgentWebSocket,
  ExecutionTrace,
  ToolExecutionRecord,
} from "../api/agentClient";

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

function pickJarvisVoice(): SpeechSynthesisVoice | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  const preferred = [
    /google uk english male/i,
    /microsoft george/i,
    /daniel/i,
    /arthur/i,
    /en-gb/i,
    /english/i,
  ];
  for (const rx of preferred) {
    const match = voices.find((v) => rx.test(v.name) || rx.test(v.lang));
    if (match) return match;
  }
  return voices[0];
}

export const AgentConsoleApp: React.FC = () => {
  const simConnected = useSimStore((s) => s.connected);
  const activeState = useSimStore((s) => s.activeState);

  const [agentConnected, setAgentConnected] = useState(false);
  const [status, setStatus] = useState<AgentRuntimeStatus | null>(null);
  const [sessionId, setSessionId] = useState<string>("");
  const [traces, setTraces] = useState<ExecutionTrace[]>([]);
  const [liveTools, setLiveTools] = useState<ToolExecutionRecord[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [voiceListening, setVoiceListening] = useState(false);
  const [voiceDraft, setVoiceDraft] = useState<string | null>(null);
  const [speakResponses, setSpeakResponses] = useState(true);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const [jarvisAwake, setJarvisAwake] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [spokenSubtitle, setSpokenSubtitle] = useState("Click WAKE J.A.R.V.I.S. or press the microphone to begin.");
  const [speechPulse, setSpeechPulse] = useState(0);
  const [eqBars, setEqBars] = useState<number[]>(Array(24).fill(12));

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const speakEnabledRef = useRef(speakResponses);
  const jarvisAwakeRef = useRef(jarvisAwake);

  useEffect(() => {
    speakEnabledRef.current = speakResponses;
    if (!speakResponses && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }
  }, [speakResponses]);

  useEffect(() => {
    jarvisAwakeRef.current = jarvisAwake;
  }, [jarvisAwake]);

  const speakAsJarvis = useCallback((rawText: string) => {
    const clean = rawText.replace(/[*#`_]/g, "").replace(/\s+/g, " ").trim();
    if (!clean) return;
    setSpokenSubtitle(clean.slice(0, 220));
    if (!speakEnabledRef.current || typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(clean.slice(0, 440));
    const voice = pickJarvisVoice();
    if (voice) utt.voice = voice;
    utt.rate = 1.0;
    utt.pitch = 0.9;
    utt.onstart = () => {
      setIsSpeaking(true);
      setSpeechPulse((p) => p + 1);
    };
    utt.onboundary = () => {
      setSpeechPulse((p) => p + 1);
    };
    utt.onend = () => setIsSpeaking(false);
    utt.onerror = () => setIsSpeaking(false);
    window.speechSynthesis.speak(utt);
  }, []);

  const refreshStatus = () => {
    agentApi.getStatus().then(setStatus).catch(() => {});
  };

  useEffect(() => {
    document.title = "J.A.R.V.I.S. — QUANTUM RESCUE V2 (:5175)";
    if ("speechSynthesis" in window) window.speechSynthesis.getVoices();
    refreshStatus();
    agentApi.getCurrentSession().then((s) => setSessionId(s.session_id)).catch(() => {});

    const disconnect = createAgentWebSocket((msg) => {
      if (msg.type === "status") {
        setStatus(msg.payload as unknown as AgentRuntimeStatus);
      } else if (msg.type === "tool_started") {
        const p = msg.payload;
        setLiveTools((prev) => [
          ...prev.slice(-10),
          {
            execution_id: String(p.execution_id || ""),
            tool_call_id: String(p.tool_call_id || ""),
            tool: String(p.tool || ""),
            provider: String(p.provider || ""),
            key_alias: String(p.key_alias || ""),
            status: "RUNNING",
            started_at: msg.timestamp || new Date().toISOString(),
            completed_at: null,
            duration_ms: 0,
            state_version_before: 0,
            state_version_after: 0,
            arguments: (p.arguments as Record<string, unknown>) || {},
            result: null,
            error: null,
          },
        ]);
      } else if (msg.type === "tool_completed") {
        const rec = msg.payload as unknown as ToolExecutionRecord;
        setLiveTools((prev) => {
          const idx = prev.findIndex((x) => x.tool_call_id === rec.tool_call_id);
          if (idx >= 0) {
            const copy = [...prev];
            copy[idx] = rec;
            return copy;
          }
          return [...prev.slice(-10), rec];
        });
      } else if (msg.type === "world_alert") {
        const evName = String(msg.payload.event_type || "EVENT").replace(/_/g, " ");
        if (jarvisAwakeRef.current) {
          speakAsJarvis(`Alert, sir. Live simulation reported ${evName}. Standing by for rescue dispatch.`);
        }
      } else if (msg.type === "execution_completed" || msg.type === "approval_executed") {
        refreshStatus();
      }
    }, setAgentConnected);

    const timer = setInterval(refreshStatus, 5000);
    return () => {
      disconnect();
      clearInterval(timer);
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    };
  }, [speakAsJarvis]);

  const runningTool = liveTools.find((t) => t.status === "RUNNING");
  const latestTrace = traces[traces.length - 1];
  const jarvisState: JarvisState = voiceListening
    ? "LISTENING"
    : runningTool
    ? "EXECUTING"
    : sending
    ? "THINKING"
    : isSpeaking
    ? "SPEAKING"
    : latestTrace?.status === "FAILED" || latestTrace?.status === "INTERRUPTED"
    ? "ALERT"
    : latestTrace?.status === "COMPLETED" && latestTrace.verified.length > 0
    ? "VERIFIED"
    : "IDLE";

  useEffect(() => {
    if (jarvisState !== "SPEAKING" && jarvisState !== "LISTENING" && jarvisState !== "EXECUTING") {
      setEqBars(Array(24).fill(12));
      return;
    }
    const id = setInterval(() => {
      const base = jarvisState === "SPEAKING" ? 48 : 36;
      setEqBars(Array.from({ length: 24 }, () => Math.max(12, Math.min(100, Math.round(base + (Math.random() - 0.35) * 62)))));
    }, 85);
    return () => clearInterval(id);
  }, [jarvisState]);

  const handleWakeJarvis = () => {
    setJarvisAwake(true);
    setSpeakResponses(true);
    speakEnabledRef.current = true;
    const dCount = activeState?.disasters?.length || 0;
    const sCount = activeState?.survivors?.length || 0;
    const drCount = activeState?.drones?.length || 0;
    speakAsJarvis(
      dCount > 0
        ? `Good day, sir. J.A.R.V.I.S. is online. Tracking ${drCount} autonomous drones, ${dCount} active disaster zones, and ${sCount} simulated survivors. What are your orders?`
        : `Good day, sir. J.A.R.V.I.S. is online. All ${drCount} rescue drones are standing by across the metropolitan digital twin. Awaiting your command.`
    );
  };

  const sendCommand = async (rawText: string) => {
    const text = rawText.trim();
    if (!text || sending) return;
    setJarvisAwake(true);
    setSending(true);
    setInput("");
    setVoiceDraft(null);
    setLiveTools([]);
    setSpokenSubtitle(`Processing: “${text}”`);
    try {
      const trace = await agentApi.sendChat({
        message: text,
        session_id: sessionId || undefined,
      });
      setSessionId(trace.session_id);
      setTraces((prev) => [...prev, trace]);
      refreshStatus();
      if (trace.final_response) speakAsJarvis(trace.final_response);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      speakAsJarvis(`Warning, sir. Agent service reported an error: ${msg}`);
    } finally {
      setSending(false);
    }
  };

  const toggleVoice = () => {
    setVoiceError(null);
    setJarvisAwake(true);
    if (voiceListening && recognitionRef.current) {
      recognitionRef.current.stop();
      setVoiceListening(false);
      return;
    }
    const w = window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    const SR = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!SR) {
      setVoiceError("Web Speech API unavailable in this browser. Use Chrome/Edge or type below.");
      return;
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setIsSpeaking(false);
    const rec = new SR();
    rec.lang = "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (e) => {
      let tr = "";
      for (let i = 0; i < e.results.length; i++) tr += e.results[i][0].transcript;
      setVoiceDraft(tr);
      setSpokenSubtitle(`Listening: “${tr}”`);
    };
    rec.onerror = (e) => {
      setVoiceError(`Voice error: ${e.error}`);
      setVoiceListening(false);
    };
    rec.onend = () => setVoiceListening(false);
    recognitionRef.current = rec;
    setVoiceListening(true);
    setSpokenSubtitle("Listening to your voice command, sir...");
    rec.start();
  };

  const handleApprove = async (executionId: string) => {
    try {
      const updated = await agentApi.approveActions(executionId);
      setTraces((prev) => prev.map((t) => (t.execution_id === executionId ? updated : t)));
      refreshStatus();
      speakAsJarvis(`Approved actions executed and verified, sir. ${updated.executed.length} operation completed.`);
    } catch {
      /* ignore */
    }
  };

  const handleReject = async (executionId: string) => {
    try {
      const updated = await agentApi.rejectActions(executionId);
      setTraces((prev) => prev.map((t) => (t.execution_id === executionId ? updated : t)));
      refreshStatus();
      speakAsJarvis("Understood, sir. Pending actions cancelled.");
    } catch {
      /* ignore */
    }
  };

  const drones = activeState?.drones || [];
  const disasters = activeState?.disasters || [];
  const survivors = activeState?.survivors || [];
  const pendingApprovalTrace = traces.find((t) => t.pending_actions.some((a) => a.status === "PENDING_APPROVAL"));

  return (
    <div className="relative w-screen h-screen bg-[#010203] text-zinc-100 overflow-hidden font-mono select-none">
      {/* FULL-SCREEN 100vw x 100vh IRON MAN 3D HOLOGRAPHIC J.A.R.V.I.S. */}
      <Jarvis3DCore
        state={jarvisState}
        speechPulse={speechPulse}
        voiceListening={voiceListening}
      />

      {/* TOP-LEFT FLOATING MINIMAL TELEMETRY HUD */}
      <div className="absolute top-4 left-4 z-20 flex flex-col gap-2 pointer-events-auto">
        <div className="px-3 py-2 bg-black/55 backdrop-blur-md border border-amber-500/35 flex items-center gap-3">
          <div className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse shadow-[0_0_10px_#fbbf24]" />
          <div>
            <div className="text-xs font-bold tracking-[0.22em] text-amber-300">J.A.R.V.I.S.</div>
            <div className="text-[9px] text-zinc-400 tracking-widest">
              {jarvisState} · {status?.mode || "ASSISTED"} · {status?.providers.mode || "AUTO"}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] tabular-nums">
          <span className="px-2 py-1 bg-black/55 backdrop-blur-md border border-zinc-800 flex items-center gap-1">
            <Radio className={`w-3 h-3 ${simConnected ? "text-emerald-400" : "text-red-400"}`} />
            SIM {simConnected ? "LIVE" : "OFF"}
          </span>
          <span className="px-2 py-1 bg-black/55 backdrop-blur-md border border-zinc-800 text-amber-300">
            DIS {disasters.length}
          </span>
          <span className="px-2 py-1 bg-black/55 backdrop-blur-md border border-zinc-800 text-red-300">
            SUR {survivors.length}
          </span>
          <span className="px-2 py-1 bg-black/55 backdrop-blur-md border border-zinc-800 text-zinc-200">
            DRN {drones.length}
          </span>
        </div>
      </div>

      {/* TOP-RIGHT FLOATING CONTROLS */}
      <div className="absolute top-4 right-4 z-20 flex items-center gap-1.5 text-[10px] pointer-events-auto">
        {!jarvisAwake && (
          <button
            onClick={handleWakeJarvis}
            className="px-3 py-1.5 bg-amber-500 hover:bg-amber-400 text-black font-bold tracking-wider shadow-[0_0_18px_rgba(245,158,11,0.6)]"
          >
            WAKE J.A.R.V.I.S.
          </button>
        )}
        <button
          onClick={toggleVoice}
          className={`px-3 py-1.5 border backdrop-blur-md font-bold flex items-center gap-1.5 ${
            voiceListening
              ? "bg-red-600/90 border-red-400 text-white animate-pulse"
              : "bg-black/55 border-amber-500/45 text-amber-300 hover:bg-amber-500/20"
          }`}
        >
          {voiceListening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
          {voiceListening ? "LISTENING" : "SPEAK"}
        </button>
        <button
          onClick={() => setSpeakResponses(!speakResponses)}
          className="p-1.5 bg-black/55 backdrop-blur-md border border-zinc-700 text-amber-300 hover:border-amber-400"
          title="Toggle J.A.R.V.I.S. Voice"
        >
          {speakResponses ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4 text-zinc-500" />}
        </button>
        <a
          href="http://localhost:5173"
          target="_blank"
          rel="noreferrer"
          className="px-2.5 py-1.5 bg-black/55 backdrop-blur-md border border-zinc-700 text-zinc-200 hover:border-zinc-400 flex items-center gap-1"
        >
          3D :5173 <ExternalLink className="w-3 h-3" />
        </a>
        <a
          href="http://localhost:5174"
          target="_blank"
          rel="noreferrer"
          className="px-2.5 py-1.5 bg-black/55 backdrop-blur-md border border-zinc-700 text-zinc-200 hover:border-zinc-400 flex items-center gap-1"
        >
          TERMINAL :5174 <ExternalLink className="w-3 h-3" />
        </a>
        <button
          onClick={() => setDrawerOpen(!drawerOpen)}
          className="px-2.5 py-1.5 bg-black/65 backdrop-blur-md border border-amber-500/45 text-amber-200 hover:bg-amber-500/20 flex items-center gap-1.5 font-bold"
        >
          <SlidersHorizontal className="w-3.5 h-3.5" /> HUD & LOGS
        </button>
      </div>

      {/* FLOATING LIVE TOOL EXECUTION PILLS (UPPER CENTER, ONLY WHEN ACTIVE) */}
      <AnimatePresence>
        {(runningTool || liveTools.length > 0) && sending && (
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="absolute top-20 left-1/2 -translate-x-1/2 z-20 flex flex-wrap justify-center gap-1.5 max-w-xl"
          >
            {liveTools.slice(-4).map((lt) => (
              <div
                key={lt.tool_call_id}
                className="px-2.5 py-1 bg-black/75 backdrop-blur-md border border-amber-500/50 text-[10px] text-amber-200 flex items-center gap-1.5"
              >
                {lt.status === "SUCCESS" ? (
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                ) : (
                  <Clock className="w-3 h-3 text-amber-400 animate-spin" />
                )}
                <span>{lt.tool}</span>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* FLOATING OPERATOR APPROVAL CARD (ASSISTED / DESTRUCTIVE MODE) */}
      <AnimatePresence>
        {pendingApprovalTrace && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="absolute bottom-36 left-1/2 -translate-x-1/2 z-30 w-[520px] max-w-[92vw] p-3 bg-black/85 backdrop-blur-lg border border-amber-400/80 shadow-[0_0_28px_rgba(245,158,11,0.3)] space-y-2 text-[11px]"
          >
            <div className="flex items-center gap-2 text-amber-300 font-bold">
              <ShieldAlert className="w-4 h-4" /> OPERATOR AUTHORIZATION REQUIRED ({pendingApprovalTrace.execution_id})
            </div>
            {pendingApprovalTrace.pending_actions
              .filter((a) => a.status === "PENDING_APPROVAL")
              .map((a) => (
                <div key={a.action_id} className="p-2 bg-zinc-950/90 border border-amber-800/60 text-[10px]">
                  <div className="font-bold text-zinc-100">{a.tool_name}</div>
                  <div className="text-zinc-400 break-all">{JSON.stringify(a.arguments)}</div>
                </div>
              ))}
            <div className="flex gap-2">
              <button onClick={() => handleApprove(pendingApprovalTrace.execution_id)} className="px-4 py-1.5 bg-amber-500 hover:bg-amber-400 text-black font-bold">
                AUTHORIZE & EXECUTE
              </button>
              <button onClick={() => handleReject(pendingApprovalTrace.execution_id)} className="px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-300">
                DENY
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* BOTTOM FLOATING CINEMATIC SUBTITLE + EQUALIZER + COMMAND BAR */}
      <div className="absolute bottom-5 left-1/2 -translate-x-1/2 z-20 w-[720px] max-w-[94vw] flex flex-col items-center gap-2.5">
        {/* Live Voice Equalizer */}
        <div className="flex items-end justify-center gap-1 h-5">
          {eqBars.map((h, i) => (
            <div
              key={i}
              style={{ height: `${h}%` }}
              className="w-1 bg-amber-400/85 rounded-full transition-all duration-75 shadow-[0_0_6px_rgba(251,191,36,0.7)]"
            />
          ))}
        </div>

        {/* Spoken Subtitle Caption */}
        <div className="px-4 py-1.5 bg-black/65 backdrop-blur-md border border-amber-500/30 text-xs text-amber-100 text-center max-w-full truncate">
          “{spokenSubtitle}”
        </div>

        {/* Editable Voice Transcript Preview */}
        {voiceDraft !== null && (
          <div className="w-full px-3 py-1.5 bg-amber-950/75 backdrop-blur-md border border-amber-500 flex items-center gap-2 text-[11px]">
            <span className="text-amber-300 font-bold text-[10px] shrink-0">TRANSCRIPT:</span>
            <input
              value={voiceDraft}
              onChange={(e) => setVoiceDraft(e.target.value)}
              className="flex-1 bg-black/70 border border-amber-600/60 px-2 py-1 text-zinc-100"
            />
            <button onClick={() => sendCommand(voiceDraft)} className="px-3 py-1 bg-amber-500 text-black font-bold">EXECUTE</button>
            <button onClick={() => setVoiceDraft(null)} className="px-2 py-1 bg-zinc-900 text-zinc-300">CANCEL</button>
          </div>
        )}
        {voiceError && <div className="text-[10px] text-red-400 bg-black/75 px-3 py-1 border border-red-900">{voiceError}</div>}

        {/* Translucent Command Bar */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendCommand(input);
          }}
          className="w-full flex items-center gap-2 bg-black/70 backdrop-blur-lg border border-amber-500/40 p-1.5 shadow-[0_0_24px_rgba(0,0,0,0.7)]"
        >
          <button
            type="button"
            onClick={toggleVoice}
            className={`p-2 border ${voiceListening ? "bg-red-600 border-red-400 text-white" : "bg-zinc-950 border-amber-500/40 text-amber-300 hover:bg-amber-500/15"}`}
          >
            {voiceListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
          </button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Speak or type a command to J.A.R.V.I.S. (e.g., 'Analyse disasters and dispatch medical drones')..."
            className="flex-1 bg-transparent px-2 py-1.5 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="px-4 py-1.5 bg-amber-500 hover:bg-amber-400 disabled:opacity-40 text-black font-bold text-xs flex items-center gap-1.5"
          >
            <Send className="w-3.5 h-3.5" /> SEND
          </button>
        </form>
      </div>

      {/* SLIDE-OVER HUD & EXECUTION LOG DRAWER (Keeps main screen 100% pure J.A.R.V.I.S.) */}
      <AnimatePresence>
        {drawerOpen && (
          <motion.aside
            initial={{ x: 420 }}
            animate={{ x: 0 }}
            exit={{ x: 420 }}
            transition={{ type: "spring", stiffness: 280, damping: 28 }}
            className="absolute top-0 right-0 bottom-0 z-40 w-[390px] max-w-[92vw] bg-black/90 backdrop-blur-xl border-l border-amber-500/35 p-3.5 flex flex-col gap-3 overflow-y-auto text-[10px]"
          >
            <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
              <span className="font-bold text-amber-300 tracking-wider">J.A.R.V.I.S. SYSTEM HUD & LOGS</span>
              <button onClick={() => setDrawerOpen(false)} className="p-1 text-zinc-400 hover:text-white"><X className="w-4 h-4" /></button>
            </div>

            {/* Quick Demo Choreography */}
            <div className="space-y-1.5">
              <div className="text-[9px] text-zinc-400 uppercase">Live Demo Actions</div>
              <div className="grid grid-cols-2 gap-1.5">
                <button onClick={() => { api.loadDisasterPreset("METRO_EARTHQUAKE_CASCADE").catch(() => {}); speakAsJarvis("Seismic cascade triggered across downtown. Survivors detected."); }} className="p-1.5 bg-zinc-950 hover:bg-amber-500/20 border border-amber-500/40 text-amber-200">1. QUAKE CASCADE</button>
                <button disabled={sending} onClick={() => sendCommand("Use get_tactical_situation_brief and plan_and_dispatch_disaster_response to rescue top priority survivors now.")} className="p-1.5 bg-zinc-950 hover:bg-amber-500/20 border border-amber-500/40 text-amber-200">2. AI TRIAGE & DISPATCH</button>
                <button onClick={() => { api.syncUi("camera_mode", { mode: "disaster_focus" }); speakAsJarvis("Focusing 3D camera on active disaster zone."); }} className="p-1.5 bg-zinc-950 hover:bg-zinc-800 border border-zinc-700 text-zinc-200">3. FOCUS 3D</button>
                <button onClick={() => { api.startBenchmark().catch(() => {}); speakAsJarvis("Running 4-strategy Quantum QAOA benchmark."); }} className="p-1.5 bg-zinc-950 hover:bg-zinc-800 border border-zinc-700 text-zinc-200">4. 4-SOLVER ARENA</button>
              </div>
            </div>

            {/* Stop / Pause / Resume */}
            <div className="grid grid-cols-3 gap-1.5">
              <button onClick={() => { agentApi.stopExecution().then(refreshStatus); speakAsJarvis("Execution stopped, sir."); }} className="py-1.5 bg-red-950/80 border border-red-700 text-red-100 font-bold flex items-center justify-center gap-1"><Square className="w-3 h-3" /> STOP</button>
              <button onClick={() => { agentApi.pauseAgent().then(refreshStatus); speakAsJarvis("Agent paused."); }} className="py-1.5 bg-zinc-950 border border-zinc-700 text-zinc-200 flex items-center justify-center gap-1"><Pause className="w-3 h-3" /> PAUSE</button>
              <button onClick={() => { agentApi.resumeAgent().then(refreshStatus); speakAsJarvis("Resuming monitoring."); }} className="py-1.5 bg-zinc-950 border border-zinc-700 text-emerald-300 flex items-center justify-center gap-1"><Play className="w-3 h-3" /> RESUME</button>
            </div>

            {/* Mode & Provider */}
            <div className="grid grid-cols-3 gap-1">
              {(["OBSERVE", "ASSISTED", "AUTONOMOUS"] as const).map((m) => (
                <button key={m} onClick={() => { agentApi.setMode(m).then(refreshStatus); speakAsJarvis(`${m.toLowerCase()} mode engaged.`); }} className={`py-1 border ${status?.mode === m ? "bg-amber-500 text-black font-bold border-amber-400" : "bg-zinc-950 border-zinc-800 text-zinc-400"}`}>{m}</button>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-1">
              {(["AUTO", "GROK", "GEMINI"] as const).map((p) => (
                <button key={p} onClick={() => agentApi.setProviderMode(p).then(refreshStatus)} className={`py-1 border ${status?.providers.mode === p ? "bg-zinc-200 text-black font-bold border-white" : "bg-zinc-950 border-zinc-800 text-zinc-400"}`}>{p}</button>
              ))}
            </div>

            {/* 6-Key Health */}
            {status && (
              <div className="space-y-1.5">
                {[status.providers.grok, status.providers.gemini].map((pool) => (
                  <div key={pool.provider} className="p-2 bg-zinc-950 border border-zinc-800 space-y-1">
                    <div className="flex justify-between font-bold text-zinc-200">
                      <span>{pool.provider}</span>
                      <span className="text-zinc-400">{pool.healthy_keys}/3 HEALTHY</span>
                    </div>
                    {pool.keys.map((k) => (
                      <div key={k.alias} className="flex justify-between text-[9px] text-zinc-400">
                        <span>{k.alias}</span>
                        <span className={k.health === "HEALTHY" ? "text-emerald-400" : "text-zinc-500"}>{k.health} · {k.request_count} req</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}

            {/* Execution History & Tool Receipts */}
            <div className="flex-1 space-y-2">
              <div className="flex justify-between items-center text-[9px] text-zinc-400 uppercase">
                <span>Execution Receipts ({traces.length})</span>
                <button onClick={async () => { const s = await agentApi.createSession(); setSessionId(s.session_id); setTraces([]); }} className="text-amber-300 flex items-center gap-1"><RefreshCw className="w-3 h-3" /> NEW</button>
              </div>
              {traces.slice().reverse().map((tr) => (
                <div key={tr.execution_id} className="p-2 bg-zinc-950 border border-zinc-800 space-y-1">
                  <div className="flex justify-between text-[9px]">
                    <span className="text-amber-300 font-bold">{tr.execution_id}</span>
                    <a href={agentApi.executionJsonUrl(tr.execution_id)} target="_blank" rel="noreferrer" className="text-zinc-400 hover:text-white flex items-center gap-0.5"><Download className="w-3 h-3" /> JSON</a>
                  </div>
                  <div className="text-zinc-200">{tr.user_message}</div>
                  {tr.tool_records.map((rec) => (
                    <div key={rec.tool_call_id + rec.started_at} className="text-[9px] text-zinc-400 flex items-center gap-1">
                      {rec.status === "SUCCESS" ? <CheckCircle2 className="w-2.5 h-2.5 text-emerald-400" /> : <XCircle className="w-2.5 h-2.5 text-red-400" />}
                      <span>{rec.tool} ({rec.duration_ms}ms)</span>
                    </div>
                  ))}
                  <div className="text-[10px] text-zinc-300 border-t border-zinc-800 pt-1">{tr.final_response}</div>
                </div>
              ))}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  );
};
