export interface KeySlotStatus {
  index: number;
  alias: string;
  masked_key: string;
  configured: boolean;
  health: string;
  consecutive_failures: number;
  last_success_at: string | null;
  cooldown_remaining_s: number;
  rate_limited: boolean;
  request_count: number;
  avg_latency_ms: number;
  last_error_kind: string | null;
}

export interface ProviderPoolStatus {
  provider: string;
  active_key_index: number;
  active_key_alias: string;
  healthy_keys: number;
  configured_keys: number;
  model_id: string;
  keys: KeySlotStatus[];
}

export interface AgentRuntimeStatus {
  mode: "OBSERVE" | "ASSISTED" | "AUTONOMOUS";
  paused: boolean;
  active_execution_id: string | null;
  pending_approvals_count: number;
  last_verified_at: string | null;
  registered_tools_count: number;
  ws_observer?: {
    connected: boolean;
    last_world_version: number;
    reconnect_attempts: number;
  };
  providers: {
    mode: "GROK" | "GEMINI" | "AUTO";
    last_provider: string | null;
    grok: ProviderPoolStatus;
    gemini: ProviderPoolStatus;
  };
}

export interface ToolExecutionRecord {
  execution_id: string;
  tool_call_id: string;
  tool: string;
  provider: string;
  key_alias: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_ms: number;
  state_version_before: number;
  state_version_after: number;
  arguments: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface PendingAction {
  action_id: string;
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  permission_level: string;
  reason: string;
  status: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
}

export interface ExecutionTrace {
  execution_id: string;
  session_id: string;
  user_message: string;
  mode: string;
  provider_mode: string;
  provider_used: string;
  key_alias_used: string;
  provider_switches: string[];
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_ms: number;
  tool_records: ToolExecutionRecord[];
  pending_actions: PendingAction[];
  final_response: string;
  recommended: string[];
  executed: string[];
  verified: string[];
  incomplete: string[];
  error: string | null;
}

const AGENT_BASE =
  (window.location.port === "5175" || window.location.port === "5174") ? "/agent-api" : "http://127.0.0.1:8001/api/agent";

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${AGENT_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `HTTP ${res.status}`);
  }
  return res.json();
}

export const agentApi = {
  getStatus: () => req<AgentRuntimeStatus>("/status"),
  setMode: (mode: "OBSERVE" | "ASSISTED" | "AUTONOMOUS") =>
    req<{ mode: string }>("/mode", { method: "POST", body: JSON.stringify({ mode }) }),
  setProviderMode: (mode: "GROK" | "GEMINI" | "AUTO") =>
    req<{ mode: string }>("/providers/mode", { method: "POST", body: JSON.stringify({ mode }) }),
  sendChat: (body: { message: string; session_id?: string; mode?: string; provider_mode?: string }) =>
    req<ExecutionTrace>("/chat", { method: "POST", body: JSON.stringify(body) }),
  approveActions: (executionId: string, actionIds?: string[]) =>
    req<ExecutionTrace>(`/approvals/${executionId}/approve`, {
      method: "POST",
      body: JSON.stringify({ action_ids: actionIds }),
    }),
  rejectActions: (executionId: string) =>
    req<ExecutionTrace>(`/approvals/${executionId}/reject`, { method: "POST" }),
  stopExecution: () => req<{ stop_requested: boolean }>("/stop", { method: "POST" }),
  pauseAgent: () => req<{ paused: boolean }>("/pause", { method: "POST" }),
  resumeAgent: () => req<{ paused: boolean }>("/resume", { method: "POST" }),
  getCurrentSession: () =>
    req<{ session_id: string; messages: Array<{ role: string; content: string; execution_id?: string; timestamp?: string }> }>("/sessions/current"),
  createSession: () =>
    req<{ session_id: string }>("/sessions", { method: "POST", body: JSON.stringify({}) }),
  listExecutions: () =>
    req<Array<{ execution_id: string; user_message: string; status: string; provider_used: string; tool_count: number; duration_ms: number; started_at: string }>>("/executions"),
  executionJsonUrl: (executionId: string) => `${AGENT_BASE}/executions/${executionId}`,
};

export function createAgentWebSocket(
  onEvent: (msg: { type: string; timestamp?: string; payload: Record<string, unknown> }) => void,
  onStatus: (connected: boolean) => void
) {
  let ws: WebSocket | null = null;
  let closed = false;
  const connect = () => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url =
      window.location.port === "5175"
        ? `${proto}//${window.location.host}/agent-ws`
        : "ws://127.0.0.1:8001/ws/agent";
    ws = new WebSocket(url);
    ws.onopen = () => onStatus(true);
    ws.onmessage = (ev) => {
      try {
        onEvent(JSON.parse(ev.data));
      } catch {
        /* ignore */
      }
    };
    ws.onclose = () => {
      onStatus(false);
      if (!closed) setTimeout(connect, 2000);
    };
    ws.onerror = () => ws?.close();
  };
  connect();
  return () => {
    closed = true;
    ws?.close();
  };
}
