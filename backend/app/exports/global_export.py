from __future__ import annotations
import csv
import io
import json
import zipfile
from typing import Any, Dict, List

from app.ai.jarvis_agent import JarvisAgent
from app.approvals.engine import ApprovalEngine
from app.core.compat import to_dict, utc_now_iso
from app.navigation.route_explorer import AdvancedRouteExplorer
from app.world.global_engine import GlobalWorldEngine


def _csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    if not rows:
        return b""
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        flat = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in r.items()}
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

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{root}/manifest.json", json.dumps({
            "exported_at": utc_now_iso(),
            "scenario_id": world.scenario_id,
            "seed": world.seed,
            "world_version": world.event_bus.world_version,
            "format_version": "2.0.0",
        }, indent=2))
        zf.writestr(f"{root}/experiment_summary.json", json.dumps({"global": overview["totals"], "tactical_theater": legacy_summary}, indent=2))
        zf.writestr(f"{root}/world_configuration.json", json.dumps({"clock": world.get_clock_info(), "seed": world.seed}, indent=2))
        zf.writestr(f"{root}/country_profiles.json", json.dumps(overview["countries"], indent=2))
        zf.writestr(f"{root}/population_summary.json", json.dumps([to_dict(d) for d in world.districts.values()], indent=2))
        zf.writestr(f"{root}/disaster_events.json", json.dumps([to_dict(d) for d in world.disasters.values()], indent=2))
        zf.writestr(f"{root}/drone_telemetry.csv", _csv_bytes([to_dict(d) for d in world.drones.values()]))
        zf.writestr(f"{root}/ambulance_telemetry.csv", _csv_bytes([to_dict(a) for a in world.ambulances.values()]))
        zf.writestr(f"{root}/hospital_status.csv", _csv_bytes([{**to_dict(h), "available_beds": h.available_beds} for h in world.hospitals.values()]))
        zf.writestr(f"{root}/shelter_status.csv", _csv_bytes([{**to_dict(s), "remaining_capacity": s.remaining_capacity} for s in world.shelters.values()]))
        zf.writestr(f"{root}/resource_inventory.csv", _csv_bytes([to_dict(w) for w in world.warehouses.values()]))
        zf.writestr(f"{root}/swarm_operations.json", json.dumps([to_dict(s) for s in world.swarms.values()], indent=2))
        zf.writestr(f"{root}/route_calculation_logs.json", json.dumps(route_explorer.route_logs, indent=2))
        zf.writestr(f"{root}/ai_interactions.json", json.dumps({k: list(v) for k, v in jarvis.conversations.items()}, indent=2))
        zf.writestr(f"{root}/approval_history.json", json.dumps(approval_engine.list_approvals(), indent=2))
        zf.writestr(f"{root}/audit_log.json", json.dumps(list(approval_engine.audit_log), indent=2))
        zf.writestr(f"{root}/event_timeline.json", json.dumps(world.event_bus.get_events(limit=1000), indent=2))
        zf.writestr(f"{root}/world_routes.geojson", json.dumps(build_global_geojson(world), indent=2))
        zf.writestr(f"{root}/report.html", (
            f"<!doctype html><html><head><meta charset='utf-8'><title>Quantum Rescue Report — {world.scenario_id}</title>"
            f"<style>body{{font-family:Inter,sans-serif;max-width:960px;margin:2rem auto;color:#0f172a;line-height:1.5}}"
            f"table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #cbd5e1;padding:8px;text-align:left}}</style></head>"
            f"<body><h1>Quantum Rescue — Global Experiment Report</h1>"
            f"<p><strong>Scenario:</strong> {world.scenario_id} | <strong>Seed:</strong> {world.seed} | "
            f"<strong>World Version:</strong> {world.event_bus.world_version}</p>"
            f"<h2>Global Totals</h2><pre>{json.dumps(overview['totals'], indent=2)}</pre>"
            f"<h2>Active Disasters ({len(world.disasters)})</h2><pre>{json.dumps([to_dict(d) for d in world.disasters.values()], indent=2)}</pre>"
            f"</body></html>"
        ))
    return buf.getvalue()
