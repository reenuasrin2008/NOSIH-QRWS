import { DisasterEvent, DisasterPreset, DisasterType, ServerPayload, StrategyType } from "../types/simulation";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `HTTP ${res.status}`);
  }
  return res.json();
}

export interface UiCommandMessage {
  type: "ui_command";
  action: string;
  payload: Record<string, unknown>;
}

export const api = {
  getScenario: () => request<ServerPayload>("/api/scenarios"),
  generateScenario: (body: { seed: number; city_density?: number; building_density?: number; strategy?: StrategyType }) =>
    request<ServerPayload>("/api/scenarios/generate", { method: "POST", body: JSON.stringify(body) }),
  startSim: () => request<ServerPayload>("/api/simulation/start", { method: "POST" }),
  pauseSim: () => request<ServerPayload>("/api/simulation/pause", { method: "POST" }),
  resumeSim: () => request<ServerPayload>("/api/simulation/resume", { method: "POST" }),
  stepSim: () => request<ServerPayload>("/api/simulation/step", { method: "POST" }),
  resetSim: () => request<ServerPayload>("/api/simulation/reset", { method: "POST" }),
  setSpeed: (speed: number) => request<{ speed: number }>("/api/simulation/speed", { method: "POST", body: JSON.stringify({ speed }) }),
  startBenchmark: () => request<ServerPayload>("/api/benchmarks/start", { method: "POST" }),
  switchView: (strategy: StrategyType) =>
    request<ServerPayload>("/api/benchmarks/view", { method: "POST", body: JSON.stringify({ strategy }) }),
  createTask: (body: Record<string, unknown>) =>
    request<{ created: unknown; state: ServerPayload }>("/api/tasks", { method: "POST", body: JSON.stringify(body) }),
  setDroneWaypoint: (droneId: string, destination: [number, number, number]) =>
    request<{ result: unknown; state: ServerPayload }>(`/api/drones/${droneId}/waypoint`, {
      method: "POST", body: JSON.stringify({ destination }),
    }),
  injectFailure: (droneId: string, failure_type: string, scope: "all" | "selected") =>
    request<{ result: unknown; state: ServerPayload }>(`/api/drones/${droneId}/failure`, {
      method: "POST", body: JSON.stringify({ failure_type, scope }),
    }),
  returnToBase: (droneId: string) => request<ServerPayload>(`/api/drones/${droneId}/rtb`, { method: "POST" }),
  injectEnvEvent: (event_kind: string, params: Record<string, unknown> = {}) =>
    request<{ result: unknown; state: ServerPayload }>("/api/environment/events", {
      method: "POST", body: JSON.stringify({ event_kind, params }),
    }),

  // Disaster Lifecycle Studio APIs
  listDisasters: () => request<DisasterEvent[]>("/api/disasters"),
  listDisasterPresets: () => request<DisasterPreset[]>("/api/disasters/presets"),
  createDisaster: (body: {
    type: DisasterType; x: number; z: number; severity: number;
    affected_radius: number; duration: number; propagation_speed: number;
    start_delay?: number; auto_start?: boolean; magnitude?: number;
  }) => request<{ disaster: DisasterEvent; state_version: number }>("/api/disasters", { method: "POST", body: JSON.stringify(body) }),
  loadDisasterPreset: (preset_id: string) =>
    request<{ disasters: DisasterEvent[] }>("/api/disasters/preset", { method: "POST", body: JSON.stringify({ preset_id }) }),
  triggerRandomDisaster: () =>
    request<{ disasters: DisasterEvent[] }>("/api/disasters/random", { method: "POST", body: JSON.stringify({}) }),
  startDisaster: (id: string) => request<{ disaster: DisasterEvent }>(`/api/disasters/${id}/start`, { method: "POST" }),
  pauseDisaster: (id: string) => request<{ disaster: DisasterEvent }>(`/api/disasters/${id}/pause`, { method: "POST" }),
  resumeDisaster: (id: string) => request<{ disaster: DisasterEvent }>(`/api/disasters/${id}/resume`, { method: "POST" }),
  stopDisaster: (id: string) => request<{ disaster: DisasterEvent }>(`/api/disasters/${id}/stop`, { method: "POST" }),
  removeDisaster: (id: string) => request<{ removed: boolean }>(`/api/disasters/${id}`, { method: "DELETE" }),
  resetDisaster: (id: string) => request<{ disaster: DisasterEvent }>(`/api/disasters/${id}/reset`, { method: "POST" }),
  adjustDisasterSeverity: (id: string, delta: number) =>
    request<{ disaster: DisasterEvent }>(`/api/disasters/${id}/severity`, { method: "POST", body: JSON.stringify({ delta }) }),
  triggerAftershock: (id: string) =>
    request<{ disaster: DisasterEvent }>(`/api/disasters/${id}/aftershock`, { method: "POST", body: JSON.stringify({ scale: 0.65 }) }),

  // JSON Experiment Archive & Replay
  saveExperiment: () => request<{ saved: boolean; run_id: string }>("/api/experiments/save", { method: "POST" }),
  listExperiments: () => request<Array<{ run_id: string; scenario_id: string; seed: number; strategy: string; status: string; sim_time_s: number; score: number; created_at: string }>>("/api/experiments"),
  getSavedReplay: (runId: string) => request<{ frames: Array<{ t: number; drones: Record<string, { pos: [number, number, number]; status: string; bat: number; hdg: number }>; tasks: Record<string, string> }>; run_id: string }>(`/api/experiments/${runId}/replay`),
  getReplay: () => request<{ frames: Array<{ t: number; drones: Record<string, { pos: [number, number, number]; status: string; bat: number; hdg: number }>; tasks: Record<string, string> }>; run_id: string }>("/api/experiments/current/replay"),
  exportZipUrl: () => "/api/experiments/current/export?fmt=zip",
  exportJsonUrl: () => "/api/experiments/current/export?fmt=json",
  getConfig: () => request<{ weights: Record<string, number>; qaoa: Record<string, number> }>("/api/config"),
  updateConfig: (body: Record<string, number>) => request<{ weights: Record<string, number>; qaoa: Record<string, number> }>("/api/config", { method: "POST", body: JSON.stringify(body) }),
  syncUi: (action: string, payload: Record<string, unknown> = {}) =>
    fetch("/api/ui/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, payload }),
    }).catch(() => {}),
};

export function createSimWebSocket(
  onMessage: (payload: ServerPayload) => void,
  onStatus: (connected: boolean) => void,
  onUiCommand?: (cmd: UiCommandMessage) => void
) {
  let ws: WebSocket | null = null;
  let closed = false;
  const connect = () => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${window.location.host}/ws/simulation`);
    ws.onopen = () => onStatus(true);
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data && data.type === "ui_command") {
          onUiCommand?.(data as UiCommandMessage);
        } else if (data && data.benchmark) {
          onMessage(data as ServerPayload);
        }
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => {
      onStatus(false);
      if (!closed) setTimeout(connect, 1800);
    };
    ws.onerror = () => ws?.close();
  };
  connect();
  return () => { closed = true; ws?.close(); };
}
