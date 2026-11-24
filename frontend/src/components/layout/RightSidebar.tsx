import React from "react";
import { motion } from "framer-motion";
import { AlertTriangle, Crosshair, Home, Activity, Trophy, Cpu, Radio, BarChart3 } from "lucide-react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, BarChart, Bar } from "recharts";
import { useSimStore } from "../../state/simulationStore";
import { api } from "../../api/client";
import { QuantumCharts } from "../panels/QuantumCharts";
import { StationStatusPanel } from "../panels/StationStatusPanel";
import { GimbalPreview } from "../panels/GimbalPreview";

export const RightSidebar: React.FC = () => {
  const rightTab = useSimStore((s) => s.rightTab);
  const setRightTab = useSimStore((s) => s.setRightTab);
  const activeState = useSimStore((s) => s.activeState);
  const leaderboard = useSimStore((s) => s.leaderboard);
  const leaderboardSort = useSimStore((s) => s.leaderboardSort);
  const setLeaderboardSort = useSimStore((s) => s.setLeaderboardSort);
  const sortedLeaderboard = React.useMemo(() => {
    const arr = [...leaderboard];
    if (leaderboardSort === 'energy') return arr.sort((a, b) => a.total_energy_wh - b.total_energy_wh);
    if (leaderboardSort === 'rescue_time') return arr.sort((a, b) => a.avg_response_time_s - b.avg_response_time_s);
    if (leaderboardSort === 'risk') return arr.sort((a, b) => a.operational_risk - b.operational_risk);
    if (leaderboardSort === 'completed') return arr.sort((a, b) => b.missions_completed - a.missions_completed);
    if (leaderboardSort === 'runtime') return arr.sort((a, b) => a.solver_runtime_ms - b.solver_runtime_ms);
    return arr;
  }, [leaderboard, leaderboardSort]);
  const selectedDroneId = useSimStore((s) => s.selectedDroneId);
  const setShowFailureModal = useSimStore((s) => s.setShowFailureModal);
  const setPlacementMode = useSimStore((s) => s.setPlacementMode);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setToast = useSimStore((s) => s.setToast);

  const drones = activeState?.drones || [];
  const tasks = activeState?.tasks || [];
  const metrics = activeState?.metrics;
  const qMetrics = activeState?.quantum_metrics;
  const analytics = activeState?.analytics || [];
  const selectedDrone = drones.find((d) => d.id === selectedDroneId) || drones[0];

  const completedCount = tasks.filter((t) => t.status === "completed").length;
  const completionPct = tasks.length ? Math.round((completedCount / tasks.length) * 100) : 0;
  const criticalPending = tasks.filter((t) => t.priority === "critical" && t.status !== "completed").length;
  const recoveryPending = tasks.filter((t) => t.status === "requires_reassignment" || t.status === "unassigned").length;

  const handleRtb = async (id: string) => {
    const data = await api.returnToBase(id);
    applyServerPayload(data);
    setToast(`Drone ${id} ordered to Return to Base.`);
  };

  return (
    <aside className="w-80 xl:w-96 bg-[#11161f] border-l border-[#242c3a] flex flex-col shrink-0 text-xs">
      {/* 5 Tabs */}
      <div className="grid grid-cols-5 border-b border-[#242c3a] font-mono text-[10px]">
        {[
          { id: "ops", label: "OPS", icon: Activity },
          { id: "leaderboard", label: "RANK", icon: Trophy },
          { id: "quantum", label: "QAOA", icon: Cpu },
          { id: "drone", label: "UNIT", icon: Radio },
          { id: "analytics", label: "DATA", icon: BarChart3 },
        ].map((tab) => {
          const Icon = tab.icon;
          const active = rightTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setRightTab(tab.id as typeof rightTab)}
              className={`py-2 flex flex-col items-center gap-0.5 border-b-2 transition ${
                active ? "border-zinc-100 text-zinc-100 bg-[#171d28]" : "border-transparent text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 font-mono tabular-nums">
        {rightTab === "ops" && (
          <>
            <div className="p-2.5 bg-[#0b0e14] border border-[#242c3a]">
              <div className="flex justify-between text-[11px] mb-1">
                <span className="text-zinc-400">MISSION COMPLETION</span>
                <span className="text-emerald-400 font-semibold">{completedCount}/{tasks.length} ({completionPct}%)</span>
              </div>
              <div className="w-full h-2 bg-[#171d28] border border-[#242c3a]">
                <div className="h-full bg-emerald-500 transition-all" style={{ width: `${completionPct}%` }} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[11px]">
              {[
                ["ACTIVE DRONES", drones.filter((d) => !["DESTROYED", "DAMAGED"].includes(d.status)).length, "text-zinc-100"],
                ["FAILED DRONES", metrics?.failed_drones ?? 0, "text-red-400"],
                ["COMPLETED", completedCount, "text-emerald-400"],
                ["PENDING", metrics?.missions_pending ?? 0, "text-amber-400"],
                ["CRITICAL OPEN", criticalPending, "text-red-400"],
                ["RECOVERY QUEUE", recoveryPending, "text-amber-300"],
                ["REPLAN CYCLES", metrics?.replanning_count ?? 0, "text-blue-400"],
                ["AIRSPACE CONFLICTS", metrics?.airspace_conflicts ?? 0, "text-zinc-200"],
              ].map(([label, val, cls]) => (
                <div key={label as string} className="p-2 bg-[#0b0e14] border border-[#242c3a]">
                  <div className="text-[10px] text-zinc-500">{label as string}</div>
                  <div className={`text-base font-semibold mt-0.5 ${cls as string}`}>{val as number}</div>
                </div>
              ))}
            </div>
            <StationStatusPanel stations={activeState?.stations || []} utilization={activeState?.station_utilization} />
          </>
        )}

        {rightTab === "leaderboard" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-zinc-400 uppercase tracking-wider">Live Strategy Ranking</span>
              <select value={leaderboardSort} onChange={(e) => setLeaderboardSort(e.target.value)} className="bg-[#0b0e14] border border-[#242c3a] text-[10px] text-zinc-200 px-1.5 py-0.5">
                <option value="score">Sort: Score</option>
                <option value="completed">Sort: Completed</option>
                <option value="rescue_time">Sort: Response Time</option>
                <option value="energy">Sort: Lowest Energy</option>
                <option value="risk">Sort: Lowest Risk</option>
                <option value="runtime">Sort: Solver Speed</option>
              </select>
            </div>
            <div className="border border-[#242c3a] bg-[#0b0e14] overflow-hidden">
              <table className="w-full text-left text-[11px]">
                <thead className="bg-[#171d28] text-zinc-400 border-b border-[#242c3a]">
                  <tr>
                    <th className="p-1.5">#</th>
                    <th className="p-1.5">ALGO</th>
                    <th className="p-1.5 text-right">DONE</th>
                    <th className="p-1.5 text-right">Wh</th>
                    <th className="p-1.5 text-right">SCORE</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedLeaderboard.map((row) => (
                    <motion.tr layout transition={{ duration: 0.28 }} key={row.strategy} className="border-b border-[#1c2331] last:border-0">
                      <td className="p-1.5 text-zinc-400">#{row.rank}</td>
                      <td className="p-1.5 font-semibold uppercase text-zinc-100">{row.strategy}</td>
                      <td className="p-1.5 text-right text-emerald-400">{row.missions_completed}</td>
                      <td className="p-1.5 text-right text-zinc-300">{row.total_energy_wh.toFixed(0)}</td>
                      <td className="p-1.5 text-right font-bold text-zinc-100">{row.score.toFixed(1)}</td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* 4 Strategy Telemetry Cards with Score Bars & Greedy Delta */}
            <div className="space-y-2">
              {(() => {
                const greedyScore = leaderboard.find((x) => x.strategy === "greedy")?.score ?? null;
                return sortedLeaderboard.map((m) => {
                  const delta = greedyScore !== null && m.strategy !== "greedy" ? m.score - greedyScore : null;
                  const isLeader = m.rank === 1 && leaderboard.length > 1;
                  return (
                    <motion.div
                      layout
                      transition={{ duration: 0.28 }}
                      key={m.strategy}
                      className={`p-2 bg-[#0b0e14] border text-[10px] space-y-1.5 ${
                        isLeader ? "border-emerald-700/80" : "border-[#242c3a]"
                      }`}
                    >
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-zinc-100 uppercase">{m.strategy}</span>
                          {isLeader && <span className="px-1 py-0.2 bg-emerald-950 border border-emerald-700 text-emerald-300 text-[9px]">LEADER</span>}
                          {delta !== null && (
                            <span className={`text-[9px] ${delta >= 0 ? "text-emerald-400" : "text-amber-400"}`}>
                              {delta >= 0 ? "+" : ""}{delta.toFixed(1)}
                            </span>
                          )}
                        </div>
                        <span className="text-zinc-300 font-semibold">{m.score.toFixed(1)} / 100</span>
                      </div>
                      <div className="w-full h-1 bg-[#171d28]">
                        <div className={`h-full ${isLeader ? "bg-emerald-500" : "bg-zinc-400"}`} style={{ width: `${Math.min(100, m.score)}%` }} />
                      </div>
                      <div className="grid grid-cols-3 gap-1 text-zinc-400">
                        <div>SOLV: <span className="text-zinc-200">{m.solver_runtime_ms.toFixed(0)}ms</span></div>
                        <div>RESP: <span className="text-zinc-200">{m.avg_response_time_s}s</span></div>
                        <div>RECOV: <span className="text-emerald-400">{m.tasks_recovered} ({m.recovery_rate_pct}%)</span></div>
                      </div>
                    </motion.div>
                  );
                });
              })()}
            </div>
          </div>
        )}

        {rightTab === "quantum" && (
          <div className="space-y-2.5 text-[11px]">
            <div className="p-2 bg-[#0b0e14] border border-[#242c3a]">
              <div className="text-[10px] text-amber-400 font-semibold uppercase">
                {qMetrics?.backend_name || "QAOA — Classical quantum-circuit simulation"}
              </div>
              <div className="text-[10px] text-zinc-400 mt-1">
                Reduced-subproblem QUBO circuit simulator (4–8 qubits). No real quantum hardware or speedup claimed.
              </div>
            </div>

            {qMetrics && qMetrics.executed ? (
              <>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    ["QUBITS", qMetrics.num_qubits],
                    ["CIRCUIT DEPTH", qMetrics.circuit_depth],
                    ["QAOA LAYERS (p)", qMetrics.qaoa_layers],
                    ["ITERATIONS", qMetrics.iterations],
                    ["SHOTS", qMetrics.shots],
                    ["EXEC TIME", `${qMetrics.execution_time_ms} ms`],
                    ["BEST ENERGY", qMetrics.best_energy],
                    ["REPAIRED", qMetrics.repaired_assignments],
                  ].map(([k, v]) => (
                    <div key={k as string} className="p-2 bg-[#0b0e14] border border-[#242c3a]">
                      <div className="text-[10px] text-zinc-500">{k as string}</div>
                      <div className="text-zinc-100 font-semibold">{v as string}</div>
                    </div>
                  ))}
                </div>
                <div className="p-2 bg-[#0b0e14] border border-[#242c3a] space-y-1">
                  <div className="text-[10px] text-zinc-400">BEST BITSTRING: <span className="text-amber-300 font-bold">{qMetrics.best_bitstring}</span></div>
                  <div className="text-[10px] text-zinc-400">VALIDATION: <span className={qMetrics.validation_passed ? "text-emerald-400" : "text-amber-400"}>{qMetrics.validation_passed ? "PASSED DIRECTLY" : "REPAIRED CLASSICALLY"}</span></div>
                  <div className="text-[10px] text-zinc-400">SUBPROBLEM TASKS: <span className="text-zinc-200">{qMetrics.subproblem_tasks.join(", ")}</span></div>
                </div>
                <div className="p-2 bg-[#0b0e14] border border-[#242c3a]">
                  <div className="text-[10px] text-zinc-400 mb-1 uppercase">Top Measured Bitstrings</div>
                  {qMetrics.top_samples.map((s) => (
                    <div key={s.bitstring} className="flex justify-between text-[10px] py-0.5 border-b border-[#1c2331] last:border-0">
                      <span className="text-zinc-200">{s.bitstring}</span>
                      <span className="text-zinc-400">cnt={s.count}</span>
                      <span className="text-amber-300">E={s.energy}</span>
                    </div>
                  ))}
                </div>
                <QuantumCharts q={qMetrics} />
              </>
            ) : (
              <div className="p-3 bg-[#0b0e14] border border-[#242c3a] text-zinc-400 text-[11px]">
                Run a Quantum or Hybrid optimization (or press RUN ALL STRATEGIES) to inspect live quantum-inspired solver telemetry.
              </div>
            )}
          </div>
        )}

        {rightTab === "drone" && selectedDrone && (
          <div className="space-y-2.5 text-[11px]">
            <div className="p-2.5 bg-[#0b0e14] border border-[#242c3a]">
              <div className="flex justify-between items-center">
                <span className="text-sm font-bold text-zinc-100">{selectedDrone.id}</span>
                <span className="px-1.5 py-0.5 bg-[#171d28] border border-[#2d3748] text-[10px] text-zinc-200">{selectedDrone.status}</span>
              </div>
              <div className="text-[10px] text-zinc-400 mt-0.5">{selectedDrone.class_label}</div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="p-2 bg-[#0b0e14] border border-[#242c3a]">
                <div className="text-[10px] text-zinc-500">BATTERY</div>
                <div className={`font-semibold ${selectedDrone.battery_percent < 25 ? "text-red-400" : "text-emerald-400"}`}>
                  {selectedDrone.battery_percent.toFixed(1)}% ({selectedDrone.remaining_battery_wh.toFixed(0)}Wh)
                </div>
              </div>
              <div className="p-2 bg-[#0b0e14] border border-[#242c3a]">
                <div className="text-[10px] text-zinc-500">PAYLOAD</div>
                <div className="text-zinc-100 font-semibold">{selectedDrone.current_payload_kg} / {selectedDrone.max_payload_kg} kg</div>
              </div>
              <div className="p-2 bg-[#0b0e14] border border-[#242c3a]">
                <div className="text-[10px] text-zinc-500">COORDINATES</div>
                <div className="text-zinc-200">{selectedDrone.position.map((v) => v.toFixed(0)).join(", ")}</div>
              </div>
              <div className="p-2 bg-[#0b0e14] border border-[#242c3a]">
                <div className="text-[10px] text-zinc-500">GROUNDSPEED / ETA</div>
                <div className="text-zinc-200">{selectedDrone.groundspeed_mps.toFixed(1)} m/s · {selectedDrone.eta_seconds.toFixed(0)}s</div>
              </div>
              <div className="p-2 bg-[#0b0e14] border border-[#242c3a]">
                <div className="text-[10px] text-zinc-500">POWER / TEMP</div>
                <div className="text-zinc-200">{selectedDrone.power_draw_w.toFixed(0)} W · {selectedDrone.battery_temp_c.toFixed(1)}°C</div>
              </div>
              <div className="p-2 bg-[#0b0e14] border border-[#242c3a]">
                <div className="text-[10px] text-zinc-500">DISTANCE / DONE</div>
                <div className="text-zinc-200">{selectedDrone.total_distance_m.toFixed(0)}m · {selectedDrone.tasks_completed} tasks</div>
              </div>
            </div>

            <GimbalPreview drone={selectedDrone} />

            <div className="p-2 bg-[#0b0e14] border border-[#242c3a] text-[10px]">
              <div className="text-zinc-500 uppercase mb-1">Assigned Queue</div>
              <div className="text-zinc-200">{selectedDrone.assigned_task_ids.length ? selectedDrone.assigned_task_ids.join(" -> ") : "No queued missions"}</div>
            </div>

            {/* Interactive Drone Commands */}
            <div className="space-y-1.5">
              <button
                onClick={() => setPlacementMode("set_waypoint")}
                className="w-full py-1.5 px-2 bg-[#171d28] hover:bg-[#202938] border border-[#2d3748] text-zinc-200 flex items-center justify-center gap-1.5"
              >
                <Crosshair className="w-3.5 h-3.5" /> CHANGE DESTINATION
              </button>
              <button
                onClick={() => handleRtb(selectedDrone.id)}
                className="w-full py-1.5 px-2 bg-[#171d28] hover:bg-[#202938] border border-[#2d3748] text-zinc-200 flex items-center justify-center gap-1.5"
              >
                <Home className="w-3.5 h-3.5" /> RETURN TO BASE
              </button>
              <button
                onClick={() => setShowFailureModal(true)}
                className="w-full py-1.5 px-2 bg-red-950/70 hover:bg-red-900/80 border border-red-800 text-red-200 font-semibold flex items-center justify-center gap-1.5"
              >
                <AlertTriangle className="w-3.5 h-3.5" /> INJECT FAILURE / DESTROY
              </button>
            </div>
          </div>
        )}

        {rightTab === "analytics" && (
          <div className="space-y-3">
            <div className="p-2 bg-[#0b0e14] border border-[#242c3a]">
              <div className="text-[10px] text-zinc-400 uppercase mb-2">Missions Completed & Avg Battery (%)</div>
              <div className="h-36">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={analytics}>
                    <XAxis dataKey="t" stroke="#64748b" fontSize={10} />
                    <YAxis stroke="#64748b" fontSize={10} />
                    <Tooltip contentStyle={{ backgroundColor: "#11161f", borderColor: "#242c3a", fontSize: 11 }} />
                    <Line type="monotone" dataKey="completed" stroke="#10b981" dot={false} strokeWidth={1.8} />
                    <Line type="monotone" dataKey="avg_battery_pct" stroke="#3b82f6" dot={false} strokeWidth={1.5} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="p-2 bg-[#0b0e14] border border-[#242c3a]">
              <div className="text-[10px] text-zinc-400 uppercase mb-2">Strategy Score Comparison</div>
              <div className="h-36">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={leaderboard}>
                    <XAxis dataKey="strategy" stroke="#64748b" fontSize={10} />
                    <YAxis domain={[0, 100]} stroke="#64748b" fontSize={10} />
                    <Tooltip contentStyle={{ backgroundColor: "#11161f", borderColor: "#242c3a", fontSize: 11 }} />
                    <Bar dataKey="score" fill="#cbd5e1" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
