import React, { useRef, useEffect, useCallback } from "react";
import { useSimStore } from "../../state/simulationStore";

interface LiveWorldMapProps {
  width?: number;
  height?: number;
  className?: string;
}

const WORLD_SIZE = 4000;

/** Colour lookup for drone types */
const DRONE_COLORS: Record<string, string> = {
  surveillance: "#e2e8f0",
  medical: "#ef4444",
  heavy_lift: "#eab308",
  search_rescue: "#10b981",
};

/** Colour lookup for disaster types */
const DISASTER_COLORS: Record<string, string> = {
  flood: "#1e64c8",
  earthquake: "#b45309",
  fire: "#ef4444",
  cyclone: "#7c3aed",
  building_collapse: "#78716c",
  landslide: "#92400e",
};

export const LiveWorldMap: React.FC<LiveWorldMapProps> = ({
  width = 320,
  height = 320,
  className,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  // Pull everything from the store once and use the refs below so the rAF
  // closure always reads the latest value without re-subscribing each frame.
  const city = useSimStore((s) => s.city);
  const activeState = useSimStore((s) => s.activeState);
  const aiScanPulses = useSimStore((s) => s.aiScanPulses);
  const aiDispatchBeams = useSimStore((s) => s.aiDispatchBeams);
  const selectedDroneId = useSimStore((s) => s.selectedDroneId);
  const selectDrone = useSimStore((s) => s.selectDrone);

  // Keep mutable refs so the rAF loop always has fresh data.
  const cityRef = useRef(city);
  const stateRef = useRef(activeState);
  const pulsesRef = useRef(aiScanPulses);
  const beamsRef = useRef(aiDispatchBeams);
  const selectedRef = useRef(selectedDroneId);

  useEffect(() => { cityRef.current = city; }, [city]);
  useEffect(() => { stateRef.current = activeState; }, [activeState]);
  useEffect(() => { pulsesRef.current = aiScanPulses; }, [aiScanPulses]);
  useEffect(() => { beamsRef.current = aiDispatchBeams; }, [aiDispatchBeams]);
  useEffect(() => { selectedRef.current = selectedDroneId; }, [selectedDroneId]);

  // ─── Draw ───────────────────────────────────────────────────────────────────
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = width;
    const H = height;
    const scale = W / WORLD_SIZE;
    const now = Date.now();

    const city = cityRef.current;
    const state = stateRef.current;

    // ── 1. Background ────────────────────────────────────────────────────────
    ctx.fillStyle = "#0b1120";
    ctx.fillRect(0, 0, W, H);

    if (!city) {
      // No data yet — just show background
      ctx.fillStyle = "#10b981";
      ctx.font = "9px monospace";
      ctx.fillText("AWAITING DATA…", 8, 16);
      return;
    }

    // ── 2. Buildings ─────────────────────────────────────────────────────────
    ctx.fillStyle = "#1e2a3a";
    for (const b of city.buildings) {
      const bw = b.width * scale;
      const bd = b.depth * scale;
      if (bw < 1 || bd < 1) continue;
      ctx.fillRect(b.x * scale - bw / 2, b.z * scale - bd / 2, bw, bd);
    }

    // ── 3. Roads ─────────────────────────────────────────────────────────────
    for (const r of city.roads) {
      ctx.beginPath();
      ctx.strokeStyle = "#2a3a50";
      ctx.lineWidth = r.width > 30 ? 1.5 : 1;
      ctx.moveTo(r.start[0] * scale, r.start[1] * scale);
      ctx.lineTo(r.end[0] * scale, r.end[1] * scale);
      ctx.stroke();
    }

    // ── 4. River ─────────────────────────────────────────────────────────────
    const riverY = (city.river_z - city.river_width / 2) * scale;
    const riverH = city.river_width * scale;
    ctx.fillStyle = "#1e3a5f";
    ctx.fillRect(0, riverY, W, riverH);

    if (!state) return;

    // ── 5. Hazard zones ───────────────────────────────────────────────────────
    for (const hz of state.hazards) {
      if (!hz.active) continue;
      const cx = hz.x * scale;
      const cy = hz.z * scale;
      const r = hz.radius * scale;

      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);

      if (hz.kind === "flood") {
        ctx.fillStyle = "rgba(30,100,200,0.18)";
        ctx.fill();
      } else if (hz.kind === "fire") {
        ctx.fillStyle = "rgba(220,50,30,0.22)";
        ctx.fill();
      } else if (hz.kind === "no_fly") {
        ctx.fillStyle = "rgba(220,180,0,0.14)";
        ctx.fill();
        ctx.setLineDash([3, 3]);
        ctx.strokeStyle = "rgba(220,180,0,0.5)";
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.setLineDash([]);
      } else {
        ctx.fillStyle = "rgba(100,100,100,0.15)";
        ctx.fill();
      }
    }

    // ── 6. Disaster zones ────────────────────────────────────────────────────
    if (state.disasters) {
      for (const ev of state.disasters) {
        if (ev.status === "resolved") continue;
        const cx = ev.epicentre.x * scale;
        const cy = ev.epicentre.z * scale;
        // Animate radius ±5% using a sine wave
        const pulse = 1 + 0.05 * Math.sin(now / 600);
        const r = ev.affected_radius * scale * pulse;
        const color = DISASTER_COLORS[ev.type] ?? "#ffffff";

        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.globalAlpha = 0.7;
        ctx.stroke();
        ctx.globalAlpha = 1;

        // Inner fill
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.08;
        ctx.fill();
        ctx.globalAlpha = 1;
      }
    }

    // ── 7. AI scan pulses ────────────────────────────────────────────────────
    for (const pulse of pulsesRef.current) {
      const age = now - pulse.createdAt;
      const maxAge = 10000;
      if (age > maxAge) continue;

      const cx = pulse.point[0] * scale;
      const cy = pulse.point[2] * scale;
      const progress = age / maxAge; // 0→1
      const r = pulse.radius * scale * progress;
      const alpha = (1 - progress) * 0.7;

      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(0,255,220,${alpha})`;
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // ── 8. AI dispatch beams ─────────────────────────────────────────────────
    for (const beam of beamsRef.current) {
      const age = now - beam.createdAt;
      if (age > 10000) continue;
      const alpha = Math.max(0, 1 - age / 10000);

      ctx.beginPath();
      ctx.moveTo(beam.from[0] * scale, beam.from[2] * scale);
      ctx.lineTo(beam.to[0] * scale, beam.to[2] * scale);
      ctx.strokeStyle = `rgba(250,204,21,${alpha * 0.85})`;
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // ── 9. Tasks ─────────────────────────────────────────────────────────────
    for (const task of state.tasks) {
      const tx = task.location[0] * scale - 2;
      const ty = task.location[2] * scale - 2;
      let color = "#f59e0b"; // pending
      if (task.status === "in_progress") color = "#3b82f6";
      else if (task.status === "completed") color = "#10b981";
      else if (task.status === "failed") color = "#ef4444";

      ctx.fillStyle = color;
      ctx.fillRect(tx, ty, 4, 4);
    }

    // ── 10. Survivors ────────────────────────────────────────────────────────
    if (state.survivors) {
      ctx.fillStyle = "#ec4899";
      for (const sv of state.survivors) {
        if (!sv.detected) continue;
        const sx = sv.position[0] * scale;
        const sy = sv.position[2] * scale;
        ctx.beginPath();
        ctx.arc(sx, sy, 2, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // ── 11. Drones ───────────────────────────────────────────────────────────
    const selectedId = selectedRef.current;
    for (const drone of state.drones) {
      const dx = drone.position[0] * scale;
      const dy = drone.position[2] * scale;
      const isSelected = drone.id === selectedId;

      if (drone.status === "DESTROYED") {
        // Dark red X
        ctx.strokeStyle = "#7f1d1d";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(dx - 3, dy - 3);
        ctx.lineTo(dx + 3, dy + 3);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(dx + 3, dy - 3);
        ctx.lineTo(dx - 3, dy + 3);
        ctx.stroke();
        continue;
      }

      // White ring for selected drone
      if (isSelected) {
        ctx.beginPath();
        ctx.arc(dx, dy, 10, 0, Math.PI * 2);
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // Triangle pointing in heading direction
      const heading = drone.heading_rad ?? 0;
      const size = 6;
      const color = DRONE_COLORS[drone.drone_type] ?? "#e2e8f0";

      ctx.save();
      ctx.translate(dx, dy);
      ctx.rotate(heading);
      ctx.beginPath();
      ctx.moveTo(0, -size);
      ctx.lineTo(size * 0.6, size * 0.7);
      ctx.lineTo(-size * 0.6, size * 0.7);
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();
      ctx.restore();

      // Label for selected drone
      if (isSelected) {
        const label = `${drone.id} · ${drone.status}`;
        ctx.font = "7px monospace";
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.fillText(label, dx, dy - 14);
        ctx.textAlign = "left";
      }
    }

    // ── 12. Stations ─────────────────────────────────────────────────────────
    for (const st of state.stations) {
      const sx = st.position[0] * scale;
      const sy = st.position[2] * scale;
      ctx.beginPath();
      ctx.arc(sx, sy, 5, 0, Math.PI * 2);
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1;
      ctx.stroke();

      if (st.kind === "hospital") {
        // Red cross
        ctx.strokeStyle = "#ef4444";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(sx - 3, sy);
        ctx.lineTo(sx + 3, sy);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(sx, sy - 3);
        ctx.lineTo(sx, sy + 3);
        ctx.stroke();
      }
    }

    // Also draw city.stations in case state.stations is empty
    for (const st of city.stations) {
      // Avoid double-drawing if station is already in state
      const alreadyDrawn = state.stations.some((s) => s.id === st.id);
      if (alreadyDrawn) continue;

      const sx = st.position[0] * scale;
      const sy = st.position[2] * scale;
      ctx.beginPath();
      ctx.arc(sx, sy, 5, 0, Math.PI * 2);
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1;
      ctx.stroke();

      if (st.kind === "hospital") {
        ctx.strokeStyle = "#ef4444";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(sx - 3, sy);
        ctx.lineTo(sx + 3, sy);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(sx, sy - 3);
        ctx.lineTo(sx, sy + 3);
        ctx.stroke();
      }
    }

    // ── 13. HUD overlay ───────────────────────────────────────────────────────
    const droneCount = state.drones.filter((d) => d.status !== "DESTROYED").length;
    const taskCount = state.tasks.filter((t) => t.status !== "completed").length;
    ctx.font = "9px monospace";
    ctx.fillStyle = "#10b981";
    ctx.textAlign = "left";
    ctx.fillText(`LIVE · ${droneCount} DRONES · ${taskCount} TASKS`, 6, 14);

    // ── 14. Compass ───────────────────────────────────────────────────────────
    const cx = W - 16;
    const cy2 = 16;
    // Arrow shaft
    ctx.beginPath();
    ctx.moveTo(cx, cy2 + 6);
    ctx.lineTo(cx, cy2 - 6);
    ctx.strokeStyle = "#e2e8f0";
    ctx.lineWidth = 1;
    ctx.stroke();
    // Arrowhead
    ctx.beginPath();
    ctx.moveTo(cx, cy2 - 6);
    ctx.lineTo(cx - 3, cy2 - 1);
    ctx.lineTo(cx + 3, cy2 - 1);
    ctx.closePath();
    ctx.fillStyle = "#e2e8f0";
    ctx.fill();
    // N label
    ctx.font = "7px monospace";
    ctx.fillStyle = "#e2e8f0";
    ctx.textAlign = "center";
    ctx.fillText("N", cx, cy2 + 16);
    ctx.textAlign = "left";
  }, [width, height]);

  // ─── Animation loop ──────────────────────────────────────────────────────
  useEffect(() => {
    const loop = () => {
      draw();
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [draw]);

  // ─── Click handler ────────────────────────────────────────────────────────
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const state = stateRef.current;
      if (!state) return;

      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const mx = (e.clientX - rect.left) * (width / rect.width);
      const my = (e.clientY - rect.top) * (height / rect.height);
      const scale = width / WORLD_SIZE;

      let nearest: string | null = null;
      let nearestDist = 12; // px threshold

      for (const drone of state.drones) {
        if (drone.status === "DESTROYED") continue;
        const dx = drone.position[0] * scale - mx;
        const dy = drone.position[2] * scale - my;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < nearestDist) {
          nearestDist = dist;
          nearest = drone.id;
        }
      }

      if (nearest) {
        selectDrone(nearest === selectedRef.current ? null : nearest);
      } else {
        selectDrone(null);
      }
    },
    [width, height, selectDrone]
  );

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      onClick={handleClick}
      className={[
        "border border-[#1e2a3a] rounded bg-[#0b1120] cursor-crosshair",
        className ?? "",
      ]
        .join(" ")
        .trim()}
      style={{ display: "block" }}
    />
  );
};
