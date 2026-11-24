import React, { useEffect, useMemo, useRef, useState } from "react";
import { Crosshair, Layers, Minus, Plus, RotateCcw } from "lucide-react";
import type { CountrySummary, DisasterEvent, GeoPoint } from "../../shared/globalTypes";

interface TacticalFlatWorldMapProps {
  countries: CountrySummary[];
  disasters: DisasterEvent[];
  selectedCountryId: string;
  onSelectCountry: (countryId: string) => void;
  drones?: any[];
  hospitals?: any[];
  candidateRoutes?: Array<{ route_id: string; feasible: boolean; waypoints: GeoPoint[] }>;
  title?: string;
}

function project(lat: number, lon: number): [number, number] {
  const x = ((lon + 180) / 360) * 1000;
  const y = ((90 - lat) / 180) * 500;
  return [x, y];
}

const CONTINENT_PATHS = [
  "M 85,78 L 165,65 L 250,75 L 285,125 L 245,165 L 210,195 L 185,225 L 155,210 L 120,160 L 90,120 Z",
  "M 235,245 L 295,255 L 330,305 L 305,385 L 270,435 L 250,415 L 245,340 L 225,280 Z",
  "M 445,82 L 530,72 L 560,110 L 535,148 L 485,152 L 455,135 Z",
  "M 455,175 L 545,172 L 590,225 L 575,320 L 530,385 L 490,340 L 465,260 L 442,215 Z",
  "M 555,75 L 740,68 L 860,105 L 845,185 L 780,235 L 730,245 L 690,210 L 620,215 L 575,165 Z",
  "M 775,305 L 865,302 L 885,365 L 835,392 L 772,368 Z",
];

