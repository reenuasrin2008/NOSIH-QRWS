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
    def _get_shelter_capacity(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        shelters = [s for s in world.shelters.values() if s.country_id == cid]
        return {
            "country_id": cid,
            "total_shelters": len(shelters),
            "accessible_shelters": sum(1 for s in shelters if s.accessible),
            "total_max_occupancy": sum(s.max_occupancy for s in shelters),
            "total_current_occupancy": sum(s.current_occupancy for s in shelters),
            "total_remaining_capacity": sum(s.remaining_capacity for s in shelters),
            "shelters": [{**to_dict(s), "remaining_capacity": s.remaining_capacity} for s in shelters],
        }

    def _get_warehouse_inventory(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        whs = [w for w in world.warehouses.values() if w.country_id == cid]
        return {
            "country_id": cid,
            "warehouse_count": len(whs),
            "totals": {
                "food_packages": sum(w.food_packages for w in whs),
                "water_liters": round(sum(w.water_liters for w in whs), 1),
                "medical_kits": sum(w.medical_kits for w in whs),
                "first_aid_kits": sum(w.first_aid_kits for w in whs),
                "blankets": sum(w.blankets for w in whs),
                "fuel_liters": round(sum(w.fuel_liters for w in whs), 1),
                "generators": sum(w.generators for w in whs),
                "comm_devices": sum(w.comm_devices for w in whs),
                "rescue_kits": sum(w.rescue_kits for w in whs),
            },
            "warehouses": [to_dict(w) for w in whs],
        }

    def _get_resource_shortages(args: Dict[str, Any]) -> Dict[str, Any]:
        cid = _cid(world, args)
        horizon = float(args.get("horizon_hours", 24.0))
        res = world.calculate_resource_requirements(cid, horizon_hours=horizon)
        amb = world.calculate_ambulance_requirements(cid)
        warnings = list(res["shortage_warnings"])
        if amb["ambulance_deficit"] > 0:
            warnings.append(
                f"Ambulance deficit of {amb['ambulance_deficit']} units "
                f"(recommended {amb['recommended_operational_fleet']}, available {amb['available_ambulances']})."
            )
        return {
            "country_id": cid,
            "horizon_hours": horizon,
            "food_shortage": res["food_packages"]["shortage"],
            "water_shortage_liters": res["water_liters"]["shortage"],
            "medical_kits_shortage": res["medical_kits"]["shortage"],
            "shelter_capacity_shortage": res["shelters"]["shortage"],
            "ambulance_deficit": amb["ambulance_deficit"],
            "shortage_warnings": warnings,
            "has_shortages": bool(warnings) or any(
                v > 0 for v in (
                    res["food_packages"]["shortage"],
                    res["water_liters"]["shortage"],
                    res["medical_kits"]["shortage"],
                    res["shelters"]["shortage"],
                    amb["ambulance_deficit"],
                )
            ),
            "resource_analysis": res,
        }

    return {
        "get_shelter_capacity": _get_shelter_capacity,
        "get_warehouse_inventory": _get_warehouse_inventory,
        "calculate_resource_requirements": lambda a: world.calculate_resource_requirements(
            _cid(world, a), horizon_hours=float(a.get("horizon_hours", 24.0))
        ),
        "get_resource_shortages": _get_resource_shortages,
        "find_mutual_aid_options": lambda a: world.find_mutual_aid_options(
            _cid(world, a), resource_type=a.get("resource_type", "ambulances"), quantity=int(a.get("quantity", 8))
        ),
        "evaluate_rescue_equity": lambda a: world.evaluate_rescue_equity(_cid(world, a)),
    }
