import React, { useMemo, useState } from "react";
import { Search, Terminal } from "lucide-react";

interface LogEntry {
  event_id?: string;
  timestamp: string;
  event_type?: string;
  tool?: string;
  category?: string;
  country_id?: string | null;
  world_version?: number;
  duration_ms?: number;
  status?: string;
  summary?: string;
  payload?: any;
}

interface TacticalLiveLogsPanelProps {
  events: LogEntry[];
  toolLogs?: LogEntry[];
  title?: string;
}

const BADGE_COLORS: Record<string, string> = {
  disaster: "bg-red-50 text-red-700 border-red-200",
  recovery: "bg-amber-50 text-amber-800 border-amber-200",
  approval: "bg-amber-50 text-amber-800 border-amber-200",
  execution: "bg-emerald-50 text-emerald-700 border-emerald-200",
  swarm: "bg-emerald-50 text-emerald-700 border-emerald-200",
  ai_tool: "bg-blue-50 text-blue-700 border-blue-200",
  frontend_sync: "bg-indigo-50 text-indigo-700 border-indigo-200",
  simulation: "bg-slate-100 text-slate-700 border-slate-200",
};

export const TacticalLiveLogsPanel: React.FC<TacticalLiveLogsPanelProps> = ({
  events,
  toolLogs = [],
  title = "LIVE INTELLIGENCE & EXECUTION LOGS",
}) => {
  const [filter, setFilter] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  const merged = useMemo(() => {
    const normalizedTools: LogEntry[] = toolLogs.map((t, i) => ({
      event_id: `TOOL-${i}-${t.timestamp}`,
      timestamp: t.timestamp,
      event_type: t.tool || "ai.tool",
      category: "ai_tool",
      country_id: t.payload?.country_id || null,
      world_version: t.world_version,
      duration_ms: t.duration_ms,
      status: t.status,
      summary: t.summary,
      payload: t,
    }));
    const all = [...normalizedTools, ...events];
    all.sort((a, b) => (b.timestamp || "").localeCompare(a.timestamp || ""));
    return all.filter((item) => {
      const cat = (item.category || "simulation").toLowerCase();
      if (filter !== "all" && cat !== filter) return false;
      if (query.trim()) {
        const hay = `${item.event_type || ""} ${item.summary || ""} ${item.country_id || ""}`.toLowerCase();
        if (!hay.includes(query.toLowerCase())) return false;
      }
      return true;
    });
  }, [events, toolLogs, filter, query]);

  return (
    <div className="w-full h-full bg-white border-t border-slate-200 flex flex-col overflow-hidden">
      {/* Light Header & Filter Strip */}
      <div className="px-3 py-1.5 bg-slate-50 border-b border-slate-200 flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono">
        <div className="flex items-center gap-2 text-slate-800 font-semibold">
          <Terminal className="w-3.5 h-3.5 text-blue-700" />
          <span>{title}</span>
          <span className="text-slate-400 font-normal">({merged.length})</span>
        </div>

        <div className="flex items-center gap-1.5">
          {(["all", "disaster", "ai_tool", "approval", "execution", "recovery"] as const).map((cat) => (
            <button
              key={cat}
              onClick={() => setFilter(cat)}
              className={`px-2 py-0.5 rounded uppercase text-[10px] border ${
                filter === cat
                  ? "bg-blue-50 border-blue-300 text-blue-800 font-semibold"
                  : "bg-white border-slate-200 text-slate-500 hover:text-slate-800"
              }`}
            >
              {cat.replace("_", " ")}
            </button>
          ))}
          <div className="relative ml-1">
            <Search className="w-3 h-3 text-slate-400 absolute left-2 top-1.5" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Filter logs"
              placeholder="Filter logs..."
              className="pl-6 pr-2 py-0.5 rounded bg-white border border-slate-300 text-[11px] text-slate-800 w-36 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>
      </div>

      {/* Crisp Light Monospace Feed */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-100 font-mono text-[11px]">
        {merged.length === 0 && (
          <div className="p-3 text-slate-400">No matching events recorded yet.</div>
        )}
        {merged.slice(0, 80).map((item, idx) => {
          const cat = (item.category || "simulation").toLowerCase();
          const badgeCls = BADGE_COLORS[cat] || BADGE_COLORS.simulation;
          const timeStr = (item.timestamp || "").split("T")[1]?.slice(0, 8) || "--:--:--";
          const isOpen = expandedIdx === idx;
          return (
            <div key={item.event_id || idx} className="hover:bg-slate-50">
              <button
                type="button"
                onClick={() => setExpandedIdx(isOpen ? null : idx)}
                aria-expanded={isOpen}
                className="w-full text-left px-3 py-1.5 cursor-pointer"
              >
                <span className="flex items-center gap-2.5">
                <span className="text-slate-400 shrink-0">{timeStr}</span>
                <span className={`px-1.5 py-0.2 rounded text-[9px] uppercase border shrink-0 font-semibold ${badgeCls}`}>
                  {cat.replace("_", " ")}
                </span>
                <span className="text-slate-900 font-semibold shrink-0">{item.event_type}</span>
                {item.country_id && <span className="text-amber-700 font-semibold shrink-0">[{item.country_id}]</span>}
                <span className="text-slate-600 truncate flex-1">{item.summary || ""}</span>
                {item.duration_ms !== undefined && (
                  <span className="text-emerald-700 font-semibold shrink-0">{item.duration_ms}ms</span>
                )}
                {item.world_version !== undefined && (
                  <span className="text-slate-400 shrink-0">v{item.world_version}</span>
                )}
                </span>
              </button>
              {isOpen && item.payload && (
                <pre className="mt-1.5 mb-1.5 mx-3 p-2 rounded bg-slate-50 border border-slate-200 text-[10px] text-slate-700 overflow-x-auto max-h-32">
                  {JSON.stringify(item.payload, null, 2)}
                </pre>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
