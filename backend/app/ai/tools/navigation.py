from __future__ import annotations

from typing import Any, Callable, Dict

from app.core.compat import to_dict
from app.world.global_engine import GlobalWorldEngine


def _cid(world: GlobalWorldEngine, args: Dict[str, Any]) -> str:
    cid = args.get("country_id") or world.selected_country_id
    if cid not in world.countries:
        cid = world.selected_country_id
    return cid


def build_handlers(world: GlobalWorldEngine) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
    def _view_country(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        return to_dict(
            world.event_bus.dispatch_frontend_command(
                "camera.focus_country",
                target_id=cid,
                frontend="quantum-world",
                parameters={"transition": "smooth", "show_boundary": True, "show_city_markers": True},
            )
        )

    def _focus_hospital(args: Dict[str, Any]) -> Dict[str, Any]:
        hid = args.get("hospital_id")
        if not hid or hid not in world.hospitals:
            cid = _cid(world, args)
            h = next((x for x in world.hospitals.values() if x.country_id == cid), None)
            hid = h.hospital_id if h else None
        return to_dict(
            world.event_bus.dispatch_frontend_command(
                "camera.focus_hospital", target_id=hid, frontend="quantum-world"
            )
        )

    def _focus_drone(args: Dict[str, Any]) -> Dict[str, Any]:
        did = args.get("drone_id")
        if not did or did not in world.drones:
            cid = _cid(world, args)
            d = next((x for x in world.drones.values() if x.country_id == cid), None)
            did = d.drone_id if d else None
        return to_dict(
            world.event_bus.dispatch_frontend_command(
                "camera.focus_drone", target_id=did, frontend="quantum-world"
            )
        )

    return {
        "view_global_world": lambda a: to_dict(
            world.event_bus.dispatch_frontend_command("camera.focus_world", frontend="quantum-world")
        ),
        "view_country": _view_country,
        "focus_hospital": _focus_hospital,
        "focus_drone": _focus_drone,
    }
