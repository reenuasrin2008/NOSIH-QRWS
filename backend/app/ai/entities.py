from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.ai.session import SessionContext
from app.world.global_engine import GlobalWorldEngine

# Pre-compiled regex patterns for sub-millisecond entity extraction (Tier 1.3 disambiguated)
_RE_COUNTRY_NUM = re.compile(r"\bcountry\s*[-#]?\s*0?([1-7])\b", re.IGNORECASE)
_RE_HOSPITAL_ID = re.compile(r"\b(HOSP-\d{2}-\d{2})\b", re.IGNORECASE)
# Require disambiguating keyword ("drone"/"uav"/"unit") for short IDs (D-XX),
# or unambiguous 2-segment ID (D-XX-XX) not preceded by alphanumeric/hyphen (rejects "3D-15" & bare "D-20").
_RE_DRONE_ID = re.compile(
    r"\b(?:drone|uav|unit)\s+(D-\d{2}-\d{2}|D-\d{2})\b|(?<![A-Za-z0-9-])(D-\d{2}-\d{2})\b",
    re.IGNORECASE,
)
_RE_DISTRICT_ID = re.compile(r"\b(COUNTRY-\d{2}-CITY-\d{2}-DIST-\d{2})\b", re.IGNORECASE)
_RE_DRONE_COUNT = re.compile(r"\b(\d+)\s*[-\s]?(?:drone|drones|uav|unit|units)\b", re.IGNORECASE)
_RE_AMB_COUNT = re.compile(r"\b(\d+)\s*[-\s]?(?:ambulance|ambulances|ems)\b", re.IGNORECASE)
_RE_QTY_GENERIC = re.compile(r"\b(\d+)\s*[-\s]?(?:food|water|kit|kits|package|packages|shelter|shelters|unit|units)\b", re.IGNORECASE)
# Require battery/charge/power context OR explicit "%" sign so "under 20 minutes" never false-positives.
_RE_BATTERY_PCT = re.compile(
    r"\b(?:battery|charge|power)\s*(?:below|under|<|threshold\s*=?)\s*(\d{1,3})\s*%?|(?:\b(?:below|under)|<)\s*(\d{1,3})\s*%",
    re.IGNORECASE,
)
_RE_SEVERITY_PCT = re.compile(r"severity\s*(?:of\s*)?(\d{1,3})\s*%", re.IGNORECASE)
_RE_HOURS = re.compile(r"\b(\d{1,3})\s*(?:h|hr|hrs|hour|hours)\b", re.IGNORECASE)

_DISASTER_KEYWORDS: List[Tuple[str, str]] = [
    ("multi-hazard", "MULTI_HAZARD_CASCADE"),
    ("multi hazard", "MULTI_HAZARD_CASCADE"),
    ("industrial accident", "INDUSTRIAL_ACCIDENT"),
    ("power outage", "POWER_OUTAGE"),
    ("blackout", "COMM_BLACKOUT"),
    ("comm blackout", "COMM_BLACKOUT"),
    ("wildfire", "WILDFIRE"),
    ("forest fire", "WILDFIRE"),
    ("earthquake", "EARTHQUAKE"),
    ("landslide", "LANDSLIDE"),
    ("heatwave", "HEATWAVE"),
    ("cyclone", "CYCLONE"),
    ("hurricane", "CYCLONE"),
    ("flood", "FLOOD"),
    ("fire", "FIRE"),
]

_SENSOR_KEYWORDS: List[str] = ["thermal", "lidar", "acoustic", "gas_sensor", "sonar", "rf_relay", "rgb"]


def build_country_lookup(world: GlobalWorldEngine) -> List[Tuple[str, str]]:
    """Pre-index country names, capitals, first tokens, and flag codes for fast resolution."""
    pairs: List[Tuple[str, str]] = []
    for cid, c in world.countries.items():
        pairs.append((c.name.lower(), cid))
        pairs.append((c.capital_name.lower(), cid))
        first_word = c.name.split()[0].lower()
        if len(first_word) >= 4:
            pairs.append((first_word, cid))
        if c.flag_code:
            pairs.append((c.flag_code.lower(), cid))
    # Longest match first to prevent partial collisions
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


