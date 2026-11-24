from __future__ import annotations

from typing import Any, Callable, Dict

from app.core.compat import to_dict
from app.world.global_engine import GlobalWorldEngine
from app.world.global_models import AmbulanceStatus, HospitalStatus


def _cid(world: GlobalWorldEngine, args: Dict[str, Any]) -> str:
    cid = args.get("country_id") or world.selected_country_id
    if cid not in world.countries:
        cid = world.selected_country_id
    return cid


def build_handlers(world: GlobalWorldEngine) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
    def _get_hospital_status(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        hosps = [h for h in world.hospitals.values() if h.country_id == cid]
        return {
            "country_id": cid,
            "total_hospitals": len(hosps),
            "operational_count": sum(
                1 for h in hosps if h.status in (HospitalStatus.OPERATIONAL, HospitalStatus.PARTIALLY_OPERATIONAL)
            ),
            "total_beds": sum(h.total_beds for h in hosps),
            "occupied_beds": sum(h.occupied_beds for h in hosps),
            "available_beds": sum(h.available_beds for h in hosps),
            "hospitals": [{**to_dict(h), "available_beds": h.available_beds} for h in hosps],
        }

    def _get_available_beds(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        all_countries = bool(args.get("all_countries", False))
        hosps = [
            h for h in world.hospitals.values()
            if (all_countries or h.country_id == cid) and h.status != HospitalStatus.CLOSED
        ]
        hosps.sort(key=lambda h: h.available_beds, reverse=True)
        return {
            "country_id": "ALL" if all_countries else cid,
            "total_available_beds": sum(h.available_beds for h in hosps),
            "total_beds": sum(h.total_beds for h in hosps),
            "hospitals": [
                {
                    "hospital_id": h.hospital_id,
                    "country_id": h.country_id,
                    "name": h.name,
                    "status": h.status.value,
                    "available_beds": h.available_beds,
                    "total_beds": h.total_beds,
                    "triage_load": h.triage_load,
                }
                for h in hosps
            ],
        }

    def _get_ambulance_fleet(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        ambs = [a for a in world.ambulances.values() if a.country_id == cid]
        by_status: Dict[str, int] = {}
        by_equip: Dict[str, int] = {}
        for a in ambs:
            st = a.status.value if hasattr(a.status, "value") else str(a.status)
            by_status[st] = by_status.get(st, 0) + 1
            by_equip[a.equipment_profile] = by_equip.get(a.equipment_profile, 0) + 1
        return {
            "country_id": cid,
            "total_ambulances": len(ambs),
            "available_count": sum(1 for a in ambs if a.status == AmbulanceStatus.AVAILABLE),
            "by_status": by_status,
            "by_equipment": by_equip,
            "ambulances": [to_dict(a) for a in ambs],
        }

    def _get_fire_units(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        units = [f for f in world.fire_units.values() if f.country_id == cid]
        by_type: Dict[str, int] = {}
        for f in units:
            by_type[f.unit_type] = by_type.get(f.unit_type, 0) + 1
        return {
            "country_id": cid,
            "total_units": len(units),
            "available_count": sum(1 for f in units if f.status == "AVAILABLE"),
            "on_scene_count": sum(1 for f in units if f.status == "ON_SCENE"),
            "by_type": by_type,
            "fire_units": [to_dict(f) for f in units],
        }

    return {
        "get_hospital_status": _get_hospital_status,
        "get_available_beds": _get_available_beds,
        "get_ambulance_fleet": _get_ambulance_fleet,
        "calculate_ambulance_requirements": lambda a: world.calculate_ambulance_requirements(
            _cid(world, a), planning_window_hours=float(a.get("window_hours", 4.0))
        ),
        "get_fire_units": _get_fire_units,
    }
