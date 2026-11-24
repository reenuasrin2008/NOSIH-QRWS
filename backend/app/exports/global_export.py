from __future__ import annotations
import csv
import html
import io
import json
import zipfile
from collections import deque
from typing import Any, Dict, List

from app.ai.jarvis_agent import JarvisAgent
from app.approvals.engine import ApprovalEngine
from app.core.compat import to_dict, utc_now_iso
from app.navigation.route_explorer import AdvancedRouteExplorer
from app.world.global_engine import GlobalWorldEngine


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (deque, set, tuple)):
        return list(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _safe_dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=_json_default)


def _csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    if not rows:
        return b""
    fieldnames: List[str] = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                fieldnames.append(k)
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        flat = {
            k: (json.dumps(v, default=_json_default) if isinstance(v, (dict, list, deque, set)) else v)
            for k, v in r.items()
        }
        writer.writerow(flat)
    return buf.getvalue().encode("utf-8")


def build_global_geojson(world: GlobalWorldEngine) -> Dict[str, Any]:
    features: List[Dict[str, Any]] = []
    for c in world.countries.values():
        ring = [[pt.lon, pt.lat] for pt in c.boundary]
        if ring:
            ring.append(ring[0])
        features.append({
            "type": "Feature",
            "properties": {"entity_type": "country", "id": c.country_id, "name": c.name, "archetype": c.archetype},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })
    for ev in world.disasters.values():
        features.append({
            "type": "Feature",
            "properties": {"entity_type": "disaster", "id": ev.event_id, "name": ev.name, "type": ev.disaster_type.value, "severity": ev.severity},
            "geometry": {"type": "Point", "coordinates": [ev.origin.lon, ev.origin.lat]},
        })
    for h in world.hospitals.values():
        features.append({
            "type": "Feature",
            "properties": {"entity_type": "hospital", "id": h.hospital_id, "name": h.name, "available_beds": h.available_beds},
            "geometry": {"type": "Point", "coordinates": [h.location.lon, h.location.lat]},
        })
    return {"type": "FeatureCollection", "features": features}


def build_global_experiment_zip(
    world: GlobalWorldEngine,
    route_explorer: AdvancedRouteExplorer,
    approval_engine: ApprovalEngine,
    jarvis: JarvisAgent,
    legacy_summary: Dict[str, Any],
) -> bytes:
    overview = world.get_global_overview()
    buf = io.BytesIO()
    root = "QUANTUM_RESCUE_EXPERIMENT"
    safe_scenario_id = html.escape(str(world.scenario_id))

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{root}/manifest.json", _safe_dumps({
            "exported_at": utc_now_iso(),
            "scenario_id": world.scenario_id,
            "seed": world.seed,
            "world_version": world.event_bus.world_version,
            "format_version": "2.0.0",
        }))
        zf.writestr(f"{root}/experiment_summary.json", _safe_dumps({"global": overview["totals"], "tactical_theater": legacy_summary}))
        zf.writestr(f"{root}/world_configuration.json", _safe_dumps({"clock": world.get_clock_info(), "seed": world.seed}))
        zf.writestr(f"{root}/country_profiles.json", _safe_dumps(overview["countries"]))
        zf.writestr(f"{root}/population_summary.json", _safe_dumps([to_dict(d) for d in world.districts.values()]))
        zf.writestr(f"{root}/disaster_events.json", _safe_dumps([to_dict(d) for d in world.disasters.values()]))
        zf.writestr(f"{root}/drone_telemetry.csv", _csv_bytes([to_dict(d) for d in world.drones.values()]))
        zf.writestr(f"{root}/ambulance_telemetry.csv", _csv_bytes([to_dict(a) for a in world.ambulances.values()]))
        zf.writestr(f"{root}/hospital_status.csv", _csv_bytes([{**to_dict(h), "available_beds": h.available_beds} for h in world.hospitals.values()]))
        zf.writestr(f"{root}/shelter_status.csv", _csv_bytes([{**to_dict(s), "remaining_capacity": s.remaining_capacity} for s in world.shelters.values()]))
        zf.writestr(f"{root}/resource_inventory.csv", _csv_bytes([to_dict(w) for w in world.warehouses.values()]))
        zf.writestr(f"{root}/swarm_operations.json", _safe_dumps([to_dict(s) for s in world.swarms.values()]))
        zf.writestr(f"{root}/route_calculation_logs.json", _safe_dumps(list(route_explorer.route_logs)))
        zf.writestr(f"{root}/ai_interactions.json", _safe_dumps({k: list(v) for k, v in jarvis.conversations.items()}))
        zf.writestr(f"{root}/approval_history.json", _safe_dumps(approval_engine.list_approvals()))
        zf.writestr(f"{root}/audit_log.json", _safe_dumps(list(approval_engine.audit_log)))
        zf.writestr(f"{root}/event_timeline.json", _safe_dumps(world.event_bus.get_events(limit=1000)))
        zf.writestr(f"{root}/world_routes.geojson", _safe_dumps(build_global_geojson(world)))
        zf.writestr(f"{root}/report.html", (
            f"<!doctype html><html><head><meta charset='utf-8'><title>Quantum Rescue Report — {safe_scenario_id}</title>"
            f"<style>body{{font-family:Inter,sans-serif;max-width:960px;margin:2rem auto;color:#0f172a;line-height:1.5}}"
            f"table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #cbd5e1;padding:8px;text-align:left}}</style></head>"
            f"<body><h1>Quantum Rescue — Global Experiment Report</h1>"
            f"<p><strong>Scenario:</strong> {safe_scenario_id} | <strong>Seed:</strong> {world.seed} | "
            f"<strong>World Version:</strong> {world.event_bus.world_version}</p>"
            f"<h2>Global Totals</h2><pre>{html.escape(_safe_dumps(overview['totals']))}</pre>"
            f"<h2>Active Disasters ({len(world.disasters)})</h2><pre>{html.escape(_safe_dumps([to_dict(d) for d in world.disasters.values()]))}</pre>"
            f"</body></html>"
        ))
    return buf.getvalue()