export const TacticalFlatWorldMap: React.FC<TacticalFlatWorldMapProps> = ({
  countries,
  disasters,
  selectedCountryId,
  onSelectCountry,
  drones = [],
  hospitals = [],
  candidateRoutes = [],
  title = "GLOBAL TACTICAL MONITOR — 7 NATIONS",
}) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const [zoom, setZoom] = useState(2.2);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: -1080, y: -180 });
  const [dragging, setDragging] = useState(false);
  const lastMouseRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const [layers, setLayers] = useState({
    borders: true,
    disasters: true,
    drones: true,
    hospitals: true,
    routes: true,
  });
  const [hovered, setHovered] = useState<string | null>(null);

  // Center-anchored zoom so zooming never jumps to top-left corner
  const applyZoom = (factor: number) => {
    setZoom((prevZoom) => {
      const nextZoom = Math.max(1.0, Math.min(7.0, prevZoom * factor));
      const ratio = nextZoom / prevZoom;
      setPan((p) => ({
        x: 500 - (500 - p.x) * ratio,
        y: 250 - (250 - p.y) * ratio,
      }));
      return nextZoom;
    });
  };

  const centerOnLatLon = (lat: number, lon: number, targetZoom = 3.0) => {
    const [px, py] = project(lat, lon);
    setZoom(targetZoom);
    setPan({ x: 500 - px * targetZoom, y: 250 - py * targetZoom });
  };

  // Auto-focus when selectedCountryId changes (including via JARVIS camera commands)
  useEffect(() => {
    const sel = countries.find((c) => c.country_id === selectedCountryId);
    if (sel) {
      centerOnLatLon(sel.center.lat, sel.center.lon, Math.max(zoom, 2.4));
    }
  }, [selectedCountryId]);

  const focusTheater = () => centerOnLatLon(20.0, 79.0, 2.2);
  const resetGlobal = () => {
    setZoom(1.0);
    setPan({ x: 0, y: 0 });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!dragging || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const scaleX = 1000 / Math.max(1, rect.width);
    const scaleY = 500 / Math.max(1, rect.height);
    const dx = (e.clientX - lastMouseRef.current.x) * scaleX;
    const dy = (e.clientY - lastMouseRef.current.y) * scaleY;
    lastMouseRef.current = { x: e.clientX, y: e.clientY };
    setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    applyZoom(e.deltaY < 0 ? 1.15 : 0.87);
  };

  const activeDisasters = useMemo(
    () => disasters.filter((d) => d.status === "ACTIVE"),
    [disasters]
  );

  return (
    <div className="w-full h-full bg-[#E8F1F8] relative overflow-hidden select-none flex flex-col">
      <div className="h-9 px-3 bg-white/95 border-b border-slate-200 flex items-center justify-between text-[11px] font-mono z-10">
        <div className="flex items-center gap-2 text-slate-800 font-semibold">
          <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse" />
          <span className="tracking-wider">{title}</span>
          <span className="text-slate-400 font-normal">| FLAT GIS PROJECTION</span>
        </div>

        <div className="flex items-center gap-1.5">
          {(["borders", "disasters", "drones", "hospitals", "routes"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setLayers((prev) => ({ ...prev, [k]: !prev[k] }))}
              className={`px-2 py-0.5 rounded uppercase text-[10px] border transition ${
                layers[k]
                  ? "bg-blue-50 border-blue-300 text-blue-800 font-medium"
                  : "bg-slate-50 border-slate-200 text-slate-400"
              }`}
            >
              {k}
            </button>
          ))}
        </div>
      </div>

      <div
        className="flex-1 relative cursor-grab active:cursor-grabbing"
        onWheel={handleWheel}
        onMouseDown={(e) => {
          setDragging(true);
          lastMouseRef.current = { x: e.clientX, y: e.clientY };
        }}
        onMouseMove={handleMouseMove}
        onMouseUp={() => setDragging(false)}
        onMouseLeave={() => setDragging(false)}
      >
        <svg ref={svgRef} viewBox="0 0 1000 500" className="w-full h-full">
          <defs>
            <radialGradient id="disasterGlowLight" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#dc2626" stopOpacity="0.42" />
              <stop offset="100%" stopColor="#dc2626" stopOpacity="0" />
            </radialGradient>
            <pattern id="gridPatternLight" width="50" height="50" patternUnits="userSpaceOnUse">
              <path d="M 50 0 L 0 0 0 50" fill="none" stroke="#CBDCEB" strokeWidth="0.7" />
            </pattern>
          </defs>

          <rect width="1000" height="500" fill="#E8F1F8" />
          <rect width="1000" height="500" fill="url(#gridPatternLight)" />

          <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
            {CONTINENT_PATHS.map((d, idx) => (
              <path key={idx} d={d} fill="#F4F6F2" stroke="#94A3B8" strokeWidth={0.9 / zoom} />
            ))}

            {countries.map((c) => {
              const isSel = c.country_id === selectedCountryId;
              const [cx, cy] = project(c.center.lat, c.center.lon);
              const polyPts = c.boundary.map((pt) => project(pt.lat, pt.lon).join(",")).join(" ");

              return (
                <g
                  key={c.country_id}
                  className="cursor-pointer"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectCountry(c.country_id);
                  }}
                  onMouseEnter={() =>
                    setHovered(
                      `${c.name} (${c.country_id}) · Exposed: ${c.exposed_population.toLocaleString()} · Drones: ${c.drones_available}/${c.drones_total}`
                    )
                  }
                  onMouseLeave={() => setHovered(null)}
                >
                  {layers.borders && polyPts && (
                    <polygon
                      points={polyPts}
                      fill={
                        isSel
                          ? "rgba(37, 99, 235, 0.16)"
                          : c.active_disasters > 0
                          ? "rgba(220, 38, 38, 0.14)"
                          : "rgba(15, 118, 110, 0.08)"
                      }
                      stroke={isSel ? "#1D4ED8" : c.active_disasters > 0 ? "#DC2626" : "#475569"}
                      strokeWidth={(isSel ? 1.8 : 0.85) / zoom}
                    />
                  )}
                  <circle
                    cx={cx}
                    cy={cy}
                    r={(isSel ? 4.2 : 3.0) / zoom}
                    fill={c.active_disasters > 0 ? "#DC2626" : isSel ? "#1D4ED8" : "#15803D"}
                    stroke="#FFFFFF"
                    strokeWidth={0.9 / zoom}
                  />
                  <text
                    x={cx + 5 / zoom}
                    y={cy + 3 / zoom}
                    fill={isSel ? "#0F172A" : "#334155"}
                    fontWeight={isSel ? "700" : "500"}
                    fontSize={9 / zoom}
                    fontFamily="monospace"
                  >
                    {c.flag_code} · {c.name}
                  </text>
                </g>
              );
            })}

            {layers.hospitals &&
              hospitals.map((h) => {
                const [hx, hy] = project(h.location.lat, h.location.lon);
                return <circle key={h.hospital_id} cx={hx} cy={hy} r={2.0 / zoom} fill="#0284C7" stroke="#FFFFFF" strokeWidth={0.4 / zoom} />;
              })}

            {layers.drones &&
              drones.map((d) => {
                const [dx, dy] = project(d.location.lat, d.location.lon);
                const col = d.status === "DESTROYED" ? "#DC2626" : d.status === "IN_FLIGHT" ? "#15803D" : "#0F766E";
                return <circle key={d.drone_id} cx={dx} cy={dy} r={1.7 / zoom} fill={col} />;
              })}

            {layers.disasters &&
              activeDisasters.map((ev) => {
                const [ex, ey] = project(ev.origin.lat, ev.origin.lon);
                return (
                  <g key={ev.event_id}>
                    <circle cx={ex} cy={ey} r={18 / zoom} fill="url(#disasterGlowLight)" />
                    <circle
                      cx={ex}
                      cy={ey}
                      r={7.5 / zoom}
                      fill="none"
                      stroke={ev.disaster_type === "CYCLONE" ? "#D97706" : "#DC2626"}
                      strokeWidth={1.3 / zoom}
                      strokeDasharray={`${3 / zoom} ${2 / zoom}`}
                    />
                  </g>
                );
              })}

            {layers.routes &&
              candidateRoutes.slice(0, 10).map((rc) => {
                const pts = rc.waypoints.map((w) => project(w.lat, w.lon).join(",")).join(" ");
                return (
                  <polyline
                    key={rc.route_id}
                    points={pts}
                    fill="none"
                    stroke={rc.feasible ? "#15803D" : "#DC2626"}
                    strokeWidth={(rc.feasible ? 1.8 : 1.0) / zoom}
                    strokeDasharray={rc.feasible ? undefined : `${3 / zoom} ${2 / zoom}`}
                  />
                );
              })}
          </g>
        </svg>

        {hovered && (
          <div className="absolute top-3 left-3 px-2.5 py-1 rounded bg-white/95 border border-slate-300 shadow-sm text-[11px] font-mono text-slate-800 pointer-events-none">
            {hovered}
          </div>
        )}

        <div className="absolute bottom-3 right-3 flex flex-col gap-1 bg-white/95 border border-slate-300 rounded p-1 shadow-sm">
          <button onClick={() => applyZoom(1.25)} className="p-1.5 hover:bg-slate-100 rounded text-slate-700" title="Zoom In">
            <Plus className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => applyZoom(0.8)} className="p-1.5 hover:bg-slate-100 rounded text-slate-700" title="Zoom Out">
            <Minus className="w-3.5 h-3.5" />
          </button>
          <button onClick={focusTheater} className="p-1.5 hover:bg-slate-100 rounded text-blue-700" title="Focus 7-Nation Theater">
            <Crosshair className="w-3.5 h-3.5" />
          </button>
          <button onClick={resetGlobal} className="p-1.5 hover:bg-slate-100 rounded text-slate-500" title="Reset Global View">
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="absolute bottom-3 left-3 px-2.5 py-1.5 rounded bg-white/95 border border-slate-300 shadow-sm flex items-center gap-3 text-[10px] font-mono text-slate-700">
          <span className="flex items-center gap-1 font-semibold"><Layers className="w-3 h-3 text-blue-700" /> LEGEND:</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-600" /> DISASTER</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-700" /> DRONE</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-sky-600" /> HOSPITAL</span>
        </div>
      </div>
    </div>
  );
};
