import type {
  ApprovalItem,
  GlobalOverview,
  JarvisReply,
  ProviderStatusPayload,
} from "./globalTypes";

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export const globalApi = {
  getOverview: () => req<GlobalOverview>("/api/world/overview"),
  getCountry: (countryId: string) => req<any>(`/api/countries/${countryId}`),
  updateCountry: (countryId: string, body: Record<string, any>) =>
    req<any>(`/api/countries/${countryId}`, { method: "PATCH", body: JSON.stringify(body) }),
  tickWorld: (dtSeconds = 60) => req<any>(`/api/world/tick?dt_seconds=${dtSeconds}`, { method: "POST" }),
  emergencyStop: () => req<any>("/api/world/emergency-stop", { method: "POST" }),
  emergencyResume: () => req<any>("/api/world/emergency-resume", { method: "POST" }),

  createDisaster: (body: Record<string, any>) =>
    req<any>("/api/disasters", { method: "POST", body: JSON.stringify(body) }),
  stopDisaster: (eventId: string) =>
    req<any>(`/api/disasters/${eventId}/stop`, { method: "POST" }),
  getCascade: (countryId: string) => req<any>(`/api/disasters/cascade/${countryId}`),

  getGlobalDrones: (countryId?: string) =>
    req<{ drones: any[]; count: number }>(
      countryId ? `/api/global/drones?country_id=${countryId}` : "/api/global/drones"
    ),
  prepareDroneDestroy: (droneId: string) =>
    req<ApprovalItem>(`/api/global/drones/${droneId}/destroy/prepare`, { method: "POST" }),
  prepareSwarm: (body: Record<string, any>) =>
    req<ApprovalItem>("/api/swarms/prepare", { method: "POST", body: JSON.stringify(body) }),
  getSwarms: () => req<{ swarms: any[] }>("/api/swarms"),

  exploreRoutes: (body: Record<string, any>) =>
    req<any>("/api/routes/explore", { method: "POST", body: JSON.stringify(body) }),
  getRouteLogs: () => req<{ logs: any[] }>("/api/routes/logs"),

  runCounterfactual: (countryId: string, whatIf?: Record<string, any>) =>
    req<any>(`/api/counterfactual/${countryId}`, {
      method: "POST",
      body: JSON.stringify(whatIf || {}),
    }),
  getMutualAid: (countryId: string, resourceType = "ambulances") =>
    req<any>(`/api/mutual-aid/${countryId}?resource_type=${resourceType}`),
  prepareMutualAid: (body: Record<string, any>) =>
    req<ApprovalItem>("/api/mutual-aid/prepare", { method: "POST", body: JSON.stringify(body) }),
  getEquity: (countryId: string) => req<any>(`/api/equity/${countryId}`),
  getPlaybooks: () => req<{ playbooks: Array<{ id: string; title: string; category: string }> }>("/api/playbooks"),

  jarvisChat: (message: string, sessionId = "default") =>
    req<JarvisReply>("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
    }),
  getProvidersStatus: () => req<ProviderStatusPayload>("/api/ai/providers/status"),
  getApprovals: (status?: string) =>
    req<{ approvals: ApprovalItem[] }>(status ? `/api/approvals?status=${status}` : "/api/approvals"),
  approveOperation: (approvalId: string, autoExecute = true) =>
    req<ApprovalItem>(`/api/approvals/${approvalId}/approve`, {
      method: "POST",
      body: JSON.stringify({ auto_execute: autoExecute }),
    }),
  rejectOperation: (approvalId: string, note = "Rejected by operator") =>
    req<ApprovalItem>(`/api/approvals/${approvalId}/reject`, {
      method: "POST",
      body: JSON.stringify({ note }),
    }),
  getEvents: (limit = 80) => req<{ world_version: number; events: any[] }>(`/api/events?limit=${limit}`),
  getAuditLogs: () => req<{ audit_log: any[]; tool_logs: any[] }>("/api/audit-logs"),
  ackFrontendCommand: (commandId: string, frontend: string) =>
    req<any>("/api/frontend/commands/ack", {
      method: "POST",
      body: JSON.stringify({ command_id: commandId, frontend }),
    }),
};

export function connectGlobalWebSocket(
  clientName: "quantum-world" | "quantum-operations" | "quantum-jarvis",
  handlers: {
    onSnapshot?: (data: any) => void;
    onWorldEvent?: (event: any) => void;
    onFrontendCommand?: (command: any) => void;
    onConnectionChange?: (connected: boolean) => void;
  }
): () => void {
  let closed = false;
  let ws: WebSocket | null = null;
  let timer: number | undefined;

  const connect = () => {
    if (closed) return;
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${window.location.host}/ws/global?client=${clientName}`;
    ws = new WebSocket(url);
    ws.onopen = () => handlers.onConnectionChange?.(true);
    ws.onclose = () => {
      handlers.onConnectionChange?.(false);
      if (!closed) {
        timer = window.setTimeout(connect, 2000);
      }
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "global_snapshot") handlers.onSnapshot?.(msg);
        else if (msg.type === "world_event") handlers.onWorldEvent?.(msg.event);
        else if (msg.type === "frontend_command") {
          handlers.onFrontendCommand?.(msg.command);
          if (msg.command?.command_id && (msg.command.frontend === clientName || msg.command.frontend === "all")) {
            globalApi.ackFrontendCommand(msg.command.command_id, clientName).catch(() => {});
          }
        }
      } catch {
        // ignore malformed frames
      }
    };
  };

  connect();
  return () => {
    closed = true;
    if (timer) window.clearTimeout(timer);
    ws?.close();
  };
}
