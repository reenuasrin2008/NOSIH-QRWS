import React, { useEffect, useRef } from "react";

export type OrbState = "IDLE" | "THINKING" | "EXECUTING" | "VERIFIED" | "ALERT" | "VOICE";

interface AiCoreOrbProps {
  state: OrbState;
  activeTool?: string;
  providerLabel?: string;
  voiceListening?: boolean;
}

const PALETTES: Record<OrbState, { core: string; mid: string; glow: string; ring: string; label: string }> = {
  IDLE:      { core: "#fef08a", mid: "#f59e0b", glow: "rgba(245,158,11,0.35)", ring: "#fbbf24", label: "STANDBY · MONITORING" },
  THINKING:  { core: "#fffbeb", mid: "#fbbf24", glow: "rgba(251,191,36,0.62)", ring: "#fde047", label: "NEURAL REASONING" },
  EXECUTING: { core: "#fff7ed", mid: "#f97316", glow: "rgba(249,115,22,0.68)", ring: "#fb923c", label: "EXECUTING TOOL" },
  VERIFIED:  { core: "#ecfdf5", mid: "#10b981", glow: "rgba(16,185,129,0.58)", ring: "#34d399", label: "STATE VERIFIED" },
  ALERT:     { core: "#fef2f2", mid: "#ef4444", glow: "rgba(239,68,68,0.62)",  ring: "#f87171", label: "ALERT / INTERRUPTED" },
  VOICE:     { core: "#fffbeb", mid: "#eab308", glow: "rgba(234,179,8,0.65)",  ring: "#fde047", label: "VOICE LINK ACTIVE" },
};

