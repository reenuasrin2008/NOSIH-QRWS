from __future__ import annotations
import math
import random
from typing import List, Tuple
from app.core.config import DEFAULT_SCENARIO_ID, DEFAULT_SCENARIO_NAME, DEFAULT_SEED, WORLD_SIZE
from app.core.models import (
    Building, CityEnvironment, HazardZone, RoadSegment, Station, VehicleProp, WeatherState
)


def generate_city(
    seed: int = DEFAULT_SEED,
    scenario_id: str = DEFAULT_SCENARIO_ID,
    scenario_name: str = DEFAULT_SCENARIO_NAME,
    city_density: float = 1.0,
    building_density: float = 1.0,
) -> CityEnvironment:
    """
    Deterministic seeded 4,000 x 4,000m multi-district metropolis generator:
    - Dense Downtown Financial Core (90-210m glass skyscrapers)
    - Eastern Coastal Port & Industrial Logistics Belt
    - Outer Suburban Residential & Apartment Grids
    - Wide Adyar River Delta (z=2000, width=160m) with multi-lane flyover bridges
    - 1,400-1,800 buildings (instanced on GPU), 300+ streetlights, 600+ trees, 80+ moving vehicles
    """
    rng = random.Random(seed)
    world = WORLD_SIZE
    river_z = 2000.0
    river_width = 160.0

    # Arterial highway grid every 400m
    roads: List[RoadSegment] = []
    h_lines = [400.0, 800.0, 1200.0, 1600.0, 2400.0, 2800.0, 3200.0, 3600.0]
    for idx, pos in enumerate(h_lines):
        roads.append(RoadSegment(
            id=f"RD-H-{idx+1}",
            start=(80.0, pos),
            end=(world - 80.0, pos),
            width=36.0 if pos in (800.0, 1600.0, 2400.0, 3200.0) else 24.0,
            is_bridge=False,
            blocked=False,
        ))

    v_lines = [400.0, 800.0, 1200.0, 1600.0, 2000.0, 2400.0, 2800.0, 3200.0, 3600.0]
    for idx, pos in enumerate(v_lines):
        is_major = pos in (800.0, 1600.0, 2000.0, 2400.0, 3200.0)
        roads.append(RoadSegment(
            id=f"RD-V-{idx+1}",
            start=(pos, 80.0),
            end=(pos, world - 80.0),
            width=36.0 if is_major else 24.0,
            is_bridge=is_major,
            blocked=(pos == 2000.0),  # Central river bridge blocked in Demo
        ))

    # 3 Major Hospitals + 5 Distributed Charging Hubs across the 4x4 km metropolis
    stations: List[Station] = [
        Station(id="ST-HOSP-1", name="Chennai Central Emergency Hospital", kind="hospital", position=(1000.0, 0.0, 1000.0), capacity=12),
        Station(id="ST-HOSP-2", name="Adyar Trauma & Rescue Center", kind="hospital", position=(3000.0, 0.0, 2950.0), capacity=12),
        Station(id="ST-HOSP-3", name="Guindy Metro Medical Wing", kind="hospital", position=(1050.0, 0.0, 3000.0), capacity=10),
        Station(id="ST-CHG-1", name="Central Command Helipad HQ", kind="charging_station", position=(2200.0, 0.0, 1750.0), capacity=12),
        Station(id="ST-CHG-2", name="North Corridor Charging Hub", kind="charging_station", position=(2200.0, 0.0, 620.0), capacity=10),
        Station(id="ST-CHG-3", name="East Port Logistics Pad", kind="charging_station", position=(3380.0, 0.0, 1020.0), capacity=10),
        Station(id="ST-CHG-4", name="West Industrial Depot", kind="charging_station", position=(620.0, 0.0, 2220.0), capacity=10),
        Station(id="ST-CHG-5", name="South Delta Charging Base", kind="charging_station", position=(2180.0, 0.0, 3380.0), capacity=10),
    ]

    # Metropolitan-scale Disaster Zones
    hazards: List[HazardZone] = [
        HazardZone(id="HZ-FLOOD-1", kind="flood", x=2780.0, z=2480.0, radius=420.0, severity=0.88, altitude_ceiling=24.0, active=True),
        HazardZone(id="HZ-FLOOD-2", kind="flood", x=1260.0, z=2350.0, radius=280.0, severity=0.76, altitude_ceiling=20.0, active=True),
        HazardZone(id="HZ-FIRE-1", kind="fire", x=1380.0, z=1420.0, radius=185.0, severity=0.95, altitude_ceiling=140.0, active=True),
        HazardZone(id="HZ-FIRE-2", kind="fire", x=2640.0, z=1180.0, radius=165.0, severity=0.92, altitude_ceiling=130.0, active=True),
        HazardZone(id="HZ-FIRE-3", kind="fire", x=3150.0, z=1720.0, radius=150.0, severity=0.88, altitude_ceiling=125.0, active=True),
        HazardZone(id="HZ-NFZ-1", kind="no_fly", x=1800.0, z=1150.0, radius=155.0, severity=1.0, altitude_ceiling=240.0, active=True),
        HazardZone(id="HZ-NFZ-2", kind="no_fly", x=2240.0, z=2780.0, radius=165.0, severity=1.0, altitude_ceiling=240.0, active=True),
        HazardZone(id="HZ-NFZ-3", kind="no_fly", x=980.0, z=1550.0, radius=140.0, severity=1.0, altitude_ceiling=240.0, active=True),
    ]

    # Landmark Hospital & HQ Complexes
    buildings: List[Building] = [
        Building(id="BLD-HOSP-1", kind="hospital", x=1000.0, z=1000.0, width=96.0, depth=74.0, height=58.0, color="#9aa4b2", has_helipad=True, roof_style="helipad"),
        Building(id="BLD-HOSP-2", kind="hospital", x=3000.0, z=2950.0, width=102.0, depth=78.0, height=64.0, color="#9aa4b2", has_helipad=True, roof_style="helipad"),
        Building(id="BLD-HOSP-3", kind="hospital", x=1050.0, z=3000.0, width=88.0, depth=70.0, height=52.0, color="#9aa4b2", has_helipad=True, roof_style="helipad"),
        Building(id="BLD-HQ-1", kind="emergency_station", x=2200.0, z=1750.0, width=84.0, depth=72.0, height=48.0, color="#7b8696", has_helipad=True, roof_style="helipad"),
    ]

    palette = {
        "commercial": ["#2a3340", "#323d4d", "#242c37", "#3b4759"],
        "residential": ["#434b57", "#4d5563", "#3b434f", "#535b69"],
        "apartment": ["#48505c", "#525b68", "#3f4753"],
        "industrial": ["#3a3f46", "#444a52", "#4c5158"],
        "warehouse": ["#43484f", "#4e535b"],
    }

    def invalid_spot(x: float, z: float, half_d: float = 34.0) -> bool:
        if abs(z - river_z) < (river_width / 2.0 + half_d + 28.0):
            return True
        for st in stations:
            if math.hypot(x - st.position[0], z - st.position[2]) < 125.0:
                return True
        return False

    b_counter = 1
    trees: List[Tuple[float, float, float]] = []

    # 10x10 macro-blocks (each 400x400m) with 4x4 sub-plots => ~1,500+ buildings!
    block_centers = [200.0 + i * 400.0 for i in range(10)]
    sub_offsets = [-130.0, -45.0, 45.0, 130.0]

    for bx in block_centers:
        for bz in block_centers:
            # Skip river corridor blocks
            if abs(bz - river_z) < 160.0:
                continue

            # Dedicated Metropolitan Parks
            if (bx == 1800.0 and bz == 2600.0) or (bx == 1400.0 and bz == 1000.0) or (bx == 2600.0 and bz == 1800.0):
                for _ in range(55):
                    trees.append((round(bx + rng.uniform(-160, 160), 1), round(bz + rng.uniform(-160, 160), 1), round(rng.uniform(1.4, 2.8), 2)))
                continue

            if rng.random() > min(1.0, 0.94 * city_density):
                continue

            dist_center = math.hypot(bx - 2000.0, bz - 1800.0)
            is_east_port = bx >= 3200.0

            for sx in sub_offsets:
                for sz in sub_offsets:
                    if rng.random() > min(1.0, 0.78 * building_density):
                        if rng.random() < 0.35:
                            trees.append((round(bx + sx, 1), round(bz + sz, 1), round(rng.uniform(1.2, 2.4), 2)))
                        continue
                    x = bx + sx + rng.uniform(-10.0, 10.0)
                    z = bz + sz + rng.uniform(-10.0, 10.0)
                    if invalid_spot(x, z):
                        continue

                    if dist_center < 820.0:
                        # Downtown Financial Core
                        kind = rng.choice(["commercial", "commercial", "commercial", "apartment"])
                        h = rng.uniform(75.0, 205.0)
                        w = rng.uniform(36.0, 58.0)
                        d = rng.uniform(36.0, 58.0)
                    elif is_east_port:
                        # Coastal Port & Industrial Belt
                        kind = rng.choice(["industrial", "warehouse", "warehouse"])
                        h = rng.uniform(18.0, 44.0)
                        w = rng.uniform(42.0, 68.0)
                        d = rng.uniform(34.0, 58.0)
                    elif dist_center < 1450.0:
                        # Mid-town Mixed Urban
                        kind = rng.choice(["apartment", "commercial", "residential"])
                        h = rng.uniform(34.0, 96.0)
                        w = rng.uniform(32.0, 54.0)
                        d = rng.uniform(32.0, 52.0)
                    else:
                        # Outer Suburban Residential Grids
                        kind = rng.choice(["residential", "apartment", "industrial"])
                        h = rng.uniform(16.0, 46.0)
                        w = rng.uniform(28.0, 48.0)
                        d = rng.uniform(28.0, 46.0)

                    roof_style = rng.choice(["flat", "hvac", "tiered", "spire"]) if kind == "commercial" else rng.choice(["flat", "hvac"])
                    buildings.append(Building(
                        id=f"BLD-{b_counter:04d}",
                        kind=kind,
                        x=round(x, 1),
                        z=round(z, 1),
                        width=round(w, 1),
                        depth=round(d, 1),
                        height=round(h, 1),
                        color=rng.choice(palette[kind]),
                        has_helipad=(kind == "commercial" and h > 155.0 and rng.random() < 0.2),
                        roof_style=roof_style,
                    ))
                    b_counter += 1

    # Streetlights along primary 4x4 km avenues
    streetlights: List[Tuple[float, float]] = []
    for pos in [800.0, 1600.0, 2400.0, 3200.0]:
        for t in range(160, 3860, 150):
            streetlights.append((float(t), pos - 21.0))
            streetlights.append((float(t), pos + 21.0))

    # 80+ Moving Ground Vehicles (Civilian, Ambulances, Fire Trucks)
    vehicles: List[VehicleProp] = []
    vid = 1
    for pos in [800.0, 1600.0, 2400.0, 3200.0]:
        for _ in range(12):
            kind = rng.choice(["civilian", "civilian", "civilian", "ambulance", "fire_truck"])
            vehicles.append(VehicleProp(
                id=f"VEH-{vid:03d}", kind=kind,
                x=round(rng.uniform(140.0, 3860.0), 1),
                z=pos + rng.choice([-8.5, 8.5]),
                heading_rad=math.pi / 2 if rng.random() < 0.5 else -math.pi / 2,
                axis="x", speed_mps=rng.uniform(14.0, 24.0), road_pos=pos,
            ))
            vid += 1
    for pos in [800.0, 1600.0, 2400.0, 3200.0]:
        for _ in range(10):
            kind = rng.choice(["civilian", "civilian", "ambulance"])
            vehicles.append(VehicleProp(
                id=f"VEH-{vid:03d}", kind=kind,
                x=pos + rng.choice([-8.5, 8.5]),
                z=round(rng.uniform(140.0, 3860.0), 1),
                heading_rad=0.0 if rng.random() < 0.5 else math.pi,
                axis="z", speed_mps=rng.uniform(14.0, 22.0), road_pos=pos,
            ))
            vid += 1

    weather = WeatherState(
        condition="clear",
        wind_speed_mps=6.5,
        wind_direction_deg=128.0,
        rain_intensity=0.0,
        fog_density=0.11,
        day_mode=True,
    )

    return CityEnvironment(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        seed=seed,
        world_size=world,
        city_density=city_density,
        building_density=building_density,
        buildings=buildings,
        roads=roads,
        hazards=hazards,
        stations=stations,
        trees=trees,
        streetlights=streetlights,
        vehicles=vehicles,
        river_z=river_z,
        river_width=river_width,
        weather=weather,
    )
