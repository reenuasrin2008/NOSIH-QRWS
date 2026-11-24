import { ServerPayload, StrategyType } from "../types/simulation";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
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
  let reconnectTimer: number | undefined;
  let retryDelayMs = 1000;
  const MAX_RETRY_MS = 15000;

  const connect = () => {
    if (closed) return;
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${window.location.host}/ws/simulation`);
    ws.onopen = () => {
      retryDelayMs = 1000;
      onStatus(true);
    };
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data && (data.type === "ui_command" || data.type === "ui_sync")) {
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
      if (!closed) {
        reconnectTimer = window.setTimeout(connect, retryDelayMs);
        retryDelayMs = Math.min(MAX_RETRY_MS, retryDelayMs * 2);
      }
    };
    ws.onerror = () => ws?.close();
  };
  connect();
  return () => {
    closed = true;
    if (reconnectTimer !== undefined) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = undefined;
    }
    ws?.close();
  };
}
