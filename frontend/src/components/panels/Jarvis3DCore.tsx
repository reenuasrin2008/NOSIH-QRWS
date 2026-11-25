import React, { useEffect, useRef } from "react";
import { Canvas } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import * as THREE from "three";
import { NeuralCoreMesh } from "../jarvis/JarvisNeuralCore3D";

export type JarvisState = "IDLE" | "LISTENING" | "THINKING" | "EXECUTING" | "SPEAKING" | "VERIFIED" | "ALERT";

interface Jarvis3DCoreProps {
  state: JarvisState;
  speechPulse?: number;
  voiceListening?: boolean;
}

const STATE_COLORS: Record<JarvisState, { core: string; ring: string }> = {
  IDLE:      { core: "#ffae42", ring: "#ffba52" },
  LISTENING: { core: "#ffe08a", ring: "#fff1c2" },
  THINKING:  { core: "#ffbe0b", ring: "#ffd166" },
  EXECUTING: { core: "#ffa62b", ring: "#ffbe63" },
  SPEAKING:  { core: "#ffd06b", ring: "#ffe4a8" },
  VERIFIED:  { core: "#34d399", ring: "#a7f3d0" },
  ALERT:     { core: "#f87171", ring: "#fecaca" },
};

export const Jarvis3DCore: React.FC<Jarvis3DCoreProps> = ({
  state,
  speechPulse = 0,
  voiceListening = false,
}) => {
  const speechEnergyRef = useRef(0);
  const micEnergyRef = useRef(0);

  useEffect(() => {
    if (speechPulse > 0) speechEnergyRef.current = 1.0;
  }, [speechPulse]);

  useEffect(() => {
    if (!voiceListening || !navigator.mediaDevices?.getUserMedia) {
      micEnergyRef.current = 0;
      return;
    }
    let cancelled = false;
    let ctx: AudioContext | null = null;
    let stream: MediaStream | null = null;
    let raf = 0;

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((s) => {
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
          micEnergyRef.current = Math.min(1, avg / 70);
          raf = requestAnimationFrame(tick);
        };
        tick();
      })
      .catch(() => {
        micEnergyRef.current = 0;
      });

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
      ctx?.close().catch(() => {});
    };
  }, [voiceListening]);

  const palette = STATE_COLORS[state] || STATE_COLORS.IDLE;
  const listening = voiceListening || state === "LISTENING";
  const speaking = state === "SPEAKING";
  const thinking = state === "THINKING" || state === "EXECUTING";

  return (
    <div className="absolute inset-0 w-full h-full bg-[#040302] overflow-hidden">
      {/* Stark HUD Frame Hairlines & Spinning Bottom-Right Emblem */}
      <svg className="pointer-events-none absolute inset-0 w-full h-full z-10 opacity-65" preserveAspectRatio="none" viewBox="0 0 1200 720">
        {/* Top segmented golden header bar */}
        <rect x="85" y="24" width="690" height="18" fill="#5c3a14" fillOpacity="0.28" stroke="#925c24" strokeWidth="1" />
        <rect x="85" y="42" width="155" height="4" fill="#d99b43" fillOpacity="0.85" />
        <rect x="640" y="26" width="58" height="14" fill="#b45309" fillOpacity="0.55" />
        <rect x="706" y="29" width="58" height="8" fill="#000000" stroke="#78350f" strokeWidth="1" />
        <rect x="748" y="31" width="10" height="4" fill="#fbbf24" />
        {/* Left-mid horizontal double accent bar */}
        <rect x="0" y="210" width="315" height="6" fill="#d99b43" fillOpacity="0.45" />
        <line x1="0" y1="220" x2="290" y2="220" stroke="#f59e0b" strokeWidth="1.2" strokeOpacity="0.55" />
        {/* Thin right & bottom-left framing brackets */}
        <polyline points="870,155 1095,155 1095,620" fill="none" stroke="#78491b" strokeWidth="1" />
        <polyline points="125,520 125,630 290,630" fill="none" stroke="#78491b" strokeWidth="1" />
        {/* Bottom segmented bronze bar */}
        <rect x="40" y="688" width="995" height="8" fill="#4a2e10" fillOpacity="0.35" stroke="#78491b" strokeWidth="0.8" />
        <rect x="720" y="688" width="315" height="8" fill="#b4732a" fillOpacity="0.48" />
        {/* Spinning bottom-right miniature Stark radial emblem */}
        <g transform="translate(1140, 672)">
          <circle r="30" fill="none" stroke="#b45309" strokeWidth="1.4" strokeDasharray="8 6">
            <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="14s" repeatCount="indefinite" />
          </circle>
          <circle r="19" fill="none" stroke="#f59e0b" strokeWidth="3.2" strokeDasharray="16 8">
            <animateTransform attributeName="transform" type="rotate" from="360" to="0" dur="9s" repeatCount="indefinite" />
          </circle>
          <circle r="8" fill="none" stroke="#fef08a" strokeWidth="1.8" />
          <circle r="3.5" fill="#fffbeb" />
        </g>
      </svg>

      <Canvas
        camera={{ position: [0, 0.35, 5.2], fov: 44 }}
        gl={{ antialias: true, powerPreference: "high-performance", toneMapping: THREE.ACESFilmicToneMapping }}
      >
        <color attach="background" args={["#040302"]} />
        <NeuralCoreMesh
          listening={listening}
          speaking={speaking}
          thinking={thinking}
          speechEnergyRef={speechEnergyRef}
          micEnergyRef={micEnergyRef}
          coreColor={palette.core}
          ringColor={palette.ring}
        />
        <EffectComposer>
          <Bloom intensity={1.15} luminanceThreshold={0.15} luminanceSmoothing={0.85} mipmapBlur />
        </EffectComposer>
      </Canvas>
    </div>
  );
};