def resolve_country(text: str, ctx: SessionContext, country_lookup: List[Tuple[str, str]]) -> str:
    m = _RE_COUNTRY_NUM.search(text)
    if m:
        cid = f"COUNTRY-0{m.group(1)}"
        ctx.active_country_id = cid
        return cid
    low = text.lower()
    for token, cid in country_lookup:
        if len(token) <= 3:
            if re.search(rf"\b{re.escape(token)}\b", low):
                ctx.active_country_id = cid
                return cid
        elif token in low:
            ctx.active_country_id = cid
            return cid
    return ctx.active_country_id


def extract_drone_id(text: str) -> Optional[str]:
    m = _RE_DRONE_ID.search(text)
    if not m:
        return None
    val = m.group(1) or m.group(2)
    return val.upper() if val else None


def extract_battery_threshold(text: str) -> Optional[float]:
    m = _RE_BATTERY_PCT.search(text)
    if not m:
        return None
    val = m.group(1) or m.group(2)
    return float(val) if val is not None else None


def extract_disaster_type(low: str) -> Optional[str]:
    for kw, dtype in _DISASTER_KEYWORDS:
        if kw in low:
            return dtype
    return None


def extract_entities(
    message: str,
    low: str,
    ctx: SessionContext,
    world: GlobalWorldEngine,
    country_lookup: List[Tuple[str, str]],
) -> Dict[str, Any]:
    cid = resolve_country(message, ctx, country_lookup)
    if cid not in world.countries:
        cid = world.selected_country_id
        ctx.active_country_id = cid
    country = world.countries[cid]

    m_hosp = _RE_HOSPITAL_ID.search(message)
    hospital_id = m_hosp.group(1).upper() if m_hosp else None
    if hospital_id and hospital_id in world.hospitals:
        ctx.selected_hospital_id = hospital_id

    drone_id = extract_drone_id(message)
    if drone_id and drone_id in world.drones:
        ctx.selected_drone_id = drone_id

    m_dist = _RE_DISTRICT_ID.search(message)
    district_id = m_dist.group(1).upper() if m_dist else None
    if district_id and district_id in world.districts:
        ctx.active_district_id = district_id

    disaster_type = extract_disaster_type(low)

    counts: Dict[str, Any] = {}
    if m := _RE_DRONE_COUNT.search(low):
        counts["drone_count"] = int(m.group(1))
    if m := _RE_AMB_COUNT.search(low):
        counts["ambulance_count"] = int(m.group(1))
    if m := _RE_QTY_GENERIC.search(low):
        counts["quantity"] = int(m.group(1))
    battery_thresh = extract_battery_threshold(low)
    if battery_thresh is not None:
        counts["battery_threshold"] = battery_thresh
    if m := _RE_SEVERITY_PCT.search(low):
        counts["severity"] = round(max(0.1, min(1.0, int(m.group(1)) / 100.0)), 2)
    if m := _RE_HOURS.search(low):
        counts["hours"] = float(m.group(1))

    objective = (
        "LOWEST_ENERGY" if ("battery" in low or "energy" in low)
        else "FASTEST" if ("fastest" in low or "quickest" in low)
        else "SAFEST" if ("safest" in low or "safe route" in low)
        else "HIGHEST_RELIABILITY" if "reliable" in low
        else "WIND_OPTIMIZED" if "wind" in low
        else "EMERGENCY" if "emergency" in low
        else "BALANCED"
    )

    resource_type = (
        "drones" if ("spare drone" in low or "mutual aid drone" in low or "transfer drone" in low)
        else "food" if ("food" in low and ("mutual aid" in low or "transfer" in low))
        else "ambulances"
    )

    sensor_type = next((s for s in _SENSOR_KEYWORDS if s in low), "thermal")

    return {
        "country_id": cid,
        "country_name": country.name,
        "capital_name": country.capital_name,
        "hospital_id": hospital_id,
        "drone_id": drone_id,
        "district_id": district_id,
        "disaster_type": disaster_type,
        "counts": counts,
        "objective": objective,
        "resource_type": resource_type,
        "sensor_type": sensor_type,
    }
