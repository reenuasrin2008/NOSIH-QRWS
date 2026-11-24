import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Download,
  Globe,
  Navigation,
  OctagonAlert,
  Play,
  RotateCcw,
  Shield,
  Users,
} from "lucide-react";
import { ControlPanelApp } from "./ControlPanelApp";
import { TacticalFlatWorldMap } from "../components/map/TacticalFlatWorldMap";
import { TacticalLiveLogsPanel } from "../components/logs/TacticalLiveLogsPanel";
import { connectGlobalWebSocket, globalApi } from "../shared/globalApi";
import type { ApprovalItem, GlobalOverview } from "../shared/globalTypes";
import { useTelemetryRefresh } from "../hooks/useTelemetryRefresh";

type OpsTab = "overview" | "country" | "disasters" | "fleet" | "innovations" | "approvals" | "tactical";

export const OperationsCommandApp: React.FC = () => {
  const [tab, setTab] = useState<OpsTab>("overview");
  const [overview, setOverview] = useState<GlobalOverview | null>(null);
  const [selectedCountryId, setSelectedCountryId] = useState("COUNTRY-03");
  const [countryDetail, setCountryDetail] = useState<any>(null);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [allDrones, setAllDrones] = useState<any[]>([]);
  const [allHospitals, setAllHospitals] = useState<any[]>([]);
  const [counterfactual, setCounterfactual] = useState<any>(null);
  const [mutualAid, setMutualAid] = useState<any>(null);
  const [routeComp, setRouteComp] = useState<any>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [resettingDemo, setResettingDemo] = useState(false);

  // Disaster form state
  const [disType, setDisType] = useState("CYCLONE");
  const [disSeverity, setDisSeverity] = useState(0.8);
  const [editCountryName, setEditCountryName] = useState("");
  const selectedCountryIdRef = useRef(selectedCountryId);
  const overviewVersionRef = useRef(-1);
  selectedCountryIdRef.current = selectedCountryId;

  const applyOverview = useCallback((next: GlobalOverview) => {
    const version = Number(next?.clock?.world_version);
    if (Number.isFinite(version) && version < overviewVersionRef.current) return;
    if (Number.isFinite(version)) overviewVersionRef.current = version;
    setOverview(next);
  }, []);

  const refreshAll = useCallback(async (signal: AbortSignal) => {
    const isCurrent = () => !signal.aborted;
    // globalApi methods do not accept RequestInit; guard their responses so an
    // older country/telemetry request can never replace a newer selection.
    await Promise.all([
      globalApi.getOverview().then((d) => { if (isCurrent()) applyOverview(d); }).catch(() => {}),
      globalApi.getCountry(selectedCountryId).then((d) => {
        if (!isCurrent() || selectedCountryIdRef.current !== selectedCountryId) return;
        setCountryDetail(d);
        setEditCountryName(d?.profile?.name || "");
      }).catch(() => {}),
      globalApi.getApprovals().then((r) => { if (isCurrent()) setApprovals(r.approvals); }).catch(() => {}),
      globalApi.getEvents(40).then((r) => { if (isCurrent()) setEvents(r.events); }).catch(() => {}),
      globalApi.getGlobalDrones().then((r) => { if (isCurrent()) setAllDrones(r.drones); }).catch(() => {}),
      fetch("/api/hospitals", { signal })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then((d) => { if (isCurrent()) setAllHospitals(d.hospitals || []); })
        .catch(() => {}),
    ]);
  }, [selectedCountryId, applyOverview]);

  const requestRefresh = useTelemetryRefresh(refreshAll);

  const handleResetDemo = async () => {
    if (resettingDemo) return;
    setResettingDemo(true);
    try {
      const r1 = await fetch("/api/world/emergency-resume", { method: "POST" });
      if (!r1.ok) throw new Error(`HTTP ${r1.status}`);
      const r2 = await fetch("/api/world/reset-local-snapshots", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: "RESET_SNAPSHOTS" }),
      });
      if (!r2.ok) throw new Error(`HTTP ${r2.status}`);
    } catch {
      // Refresh dashboard regardless so operator sees authoritative state
    } finally {
      requestRefresh();
      setResettingDemo(false);
    }
  };

  useEffect(() => {
    requestRefresh();
  }, [selectedCountryId, requestRefresh]);

  useEffect(() => {
    const disconnect = connectGlobalWebSocket("quantum-operations", {
      onConnectionChange: setWsConnected,
      onSnapshot: (snap) => {
        if (snap.overview) applyOverview(snap.overview);
        requestRefresh();
      },
      onWorldEvent: () => requestRefresh(),
    });
    return disconnect;
  }, [requestRefresh, applyOverview]);

  if (tab === "tactical") {
    return (
      <div className="w-screen h-screen flex flex-col bg-[#F7F8FA] text-slate-900">
        <div className="h-10 px-4 bg-white border-b border-slate-200 flex items-center justify-between shrink-0">
          <span className="text-xs font-mono text-sky-300">02 — OPERATIONS COMMAND · TACTICAL 4-SOLVER BENCHMARK ARENA</span>
          <button
            onClick={() => setTab("overview")}
            className="px-3 py-1 rounded text-xs bg-slate-800 hover:bg-slate-700 text-white border border-slate-700"
          >
            Return to 7-Country Global Control Room
          </button>
        </div>
        <div className="flex-1 overflow-hidden">
          <ControlPanelApp />
        </div>
      </div>
    );
  }

  const totals = overview?.totals;
  const pendingCount = approvals.filter((a) => a.status === "PENDING").length;

  return (
    <div className="w-screen h-screen bg-[#F7F8FA] text-slate-900 flex flex-col overflow-hidden font-sans">
      {/* Top Global Mission Status Bar */}
      <header className="h-12 px-4 bg-white border-b border-slate-200 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <Shield className="w-4 h-4 text-sky-400" />
          <span className="font-semibold text-sm tracking-wide">QUANTUM RESCUE</span>
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-blue-50 text-blue-800 border border-blue-200 font-semibold">
            02 — OPERATIONS COMMAND (:5174)
          </span>
          {overview && (
            <div className="hidden xl:flex items-center gap-4 text-xs font-mono text-slate-700 ml-2">
              <span>CLK {overview.clock.clock_hhmm}</span>
              <span className="text-amber-400">AT RISK: {totals?.people_at_risk.toLocaleString()}</span>
              <span className="text-red-400">DISASTERS: {totals?.active_disasters}</span>
              <span className="text-emerald-400">DRONES: {totals?.drones_available}/{totals?.drones_total}</span>
              <span className="text-sky-300">AMB: {totals?.ambulances_available}/{totals?.ambulances_total}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => globalApi.tickWorld(120).then(() => requestRefresh())}
            className="px-2.5 py-1 rounded text-xs bg-white hover:bg-slate-50 border border-slate-300 text-slate-800 flex items-center gap-1"
          >
            <Play className="w-3 h-3 text-emerald-400" /> Step +2m
          </button>
          <a
            href="/api/global/export/zip"
            className="px-2.5 py-1 rounded text-xs bg-white hover:bg-slate-50 border border-slate-300 text-slate-800 flex items-center gap-1 text-slate-800"
          >
            <Download className="w-3 h-3 text-sky-400" /> Export ZIP
          </a>
          {overview?.clock.emergency_stopped ? (
            <button
              onClick={() => globalApi.emergencyResume().then(() => requestRefresh())}
              className="px-2.5 py-1 rounded text-xs font-semibold bg-emerald-700 hover:bg-emerald-600 text-white"
            >
              RESUME SIM
            </button>
          ) : (
            <button
              onClick={() => globalApi.emergencyStop().then(() => requestRefresh())}
              className="px-2.5 py-1 rounded text-xs font-semibold bg-red-700 hover:bg-red-600 text-white flex items-center gap-1"
            >
              <OctagonAlert className="w-3.5 h-3.5" /> E-STOP
            </button>
          )}
          <button
            onClick={handleResetDemo}
            disabled={resettingDemo}
            title="Demo-only reset: calls emergency-resume and resets local snapshots"
            className="px-2.5 py-1 rounded text-xs font-medium bg-amber-50 hover:bg-amber-100 border border-amber-300 text-amber-900 flex items-center gap-1 disabled:opacity-60"
          >
            <RotateCcw className="w-3 h-3 text-amber-600" />
            {resettingDemo ? "Resetting..." : "Reset Demo (Demo Only)"}
          </button>
          <span className={`text-[11px] font-mono px-2 py-0.5 rounded border ${wsConnected ? "border-emerald-700 text-emerald-300" : "border-red-800 text-red-300"}`}>
            {wsConnected ? "LIVE" : "OFFLINE"}
          </span>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Left Navigation */}
        <nav className="w-56 bg-white border-r border-slate-200 p-3 flex flex-col gap-1 shrink-0">
          {[
            ["overview", "Global Overview (7 Nations)", Globe],
            ["country", "Country Editor & Facilities", Users],
            ["disasters", "Disaster & Cascade Control", AlertTriangle],
            ["fleet", "Fleet, Swarms & Routes", Navigation],
            ["innovations", "Counterfactuals & Mutual Aid", Cpu],
            ["approvals", `Approvals (${pendingCount}) & Logs`, CheckCircle2],
            ["tactical", "4-Solver Benchmark Arena", Activity],
          ].map(([id, label, Icon]: any) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`w-full text-left px-3 py-2 rounded text-xs flex items-center gap-2 border ${
                tab === id
                  ? "bg-blue-50 border-blue-400 text-blue-900 font-medium"
                  : "bg-transparent border-transparent text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              }`}
            >
              <Icon className="w-3.5 h-3.5 shrink-0" />
              <span>{label}</span>
            </button>
          ))}

          <div className="mt-auto pt-3 border-t border-slate-200">
            <label className="text-[10px] font-mono text-slate-500 block mb-1">ACTIVE COUNTRY</label>
            <select
              value={selectedCountryId}
              onChange={(e) => setSelectedCountryId(e.target.value)}
              className="w-full bg-slate-50 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-800"
            >
              {(overview?.countries || []).map((c) => (
                <option key={c.country_id} value={c.country_id}>
                  {c.country_id} · {c.name}
                </option>
              ))}
            </select>
          </div>
        </nav>

        {/* Main Workspace */}
        <main className="flex-1 overflow-y-auto p-5 space-y-5">
          {tab === "overview" && overview && (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                {[
                  ["TOTAL POPULATION", overview.totals.total_population.toLocaleString(), "text-slate-900"],
                  ["PEOPLE AT RISK", overview.totals.people_at_risk.toLocaleString(), "text-amber-400"],
                  ["ACTIVE DISASTERS", `${overview.totals.active_disasters} (${overview.totals.countries_affected} nations)`, "text-red-400"],
                  ["GLOBAL DRONES", `${overview.totals.drones_available} avail / ${overview.totals.drones_active} active`, "text-emerald-400"],
                  ["HOSPITALS ONLINE", `${overview.totals.hospitals_operational}/${overview.totals.hospitals_total}`, "text-sky-300"],
                ].map(([label, val, cls]) => (
                  <div key={label} className="p-3 rounded bg-white border border-slate-200 shadow-sm">
                    <div className="text-[10px] font-mono text-slate-500">{label}</div>
                    <div className={`text-lg font-mono font-semibold mt-1 ${cls}`}>{val}</div>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                <div className="xl:col-span-2 h-80 rounded border border-slate-200 overflow-hidden">
                  <TacticalFlatWorldMap
                    countries={overview.countries}
                    disasters={overview.active_disasters}
                    selectedCountryId={selectedCountryId}
                    onSelectCountry={setSelectedCountryId}
                    drones={allDrones}
                    hospitals={allHospitals}
                    title="OPERATIONS TACTICAL MONITOR — 7 NATIONS"
                  />
                </div>
                <div className="h-80 rounded border border-slate-200 overflow-hidden">
                  <TacticalLiveLogsPanel events={events} title="LIVE OPERATIONS LOGS" />
                </div>
              </div>

              <div className="bg-white border border-slate-200 shadow-sm rounded overflow-hidden">
                <div className="px-4 py-2.5 border-b border-slate-200 text-xs font-mono text-slate-700 uppercase">
                  Seven-Country Operational Matrix
                </div>
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 text-slate-600 font-mono text-[11px]">
                    <tr>
                      <th className="p-2.5 text-left">Country</th>
                      <th className="p-2.5 text-left">Archetype</th>
                      <th className="p-2.5 text-right">Population</th>
                      <th className="p-2.5 text-right">Exposed</th>
                      <th className="p-2.5 text-right">Beds Free</th>
                      <th className="p-2.5 text-right">Ambulances</th>
                      <th className="p-2.5 text-right">Drones</th>
                      <th className="p-2.5 text-center">Disasters</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono">
                    {overview.countries.map((c) => (
                      <tr
                        key={c.country_id}
                        onClick={() => {
                          setSelectedCountryId(c.country_id);
                          setTab("country");
                        }}
                        className="hover:bg-slate-50 cursor-pointer"
                      >
                        <td className="p-2.5 font-sans font-medium text-slate-900">
                          {c.name} <span className="text-slate-500 text-[10px] font-mono">{c.country_id}</span>
                        </td>
                        <td className="p-2.5 font-sans text-slate-500">{c.archetype}</td>
                        <td className="p-2.5 text-right">{c.total_population.toLocaleString()}</td>
                        <td className="p-2.5 text-right text-amber-400">{c.exposed_population.toLocaleString()}</td>
                        <td className="p-2.5 text-right text-sky-300">{c.available_beds}</td>
                        <td className="p-2.5 text-right">{c.ambulances_available}/{c.ambulances_total}</td>
                        <td className="p-2.5 text-right text-emerald-400">{c.drones_available}/{c.drones_total}</td>
                        <td className="p-2.5 text-center">
                          <span className={`px-2 py-0.5 rounded text-[10px] ${c.active_disasters > 0 ? "bg-red-50 text-red-700 border border-red-200 font-semibold" : "bg-slate-800 text-slate-500"}`}>
                            {c.active_disasters}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {tab === "country" && countryDetail && (
            <div className="space-y-4">
              <div className="p-4 rounded bg-white border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-mono text-sky-400">{countryDetail.profile.country_id}</div>
                  <h2 className="text-base font-semibold">{countryDetail.profile.name}</h2>
                  <p className="text-xs text-slate-500">{countryDetail.profile.terrain_profile}</p>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    value={editCountryName}
                    onChange={(e) => setEditCountryName(e.target.value)}
                    className="bg-slate-50 border border-slate-700 rounded px-2.5 py-1 text-xs"
                    placeholder="Edit country name"
                  />
                  <button
                    onClick={() => globalApi.updateCountry(selectedCountryId, { name: editCountryName }).then(() => requestRefresh())}
                    className="px-3 py-1 rounded text-xs bg-sky-600 hover:bg-sky-500 text-white"
                  >
                    Save Profile
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="p-4 rounded bg-white border border-slate-200 shadow-sm space-y-2">
                  <h3 className="text-xs font-mono uppercase text-slate-500">Ambulance Requirement Calculator (Live)</h3>
                  <p className="text-xs text-slate-700 leading-relaxed">{countryDetail.ambulance_analysis.explanation}</p>
                  <div className="grid grid-cols-3 gap-2 pt-2 font-mono text-xs">
                    <div className="p-2 rounded bg-slate-50">Min: {countryDetail.ambulance_analysis.minimum_ambulances_required}</div>
                    <div className="p-2 rounded bg-slate-50 text-amber-300">Rec: {countryDetail.ambulance_analysis.recommended_operational_fleet}</div>
                    <div className="p-2 rounded bg-slate-50 text-red-400">Deficit: {countryDetail.ambulance_analysis.ambulance_deficit}</div>
                  </div>
                </div>

                <div className="p-4 rounded bg-white border border-slate-200 shadow-sm space-y-2">
                  <h3 className="text-xs font-mono uppercase text-slate-500">24h Humanitarian Supply Forecast</h3>
                  <div className="text-xs font-mono space-y-1">
                    <div>Food: {countryDetail.resource_analysis.food_packages.needed.toLocaleString()} needed / {countryDetail.resource_analysis.food_packages.available.toLocaleString()} stock</div>
                    <div>Water: {countryDetail.resource_analysis.water_liters.needed.toLocaleString()} L needed / {countryDetail.resource_analysis.water_liters.available.toLocaleString()} L stock</div>
                    <div>Shelters: {countryDetail.resource_analysis.shelters.demand.toLocaleString()} demand / {countryDetail.resource_analysis.shelters.remaining_capacity.toLocaleString()} free</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {tab === "disasters" && countryDetail && (
            <div className="space-y-4">
              <div className="p-4 rounded bg-white border border-slate-200 shadow-sm flex flex-wrap items-end gap-3">
                <div>
                  <label className="block text-[10px] font-mono text-slate-500 mb-1">DISASTER TYPE</label>
                  <select value={disType} onChange={(e) => setDisType(e.target.value)} className="bg-slate-50 border border-slate-700 rounded px-2.5 py-1.5 text-xs">
                    <option value="FLOOD">FLOOD</option>
                    <option value="CYCLONE">CYCLONE</option>
                    <option value="FIRE">FIRE</option>
                    <option value="MULTI_HAZARD_CASCADE">MULTI_HAZARD_CASCADE</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-mono text-slate-500 mb-1">SEVERITY ({Math.round(disSeverity * 100)}%)</label>
                  <input type="range" min={0.2} max={1.0} step={0.05} value={disSeverity} onChange={(e) => setDisSeverity(parseFloat(e.target.value))} />
                </div>
                <button
                  onClick={() => globalApi.createDisaster({ country_id: selectedCountryId, disaster_type: disType, severity: disSeverity }).then(() => requestRefresh())}
                  className="px-4 py-1.5 rounded text-xs font-medium bg-red-700 hover:bg-red-600 text-white"
                >
                  Inject Live Disaster into {selectedCountryId}
                </button>
              </div>

              <div className="p-4 rounded bg-white border border-slate-200 shadow-sm space-y-2">
                <h3 className="text-xs font-mono uppercase text-slate-500">Cascade Prediction Graph — {countryDetail.profile.name}</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {countryDetail.cascade_graph.nodes.map((n: any) => (
                    <div key={n.id} className="p-2.5 rounded bg-slate-50 border border-slate-200 text-xs">
                      <div className="font-medium text-slate-900">{n.label}</div>
                      <div className="text-[11px] font-mono text-slate-500 mt-1">
                        {n.status} · Index {(n.modelled_likelihood * 100).toFixed(0)}%
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {tab === "fleet" && countryDetail && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => globalApi.prepareSwarm({ country_id: selectedCountryId, drone_count: 8, mode: "AREA_SCAN", formation: "SEARCH_GRID" }).then(() => { requestRefresh(); setTab("approvals"); })}
                  className="px-3 py-1.5 rounded text-xs bg-sky-600 hover:bg-sky-500 text-white"
                >
                  Prepare 8-Drone Search Swarm (Approval Required)
                </button>
                <button
                  onClick={() => {
                    const h = countryDetail.hospitals[0];
                    if (h) {
                      globalApi.exploreRoutes({
                        country_id: selectedCountryId,
                        destination_lat: h.location.lat,
                        destination_lon: h.location.lon,
                        destination_label: h.name,
                        objective: "BALANCED",
                      }).then(setRouteComp);
                    }
                  }}
                  className="px-3 py-1.5 rounded text-xs bg-white hover:bg-slate-50 border border-slate-300 text-slate-800 text-slate-800"
                >
                  Run Yen's K-Shortest Multi-Drone Route Comparison
                </button>
              </div>

              {routeComp && (
                <div className="p-4 rounded bg-white border border-slate-200 shadow-sm">
                  <div className="text-xs font-mono text-sky-300 mb-2">
                    ROUTE INTELLIGENCE — {routeComp.destination_label} ({routeComp.objective})
                  </div>
                  <table className="w-full text-xs font-mono">
                    <thead className="text-slate-500 border-b border-slate-200">
                      <tr>
                        <th className="py-1.5 text-left">Rank</th>
                        <th className="py-1.5 text-left">Drone</th>
                        <th className="py-1.5 text-left">Route</th>
                        <th className="py-1.5 text-right">Dist (km)</th>
                        <th className="py-1.5 text-right">ETA (min)</th>
                        <th className="py-1.5 text-right">Battery Used</th>
                        <th className="py-1.5 text-center">Feasible</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {routeComp.ranked_comparison.map((r: any) => (
                        <tr key={r.route_id}>
                          <td className="py-1.5">#{r.rank}</td>
                          <td className="py-1.5">{r.drone_id}</td>
                          <td className="py-1.5">{r.route_id}</td>
                          <td className="py-1.5 text-right">{r.total_distance_km}</td>
                          <td className="py-1.5 text-right">{r.estimated_duration_min}</td>
                          <td className="py-1.5 text-right">{r.predicted_battery_used_pct}%</td>
                          <td className="py-1.5 text-center">{r.feasible ? "YES" : "NO"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {tab === "innovations" && countryDetail && (
            <div className="space-y-4">
              <div className="flex gap-2">
                <button
                  onClick={() => globalApi.runCounterfactual(selectedCountryId).then(setCounterfactual)}
                  className="px-3 py-1.5 rounded text-xs bg-sky-600 hover:bg-sky-500 text-white"
                >
                  Run 4-World Counterfactual Digital Twin
                </button>
                <button
                  onClick={() => globalApi.getMutualAid(selectedCountryId, "ambulances").then(setMutualAid)}
                  className="px-3 py-1.5 rounded text-xs bg-white hover:bg-slate-50 border border-slate-300 text-slate-800 text-slate-800"
                >
                  Scan Seven-Country Mutual Aid Surplus
                </button>
              </div>

              {counterfactual && (
                <div className="p-4 rounded bg-white border border-slate-200 shadow-sm">
                  <div className="text-xs font-mono text-sky-300 mb-2">
                    COUNTERFACTUAL COMPARISON ({counterfactual.counterfactual_id} · Seed {counterfactual.seed})
                  </div>
                  <table className="w-full text-xs font-mono">
                    <thead className="text-slate-500 border-b border-slate-200">
                      <tr>
                        <th className="py-1.5 text-left">Strategy</th>
                        <th className="py-1.5 text-right">Evacuated</th>
                        <th className="py-1.5 text-right">1st Response</th>
                        <th className="py-1.5 text-right">Completion</th>
                        <th className="py-1.5 text-right">Failures</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {counterfactual.scenarios.map((s: any) => (
                        <tr key={s.scenario_key}>
                          <td className="py-1.5 font-sans">{s.label}</td>
                          <td className="py-1.5 text-right text-emerald-400">{s.people_safely_evacuated.toLocaleString()}</td>
                          <td className="py-1.5 text-right">{s.time_to_first_response_min}m</td>
                          <td className="py-1.5 text-right">{s.rescue_completion_min}m</td>
                          <td className="py-1.5 text-right">{s.mission_failures}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {mutualAid && (
                <div className="p-4 rounded bg-white border border-slate-200 shadow-sm space-y-2">
                  <div className="text-xs font-mono text-amber-300">MUTUAL AID DONORS FOR {mutualAid.target_name}</div>
                  {mutualAid.eligible_donors.map((d: any) => (
                    <div key={d.donor_country_id} className="flex items-center justify-between p-2 rounded bg-slate-50 text-xs">
                      <span>{d.donor_name} ({d.distance_km} km · ETA {d.estimated_arrival_hours}h · Surplus {d.available_surplus})</span>
                      <button
                        onClick={() => globalApi.prepareMutualAid({ target_country_id: selectedCountryId, donor_country_id: d.donor_country_id, resource_type: "ambulances", quantity: d.proposed_transfer }).then(() => { requestRefresh(); setTab("approvals"); })}
                        className="px-2.5 py-1 rounded bg-sky-700 hover:bg-sky-600 text-white"
                      >
                        Propose Transfer ({d.proposed_transfer})
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === "approvals" && (
            <div className="space-y-4">
              <div className="p-4 rounded bg-white border border-slate-200 shadow-sm space-y-2">
                <h3 className="text-xs font-mono uppercase text-slate-500">Operator Authorization Queue</h3>
                {approvals.length === 0 && <div className="text-xs text-slate-500">No approval requests yet.</div>}
                {approvals.map((a) => (
                  <div key={a.approval_id} className="p-3 rounded bg-slate-50 border border-slate-200 flex items-center justify-between gap-3">
                    <div>
                      <div className="text-xs font-semibold text-slate-900">{a.title}</div>
                      <div className="text-[11px] text-slate-500">{a.description}</div>
                      <div className="text-[10px] font-mono text-slate-500 mt-0.5">{a.approval_id} · Status: {a.status}</div>
                    </div>
                    {a.status === "PENDING" && (
                      <div className="flex gap-2">
                        <button
                          onClick={() => globalApi.approveOperation(a.approval_id, true).then(() => requestRefresh())}
                          className="px-3 py-1 rounded text-xs bg-emerald-700 hover:bg-emerald-600 text-white"
                        >
                          Approve & Execute
                        </button>
                        <button
                          onClick={() => globalApi.rejectOperation(a.approval_id).then(() => requestRefresh())}
                          className="px-3 py-1 rounded text-xs bg-red-900 hover:bg-red-800 text-red-100"
                        >
                          Reject
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="p-4 rounded bg-white border border-slate-200 shadow-sm">
                <h3 className="text-xs font-mono uppercase text-slate-500 mb-2">Live Authoritative Event Timeline</h3>
                <div className="space-y-1 max-h-64 overflow-y-auto font-mono text-[11px]">
                  {events.map((ev) => (
                    <div key={ev.event_id} className="flex gap-3 text-slate-700 border-b border-slate-200/50 py-1">
                      <span className="text-slate-500">v{ev.world_version}</span>
                      <span className="text-sky-400">{ev.event_type}</span>
                      <span className="text-slate-500">{ev.country_id || "GLOBAL"}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};