export const AiCoreOrb: React.FC<AiCoreOrbProps> = ({
  state,
  activeTool,
  providerLabel,
  voiceListening,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<OrbState>(state);
  const audioLevelRef = useRef<number>(0);
  const shockRef = useRef<number>(0);

  useEffect(() => {
    stateRef.current = state;
    if (state === "EXECUTING" || state === "VERIFIED" || state === "ALERT") {
      shockRef.current = 1.0;
    }
  }, [state, activeTool]);

  // Optional live microphone amplitude modulation when voice listening is active
  useEffect(() => {
    if (!voiceListening || !navigator.mediaDevices?.getUserMedia) {
      audioLevelRef.current = 0;
      return;
    }
    let cancelled = false;
    let ctx: AudioContext | null = null;
    let stream: MediaStream | null = null;
    let raf = 0;

    navigator.mediaDevices.getUserMedia({ audio: true }).then((s) => {
      if (cancelled) {
        s.getTracks().forEach((t) => t.stop());
        return;
      }
      stream = s;
      ctx = new AudioContext();
      const src = ctx.createMediaStreamSource(s);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      src.connect(analyser);
      const buf = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        if (cancelled) return;
        analyser.getByteFrequencyData(buf);
        const avg = buf.reduce((a, b) => a + b, 0) / Math.max(1, buf.length);
        audioLevelRef.current = Math.min(1, avg / 95);
        raf = requestAnimationFrame(tick);
      };
      tick();
    }).catch(() => {
      audioLevelRef.current = 0;
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
      ctx?.close().catch(() => {});
    };
  }, [voiceListening]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Deterministic 3D spherical neural nodes
    const nodes = Array.from({ length: 42 }, (_, i) => {
      const phi = Math.acos(1 - (2 * (i + 0.5)) / 42);
      const theta = Math.PI * (1 + Math.sqrt(5)) * i;
      return { phi, theta, r: 0.72 + (i % 4) * 0.08 };
    });

    let raf = 0;
    let t = 0;

    const render = () => {
      const st = stateRef.current;
      const pal = PALETTES[st];
      const speed = st === "EXECUTING" ? 0.055 : st === "THINKING" ? 0.038 : st === "VOICE" ? 0.032 : 0.012;
      t += speed;
      shockRef.current = Math.max(0, shockRef.current - 0.025);

      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = canvas.clientWidth || 220;
      const h = canvas.clientHeight || 165;
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const cx = w / 2;
      const cy = h / 2;
      const baseR = Math.min(w, h) * 0.36;
      const breath = 1 + Math.sin(t * 2.2) * 0.04 + audioLevelRef.current * 0.16;
      const R = baseR * breath;

      // Ambient holographic aura
      const aura = ctx.createRadialGradient(cx, cy, R * 0.1, cx, cy, R * 1.45);
      aura.addColorStop(0, pal.core);
      aura.addColorStop(0.28, pal.mid);
      aura.addColorStop(0.65, pal.glow);
      aura.addColorStop(1, "rgba(8,12,18,0)");
      ctx.fillStyle = aura;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 1.45, 0, Math.PI * 2);
      ctx.fill();

      // Concentric segmented JARVIS-style holographic rings
      const rings = [
        { rad: R * 1.12, segs: 12, dir: 1, width: 1.4, alpha: 0.55 },
        { rad: R * 0.92, segs: 8, dir: -1.35, width: 2.1, alpha: 0.78 },
        { rad: R * 0.72, segs: 6, dir: 1.8, width: 1.6, alpha: 0.85 },
        { rad: R * 0.46, segs: 4, dir: -2.4, width: 2.2, alpha: 0.92 },
      ];

      rings.forEach((rg, idx) => {
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(t * rg.dir + idx * 0.8);
        ctx.strokeStyle = pal.ring;
        ctx.lineWidth = rg.width;
        ctx.globalAlpha = rg.alpha;
        const step = (Math.PI * 2) / rg.segs;
        for (let s = 0; s < rg.segs; s++) {
          ctx.beginPath();
          ctx.arc(0, 0, rg.rad, s * step + 0.08, (s + 0.68) * step);
          ctx.stroke();
        }
        ctx.restore();
      });

      // 3D Projected Orbiting Neural Filaments & Nodes
      const projected = nodes.map((n) => {
        const th = n.theta + t * 0.9;
        const x3 = Math.sin(n.phi) * Math.cos(th) * R * n.r;
        const y3 = Math.cos(n.phi) * R * n.r * 0.88;
        const z3 = Math.sin(n.phi) * Math.sin(th);
        return { x: cx + x3, y: cy + y3, z: z3 };
      });

      ctx.strokeStyle = pal.mid;
      ctx.lineWidth = 0.7;
      for (let i = 0; i < projected.length; i++) {
        const a = projected[i];
        const b = projected[(i + 5) % projected.length];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (dist < R * 0.95) {
          ctx.globalAlpha = Math.max(0.08, (a.z + 1.2) * 0.22);
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }

      projected.forEach((p) => {
        ctx.globalAlpha = Math.max(0.25, (p.z + 1.1) * 0.48);
        ctx.fillStyle = p.z > 0.2 ? pal.core : pal.ring;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.z > 0.2 ? 2.1 : 1.3, 0, Math.PI * 2);
        ctx.fill();
      });

      // Expanding kinetic shockwave ring on tool execution / verification / alert
      if (shockRef.current > 0.01) {
        const prog = 1 - shockRef.current;
        ctx.globalAlpha = shockRef.current * 0.85;
        ctx.strokeStyle = pal.core;
        ctx.lineWidth = 2.4 * shockRef.current;
        ctx.beginPath();
        ctx.arc(cx, cy, R * (0.55 + prog * 0.95), 0, Math.PI * 2);
        ctx.stroke();
      }

      // Incandescent core nucleus
      ctx.globalAlpha = 1;
      const coreGrad = ctx.createRadialGradient(cx, cy, 1, cx, cy, R * 0.34);
      coreGrad.addColorStop(0, "#ffffff");
      coreGrad.addColorStop(0.45, pal.core);
      coreGrad.addColorStop(1, "rgba(245,158,11,0)");
      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 0.34, 0, Math.PI * 2);
      ctx.fill();

      raf = requestAnimationFrame(render);
    };

    raf = requestAnimationFrame(render);
    return () => cancelAnimationFrame(raf);
  }, []);

  const pal = PALETTES[state];

  return (
    <div className="relative bg-[#070b11] border border-amber-500/35 overflow-hidden p-2">
      <div className="flex items-center justify-between text-[9px] mb-1">
        <span className="font-bold tracking-wider" style={{ color: pal.ring }}>
          {pal.label}
        </span>
        <span className="text-zinc-400">{providerLabel || "AUTO"}</span>
      </div>
      <canvas ref={canvasRef} className="w-full h-36 block" />
      {activeTool && (
        <div className="mt-1 px-2 py-0.5 bg-amber-950/50 border border-amber-500/40 text-[9px] text-amber-200 text-center truncate">
          ACTIVE TOOL: {activeTool}
        </div>
      )}
    </div>
  );
};
