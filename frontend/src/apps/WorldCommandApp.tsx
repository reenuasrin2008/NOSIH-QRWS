import React, { useEffect, useState } from "react";
import { Globe, MapPin, ShieldAlert, Radio, Compass } from "lucide-react";
import { BigFlatOpenWorld3D } from "../simulation/BigFlatOpenWorld3D";
import { TacticalFlatWorldMap } from "../components/map/TacticalFlatWorldMap";
import { connectGlobalWebSocket, globalApi } from "../shared/globalApi";
import type { GlobalOverview } from "../shared/globalTypes";

export const WorldCommandApp: React.FC = () => {
  const [viewMode, setViewMode] = useState<"flat" | "planet">("flat");
  const [overview, setOverview] = useState<GlobalOverview | null>(null);
  const [allDrones, setAllDrones] = useState<any[]>([]);
  const [allHospitals, setAllHospitals] = useState<any[]>([]);
  const [allShelters, setAllShelters] = useState<any[]>([]);
  const [allAmbulances, setAllAmbulances] = useState<any[]>([]);
  const [allFireUnits, setAllFireUnits] = useState<any[]>([]);
  const [activeSwarms, setActiveSwarms] = useState<any[]>([]);
  const [selectedCountryId, setSelectedCountryId] = useState<string>("COUNTRY-03");
  const [candidateRoutes, setCandidateRoutes] = useState<any[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [lastCommandBanner, setLastCommandBanner] = useState<string | null>(null);

  const refresh = () => {
    globalApi.getOverview().then(setOverview).catch(() => {});
    globalApi.getGlobalDrones().then((r) => setAllDrones(r.drones)).catch(() => {});
    fetch("/api/hospitals").then((r) => r.json()).then((d) => setAllHospitals(d.hospitals || [])).catch(() => {});
    fetch("/api/shelters").then((r) => r.json()).then((d) => setAllShelters(d.shelters || [])).catch(() => {});
    fetch("/api/ambulances").then((r) => r.json()).then((d) => setAllAmbulances(d.ambulances || [])).catch(() => {});
    fetch("/api/fire-units").then((r) => r.json()).then((d) => setAllFireUnits(d.fire_units || [])).catch(() => {});
    globalApi.getSwarms().then((r) => setActiveSwarms(r.swarms || [])).catch(() => {});
  };

  useEffect(() => {
    refresh();
    const disconnect = connectGlobalWebSocket("quantum-world", {
      onConnectionChange: setWsConnected,
      onSnapshot: (snap) => {
        if (snap.overview) setOverview(snap.overview);
      },
      onWorldEvent: () => refresh(),
      onFrontendCommand: (cmd) => {
        if (cmd.command_type === "camera.focus_country" && cmd.target_id) {
          setSelectedCountryId(cmd.target_id);
          setLastCommandBanner(`JARVIS Camera Focus -> ${cmd.target_id}`);
        } else if (cmd.command_type === "camera.focus_world") {
          setLastCommandBanner("JARVIS Camera Focus -> Full 7-Country Map");
        } else if (cmd.command_type === "camera.show_candidate_routes" && cmd.parameters?.candidates) {
          setCandidateRoutes(cmd.parameters.candidates);
          setLastCommandBanner(`Rendered ${cmd.parameters.candidates.length} candidate 3D routes`);
        }
      },
    });
    return disconnect;
  }, []);

  const selectedCountry = overview?.countries.find((c) => c.country_id === selectedCountryId);

  return (
    <div className="w-screen h-screen bg-[#F7F8FA] text-slate-900 flex flex-col overflow-hidden font-sans">
      {/* Top Aerospace Navigation Bar */}
      <header className="h-12 px-4 bg-white border-b border-slate-200 flex items-center justify-between shrink-0 z-20">
        <div className="flex items-center gap-3">
          <Globe className="w-4 h-4 text-sky-400" />
          <span className="font-semibold tracking-wide text-sm">QUANTUM RESCUE</span>
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-blue-50 text-blue-800 border border-blue-200 font-semibold">
            01 — WORLD COMMAND (:5173)
          </span>
          {overview && (
            <span className="text-xs font-mono text-slate-500">
              DAY {overview.clock.day} · {overview.clock.clock_hhmm} · 10×10 KM CONTINUOUS MAP · v{overview.clock.world_version}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setViewMode("flat")}
            className={`px-3 py-1 rounded text-xs font-medium border ${
              viewMode === "flat"
                ? "bg-blue-50 border-blue-400 text-blue-800 font-semibold"
                : "bg-white border-slate-300 text-slate-600 hover:text-slate-800"
            }`}
          >
            Big 7-Country Flat Open World
          </button>
          <button
            onClick={() => setViewMode("planet")}
            className={`px-3 py-1 rounded text-xs font-medium border ${
              viewMode === "planet"
                ? "bg-blue-50 border-blue-400 text-blue-800 font-semibold"
                : "bg-white border-slate-300 text-slate-600 hover:text-slate-800"
            }`}
          >
            Tactical Flat Map
          </button>
          <span
            className={`text-[11px] font-mono px-2 py-0.5 rounded border ${
              wsConnected ? "bg-emerald-50 border-emerald-300 text-emerald-700 font-semibold" : "bg-red-50 border-red-300 text-red-700 font-semibold"
            }`}
          >
            {wsConnected ? "SYNC LIVE" : "RECONNECTING"}
          </span>
        </div>
      </header>

      {lastCommandBanner && (
        <div className="px-4 py-1.5 bg-blue-50 border-b border-blue-200 text-xs font-mono text-blue-900 flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Radio className="w-3.5 h-3.5 text-sky-400" /> {lastCommandBanner}
          </span>
          <button onClick={() => setLastCommandBanner(null)} className="text-slate-500 hover:text-white">
            Dismiss
          </button>
        </div>
      )}

      {/* Main Viewport */}
      <div className="flex-1 relative overflow-hidden">
        {viewMode === "flat" ? (
          <BigFlatOpenWorld3D
            countries={overview?.countries || []}
            disasters={overview?.active_disasters || []}
            selectedCountryId={selectedCountryId}
            onSelectCountry={setSelectedCountryId}
            candidateRoutes={candidateRoutes}
            allDrones={allDrones}
            allHospitals={allHospitals}
            allShelters={allShelters}
            allAmbulances={allAmbulances}
            allFireUnits={allFireUnits}
            activeSwarms={activeSwarms}
          />
        ) : (
          <TacticalFlatWorldMap
            countries={overview?.countries || []}
            disasters={overview?.active_disasters || []}
            selectedCountryId={selectedCountryId}
            onSelectCountry={setSelectedCountryId}
            drones={allDrones}
            hospitals={allHospitals}
            candidateRoutes={candidateRoutes}
          />
        )}

        {/* Floating Left Seven-Country Selector */}
        <aside className="absolute top-4 left-4 w-64 bg-white/95 backdrop-blur border border-slate-200 shadow-md rounded-md p-3 space-y-2">
          <div className="text-[11px] font-mono uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
            <Compass className="w-3.5 h-3.5 text-sky-400" /> Seven-Country Continent
          </div>
          <div className="space-y-1 max-h-72 overflow-y-auto">
            {(overview?.countries || []).map((c) => (
              <button
                key={c.country_id}
                onClick={() => setSelectedCountryId(c.country_id)}
                className={`w-full text-left px-2.5 py-1.5 rounded text-xs border transition ${
                  c.country_id === selectedCountryId
                    ? "bg-blue-50 border-blue-400 text-blue-900 font-semibold"
                    : "bg-slate-50 border-slate-200 text-slate-700 hover:border-slate-600"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{c.name}</span>
                  <span className="font-mono text-[10px] text-slate-500">{c.flag_code}</span>
                </div>
                <div className="text-[10px] text-slate-500 flex justify-between mt-0.5">
                  <span>{c.archetype}</span>
                  {c.active_disasters > 0 && <span className="text-red-400 font-mono">ALERT</span>}
                </div>
              </button>
            ))}
          </div>
        </aside>

        {/* Floating Right Selected Country Inspector */}
        {selectedCountry && (
          <aside className="absolute top-4 right-4 w-80 bg-white/95 backdrop-blur border border-slate-200 shadow-md rounded-md p-3.5 space-y-3">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-[10px] font-mono text-sky-400">{selectedCountry.country_id}</div>
                <h2 className="text-sm font-semibold">{selectedCountry.name}</h2>
                <div className="text-xs text-slate-500">Capital: {selectedCountry.capital_name}</div>
              </div>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-800">
                Readiness {selectedCountry.readiness_score}%
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="p-2 rounded bg-slate-50 border border-slate-200">
                <div className="text-[10px] text-slate-500">POPULATION</div>
                <div className="text-sm text-slate-900">{selectedCountry.total_population.toLocaleString()}</div>
              </div>
              <div className="p-2 rounded bg-slate-50 border border-slate-200">
                <div className="text-[10px] text-slate-500">EXPOSED</div>
                <div className="text-sm text-amber-400">{selectedCountry.exposed_population.toLocaleString()}</div>
              </div>
              <div className="p-2 rounded bg-slate-50 border border-slate-200">
                <div className="text-[10px] text-slate-500">DRONES AVAIL</div>
                <div className="text-sm text-emerald-400">
                  {selectedCountry.drones_available}/{selectedCountry.drones_total}
                </div>
              </div>
              <div className="p-2 rounded bg-slate-50 border border-slate-200">
                <div className="text-[10px] text-slate-500">HOSPITAL BEDS</div>
                <div className="text-sm text-sky-300">{selectedCountry.available_beds}</div>
              </div>
            </div>

            <div className="text-xs text-slate-500 leading-relaxed">
              <MapPin className="w-3 h-3 inline mr-1 text-slate-500" />
              {selectedCountry.terrain_profile}
            </div>

            <div className="flex gap-2">
              <button
                onClick={() =>
                  globalApi
                    .createDisaster({
                      country_id: selectedCountry.country_id,
                      disaster_type: "FLOOD",
                      severity: 0.78,
                      radius_km: 11.0,
                    })
                    .then(refresh)
                }
                className="flex-1 py-1.5 rounded text-xs font-medium bg-red-50 hover:bg-red-100 border border-red-300 text-red-700 font-semibold flex items-center justify-center gap-1"
              >
                <ShieldAlert className="w-3.5 h-3.5" /> Inject Flood
              </button>
              <button
                onClick={() =>
                  globalApi
                    .createDisaster({
                      country_id: selectedCountry.country_id,
                      disaster_type: "CYCLONE",
                      severity: 0.85,
                      radius_km: 14.0,
                    })
                    .then(refresh)
                }
                className="flex-1 py-1.5 rounded text-xs font-medium bg-amber-50 hover:bg-amber-100 border border-amber-300 text-amber-800 font-semibold"
              >
                Inject Cyclone
              </button>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
};
