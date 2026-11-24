import React, { useEffect, useRef, useState } from "react";
import {
  Check,
  Mic,
  MicOff,
  Radio,
  Send,
  Sliders,
  Square,
  Terminal,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import { TacticalFlatWorldMap } from "../components/map/TacticalFlatWorldMap";
import { JarvisNeuralCore3D } from "../components/jarvis/JarvisNeuralCore3D";
import { TacticalLiveLogsPanel } from "../components/logs/TacticalLiveLogsPanel";
import { connectGlobalWebSocket, globalApi } from "../shared/globalApi";
import type { GlobalOverview, JarvisReply, ProviderStatusPayload } from "../shared/globalTypes";

const QUICK_COMMANDS = [
  "Analyze the situation in Country 3",
  "View Country 1 and find the best drones to reach the hospital",
  "Prepare a complete rescue plan for Country 3",
  "Can another country provide additional ambulances?",
  "Compare conventional vs hybrid counterfactual worlds",
  "Prepare an 8-drone medical delivery swarm in grid formation",
];

export const JarvisCommandApp: React.FC = () => {
  const [overview, setOverview] = useState<GlobalOverview | null>(null);
  const [providers, setProviders] = useState<ProviderStatusPayload | null>(null);
  const [allDrones, setAllDrones] = useState<any[]>([]);
  const [allHospitals, setAllHospitals] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [toolLogs, setToolLogs] = useState<any[]>([]);
  const [availableTools, setAvailableTools] = useState<string[]>([]);
  const [messages, setMessages] = useState<JarvisReply[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedCountryId, setSelectedCountryId] = useState("COUNTRY-03");
  const [candidateRoutes, setCandidateRoutes] = useState<any[]>([]);
  const [wsConnected, setWsConnected] = useState(false);

  const [voiceMode, setVoiceMode] = useState<"ptt" | "continuous" | "text">("ptt");
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(true);
  const [voiceRate, setVoiceRate] = useState(1.04);
  const [voiceVolume, setVoiceVolume] = useState(1.0);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoiceName, setSelectedVoiceName] = useState("");
  const [showVoiceSettings, setShowVoiceSettings] = useState(false);
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const [visualMode, setVisualMode] = useState<"core" | "map">("core");
  const [audioLevel, setAudioLevel] = useState(0);
  const recognitionRef = useRef<any>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);

  const refreshMeta = () => {
    globalApi.getOverview().then(setOverview).catch(() => {});
    globalApi.getProvidersStatus().then(setProviders).catch(() => {});
    globalApi.getGlobalDrones().then((r) => setAllDrones(r.drones)).catch(() => {});
    fetch("/api/hospitals").then((r) => r.json()).then((d) => setAllHospitals(d.hospitals || [])).catch(() => {});
    globalApi.getEvents(50).then((r) => setEvents(r.events)).catch(() => {});
    globalApi.getAuditLogs().then((r) => setToolLogs(r.tool_logs || [])).catch(() => {});
  };

  useEffect(() => {
    refreshMeta();
    fetch("/api/ai/tools").then((r) => r.json()).then((d) => setAvailableTools(Object.keys(d.tools || {}))).catch(() => {});

    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      const loadVoices = () => {
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
      onConnectionChange: setWsConnected,
      onSnapshot: (snap) => {
        if (snap.overview) setOverview(snap.overview);
        if (snap.providers) setProviders(snap.providers);
      },
      onWorldEvent: () => refreshMeta(),
    });
    return disconnect;
  }, []);

  const stopSpeaking = () => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    setSpeaking(false);
  };

  const speakText = (text: string) => {
    if (!autoSpeak || voiceMode === "text" || typeof window === "undefined" || !("speechSynthesis" in window)) return;
    stopSpeaking();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = voiceRate;
    u.volume = voiceVolume;
    const chosen = voices.find((v) => v.name === selectedVoiceName);
    if (chosen) u.voice = chosen;
    u.onstart = () => setSpeaking(true);
    u.onend = () => {
      setSpeaking(false);
      if (voiceMode === "continuous") startVoiceRecognition();
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
    try {
      const reply = await globalApi.jarvisChat(query, "command-session-1");
      setMessages((prev) => [...prev, reply]);
      if (reply.context?.active_country_id) setSelectedCountryId(reply.context.active_country_id);
      const routeCard = reply.structured_cards.find((c) => c.type === "route_comparison");
      if (routeCard?.data?.all_candidate_routes) {
        setCandidateRoutes(routeCard.data.all_candidate_routes);
      }
      speakText(reply.spoken_summary);
      refreshMeta();
    } finally {
      setLoading(false);
    }
  };

  const startVoiceRecognition = () => {
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec) {
      setVoiceNotice("Browser speech recognition unavailable; type commands or use Chrome/Edge for live mic.");
      return;
    }
    setVoiceNotice(null);
    stopSpeaking();
    const rec = new SpeechRec();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.onstart = () => {
      setListening(true);
      if (navigator.mediaDevices?.getUserMedia) {
        navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
          micStreamRef.current = stream;
          const ctx = new AudioContext();
          audioCtxRef.current = ctx;
          const src = ctx.createMediaStreamSource(stream);
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 256;
          src.connect(analyser);
          const data = new Uint8Array(analyser.frequencyBinCount);
          const tick = () => {
            analyser.getByteFrequencyData(data);
            const avg = data.reduce((a, b) => a + b, 0) / Math.max(1, data.length);
            setAudioLevel(Math.min(1, avg / 95));
            rafRef.current = requestAnimationFrame(tick);
          };
          tick();
        }).catch(() => {});
      }
    };
    rec.onresult = (ev: any) => {
      const transcript = ev.results?.[0]?.[0]?.transcript;
      if (transcript) sendCommand(transcript);
    };
    rec.onerror = (ev: any) => {
      setListening(false);
      setVoiceNotice(`Voice input status: ${ev.error}`);
    };
    rec.onend = () => {
      setListening(false);
      setAudioLevel(0);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      micStreamRef.current?.getTracks().forEach((tr) => tr.stop());
      micStreamRef.current = null;
      audioCtxRef.current?.close().catch(() => {});
      audioCtxRef.current = null;
    };
    recognitionRef.current = rec;
    rec.start();
  };

  const toggleVoiceInput = () => {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    startVoiceRecognition();
  };

  const handleApproval = async (approvalId: string, approve: boolean) => {
    if (approve) {
      await globalApi.approveOperation(approvalId, true);
      speakText(`Operation ${approvalId} approved and executed.`);
    } else {
      await globalApi.rejectOperation(approvalId);
      speakText(`Operation ${approvalId} rejected.`);
    }
    refreshMeta();
  };

  return (
    <div className="w-screen h-screen bg-[#F7F8FA] text-slate-900 flex flex-col overflow-hidden font-sans">
      {/* Light Top Aerospace & Voice Bar */}
      <header className="h-11 px-4 bg-white border-b border-slate-200 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <Terminal className="w-4 h-4 text-blue-700" />
          <span className="font-bold text-sm tracking-wide text-slate-900">JARVIS — VOICE & TACTICAL INTELLIGENCE</span>
          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-blue-50 text-blue-800 border border-blue-200 font-semibold">
            03 — JARVIS (:5175)
          </span>
          <span
            className={`text-[11px] font-mono px-2 py-0.5 rounded border flex items-center gap-1 font-semibold ${
              listening
                ? "bg-red-50 border-red-300 text-red-700"
                : speaking
                ? "bg-emerald-50 border-emerald-300 text-emerald-700"
                : "bg-slate-100 border-slate-200 text-slate-700"
            }`}
          >
            <Radio className="w-3 h-3" />
            {listening ? "MIC LISTENING" : speaking ? "JARVIS SPEAKING" : `VOICE ${voiceMode.toUpperCase()}`}
          </span>
        </div>

        <div className="flex items-center gap-2 text-[11px] font-mono">
          {providers && (
            <span className="px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-slate-700">
              GEMINI {providers.providers.gemini?.active_keys ?? 0}/3 · GROK {providers.providers.grok?.active_keys ?? 0}/3
            </span>
          )}
          <button
            onClick={() => setVisualMode((m) => (m === "core" ? "map" : "core"))}
            className="px-2.5 py-1 rounded bg-amber-50 hover:bg-amber-100 border border-amber-300 text-amber-900 font-semibold"
          >
            {visualMode === "core" ? "Show Flat Map" : "Show JARVIS Core"}
          </button>
          <button
            onClick={() => setShowVoiceSettings((v) => !v)}
            className="px-2 py-1 rounded bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 flex items-center gap-1"
          >
            <Sliders className="w-3 h-3 text-blue-700" /> Voice Settings
          </button>
          <span
            className={`px-2 py-0.5 rounded border font-semibold ${
              wsConnected ? "bg-emerald-50 border-emerald-300 text-emerald-700" : "bg-red-50 border-red-300 text-red-700"
            }`}
          >
            {wsConnected ? "LIVE" : "OFFLINE"}
          </span>
        </div>
      </header>

      {showVoiceSettings && (
        <div className="px-4 py-2 bg-slate-50 border-b border-slate-200 flex flex-wrap items-center gap-4 text-xs font-mono text-slate-700">
          <label className="flex items-center gap-2">
            MODE:
            <select value={voiceMode} onChange={(e) => setVoiceMode(e.target.value as any)} className="bg-white border border-slate-300 rounded px-2 py-0.5">
              <option value="ptt">Push-to-Talk</option>
              <option value="continuous">Continuous Voice Chat</option>
              <option value="text">Text Only</option>
            </select>
          </label>
          <label className="flex items-center gap-2">
            VOICE:
            <select value={selectedVoiceName} onChange={(e) => setSelectedVoiceName(e.target.value)} className="bg-white border border-slate-300 rounded px-2 py-0.5 max-w-[200px]">
              {voices.map((v) => (
                <option key={v.name} value={v.name}>{v.name}</option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2">
            RATE ({voiceRate.toFixed(2)}x):
            <input type="range" min={0.7} max={1.5} step={0.05} value={voiceRate} onChange={(e) => setVoiceRate(parseFloat(e.target.value))} />
          </label>
          <label className="flex items-center gap-2">
            VOL ({Math.round(voiceVolume * 100)}%):
            <input type="range" min={0.1} max={1.0} step={0.1} value={voiceVolume} onChange={(e) => setVoiceVolume(parseFloat(e.target.value))} />
          </label>
        </div>
      )}

      {/* Main Split: Flat Tactical Map + Live Logs | Voice Command Console */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="h-[64%] relative">
            {visualMode === "core" ? (
              <JarvisNeuralCore3D
                listening={listening}
                speaking={speaking}
                thinking={loading}
                audioLevel={audioLevel}
              />
            ) : (
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
            )}
          </div>
          <div className="h-[36%]">
            <TacticalLiveLogsPanel
              events={events}
              toolLogs={toolLogs}
              title="LIVE INTELLIGENCE, EVENT & AI TOOL STREAM"
            />
          </div>
        </div>

        {/* Right: Light JARVIS Voice Command Console */}
        <aside className="w-[450px] bg-white border-l border-slate-200 flex flex-col shrink-0">
          <div className="p-3 border-b border-slate-200 bg-slate-50 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <button
                  onClick={toggleVoiceInput}
                  className={`px-3 py-1.5 rounded text-xs font-mono font-semibold flex items-center gap-1.5 border shadow-sm ${
                    listening
                      ? "bg-red-600 border-red-700 text-white animate-pulse"
                      : "bg-blue-700 hover:bg-blue-600 border-blue-800 text-white"
                  }`}
                >
                  {listening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
                  {listening ? "STOP MIC" : "SPEAK TO JARVIS"}
                </button>
                <button
                  onClick={stopSpeaking}
                  disabled={!speaking}
                  className="px-2.5 py-1.5 rounded text-xs font-mono bg-amber-50 hover:bg-amber-100 disabled:opacity-40 border border-amber-300 text-amber-800 flex items-center gap-1"
                >
                  <Square className="w-3 h-3" /> Interrupt
                </button>
              </div>
              <button
                onClick={() => setAutoSpeak((v) => !v)}
                className={`p-1.5 rounded border ${
                  autoSpeak ? "bg-emerald-50 border-emerald-300 text-emerald-700" : "bg-white border-slate-300 text-slate-500"
                }`}
                title="Auto-Speak Replies"
              >
                {autoSpeak ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
              </button>
            </div>

            <div className="h-6 bg-white rounded border border-slate-200 px-2 flex items-center justify-center gap-1">
              {Array.from({ length: 24 }).map((_, i) => (
                <div
                  key={i}
                  className={`w-1 rounded-full transition-all duration-150 ${
                    listening ? "bg-red-500" : speaking ? "bg-emerald-600" : "bg-blue-200"
                  }`}
                  style={{ height: listening || speaking ? `${35 + ((i * 29) % 60)}%` : "22%" }}
                />
              ))}
            </div>
            {voiceNotice && <div className="text-[10px] font-mono text-amber-700">{voiceNotice}</div>}

            <div className="flex flex-wrap gap-1">
              {QUICK_COMMANDS.slice(0, 4).map((q) => (
                <button
                  key={q}
                  onClick={() => sendCommand(q)}
                  className="px-2 py-0.5 rounded text-[10px] bg-white hover:bg-blue-50 border border-slate-200 text-slate-700 truncate max-w-[205px]"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-2.5 bg-[#F7F8FA]">
            {messages.length === 0 && (
              <div className="p-3 rounded bg-white border border-slate-200 text-xs text-slate-600 shadow-sm">
                Click <strong>SPEAK TO JARVIS</strong> or type below. All {availableTools.length} backend tools are live and respond in under 5 ms.
              </div>
            )}
            {messages.map((m) => (
              <div key={m.reply_id} className="rounded bg-white border border-slate-200 p-3 space-y-2 shadow-sm">
                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className="text-blue-700 font-semibold">&gt; {m.user_message}</span>
                  <span className="text-emerald-700 font-semibold">{m.latency_ms}ms</span>
                </div>
                <div className="text-xs text-slate-800 whitespace-pre-line leading-relaxed">{m.assistant_message}</div>

                {m.pending_approval && (
                  <div className="p-2.5 rounded bg-amber-50 border border-amber-200 space-y-2">
                    <div className="text-xs font-semibold text-amber-900">{m.pending_approval.title}</div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleApproval(m.pending_approval!.approval_id, true)}
                        className="px-2.5 py-1 rounded text-xs bg-emerald-700 hover:bg-emerald-600 text-white flex items-center gap-1"
                      >
                        <Check className="w-3.5 h-3.5" /> Approve & Execute
                      </button>
                      <button
                        onClick={() => handleApproval(m.pending_approval!.approval_id, false)}
                        className="px-2.5 py-1 rounded text-xs bg-red-600 hover:bg-red-500 text-white flex items-center gap-1"
                      >
                        <X className="w-3.5 h-3.5" /> Reject
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="p-2.5 border-t border-slate-200 bg-white flex items-center gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendCommand()}
              placeholder="Speak or type command..."
              className="flex-1 bg-slate-50 border border-slate-300 rounded px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-blue-600"
            />
            <button
              onClick={() => sendCommand()}
              disabled={loading}
              className="px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white text-xs font-medium flex items-center gap-1"
            >
              <Send className="w-3.5 h-3.5" /> Send
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
};
