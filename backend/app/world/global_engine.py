from __future__ import annotations
import copy
from functools import wraps
import math
import random
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.compat import to_dict, utc_now_iso
from app.events.bus import AuthoritativeEventBus
from app.world.global_models import (
    AmbulanceStatus,
    AmbulanceUnit,
    AnimalGroup,
    BuildingRecord,
    CityRecord,
    CountryProfile,
    DisasterEvent,
    DisasterType,
    DistrictRecord,
    FireRescueUnit,
    GeoPoint,
    GlobalDroneUnit,
    HospitalFacility,
    HospitalStatus,
    HouseholdRecord,
    MobilityCategory,
    PersonSafetyState,
    RoadEdge,
    ShelterFacility,
    SimulationMode,
    SwarmFormation,
    SwarmMode,
    SwarmOperation,
    SyntheticPerson,
    TerrainCell,
    WarehouseInventory,
    WeatherCondition,
    haversine_km,
)


COUNTRY_ARCHETYPES: List[Dict[str, Any]] = [
    {
        "country_id": "COUNTRY-01",
        "name": "Aurelia Coast",
        "archetype": "Coastal Metropolitan",
        "flag_code": "AUR",
        "color": "#2563EB",
        "capital": "Port Aurelia",
        "center": (14.2, 79.8),
        "area_km2": 18400.0,
        "terrain_profile": "Coastal harbor, dense urban core, tidal estuaries",
        "climate_zone": "tropical_coastal",
        "population_scale": 145000,
        "hazards": ["CYCLONE", "FLOOD", "POWER_OUTAGE"],
        "cities": [("Port Aurelia", True, 0.0, 0.0, 82000), ("Bayview", False, 0.42, -0.35, 38000), ("Cape Meridian", False, -0.38, 0.25, 25000)],
        "surface": "coastline",
        "base_elev": 8.0,
    },
    {
        "country_id": "COUNTRY-02",
        "name": "Valtoria Highlands",
        "archetype": "Mountain Region",
        "flag_code": "VAL",
        "color": "#0F766E",
        "capital": "Kestrel Ridge",
        "center": (26.5, 86.2),
        "area_km2": 29600.0,
        "terrain_profile": "Alpine peaks, steep valleys, terraced passes",
        "climate_zone": "alpine",
        "population_scale": 78000,
        "hazards": ["LANDSLIDE", "EARTHQUAKE", "FLOOD"],
        "cities": [("Kestrel Ridge", True, 0.0, 0.0, 41000), ("Summit Pass", False, 0.35, 0.45, 21000), ("Glacier Basin", False, -0.32, -0.28, 16000)],
        "surface": "mountain",
        "base_elev": 1150.0,
    },
    {
        "country_id": "COUNTRY-03",
        "name": "Veridia Basin",
        "archetype": "River Basin",
        "flag_code": "VER",
        "color": "#0284C7",
        "capital": "Delta City",
        "center": (19.8, 84.5),
        "area_km2": 24100.0,
        "terrain_profile": "Braided river delta, alluvial floodplains, multi-span bridges",
        "climate_zone": "humid_subtropical",
        "population_scale": 162000,
        "hazards": ["FLOOD", "CYCLONE", "MULTI_HAZARD_CASCADE"],
        "cities": [("Delta City", True, 0.0, 0.0, 88000), ("Riverbend", False, -0.35, 0.4, 42000), ("Confluence", False, 0.42, -0.3, 32000)],
        "surface": "river",
        "base_elev": 12.0,
    },
    {
        "country_id": "COUNTRY-04",
        "name": "Solara Plains",
        "archetype": "Agricultural Plains",
        "flag_code": "SOL",
        "color": "#15803D",
        "capital": "Harveston",
        "center": (23.2, 77.4),
        "area_km2": 36200.0,
        "terrain_profile": "Fertile plains, grain corridors, distributed market towns",
        "climate_zone": "temperate_plains",
        "population_scale": 94000,
        "hazards": ["FLOOD", "HEATWAVE", "WILDFIRE"],
        "cities": [("Harveston", True, 0.0, 0.0, 48000), ("Meadowgate", False, 0.45, 0.2, 26000), ("Granary Point", False, -0.4, -0.3, 20000)],
        "surface": "farmland",
        "base_elev": 180.0,
    },
    {
        "country_id": "COUNTRY-05",
        "name": "Ferros Industrial Union",
        "archetype": "Dense Urban Industrial",
        "flag_code": "FER",
        "color": "#475569",
        "capital": "Foundry Metro",
        "center": (18.9, 73.1),
        "area_km2": 14800.0,
        "terrain_profile": "High-density logistics hub, power plants, manufacturing corridors",
        "climate_zone": "urban_temperate",
        "population_scale": 185000,
        "hazards": ["FIRE", "INDUSTRIAL_ACCIDENT", "POWER_OUTAGE"],
        "cities": [("Foundry Metro", True, 0.0, 0.0, 105000), ("Port Smelter", False, -0.3, -0.35, 48000), ("Grid Sector", False, 0.35, 0.3, 32000)],
        "surface": "urban",
        "base_elev": 35.0,
    },
    {
        "country_id": "COUNTRY-06",
        "name": "Kalahar Steppe",
        "archetype": "Arid Inland",
        "flag_code": "KAL",
        "color": "#B45309",
        "capital": "Oasis Central",
        "center": (26.8, 71.2),
        "area_km2": 41500.0,
        "terrain_profile": "Arid plateau, oasis reservoirs, long highway corridors",
        "climate_zone": "arid",
        "population_scale": 64000,
        "hazards": ["HEATWAVE", "FIRE", "COMM_BLACKOUT"],
        "cities": [("Oasis Central", True, 0.0, 0.0, 36000), ("Dune Crossing", False, 0.45, -0.4, 16000), ("Solar Mesa", False, -0.35, 0.35, 12000)],
        "surface": "desert",
        "base_elev": 320.0,
    },
    {
        "country_id": "COUNTRY-07",
        "name": "Sylva Reserve",
        "archetype": "Forest and Highlands",
        "flag_code": "SYL",
        "color": "#047857",
        "capital": "Timberwatch",
        "center": (11.4, 76.7),
        "area_km2": 27300.0,
        "terrain_profile": "Dense canopy forests, rolling hills, wildlife sanctuaries",
        "climate_zone": "montane_forest",
        "population_scale": 72000,
        "hazards": ["WILDFIRE", "FIRE", "LANDSLIDE"],
        "cities": [("Timberwatch", True, 0.0, 0.0, 39000), ("Pinehaven", False, -0.32, 0.38, 19000), ("Canopy Station", False, 0.36, -0.25, 14000)],
        "surface": "forest",
        "base_elev": 680.0,
    },
]

COUNTRY_HIGHWAY_LINKS: List[Tuple[str, str]] = [
    ("COUNTRY-03", "COUNTRY-01"),
    ("COUNTRY-03", "COUNTRY-02"),
    ("COUNTRY-03", "COUNTRY-04"),
    ("COUNTRY-03", "COUNTRY-05"),
    ("COUNTRY-03", "COUNTRY-07"),
    ("COUNTRY-02", "COUNTRY-06"),
    ("COUNTRY-04", "COUNTRY-06"),
    ("COUNTRY-04", "COUNTRY-05"),
    ("COUNTRY-01", "COUNTRY-07"),
]


def _locked_read(method):
    """Serialize public world reads/serialization with the mutation lock."""
    @wraps(method)
    def _read(self, *args, **kwargs):
        with self._mutation_lock:
            return method(self, *args, **kwargs)
    return _read


OCCUPATIONS = [
    "Teacher", "Student", "Doctor", "Nurse", "Engineer", "Shopkeeper",
    "Driver", "Farmer", "Construction Worker", "Office Worker",
    "Factory Worker", "Delivery Personnel", "Emergency Responder",
    "Public Service Staff", "Hospitality Staff", "Retired Resident",
]


class GlobalWorldEngine:
    """Authoritative 7-country continuous planetary living-world simulation engine."""

    def __init__(self, event_bus: AuthoritativeEventBus, seed: int = 20261121) -> None:
        self.event_bus = event_bus
        self._mutation_lock = threading.RLock()
        self.seed = seed
        self.rng = random.Random(seed)
        self.scenario_id = "GLOBAL_DISASTER_7NATIONS_001"
        self.mode = SimulationMode.DISASTER_RESPONSE
        self.sim_time_s: float = 8 * 3600.0  # Starts at 08:00 local planetary time
        self.speed_multiplier: float = 1.0
        self.paused: bool = False
        self.emergency_stopped: bool = False
        self.weather: WeatherCondition = WeatherCondition.CLOUDY
        self.selected_country_id: str = "COUNTRY-03"

        self.countries: Dict[str, CountryProfile] = {}
        self.cities: Dict[str, CityRecord] = {}
        self.districts: Dict[str, DistrictRecord] = {}
        self.terrain: Dict[str, TerrainCell] = {}
        self.buildings: Dict[str, BuildingRecord] = {}
        self.roads: Dict[str, RoadEdge] = {}
        self.households: Dict[str, HouseholdRecord] = {}
        self.people: Dict[str, SyntheticPerson] = {}
        self.animals: Dict[str, AnimalGroup] = {}
        self.hospitals: Dict[str, HospitalFacility] = {}
        self.shelters: Dict[str, ShelterFacility] = {}
        self.warehouses: Dict[str, WarehouseInventory] = {}
        self.ambulances: Dict[str, AmbulanceUnit] = {}
        self.fire_units: Dict[str, FireRescueUnit] = {}
        self.drones: Dict[str, GlobalDroneUnit] = {}
        self.swarms: Dict[str, SwarmOperation] = {}
        self.disasters: Dict[str, DisasterEvent] = {}
        self.decision_memory: List[Dict[str, Any]] = []
        self.counterfactual_runs: Dict[str, Dict[str, Any]] = {}
        self._ambulance_state_until: Dict[str, float] = {}
        self._first_response_sim_s: Optional[float] = None
        self._medical_admissions = 0

        self._initialize_planet()

    @staticmethod
    def _clamp_lat(lat: float) -> float:
        return round(max(-85.0, min(85.0, lat if math.isfinite(lat) else 0.0)), 5)

    @staticmethod
    def _clamp_lon(lon: float) -> float:
        if not math.isfinite(lon):
            return 0.0
        return round(max(-180.0, min(180.0, lon)), 5)

    def reset_to_seed(self, seed: int) -> None:
        with self._mutation_lock:
            self.seed = int(seed)
            self._initialize_planet()

    def _initialize_planet(self) -> None:
        with self._mutation_lock:
            self.rng = random.Random(self.seed)
            self.mode = SimulationMode.DISASTER_RESPONSE
            self.sim_time_s = 8 * 3600.0
            self.speed_multiplier = 1.0
            self.paused = False
            self.emergency_stopped = False
            self.weather = WeatherCondition.CLOUDY
            self.selected_country_id = "COUNTRY-03"
            self.decision_memory.clear()
            self.counterfactual_runs.clear()
            self._ambulance_state_until.clear()
            self._first_response_sim_s = None
            self._medical_admissions = 0
            self.countries.clear()
            self.cities.clear()
            self.districts.clear()
            self.terrain.clear()
            self.buildings.clear()
            self.roads.clear()
            self.households.clear()
            self.people.clear()
            self.animals.clear()
            self.hospitals.clear()
            self.shelters.clear()
            self.warehouses.clear()
            self.ambulances.clear()
            self.fire_units.clear()
            self.drones.clear()
            self.swarms.clear()
            self.disasters.clear()
            for idx, cfg in enumerate(COUNTRY_ARCHETYPES, start=1):
                cid = cfg["country_id"]
                clat, clon = cfg["center"]
                boundary = [
                    GeoPoint(lat=round(clat + 1.25 * math.sin(a), 4), lon=round(clon + 1.55 * math.cos(a), 4), elevation_m=cfg["base_elev"])
                    for a in [k * (2 * math.pi / 8) for k in range(8)]
                ]
                cap_id = f"{cid}-CITY-01"
                self.countries[cid] = CountryProfile(
                    country_id=cid,
                    name=cfg["name"],
                    archetype=cfg["archetype"],
                    flag_code=cfg["flag_code"],
                    color=cfg["color"],
                    capital_city_id=cap_id,
                    capital_name=cfg["capital"],
                    center=GeoPoint(lat=clat, lon=clon, elevation_m=cfg["base_elev"]),
                    boundary=boundary,
                    land_area_km2=cfg["area_km2"],
                    terrain_profile=cfg["terrain_profile"],
                    climate_zone=cfg["climate_zone"],
                    population_scale=cfg["population_scale"],
                    vulnerable_hazards=list(cfg["hazards"]),
                    readiness_score=round(self.rng.uniform(76.0, 91.0), 1),
                )

                # 4x4 terrain grid per country
                for r in range(4):
                    for c in range(4):
                        tlat = clat + (r - 1.5) * 0.45
                        tlon = clon + (c - 1.5) * 0.55
                        elev = max(1.0, cfg["base_elev"] + self.rng.uniform(-12.0, 45.0) + (r * 8.0 if cfg["surface"] == "mountain" else 0.0))
                        cell_id = f"{cid}-TER-{r}-{c}"
                        self.terrain[cell_id] = TerrainCell(
                            cell_id=cell_id,
                            country_id=cid,
                            row=r,
                            col=c,
                            center=GeoPoint(lat=round(tlat, 4), lon=round(tlon, 4), elevation_m=round(elev, 1)),
                            elevation_m=round(elev, 1),
                            slope_deg=round(self.rng.uniform(1.0, 24.0 if cfg["surface"] == "mountain" else 6.0), 1),
                            surface_type=cfg["surface"],
                            soil_category="alluvial" if cfg["surface"] == "river" else ("rocky" if cfg["surface"] == "mountain" else "loam"),
                            vegetation_density=round(0.85 if cfg["surface"] == "forest" else (0.12 if cfg["surface"] == "desert" else 0.45), 2),
                            drainage_capacity=round(0.35 if cfg["surface"] in ("river", "coastline") else 0.72, 2),
                            fire_fuel_class=round(0.85 if cfg["surface"] == "forest" else (0.55 if cfg["surface"] == "urban" else 0.35), 2),
                            climate_zone=cfg["climate_zone"],
                        )

                # Cities, districts, buildings, roads, population, facilities
                district_zones = ["waterfront", "residential", "commercial", "hospital_hub", "industrial"]
                for c_idx, (cname, is_cap, dlat, dlon, cpop) in enumerate(cfg["cities"], start=1):
                    city_id = f"{cid}-CITY-{c_idx:02d}"
                    city_center = GeoPoint(lat=round(clat + dlat, 4), lon=round(clon + dlon, 4), elevation_m=cfg["base_elev"])
                    city_districts: List[str] = []

                    num_districts = 4 if is_cap else 2
                    pop_remaining = cpop
                    for d_idx in range(1, num_districts + 1):
                        dist_id = f"{city_id}-DIST-{d_idx:02d}"
                        d_pop = pop_remaining if d_idx == num_districts else int(cpop / num_districts)
                        pop_remaining -= d_pop
                        ztype = district_zones[(d_idx - 1) % len(district_zones)]
                        d_center = GeoPoint(
                            lat=round(city_center.lat + (d_idx - 2) * 0.04, 4),
                            lon=round(city_center.lon + ((d_idx % 2) * 2 - 1) * 0.045, 4),
                            elevation_m=max(2.0, cfg["base_elev"] + self.rng.uniform(-4.0, 15.0)),
                        )
                        vuln = int(d_pop * self.rng.uniform(0.14, 0.22))
                        hh_count = max(1, d_pop // 3)
                        self.districts[dist_id] = DistrictRecord(
                            district_id=dist_id,
                            city_id=city_id,
                            country_id=cid,
                            name=f"{cname} {ztype.replace('_', ' ').title()} Sector {d_idx}",
                            center=d_center,
                            radius_km=2.8,
                            zone_type=ztype,
                            total_residents=d_pop,
                            vulnerable_residents=vuln,
                            household_count=hh_count,
                            building_count=max(12, d_pop // 250),
                        )
                        city_districts.append(dist_id)

                        # Representative street-level buildings & households (hierarchical without double counting)
                        for b_idx in range(1, 4):
                            bid = f"{dist_id}-BLD-{b_idx:02d}"
                            bcat = "hospital" if (ztype == "hospital_hub" and b_idx == 1) else (
                                "school" if b_idx == 2 else ("apartment" if ztype in ("residential", "waterfront") else "commercial")
                            )
                            bpos = GeoPoint(
                                lat=round(d_center.lat + self.rng.uniform(-0.015, 0.015), 5),
                                lon=round(d_center.lon + self.rng.uniform(-0.015, 0.015), 5),
                                elevation_m=d_center.elevation_m,
                            )
                            floors = self.rng.randint(2, 14 if bcat in ("apartment", "commercial") else 5)
                            cap = floors * 35
                            self.buildings[bid] = BuildingRecord(
                                building_id=bid,
                                country_id=cid,
                                city_id=city_id,
                                district_id=dist_id,
                                category=bcat,
                                position=bpos,
                                height_m=round(floors * 3.6, 1),
                                floors=floors,
                                capacity=cap,
                                occupancy=int(cap * self.rng.uniform(0.55, 0.88)),
                            )

                        # Seeded representative synthetic households & individuals for street-level inspection
                        if is_cap and d_idx <= 2:
                            for h_idx in range(1, 5):
                                hh_id = f"{dist_id}-HH-{h_idx:03d}"
                                home_bld = f"{dist_id}-BLD-01"
                                size = self.rng.randint(2, 5)
                                member_ids: List[str] = []
                                needs_assist = False
                                for m_idx in range(1, size + 1):
                                    pid = f"P-{idx}{c_idx}{d_idx}{h_idx:02d}{m_idx}"
                                    age_band = "senior" if m_idx == 1 and h_idx % 2 == 0 else ("child" if m_idx >= 3 else "adult")
                                    mobility = (
                                        MobilityCategory.WHEELCHAIR_ACCESSIBLE
                                        if (age_band == "senior" and h_idx == 2)
                                        else (MobilityCategory.ASSISTED_WALKING if age_band == "senior" else MobilityCategory.INDEPENDENT)
                                    )
                                    if mobility != MobilityCategory.INDEPENDENT:
                                        needs_assist = True
                                    self.people[pid] = SyntheticPerson(
                                        person_id=pid,
                                        country_id=cid,
                                        city_id=city_id,
                                        district_id=dist_id,
                                        household_id=hh_id,
                                        home_building_id=home_bld,
                                        age_band=age_band,
                                        occupation=self.rng.choice(OCCUPATIONS),
                                        mobility=mobility,
                                        medical_vulnerability="chronic" if age_band == "senior" else "none",
                                        activity="working" if age_band == "adult" else ("studying" if age_band == "child" else "home"),
                                        location=GeoPoint(
                                            lat=round(d_center.lat + self.rng.uniform(-0.01, 0.01), 5),
                                            lon=round(d_center.lon + self.rng.uniform(-0.01, 0.01), 5),
                                            elevation_m=d_center.elevation_m,
                                        ),
                                    )
                                    member_ids.append(pid)
                                has_pets = h_idx % 2 == 1
                                self.households[hh_id] = HouseholdRecord(
                                    household_id=hh_id,
                                    country_id=cid,
                                    city_id=city_id,
                                    district_id=dist_id,
                                    home_building_id=home_bld,
                                    member_ids=member_ids,
                                    resident_count=len(member_ids),
                                    has_vehicle=h_idx != 4,
                                    has_pets=has_pets,
                                    pet_count=1 if has_pets else 0,
                                    needs_assisted_transport=needs_assist,
                                )

                    self.cities[city_id] = CityRecord(
                        city_id=city_id,
                        country_id=cid,
                        name=cname,
                        is_capital=is_cap,
                        center=city_center,
                        population=cpop,
                        districts=city_districts,
                        elevation_m=cfg["base_elev"],
                        coastal=cfg["surface"] == "coastline",
                    )

                    # Connect districts with roads & bridges
                    for i in range(len(city_districts)):
                        d_a = self.districts[city_districts[i]]
                        d_b = self.districts[city_districts[(i + 1) % len(city_districts)]]
                        rid = f"{city_id}-RD-{i + 1:02d}"
                        is_bridge = cfg["surface"] in ("river", "coastline") and i == 0
                        self.roads[rid] = RoadEdge(
                            road_id=rid,
                            country_id=cid,
                            city_id=city_id,
                            name=f"{cname} {'River Bridge' if is_bridge else 'Corridor'} {i + 1}",
                            category="bridge" if is_bridge else ("highway" if i == 1 else "main"),
                            start=d_a.center,
                            end=d_b.center,
                            length_km=round(max(1.2, haversine_km(d_a.center, d_b.center)), 2),
                            speed_limit_kph=80.0 if i == 1 else 55.0,
                            is_bridge=is_bridge,
                        )

                    # District spokes join every sector to the city-center highway hub.
                    for i, dist_id in enumerate(city_districts, start=1):
                        district = self.districts[dist_id]
                        rid = f"{city_id}-RD-SPOKE-{i:02d}"
                        self.roads[rid] = RoadEdge(
                            road_id=rid,
                            country_id=cid,
                            city_id=city_id,
                            name=f"{cname} Central Connector {i}",
                            category="main",
                            start=city_center,
                            end=district.center,
                            length_km=round(max(0.8, haversine_km(city_center, district.center)), 2),
                            speed_limit_kph=50.0,
                        )

                    # Hospitals per city
                    h_count = 3 if is_cap else 1
                    for h_i in range(1, h_count + 1):
                        hid = f"HOSP-{idx:02d}-{c_idx}{h_i}"
                        dist_ref = city_districts[(h_i - 1) % len(city_districts)]
                        d_loc = self.districts[dist_ref].center
                        beds = self.rng.randint(180, 420) if is_cap else self.rng.randint(70, 150)
                        occ = int(beds * self.rng.uniform(0.45, 0.72))
                        self.hospitals[hid] = HospitalFacility(
                            hospital_id=hid,
                            country_id=cid,
                            city_id=city_id,
                            district_id=dist_ref,
                            name=f"{cname} General Hospital #{h_i}",
                            location=GeoPoint(lat=round(d_loc.lat + 0.008 * h_i, 5), lon=round(d_loc.lon - 0.007 * h_i, 5), elevation_m=d_loc.elevation_m),
                            total_beds=beds,
                            occupied_beds=occ,
                            emergency_staff=max(24, beds // 5),
                            medical_kits=beds * 3,
                        )

                    # Shelters per city
                    s_count = 3 if is_cap else 2
                    for s_i in range(1, s_count + 1):
                        sid = f"SHLT-{idx:02d}-{c_idx}{s_i}"
                        dist_ref = city_districts[(s_i) % len(city_districts)]
                        d_loc = self.districts[dist_ref].center
                        max_occ = self.rng.randint(1800, 4500) if is_cap else self.rng.randint(800, 1800)
                        self.shelters[sid] = ShelterFacility(
                            shelter_id=sid,
                            country_id=cid,
                            city_id=city_id,
                            district_id=dist_ref,
                            name=f"{cname} Relief Shelter {s_i}",
                            location=GeoPoint(lat=round(d_loc.lat - 0.01 * s_i, 5), lon=round(d_loc.lon + 0.01 * s_i, 5), elevation_m=d_loc.elevation_m + 5.0),
                            max_occupancy=max_occ,
                            food_packages=max_occ * 3,
                            water_liters=float(max_occ * 9),
                            medical_kits=max(80, max_occ // 15),
                        )

                    # Warehouse per city
                    wid = f"WH-{idx:02d}-{c_idx:02d}"
                    self.warehouses[wid] = WarehouseInventory(
                        warehouse_id=wid,
                        country_id=cid,
                        city_id=city_id,
                        name=f"{cname} Central Logistics Depot",
                        location=GeoPoint(lat=round(city_center.lat + 0.02, 5), lon=round(city_center.lon + 0.02, 5), elevation_m=cfg["base_elev"]),
                        food_packages=45000 if is_cap else 18000,
                        water_liters=180000.0 if is_cap else 75000.0,
                        medical_kits=5000 if is_cap else 1800,
                        fuel_liters=40000.0 if is_cap else 16000.0,
                        generators=30 if is_cap else 12,
                    )

                # Animals (Domestic, Livestock, Wildlife) per country
                self.animals[f"ANIM-{idx:02d}-DOM"] = AnimalGroup(
                    group_id=f"ANIM-{idx:02d}-DOM",
                    country_id=cid,
                    category="domestic",
                    species="Household Pets (Dogs & Cats)",
                    count=int(cfg["population_scale"] * 0.12),
                    habitat="urban_households",
                    location=GeoPoint(lat=clat, lon=clon, elevation_m=cfg["base_elev"]),
                )
                self.animals[f"ANIM-{idx:02d}-LIV"] = AnimalGroup(
                    group_id=f"ANIM-{idx:02d}-LIV",
                    country_id=cid,
                    category="livestock",
                    species="Farm Livestock (Cattle, Goats, Poultry)",
                    count=int(cfg["population_scale"] * (0.45 if cfg["surface"] in ("farmland", "river") else 0.10)),
                    habitat="agricultural_farms",
                    location=GeoPoint(lat=round(clat - 0.2, 4), lon=round(clon + 0.25, 4), elevation_m=cfg["base_elev"]),
                )
                self.animals[f"ANIM-{idx:02d}-WLD"] = AnimalGroup(
                    group_id=f"ANIM-{idx:02d}-WLD",
                    country_id=cid,
                    category="wildlife",
                    species="Regional Wildlife (Deer, Birds, Small Mammals)",
                    count=int(24000 if cfg["surface"] in ("forest", "mountain") else 8500),
                    habitat=cfg["surface"],
                    location=GeoPoint(lat=round(clat + 0.3, 4), lon=round(clon - 0.3, 4), elevation_m=cfg["base_elev"] + 25.0),
                )

                # Ambulances per country (12-20 per country)
                amb_count = 18 if cfg["population_scale"] > 120000 else 12
                for a_i in range(1, amb_count + 1):
                    aid = f"AMB-{idx:02d}-{a_i:02d}"
                    self.ambulances[aid] = AmbulanceUnit(
                        ambulance_id=aid,
                        country_id=cid,
                        city_id=cap_id,
                        home_station=f"{cfg['capital']} EMS Station {(a_i % 3) + 1}",
                        location=GeoPoint(
                            lat=round(clat + self.rng.uniform(-0.08, 0.08), 5),
                            lon=round(clon + self.rng.uniform(-0.08, 0.08), 5),
                            elevation_m=cfg["base_elev"],
                        ),
                        equipment_profile="ICU_TRANSPORT" if a_i <= 4 else ("ALS" if a_i <= 10 else "BLS"),
                    )

                # Fire & Rescue Units per country
                unit_types = ["fire_truck", "water_tanker", "rescue_truck", "rescue_boat", "helicopter"]
                for f_i in range(1, 9):
                    fid = f"FRU-{idx:02d}-{f_i:02d}"
                    self.fire_units[fid] = FireRescueUnit(
                        unit_id=fid,
                        country_id=cid,
                        city_id=cap_id,
                        unit_type=unit_types[(f_i - 1) % len(unit_types)],
                        location=GeoPoint(
                            lat=round(clat + self.rng.uniform(-0.06, 0.06), 5),
                            lon=round(clon + self.rng.uniform(-0.06, 0.06), 5),
                            elevation_m=cfg["base_elev"],
                        ),
                    )

                # Drones per country (14 per country = 98 global autonomous drones)
                drone_cats = [
                    ("SURVEILLANCE", ["surveillance", "thermal_scan", "area_scan"], ["rgb", "thermal", "lidar"], 1.2, 42.0),
                    ("MEDICAL_DELIVERY", ["medical_payload", "first_aid"], ["rgb", "barometer"], 3.0, 36.0),
                    ("SEARCH_AND_RESCUE", ["survivor_search", "thermal_scan", "area_scan"], ["rgb", "thermal", "acoustic"], 2.5, 34.0),
                    ("HEAVY_LIFT", ["heavy_payload", "water_supply", "equipment_delivery"], ["rgb", "obstacle_radar"], 9.0, 26.0),
                    ("COMMUNICATION_RELAY", ["comm_relay", "surveillance"], ["rgb", "rf_relay"], 1.5, 35.0),
                    ("FIRE_MONITORING", ["thermal_scan", "fire_monitoring"], ["rgb", "thermal", "gas_sensor"], 1.4, 38.0),
                    ("FLOOD_MONITORING", ["surveillance", "flood_monitoring"], ["rgb", "lidar", "sonar"], 1.6, 37.0),
                ]
                for d_i in range(1, 15):
                    cat, caps, sens, payload, spd = drone_cats[(d_i - 1) % len(drone_cats)]
                    did = f"D-{idx:02d}-{d_i:02d}"
                    self.drones[did] = GlobalDroneUnit(
                        drone_id=did,
                        country_id=cid,
                        city_id=cap_id,
                        home_station=f"{cfg['capital']} Airbase {((d_i - 1) % 2) + 1}",
                        category=cat,
                        location=GeoPoint(
                            lat=round(clat + self.rng.uniform(-0.07, 0.07), 5),
                            lon=round(clon + self.rng.uniform(-0.07, 0.07), 5),
                            elevation_m=cfg["base_elev"],
                        ),
                        speed_mps=spd,
                        battery_pct=round(self.rng.uniform(74.0, 100.0), 1),
                        max_payload_kg=payload,
                        sensors=list(sens),
                        capabilities=list(caps),
                    )

            # Inter-city highways join every city to its country's capital hub.
            for cid, country in self.countries.items():
                city_ids = [city_id for city_id, city in self.cities.items() if city.country_id == cid]
                for i in range(len(city_ids) - 1):
                    source = self.cities[city_ids[i]]
                    target = self.cities[city_ids[i + 1]]
                    rid = f"{cid}-HW-{i + 1:02d}"
                    self.roads[rid] = RoadEdge(
                        road_id=rid,
                        country_id=cid,
                        city_id=source.city_id,
                        name=f"{country.name} Inter-City Highway {i + 1}",
                        category="highway",
                        start=source.center,
                        end=target.center,
                        length_km=round(max(1.0, haversine_km(source.center, target.center)), 2),
                        speed_limit_kph=110.0,
                        capacity_vph=2400,
                    )

            # Cross-border highways make all seven national networks one connected graph.
            for i, (source_id, target_id) in enumerate(COUNTRY_HIGHWAY_LINKS, start=1):
                source = self.countries[source_id]
                target = self.countries[target_id]
                rid = f"XBW-{source_id[-2:]}-{target_id[-2:]}"
                self.roads[rid] = RoadEdge(
                    road_id=rid,
                    country_id=source_id,
                    city_id=source.capital_city_id,
                    name=f"{source.name} ↔ {target.name} Cross-Border Highway",
                    category="highway",
                    start=source.center,
                    end=target.center,
                    length_km=round(max(1.0, haversine_km(source.center, target.center)), 2),
                    speed_limit_kph=120.0,
                    capacity_vph=2800,
                )

            # Start from a clean, alert-free world. Disasters can still be injected
            # manually or through the Demo Director scenarios.
            self.event_bus.emit(
                "world.initialized",
                payload={"scenario_id": self.scenario_id, "countries": len(self.countries), "drones": len(self.drones)},
                source="global_world_engine",
                category="simulation",
            )

    # ------------------------------------------------------------------
    # Simulation Clock & Tick Progression
    # ------------------------------------------------------------------
    @_locked_read
    def get_clock_info(self) -> Dict[str, Any]:
        total_sec = int(self.sim_time_s) % 86400
        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60
        day = int(self.sim_time_s // 86400) + 1
        phase = (
            "night" if (hours < 5 or hours >= 20)
            else "sunrise" if hours < 7
            else "morning" if hours < 12
            else "afternoon" if hours < 17
            else "sunset"
        )
        sun_elevation_deg = round(math.sin(((hours + minutes / 60.0) - 6.0) / 12.0 * math.pi) * 75.0, 1)
        return {
            "sim_time_s": round(self.sim_time_s, 1),
            "day": day,
            "clock_hhmm": f"{hours:02d}:{minutes:02d}",
            "day_phase": phase,
            "sun_elevation_deg": sun_elevation_deg,
            "speed_multiplier": self.speed_multiplier,
            "paused": self.paused,
            "emergency_stopped": self.emergency_stopped,
            "mode": self.mode.value,
            "weather": self.weather.value,
            "world_version": self.event_bus.world_version,
        }

    def step(self, dt_seconds: float = 60.0) -> Dict[str, Any]:
        with self._mutation_lock:
            if self.paused or self.emergency_stopped:
                return self.get_clock_info()
            dt_seconds = max(0.0, min(86400.0, float(dt_seconds))) if math.isfinite(dt_seconds) else 0.0
            speed = max(0.0, min(100.0, float(self.speed_multiplier))) if math.isfinite(self.speed_multiplier) else 1.0
            self.speed_multiplier = speed
            sim_dt = dt_seconds * speed
            if sim_dt <= 0.0:
                return self.get_clock_info()
            self.sim_time_s += sim_dt
            hour = int((self.sim_time_s % 86400) // 3600)

            # Update synthetic people daily routines when safe
            for p in self.people.values():
                if p.safety_state == PersonSafetyState.SAFE_AT_HOME:
                    if hour < 6 or hour >= 22:
                        p.activity = "sleeping"
                    elif 7 <= hour < 9 or 17 <= hour < 19:
                        p.activity = "commuting"
                    elif 9 <= hour < 17:
                        p.activity = "studying" if p.age_band == "child" else ("working" if p.age_band == "adult" else "home")
                    else:
                        p.activity = "shopping"

            # Advance active disasters (cyclone movement, flood spread, fire spread, cascades)
            for ev in list(self.disasters.values()):
                if ev.status != "ACTIVE":
                    continue
                if ev.disaster_type == DisasterType.CYCLONE:
                    # Move cyclone along heading with geographic bounds clamping
                    dist_km = max(0.0, ev.travel_speed_kph) * (sim_dt / 3600.0)
                    rad = math.radians(ev.heading_deg)
                    ev.origin.lat = self._clamp_lat(ev.origin.lat + (dist_km / 111.0) * math.cos(rad))
                    lon_scale = 111.0 * max(0.1, math.cos(math.radians(ev.origin.lat)))
                    ev.origin.lon = self._clamp_lon(ev.origin.lon + (dist_km / lon_scale) * math.sin(rad))
                    ev.radius_km = min(28.0, round(ev.radius_km + ev.growth_rate * 0.4 * (sim_dt / 60.0), 2))
                    # Trigger secondary flood cascade if heavy rain persists and not yet triggered
                    if ev.rainfall_mm_hr >= 55.0 and not ev.triggered_cascades:
                        flood_ev = self.inject_disaster(
                            country_id=ev.country_id,
                            disaster_type=DisasterType.FLOOD,
                            name=f"Secondary Flood Cascade ({ev.name})",
                            origin=GeoPoint(lat=ev.origin.lat, lon=ev.origin.lon, elevation_m=ev.origin.elevation_m),
                            severity=min(0.95, round(ev.severity * 0.9, 2)),
                            radius_km=max(6.0, round(ev.radius_km * 0.7, 1)),
                            rainfall_mm_hr=ev.rainfall_mm_hr,
                            parent_event_id=ev.event_id,
                        )
                        ev.triggered_cascades.append(flood_ev.event_id)
                elif ev.disaster_type in (DisasterType.FLOOD, DisasterType.FIRE, DisasterType.WILDFIRE):
                    ev.radius_km = min(22.0, round(ev.radius_km + ev.growth_rate * 0.25 * (sim_dt / 60.0), 2))
                self._recompute_disaster_impact(ev)

            # Advance active swarms & drones
            for swarm in self.swarms.values():
                if swarm.status == "ACTIVE":
                    swarm.progress_pct = min(100.0, round(swarm.progress_pct + 4.5 * (sim_dt / 60.0), 1))
                    for did in swarm.drone_ids:
                        d = self.drones.get(did)
                        if d and d.status in ("ASSIGNED", "IN_FLIGHT"):
                            d.status = "IN_FLIGHT"
                            d.battery_pct = max(0.0, min(100.0, round(d.battery_pct - 0.6 * (sim_dt / 60.0), 1)))
                            # Move toward target center
                            move_ratio = min(1.0, 0.15 * (sim_dt / 60.0))
                            d.location.lat = self._clamp_lat(d.location.lat + (swarm.target_center.lat - d.location.lat) * move_ratio)
                            d.location.lon = self._clamp_lon(d.location.lon + (swarm.target_center.lon - d.location.lon) * move_ratio)
                            d.altitude_m = round((swarm.altitude_band_m[0] + swarm.altitude_band_m[1]) / 2.0, 1)
                    if swarm.progress_pct >= 100.0:
                        swarm.status = "COMPLETED"
                        for did in swarm.drone_ids:
                            d = self.drones.get(did)
                            if d and d.status == "IN_FLIGHT":
                                d.status = "AVAILABLE"
                                d.swarm_id = None

            # Ambulance state transitions are driven by distance/arrival in
            # _advance_ambulances; no tick may teleport them to a hospital.

            self._advance_terrain_physics(sim_dt)
            self._advance_living_agents(sim_dt)
            self._advance_ambulances(sim_dt)
            self._advance_detailed_civilization(sim_dt)
            return self.get_clock_info()

    # ------------------------------------------------------------------
    # Disaster Injection & Terrain-Aware Impact Model
    # ------------------------------------------------------------------
    def inject_disaster(
        self,
        country_id: str,
        disaster_type: DisasterType,
        name: Optional[str] = None,
        origin: Optional[GeoPoint] = None,
        severity: float = 0.75,
        radius_km: float = 10.0,
        wind_kph: float = 55.0,
        rainfall_mm_hr: float = 45.0,
        polygon: Optional[List[GeoPoint]] = None,
        parent_event_id: Optional[str] = None,
    ) -> DisasterEvent:
        with self._mutation_lock:
            if country_id not in self.countries:
                raise ValueError(f"Unknown country_id: {country_id}")
            country = self.countries[country_id]
            cap = self.cities[country.capital_city_id]
            raw_orig = origin or GeoPoint(lat=cap.center.lat, lon=cap.center.lon, elevation_m=cap.elevation_m)
            orig = GeoPoint(
                lat=self._clamp_lat(raw_orig.lat),
                lon=self._clamp_lon(raw_orig.lon),
                elevation_m=raw_orig.elevation_m if math.isfinite(raw_orig.elevation_m) else cap.elevation_m,
            )
            safe_severity = max(0.1, min(1.0, float(severity))) if math.isfinite(severity) else 0.75
            safe_radius = max(0.5, min(100.0, float(radius_km))) if math.isfinite(radius_km) else 10.0
            safe_wind = max(0.0, float(wind_kph)) if math.isfinite(wind_kph) else 55.0
            safe_rain = max(0.0, float(rainfall_mm_hr)) if math.isfinite(rainfall_mm_hr) else 45.0
            eid = f"DIS-{disaster_type.value[:3]}-{self.rng.randrange(0x1000000):06X}"
            ev = DisasterEvent(
                event_id=eid,
                country_id=country_id,
                city_id=cap.city_id,
                disaster_type=disaster_type,
                name=name or f"{disaster_type.value.title()} in {country.name}",
                origin=orig,
                radius_km=safe_radius,
                polygon=polygon or [],
                severity=safe_severity,
                wind_kph=safe_wind,
                rainfall_mm_hr=safe_rain,
                start_sim_time_s=self.sim_time_s,
                parent_event_id=parent_event_id,
            )
            self.disasters[eid] = ev
            if disaster_type == DisasterType.CYCLONE:
                self.weather = WeatherCondition.CYCLONE
            elif disaster_type == DisasterType.FLOOD:
                self.weather = WeatherCondition.HEAVY_RAIN
            self._recompute_disaster_impact(ev)
            self.event_bus.emit(
                "disaster.created",
                payload=to_dict(ev),
                country_id=country_id,
                entity_id=eid,
                source="disaster_engine",
                category="disaster",
            )
            return ev

    def _recompute_disaster_impact(self, ev: DisasterEvent) -> None:
        affected_pop = 0
        evac_demand = 0
        est_injuries = 0
        blocked_roads = 0
        affected_buildings = 0
        affected_districts: List[str] = []

        # Terrain-cell hydrology/fire propagation
        for cell in self.terrain.values():
            if cell.country_id != ev.country_id:
                continue
            dist_km = haversine_km(ev.origin, cell.center)
            if dist_km <= ev.radius_km * 3.5:
                proximity = max(0.0, 1.0 - dist_km / max(1.0, ev.radius_km * 3.5))
                if ev.disaster_type in (DisasterType.FLOOD, DisasterType.CYCLONE):
                    elev_factor = max(0.25, 1.4 - (cell.elevation_m / 120.0))
                    drain_factor = max(0.3, 1.2 - cell.drainage_capacity)
                    depth = round(ev.severity * proximity * elev_factor * drain_factor * 2.4, 2)
                    cell.water_depth_m = max(cell.water_depth_m, depth)
                    if cell.water_depth_m >= 0.8:
                        cell.accessible = False
                elif ev.disaster_type in (DisasterType.FIRE, DisasterType.WILDFIRE):
                    intensity = round(ev.severity * proximity * (0.5 + cell.fire_fuel_class), 2)
                    cell.fire_intensity = max(cell.fire_intensity, intensity)
                    if cell.fire_intensity >= 0.6:
                        cell.accessible = False

        # District & population exposure (never automatically mark everyone as injured!)
        for dist in self.districts.values():
            if dist.country_id != ev.country_id:
                continue
            d_km = haversine_km(ev.origin, dist.center)
            if d_km <= max(ev.radius_km * 1.6, 14.0):
                affected_districts.append(dist.district_id)
                proximity = max(0.15, 1.0 - d_km / max(15.0, ev.radius_km * 2.0))
                exposure_ratio = min(0.82, ev.severity * proximity * (0.75 if dist.zone_type in ("waterfront", "industrial") else 0.55))
                exposed = int(dist.total_residents * exposure_ratio)
                dist.exposed_residents = max(dist.exposed_residents, exposed)
                if ev.disaster_type in (DisasterType.FLOOD, DisasterType.CYCLONE):
                    dist.flood_depth_m = max(dist.flood_depth_m, round(ev.severity * proximity * 1.9, 2))
                    dist.road_accessibility = round(max(0.15, 1.0 - dist.flood_depth_m * 0.42), 2)
                elif ev.disaster_type in (DisasterType.FIRE, DisasterType.WILDFIRE):
                    dist.fire_risk = max(dist.fire_risk, round(ev.severity * proximity, 2))
                    dist.road_accessibility = round(max(0.2, 1.0 - dist.fire_risk * 0.5), 2)
                if ev.severity >= 0.7 and proximity > 0.5:
                    dist.power_available = False

                affected_pop += dist.exposed_residents
                # Realistic differentiation: only a subset needs evacuation and a much smaller fraction is injured
                evac_demand += int(dist.exposed_residents * (0.42 if ev.severity >= 0.7 else 0.25))
                inj = int(dist.exposed_residents * ev.severity * 0.012)
                dist.injured_residents = max(dist.injured_residents, inj)
                est_injuries += dist.injured_residents

        # Update street-level buildings, roads, people, animals
        for bld in self.buildings.values():
            if bld.district_id in affected_districts:
                dist = self.districts[bld.district_id]
                bld.flood_exposure_m = dist.flood_depth_m
                bld.fire_exposure = dist.fire_risk
                if dist.flood_depth_m >= 1.0 or dist.fire_risk >= 0.75:
                    bld.accessible = False
                    bld.structural_condition = "DAMAGED"
                affected_buildings += 1

        for rd in self.roads.values():
            if rd.country_id == ev.country_id:
                d_km = haversine_km(ev.origin, rd.start)
                if d_km <= max(ev.radius_km * 1.3, 10.0) and ev.severity >= 0.6:
                    rd.flood_depth_m = round(ev.severity * 1.4, 2) if ev.disaster_type in (DisasterType.FLOOD, DisasterType.CYCLONE) else 0.0
                    if rd.is_bridge or rd.flood_depth_m >= 0.7 or ev.disaster_type in (DisasterType.FIRE, DisasterType.EARTHQUAKE):
                        rd.accessible = False
                        rd.blocked_reason = f"{ev.disaster_type.value} hazard ({ev.event_id})"
                        blocked_roads += 1

        for p in self.people.values():
            if p.district_id in affected_districts and p.safety_state == PersonSafetyState.SAFE_AT_HOME:
                if p.mobility != MobilityCategory.INDEPENDENT:
                    p.safety_state = PersonSafetyState.NEEDS_SPECIAL_ASSISTANCE
                else:
                    p.safety_state = PersonSafetyState.AWARE_OF_EMERGENCY

        for anim in self.animals.values():
            if anim.country_id == ev.country_id:
                anim.exposed_count = int(anim.count * ev.severity * 0.35)
                anim.shelter_needed = anim.exposed_count > 0

        # Update hospital readiness if power is out in district
        for h in self.hospitals.values():
            if h.district_id in affected_districts:
                dist = self.districts[h.district_id]
                if not dist.power_available and h.status == HospitalStatus.OPERATIONAL:
                    h.status = HospitalStatus.PARTIALLY_OPERATIONAL
                h.triage_load = max(h.triage_load, int(dist.injured_residents * 0.6))

        ev.district_ids = affected_districts
        ev.affected_population = affected_pop
        ev.evacuation_demand = evac_demand
        ev.estimated_injuries = est_injuries
        ev.blocked_roads = blocked_roads
        ev.affected_buildings = affected_buildings

    # ------------------------------------------------------------------
    # Humanitarian & Operational Calculators (Grounded in Live State)
    # ------------------------------------------------------------------
    @_locked_read
    def calculate_ambulance_requirements(
        self,
        country_id: str,
        planning_window_hours: float = 4.0,
        reserve_pct: float = 0.20,
    ) -> Dict[str, Any]:
        if country_id not in self.countries:
            raise ValueError(f"Unknown country_id: {country_id}")
        planning_window_hours = max(0.25, float(planning_window_hours)) if math.isfinite(planning_window_hours) else 4.0
        reserve_pct = max(0.0, min(2.0, float(reserve_pct))) if math.isfinite(reserve_pct) else 0.20
        c_districts = [d for d in self.districts.values() if d.country_id == country_id]
        c_hospitals = [h for h in self.hospitals.values() if h.country_id == country_id]
        c_ambulances = [a for a in self.ambulances.values() if a.country_id == country_id]

        injured_total = sum(d.injured_residents for d in c_districts)
        # Triage distribution (configurable model)
        immediate = int(round(injured_total * 0.22))
        delayed = int(round(injured_total * 0.38))
        minor = max(0, injured_total - immediate - delayed)
        # Patients needing ambulance transport = 100% immediate + 60% delayed + assisted non-ambulatory
        transport_demand = immediate + int(round(delayed * 0.60))
        avg_accessibility = sum(d.road_accessibility for d in c_districts) / max(1, len(c_districts))

        # Cycle duration (minutes): travel + loading + hospital handover + return
        base_cycle_min = 42.0
        adjusted_cycle_min = round(base_cycle_min / max(0.35, avg_accessibility), 1)
        trips_per_amb = max(1.0, (planning_window_hours * 60.0) / adjusted_cycle_min)
        avg_capacity = 1.6  # weighted average patient capacity per trip
        patients_per_amb = trips_per_amb * avg_capacity

        min_required = int(math.ceil(transport_demand / max(1.0, patients_per_amb))) if transport_demand > 0 else 0
        reserve_fleet = int(math.ceil(min_required * reserve_pct))
        recommended = min_required + reserve_fleet
        available = sum(1 for a in c_ambulances if a.status == AmbulanceStatus.AVAILABLE)
        deficit = max(0, recommended - available)
        total_avail_beds = sum(h.available_beds for h in c_hospitals if h.status != HospitalStatus.CLOSED)

        return {
            "country_id": country_id,
            "sim_time_s": round(self.sim_time_s, 1),
            "source_subsystem": "medical_triage_and_ambulance_engine",
            "data_kind": "calculated_from_live_simulation_state",
            "triage_breakdown": {
                "total_estimated_injured": injured_total,
                "immediate_critical": immediate,
                "delayed_urgent": delayed,
                "minor": minor,
                "patients_requiring_transport": transport_demand,
            },
            "minimum_ambulances_required": min_required,
            "recommended_operational_fleet": recommended,
            "reserve_fleet_included": reserve_fleet,
            "available_ambulances": available,
            "total_country_ambulances": len(c_ambulances),
            "ambulance_deficit": deficit,
            "available_hospital_beds": total_avail_beds,
            "predicted_avg_response_min": round(adjusted_cycle_min * 0.35, 1),
            "confidence_range": [max(0, int(min_required * 0.85)), int(math.ceil(recommended * 1.15))],
            "assumptions": {
                "planning_window_hours": planning_window_hours,
                "reserve_ratio": reserve_pct,
                "service_cycle_minutes": adjusted_cycle_min,
                "avg_road_accessibility": round(avg_accessibility, 2),
                "avg_patients_per_trip": avg_capacity,
                "trips_per_ambulance_in_window": round(trips_per_amb, 2),
            },
            "explanation": (
                f"In {self.countries[country_id].name}, {transport_demand} simulated patients require ambulance transport "
                f"({immediate} immediate, {int(round(delayed * 0.60))} delayed). At {adjusted_cycle_min} min/cycle "
                f"(road accessibility {int(avg_accessibility * 100)}%), each ambulance completes ~{trips_per_amb:.1f} trips "
                f"in {planning_window_hours:.0f}h, requiring a minimum of {min_required} ambulances ({recommended} with "
                f"{int(reserve_pct * 100)}% reserve). Currently {available} are available (deficit: {deficit})."
            ),
        }

    @_locked_read
    def calculate_resource_requirements(self, country_id: str, horizon_hours: float = 24.0) -> Dict[str, Any]:
        if country_id not in self.countries:
            raise ValueError(f"Unknown country_id: {country_id}")
        horizon_hours = max(0.25, float(horizon_hours)) if math.isfinite(horizon_hours) else 24.0
        c_districts = [d for d in self.districts.values() if d.country_id == country_id]
        c_warehouses = [w for w in self.warehouses.values() if w.country_id == country_id]
        c_shelters = [s for s in self.shelters.values() if s.country_id == country_id]

        exposed = sum(d.exposed_residents for d in c_districts)
        evac_need = sum(int(d.exposed_residents * 0.42) for d in c_districts)
        days = horizon_hours / 24.0

        # Configurable humanitarian planning norms (explicitly disclosed as assumptions)
        food_per_person_day = 2.0  # packages/day
        water_liters_per_person_day = 4.5  # drinking + basic hygiene L/day
        med_kits_per_100_exposed = 3.0

        food_needed = int(math.ceil(exposed * food_per_person_day * days))
        water_needed_l = round(exposed * water_liters_per_person_day * days, 1)
        med_needed = int(math.ceil((exposed / 100.0) * med_kits_per_100_exposed))

        food_stock = sum(w.food_packages for w in c_warehouses) + sum(s.food_packages for s in c_shelters)
        water_stock = sum(w.water_liters for w in c_warehouses) + sum(s.water_liters for s in c_shelters)
        med_stock = sum(w.medical_kits for w in c_warehouses) + sum(s.medical_kits for s in c_shelters)
        shelter_cap = sum(s.remaining_capacity for s in c_shelters if s.accessible)

        food_rate_hr = (exposed * food_per_person_day) / 24.0
        water_rate_hr = (exposed * water_liters_per_person_day) / 24.0
        food_hours_left = round(food_stock / food_rate_hr, 1) if food_rate_hr > 0 else 999.0
        water_hours_left = round(water_stock / water_rate_hr, 1) if water_rate_hr > 0 else 999.0

        return {
            "country_id": country_id,
            "horizon_hours": horizon_hours,
            "sim_time_s": round(self.sim_time_s, 1),
            "exposed_population": exposed,
            "evacuation_shelter_demand": evac_need,
            "food_packages": {"needed": food_needed, "available": food_stock, "shortage": max(0, food_needed - food_stock), "hours_until_depletion": food_hours_left},
            "water_liters": {"needed": water_needed_l, "available": round(water_stock, 1), "shortage": round(max(0.0, water_needed_l - water_stock), 1), "hours_until_depletion": water_hours_left},
            "medical_kits": {"needed": med_needed, "available": med_stock, "shortage": max(0, med_needed - med_stock)},
            "shelters": {"demand": evac_need, "remaining_capacity": shelter_cap, "shortage": max(0, evac_need - shelter_cap)},
            "shortage_warnings": [
                w for w in [
                    f"Food inventory projected to fall below reserve in {food_hours_left} simulated hours." if food_hours_left < 24.0 else None,
                    f"Drinking water projected to deplete in {water_hours_left} simulated hours." if water_hours_left < 24.0 else None,
                    f"Shelter capacity deficit of {evac_need - shelter_cap} residents." if evac_need > shelter_cap else None,
                ] if w
            ],
            "assumptions": {
                "food_packages_per_person_per_day": food_per_person_day,
                "water_liters_per_person_per_day": water_liters_per_person_day,
                "medical_kits_per_100_exposed": med_kits_per_100_exposed,
            },
        }

    # ------------------------------------------------------------------
    # Innovation 2: Seven-Country Mutual Aid Network
    # ------------------------------------------------------------------
    @_locked_read
    def find_mutual_aid_options(self, target_country_id: str, resource_type: str = "ambulances", quantity: int = 8) -> Dict[str, Any]:
        if target_country_id not in self.countries:
            raise ValueError(f"Unknown country_id: {target_country_id}")
        quantity = max(0, int(quantity))
        target = self.countries[target_country_id]
        donors: List[Dict[str, Any]] = []
        for cid, c in self.countries.items():
            if cid == target_country_id:
                continue
            dist_km = round(haversine_km(target.center, c.center), 1)
            active_dis = sum(1 for d in self.disasters.values() if d.country_id == cid and d.status == "ACTIVE")
            if active_dis > 0:
                continue  # Don't drain a country experiencing an active disaster
            if resource_type == "ambulances":
                avail = [a for a in self.ambulances.values() if a.country_id == cid and a.status == AmbulanceStatus.AVAILABLE]
                surplus = max(0, len(avail) - 6)  # keep minimum domestic reserve of 6
                eta_hours = round(dist_km / 72.0 + 0.5, 1)
            elif resource_type == "drones":
                avail = [d for d in self.drones.values() if d.country_id == cid and d.status == "AVAILABLE"]
                surplus = max(0, len(avail) - 5)
                eta_hours = round(dist_km / 110.0 + 0.2, 1)
            else:
                whs = [w for w in self.warehouses.values() if w.country_id == cid]
                surplus = sum(w.food_packages for w in whs) // 4
                eta_hours = round(dist_km / 65.0 + 1.0, 1)
            if surplus > 0:
                donors.append({
                    "donor_country_id": cid,
                    "donor_name": c.name,
                    "distance_km": dist_km,
                    "available_surplus": surplus,
                    "proposed_transfer": min(surplus, quantity),
                    "estimated_arrival_hours": eta_hours,
                    "border_clearance": "MUTUAL_AID_CORRIDOR_OPEN",
                })
        donors.sort(key=lambda x: x["distance_km"])
        return {
            "target_country_id": target_country_id,
            "target_name": target.name,
            "resource_type": resource_type,
            "requested_quantity": quantity,
            "eligible_donors": donors,
            "total_available_from_network": sum(d["available_surplus"] for d in donors),
        }

    # ------------------------------------------------------------------
    # Innovation 3: Rescue Equity Engine
    # ------------------------------------------------------------------
    @_locked_read
    def evaluate_rescue_equity(self, country_id: str) -> Dict[str, Any]:
        c_districts = [d for d in self.districts.values() if d.country_id == country_id]
        rows = []
        for d in c_districts:
            vuln_ratio = d.vulnerable_residents / max(1, d.total_residents)
            exposure_ratio = d.exposed_residents / max(1, d.total_residents)
            access_penalty = 1.0 - d.road_accessibility
            # Standard distance-only priority vs Equity-aware priority
            standard_score = round((1.0 - access_penalty) * 0.6 + exposure_ratio * 0.4, 3)
            equity_score = round(exposure_ratio * 0.35 + vuln_ratio * 0.30 + access_penalty * 0.35, 3)
            rows.append({
                "district_id": d.district_id,
                "name": d.name,
                "exposed_residents": d.exposed_residents,
                "vulnerable_residents": d.vulnerable_residents,
                "road_accessibility": d.road_accessibility,
                "standard_priority_score": standard_score,
                "equity_priority_score": equity_score,
                "underserved_flag": (equity_score - standard_score) > 0.15 and d.exposed_residents > 0,
            })
        rows.sort(key=lambda r: r["equity_priority_score"], reverse=True)
        return {
            "country_id": country_id,
            "methodology": "Weighted composite of exposure (35%), vulnerability (30%), and road isolation/inaccessibility (35%)",
            "districts": rows,
            "underserved_count": sum(1 for r in rows if r["underserved_flag"]),
        }

    # ------------------------------------------------------------------
    # Innovation 4: Cascade Prediction Graph
    # ------------------------------------------------------------------
    @_locked_read
    def get_cascade_graph(self, country_id: str) -> Dict[str, Any]:
        c_disasters = [d for d in self.disasters.values() if d.country_id == country_id and d.status == "ACTIVE"]
        max_sev = max((d.severity for d in c_disasters), default=0.0)
        primary_type = c_disasters[0].disaster_type.value if c_disasters else "CYCLONE"
        nodes = [
            {"id": "N1", "label": f"Primary {primary_type}", "status": "ACTIVE" if c_disasters else "POTENTIAL", "modelled_likelihood": round(max(0.2, max_sev), 2), "category": "hazard"},
            {"id": "N2", "label": "Heavy Rainfall & Surge", "status": "ACTIVE" if max_sev > 0.5 else "ELEVATED", "modelled_likelihood": round(min(0.95, max_sev * 0.92), 2), "category": "hazard"},
            {"id": "N3", "label": "Floodplain & Bridge Closure", "status": "ACTIVE" if any(not r.accessible for r in self.roads.values() if r.country_id == country_id) else "AT_RISK", "modelled_likelihood": round(min(0.9, max_sev * 0.85), 2), "category": "infrastructure"},
            {"id": "N4", "label": "Power Grid Disruption", "status": "ACTIVE" if any(not d.power_available for d in self.districts.values() if d.country_id == country_id) else "AT_RISK", "modelled_likelihood": round(min(0.88, max_sev * 0.8), 2), "category": "infrastructure"},
            {"id": "N5", "label": "Hospital Surge & Access Loss", "status": "ELEVATED", "modelled_likelihood": round(min(0.82, max_sev * 0.72), 2), "category": "medical"},
            {"id": "N6", "label": "Shelter & Water Shortage", "status": "MONITORING", "modelled_likelihood": round(min(0.75, max_sev * 0.65), 2), "category": "humanitarian"},
        ]
        edges = [
            {"from": "N1", "to": "N2", "relation": "triggers_precipitation"},
            {"from": "N2", "to": "N3", "relation": "submerges_low_bridges"},
            {"from": "N1", "to": "N4", "relation": "damages_substations"},
            {"from": "N3", "to": "N5", "relation": "delays_ambulances"},
            {"from": "N4", "to": "N5", "relation": "forces_generator_backup"},
            {"from": "N4", "to": "N6", "relation": "disrupts_water_pumps"},
        ]
        return {
            "country_id": country_id,
            "note": "Likelihoods are scenario-modelled simulation indices, not real-world meteorological forecasts.",
            "nodes": nodes,
            "edges": edges,
        }

    # ------------------------------------------------------------------
    # Innovation 1 & 5: Counterfactual / What-If Twin Runner
    # ------------------------------------------------------------------
    def _clone_for_counterfactual(self) -> "GlobalWorldEngine":
        """Clone mutable state without copying locks or sharing the live event bus."""
        cloned = object.__new__(GlobalWorldEngine)
        cloned._mutation_lock = threading.RLock()
        cloned.event_bus = AuthoritativeEventBus()
        cloned.rng = random.Random(self.seed)
        cloned.rng.setstate(copy.deepcopy(self.rng.getstate()))
        for name, value in self.__dict__.items():
            if name not in ("_mutation_lock", "event_bus", "rng"):
                setattr(cloned, name, copy.deepcopy(value))
        return cloned

    def run_counterfactual_comparison(self, country_id: str, what_if_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run modest interventions on isolated clones and report measured outcomes."""
        with self._mutation_lock:
            if country_id not in self.countries:
                raise ValueError(f"Unknown country_id: {country_id}")
            base_exposed = sum(d.exposed_residents for d in self.districts.values() if d.country_id == country_id)
            params = what_if_params or {}
            raw_loss = float(params.get("ambulance_loss_ratio", 0.0))
            amb_loss_ratio = max(0.0, min(1.0, raw_loss)) if math.isfinite(raw_loss) else 0.0
            horizon_s = 600.0
            raw_lead = float(params.get("early_evacuation_lead_seconds", 600.0))
            early_lead_s = max(0.0, min(1800.0, raw_lead)) if math.isfinite(raw_lead) else 600.0

            strategies = [
                ("SCENARIO_A_CONVENTIONAL", "Conventional Response (Baseline)", "none", 0, False),
                ("SCENARIO_B_HYBRID_OPT", "Additional Ambulance Dispatch", "dispatch", 4, False),
                ("SCENARIO_C_EARLY_EVAC", "Early Evacuation + Dispatch", "early", 2, False),
                ("SCENARIO_D_SWARM_ASSIST", "Drone Swarm + Dispatch", "swarm", 4, True),
            ]
            results = []
            for sid, label, intervention, dispatch_count, use_swarm in strategies:
                twin = self._clone_for_counterfactual()
                twin.speed_multiplier = 1.0
                twin.paused = False
                twin.emergency_stopped = False
                ambulances = [a for a in twin.ambulances.values() if a.country_id == country_id]
                for amb in ambulances[:int(len(ambulances) * amb_loss_ratio)]:
                    amb.status = AmbulanceStatus.OUT_OF_SERVICE
                    amb.patients_onboard = 0
                if intervention == "early" and early_lead_s > 0.0:
                    # Actually simulate an earlier response window on the clone;
                    # no outcome multiplier is applied.
                    twin.step(dt_seconds=early_lead_s)

                injured_districts = sorted(
                    (d for d in twin.districts.values() if d.country_id == country_id),
                    key=lambda d: d.injured_residents, reverse=True,
                )
                available = [a for a in ambulances if a.status == AmbulanceStatus.AVAILABLE]
                for idx, amb in enumerate(available[:dispatch_count]):
                    amb.status = AmbulanceStatus.DISPATCHED
                    if injured_districts:
                        amb.assigned_district_id = injured_districts[idx % len(injured_districts)].district_id
                    hospitals = [h for h in twin.hospitals.values() if h.country_id == country_id and h.available_beds > 0]
                    if hospitals:
                        amb.destination_hospital_id = hospitals[idx % len(hospitals)].hospital_id

                if use_swarm:
                    drones = [
                        d for d in twin.drones.values()
                        if d.country_id == country_id and d.status == "AVAILABLE" and d.battery_pct >= 45.0
                    ][:2]
                    if drones:
                        swarm_id = f"CF-SWARM-{uuid.uuid4().hex[:6].upper()}"
                        twin.swarms[swarm_id] = SwarmOperation(
                            swarm_id=swarm_id,
                            country_id=country_id,
                            name=f"{label} survey swarm",
                            mode=SwarmMode.AREA_SCAN,
                            formation=SwarmFormation.SEARCH_GRID,
                            drone_ids=[d.drone_id for d in drones],
                            target_center=copy.deepcopy(twin.countries[country_id].center),
                            status="ACTIVE",
                        )
                        for drone in drones:
                            drone.status = "IN_FLIGHT"
                            drone.swarm_id = swarm_id
                            drone.assigned_mission_id = swarm_id

                base_admissions = twin._medical_admissions
                twin._first_response_sim_s = None
                start_time = twin.sim_time_s
                twin.step(dt_seconds=horizon_s)
                elapsed_min = round((twin.sim_time_s - start_time) / 60.0, 1)
                evacuated = sum(d.evacuated_residents for d in twin.districts.values() if d.country_id == country_id)
                remaining = max(0, base_exposed - evacuated)
                first_response = twin._first_response_sim_s
                active_drones = sum(
                    1 for d in twin.drones.values()
                    if d.country_id == country_id and d.status in ("ASSIGNED", "IN_FLIGHT", "DELIVERING")
                )
                effective_amb = sum(1 for a in ambulances if a.status != AmbulanceStatus.OUT_OF_SERVICE)
                shelters = [s for s in twin.shelters.values() if s.country_id == country_id]
                water_risk = round(
                    100.0 * sum(1 for s in shelters if s.water_liters < s.current_occupancy * 4.5) / max(1, len(shelters)), 1
                )
                results.append({
                    "scenario_key": sid,
                    "label": label,
                    "seed": twin.seed,
                    "country_id": country_id,
                    "people_safely_evacuated": evacuated,
                    "remaining_exposed": remaining,
                    "time_to_first_response_min": round((first_response - start_time) / 60.0, 1) if first_response is not None else None,
                    "rescue_completion_min": elapsed_min if remaining == 0 else None,
                    "medical_transport_cases": twin._medical_admissions - base_admissions,
                    "effective_ambulances": effective_amb,
                    "active_drones": active_drones,
                    "water_shortage_risk_pct": water_risk,
                    "mission_failures": (
                        sum(1 for a in ambulances if a.status == AmbulanceStatus.OUT_OF_SERVICE)
                        + sum(1 for d in twin.drones.values() if d.country_id == country_id and d.status in ("FAILED", "DESTROYED"))
                    ),
                    "response_observed": first_response is not None,
                    "intervention": intervention,
                    "intervention_lead_min": round(early_lead_s / 60.0, 1) if intervention == "early" else 0.0,
                    "simulated_horizon_min": elapsed_min,
                })

            run_id = f"CF-{uuid.uuid4().hex[:6].upper()}"
            record = {
                "counterfactual_id": run_id,
                "country_id": country_id,
                "seed": self.seed,
                "world_version": self.event_bus.world_version,
                "what_if_params": params,
                "created_at": utc_now_iso(),
                "methodology": "isolated cloned-state interventions with measured simulation outcomes",
                "scenarios": results,
            }
            if len(self.counterfactual_runs) >= 100:
                oldest_key = next(iter(self.counterfactual_runs))
                del self.counterfactual_runs[oldest_key]
            self.counterfactual_runs[run_id] = record
            return record

    # ------------------------------------------------------------------
    # Drone Failure & Swarm Recovery
    # ------------------------------------------------------------------
    def inject_drone_failure(self, drone_id: str, failure_type: str = "COMPLETE_DRONE_DESTRUCTION") -> Dict[str, Any]:
        with self._mutation_lock:
            if drone_id not in self.drones:
                raise ValueError(f"Unknown drone_id: {drone_id}")
            drone = self.drones[drone_id]
            prev_swarm = drone.swarm_id
            prev_mission = drone.assigned_mission_id
            drone.status = "DESTROYED" if "DESTRUCTION" in failure_type else "FAILED"
            drone.comm_connected = False
            drone.battery_pct = 0.0 if drone.status == "DESTROYED" else drone.battery_pct
            fail_entry = {"timestamp": utc_now_iso(), "failure_type": failure_type, "previous_swarm": prev_swarm, "previous_mission": prev_mission}
            drone.failure_history.append(fail_entry)
            if len(drone.failure_history) > 100:
                del drone.failure_history[:-100]

            # Automatic recovery: find best replacement in same country
            replacement_id: Optional[str] = None
            candidates = [
                d for d in self.drones.values()
                if d.country_id == drone.country_id
                and d.drone_id != drone_id
                and d.status == "AVAILABLE"
                and d.battery_pct >= 45.0
            ]
            candidates.sort(key=lambda d: d.battery_pct, reverse=True)
            if candidates and (prev_swarm or prev_mission):
                rep = candidates[0]
                replacement_id = rep.drone_id
                rep.status = "ASSIGNED"
                rep.swarm_id = prev_swarm
                rep.assigned_mission_id = prev_mission
                if prev_swarm and prev_swarm in self.swarms:
                    sw = self.swarms[prev_swarm]
                    sw.drone_ids = [replacement_id if x == drone_id else x for x in sw.drone_ids]
            drone.swarm_id = None
            drone.assigned_mission_id = None

            rec = {
                "drone_id": drone_id,
                "country_id": drone.country_id,
                "failure_type": failure_type,
                "new_status": drone.status,
                "affected_swarm": prev_swarm,
                "replacement_drone_id": replacement_id,
                "recovery_status": "REASSIGNED" if replacement_id else "NO_ACTIVE_TASK_AFFECTED",
            }
            self.decision_memory.append({"timestamp": utc_now_iso(), "type": "drone_recovery", "detail": rec})
            if len(self.decision_memory) > 500:
                del self.decision_memory[:-500]
            self.event_bus.emit(
                "drone.destroyed" if drone.status == "DESTROYED" else "drone.failed",
                payload=rec,
                country_id=drone.country_id,
                entity_id=drone_id,
                source="swarm_recovery_engine",
                category="recovery",
            )
            return rec

    # ------------------------------------------------------------------
    # Serialization for All Three Frontends
    # ------------------------------------------------------------------
    @_locked_read
    def get_global_overview(self) -> Dict[str, Any]:
        country_summaries = []
        for cid, c in self.countries.items():
            c_dists = [d for d in self.districts.values() if d.country_id == cid]
            c_dis = [ev for ev in self.disasters.values() if ev.country_id == cid and ev.status == "ACTIVE"]
            c_hosp = [h for h in self.hospitals.values() if h.country_id == cid]
            c_amb = [a for a in self.ambulances.values() if a.country_id == cid]
            c_drn = [d for d in self.drones.values() if d.country_id == cid]
            c_shlt = [s for s in self.shelters.values() if s.country_id == cid]
            country_summaries.append({
                **to_dict(c),
                "total_population": sum(d.total_residents for d in c_dists),
                "exposed_population": sum(d.exposed_residents for d in c_dists),
                "evacuated_population": sum(d.evacuated_residents for d in c_dists),
                "injured_population": sum(d.injured_residents for d in c_dists),
                "active_disasters": len(c_dis),
                "hospitals_operational": sum(1 for h in c_hosp if h.status in (HospitalStatus.OPERATIONAL, HospitalStatus.PARTIALLY_OPERATIONAL)),
                "hospitals_total": len(c_hosp),
                "available_beds": sum(h.available_beds for h in c_hosp),
                "ambulances_available": sum(1 for a in c_amb if a.status == AmbulanceStatus.AVAILABLE),
                "ambulances_total": len(c_amb),
                "drones_available": sum(1 for d in c_drn if d.status == "AVAILABLE"),
                "drones_active": sum(1 for d in c_drn if d.status in ("ASSIGNED", "IN_FLIGHT", "DELIVERING")),
                "drones_total": len(c_drn),
                "shelter_remaining_capacity": sum(s.remaining_capacity for s in c_shlt),
            })

        return {
            "scenario_id": self.scenario_id,
            "seed": self.seed,
            "selected_country_id": self.selected_country_id,
            "clock": self.get_clock_info(),
            "totals": {
                "countries": len(self.countries),
                "countries_affected": sum(1 for cs in country_summaries if cs["active_disasters"] > 0),
                "active_disasters": sum(1 for d in self.disasters.values() if d.status == "ACTIVE"),
                "total_population": sum(cs["total_population"] for cs in country_summaries),
                "people_at_risk": sum(cs["exposed_population"] for cs in country_summaries),
                "people_evacuated": sum(cs["evacuated_population"] for cs in country_summaries),
                "drones_total": len(self.drones),
                "drones_active": sum(1 for d in self.drones.values() if d.status in ("ASSIGNED", "IN_FLIGHT", "DELIVERING")),
                "drones_available": sum(1 for d in self.drones.values() if d.status == "AVAILABLE"),
                "ambulances_available": sum(1 for a in self.ambulances.values() if a.status == AmbulanceStatus.AVAILABLE),
                "ambulances_total": len(self.ambulances),
                "hospitals_operational": sum(1 for h in self.hospitals.values() if h.status in (HospitalStatus.OPERATIONAL, HospitalStatus.PARTIALLY_OPERATIONAL)),
                "hospitals_total": len(self.hospitals),
                "active_swarms": sum(1 for s in self.swarms.values() if s.status == "ACTIVE"),
            },
            "countries": country_summaries,
            "active_disasters": [to_dict(d) for d in self.disasters.values()],
            "frontends": self.event_bus.frontend_status(),
        }

    @_locked_read
    def get_country_detail(self, country_id: str) -> Dict[str, Any]:
        if country_id not in self.countries:
            raise ValueError(f"Unknown country_id: {country_id}")
        return {
            "profile": to_dict(self.countries[country_id]),
            "cities": [to_dict(c) for c in self.cities.values() if c.country_id == country_id],
            "districts": [to_dict(d) for d in self.districts.values() if d.country_id == country_id],
            "hospitals": [{**to_dict(h), "available_beds": h.available_beds} for h in self.hospitals.values() if h.country_id == country_id],
            "shelters": [{**to_dict(s), "remaining_capacity": s.remaining_capacity} for s in self.shelters.values() if s.country_id == country_id],
            "warehouses": [to_dict(w) for w in self.warehouses.values() if w.country_id == country_id],
            "ambulances": [to_dict(a) for a in self.ambulances.values() if a.country_id == country_id],
            "fire_units": [to_dict(f) for f in self.fire_units.values() if f.country_id == country_id],
            "drones": [to_dict(d) for d in self.drones.values() if d.country_id == country_id],
            "roads": [to_dict(r) for r in self.roads.values() if r.country_id == country_id],
            "animals": [to_dict(a) for a in self.animals.values() if a.country_id == country_id],
            "disasters": [to_dict(ev) for ev in self.disasters.values() if ev.country_id == country_id],
            "ambulance_analysis": self.calculate_ambulance_requirements(country_id),
            "resource_analysis": self.calculate_resource_requirements(country_id),
            "equity_analysis": self.evaluate_rescue_equity(country_id),
            "cascade_graph": self.get_cascade_graph(country_id),
        }

    # ------------------------------------------------------------------
    # Realistic 2D Downhill Flood Hydrology, Cellular Fire Spread & Live Motion
    # ------------------------------------------------------------------
    def _advance_terrain_physics(self, dt_seconds: float) -> None:
        """Real neighbor-to-neighbor downhill water flow and wind-driven cellular fire spread."""
        # Group terrain cells by (country_id, row, col)
        grid: Dict[Tuple[str, int, int], TerrainCell] = {
            (c.country_id, c.row, c.col): c for c in self.terrain.values()
        }
        water_deltas: Dict[str, float] = {}
        fire_deltas: Dict[str, float] = {}

        active_winds: Dict[str, Tuple[float, float]] = {}
        for ev in self.disasters.values():
            if ev.status == "ACTIVE":
                active_winds[ev.country_id] = (ev.wind_kph, ev.wind_direction_deg)

        dt_hr = dt_seconds / 3600.0
        dt_min = dt_seconds / 60.0
        for (cid, r, c), cell in grid.items():
            # Downhill water diffusion + natural drainage recession
            if cell.water_depth_m > 0.05:
                drain = cell.drainage_capacity * 0.12 * dt_hr
                water_deltas[cell.cell_id] = water_deltas.get(cell.cell_id, 0.0) - min(cell.water_depth_m, drain)
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nb = grid.get((cid, r + dr, c + dc))
                    if nb and (cell.elevation_m + cell.water_depth_m) > (nb.elevation_m + nb.water_depth_m):
                        head_diff = (cell.elevation_m + cell.water_depth_m) - (nb.elevation_m + nb.water_depth_m)
                        flow = min(cell.water_depth_m * 0.18, head_diff * 0.04 * max(0.0, dt_hr * 8.0))
                        water_deltas[cell.cell_id] = water_deltas.get(cell.cell_id, 0.0) - flow * 0.25
                        water_deltas[nb.cell_id] = water_deltas.get(nb.cell_id, 0.0) + flow * 0.25

            # Wind-driven cellular fire propagation
            if cell.fire_intensity > 0.15:
                wind_kph, wind_deg = active_winds.get(cid, (15.0, 225.0))
                wrad = math.radians(wind_deg)
                wx, wy = math.sin(wrad), math.cos(wrad)
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nb = grid.get((cid, r + dr, c + dc))
                    if nb and nb.water_depth_m < 0.2:
                        align = max(0.15, 0.5 + 0.5 * (dc * wx + dr * wy))
                        spread = cell.fire_intensity * nb.fire_fuel_class * align * (1.0 + wind_kph / 90.0) * 0.06 * dt_min
                        fire_deltas[nb.cell_id] = fire_deltas.get(nb.cell_id, 0.0) + spread

        for cell_id, dw in water_deltas.items():
            cell = self.terrain[cell_id]
            cell.water_depth_m = round(max(0.0, min(4.5, cell.water_depth_m + dw)), 3)
            cell.accessible = cell.water_depth_m < 0.8 and cell.fire_intensity < 0.6

        for cell_id, df in fire_deltas.items():
            cell = self.terrain[cell_id]
            cell.fire_intensity = round(max(0.0, min(1.0, cell.fire_intensity + df)), 3)
            if cell.fire_intensity >= 0.6:
                cell.accessible = False

    def _advance_living_agents(self, dt_seconds: float) -> None:
        """Move synthetic people toward shelters/work, ambulances along routes, and fire units to active fires."""
        step_deg = 0.0012 * max(0.0, dt_seconds / 60.0)

        # Synthetic residents: evacuate toward nearest accessible shelter if exposed, else commute
        shelters_by_country: Dict[str, List[ShelterFacility]] = {}
        for s in self.shelters.values():
            if s.accessible and s.remaining_capacity > 0:
                shelters_by_country.setdefault(s.country_id, []).append(s)

        # Deterministic schedule-driven movement + road-aware evacuation
        for p in self.people.values():
            dist_rec = self.districts.get(p.district_id)
            road_factor = dist_rec.road_accessibility if dist_rec else 1.0
            if p.safety_state in (PersonSafetyState.AWARE_OF_EMERGENCY, PersonSafetyState.EVACUATING, PersonSafetyState.NEEDS_SPECIAL_ASSISTANCE):
                c_shelters = [s for s in shelters_by_country.get(p.country_id, []) if s.remaining_capacity > 0]
                if c_shelters:
                    target = min(c_shelters, key=lambda s: haversine_km(p.location, s.location))
                    p.safety_state = PersonSafetyState.EVACUATING
                    p.activity = "evacuating"
                    p.assigned_shelter_id = target.shelter_id
                    dlat = target.location.lat - p.location.lat
                    dlon = target.location.lon - p.location.lon
                    dist = math.hypot(dlat, dlon)
                    spd = step_deg * road_factor * (0.6 if p.mobility != MobilityCategory.INDEPENDENT else 1.2)
                    if dist <= max(0.000001, spd):
                        p.location.lat = target.location.lat
                        p.location.lon = target.location.lon
                        if target.current_occupancy < target.max_occupancy:
                            p.safety_state = PersonSafetyState.AT_SHELTER
                            p.activity = "sheltered"
                            target.current_occupancy += 1
                            target.status = "FULL" if target.current_occupancy >= target.max_occupancy else "ACTIVE"
                            if dist_rec:
                                dist_rec.evacuated_residents = min(dist_rec.total_residents, dist_rec.evacuated_residents + 1)
                    else:
                        p.location.lat = self._clamp_lat(p.location.lat + (dlat / dist) * spd)
                        p.location.lon = self._clamp_lon(p.location.lon + (dlon / dist) * spd)

        # Pure logic-driven drone battery RTB & charging cycle
        for d in self.drones.values():
            if d.status in ("IN_FLIGHT", "ASSIGNED"):
                if d.battery_pct < 22.0:
                    d.status = "RETURNING"
                    d.swarm_id = None
                    d.assigned_mission_id = None
                    self.event_bus.emit("drone.low_battery", payload={"drone_id": d.drone_id, "battery_pct": d.battery_pct}, country_id=d.country_id, entity_id=d.drone_id, category="recovery", bump_version=False)
            elif d.status == "RETURNING":
                c_center = self.countries[d.country_id].center
                move_ratio = min(1.0, 0.3 * max(0.0, dt_seconds / 60.0))
                d.location.lat = self._clamp_lat(d.location.lat + (c_center.lat - d.location.lat) * move_ratio)
                d.location.lon = self._clamp_lon(d.location.lon + (c_center.lon - d.location.lon) * move_ratio)
                if haversine_km(d.location, c_center) < 1.5:
                    d.status = "CHARGING"
                    d.altitude_m = 0.0
            elif d.status == "CHARGING":
                d.battery_pct = min(100.0, round(d.battery_pct + 8.0 * max(0.0, dt_seconds / 60.0), 1))
                if d.battery_pct >= 95.0:
                    d.status = "AVAILABLE"

    def _move_ambulance(self, amb: AmbulanceUnit, target: GeoPoint, dt_seconds: float, road_factor: float = 1.0) -> bool:
        """Move by ground distance and report physical arrival (never teleport)."""
        distance_km = haversine_km(amb.location, target)
        speed_km_s = max(0.0, amb.speed_kph) * max(0.0, min(1.0, road_factor)) / 3600.0
        step_km = speed_km_s * max(0.0, dt_seconds)
        amb.fuel_pct = max(0.0, round(amb.fuel_pct - step_km * 0.12, 2))
        if distance_km <= max(0.001, step_km):
            amb.location.lat = target.lat
            amb.location.lon = target.lon
            amb.location.elevation_m = target.elevation_m
            return True
        if distance_km > 0.0:
            ratio = step_km / distance_km
            amb.location.lat = self._clamp_lat(amb.location.lat + (target.lat - amb.location.lat) * ratio)
            amb.location.lon = self._clamp_lon(amb.location.lon + (target.lon - amb.location.lon) * ratio)
            amb.location.elevation_m = round(
                amb.location.elevation_m + (target.elevation_m - amb.location.elevation_m) * ratio, 2
            )
        return False

    def _advance_ambulances(self, dt_seconds: float) -> None:
        """Distance-driven dispatch, scene, transport, handover, and return states."""
        for amb in self.ambulances.values():
            if amb.fuel_pct <= 0.0 and amb.status != AmbulanceStatus.OUT_OF_SERVICE:
                amb.status = AmbulanceStatus.OUT_OF_SERVICE
                amb.patients_onboard = 0
                continue
            districts = [d for d in self.districts.values() if d.country_id == amb.country_id]
            avg_road = sum(d.road_accessibility for d in districts) / max(1, len(districts))

            if amb.status in (AmbulanceStatus.DISPATCHED, AmbulanceStatus.EN_ROUTE_TO_PATIENT):
                amb.status = AmbulanceStatus.EN_ROUTE_TO_PATIENT
                district = self.districts.get(amb.assigned_district_id or "")
                if district is None:
                    district = max(districts, key=lambda d: d.injured_residents, default=None)
                    if district:
                        amb.assigned_district_id = district.district_id
                target = district.center if district else self.countries[amb.country_id].center
                if self._move_ambulance(amb, target, dt_seconds, avg_road):
                    amb.status = AmbulanceStatus.ON_SCENE
                    self._ambulance_state_until[amb.ambulance_id] = self.sim_time_s + 30.0
                    if self._first_response_sim_s is None:
                        self._first_response_sim_s = self.sim_time_s

            elif amb.status == AmbulanceStatus.ON_SCENE:
                if self.sim_time_s >= self._ambulance_state_until.get(amb.ambulance_id, self.sim_time_s):
                    hospitals = [
                        h for h in self.hospitals.values()
                        if h.country_id == amb.country_id and h.status not in (HospitalStatus.CLOSED, HospitalStatus.DAMAGED)
                    ]
                    if amb.destination_hospital_id not in {h.hospital_id for h in hospitals}:
                        amb.destination_hospital_id = min(
                            hospitals, key=lambda h: haversine_km(amb.location, h.location), default=None
                        ).hospital_id if hospitals else None
                    amb.patients_onboard = min(amb.patient_capacity, 2)
                    amb.status = AmbulanceStatus.TRANSPORTING if amb.destination_hospital_id else AmbulanceStatus.RETURNING

            elif amb.status == AmbulanceStatus.TRANSPORTING:
                hospital = self.hospitals.get(amb.destination_hospital_id or "")
                if hospital is None:
                    amb.status = AmbulanceStatus.RETURNING
                    continue
                if self._move_ambulance(amb, hospital.location, dt_seconds, avg_road):
                    amb.status = AmbulanceStatus.AT_HOSPITAL
                    admitted = max(0, min(amb.patients_onboard, hospital.available_beds))
                    hospital.occupied_beds = min(hospital.total_beds, hospital.occupied_beds + admitted)
                    self._medical_admissions += admitted
                    amb.patients_onboard = 0
                    if hospital.available_beds == 0:
                        hospital.status = HospitalStatus.OVERLOADED
                    self._ambulance_state_until[amb.ambulance_id] = self.sim_time_s + 30.0

            elif amb.status == AmbulanceStatus.AT_HOSPITAL:
                if self.sim_time_s >= self._ambulance_state_until.get(amb.ambulance_id, self.sim_time_s):
                    amb.status = AmbulanceStatus.AVAILABLE
                    amb.assigned_district_id = None
                    amb.destination_hospital_id = None

            elif amb.status == AmbulanceStatus.RETURNING:
                home = self.countries[amb.country_id].center
                if self._move_ambulance(amb, home, dt_seconds, avg_road):
                    amb.status = AmbulanceStatus.AVAILABLE
                    amb.assigned_district_id = None
                    amb.destination_hospital_id = None

    @_locked_read
    def get_live_entities(self, country_id: str) -> Dict[str, Any]:
        """Return real moving positions & states for 3D rendering in World Command."""
        if country_id not in self.countries:
            raise ValueError(f"Unknown country_id: {country_id}")
        return {
            "country_id": country_id,
            "country": to_dict(self.countries[country_id]),
            "clock": self.get_clock_info(),
            "terrain": [to_dict(t) for t in self.terrain.values() if t.country_id == country_id],
            "people": [to_dict(p) for p in self.people.values() if p.country_id == country_id],
            "ambulances": [to_dict(a) for a in self.ambulances.values() if a.country_id == country_id],
            "fire_units": [to_dict(f) for f in self.fire_units.values() if f.country_id == country_id],
            "drones": [to_dict(d) for d in self.drones.values() if d.country_id == country_id],
            "hospitals": [{**to_dict(h), "available_beds": h.available_beds} for h in self.hospitals.values() if h.country_id == country_id],
            "shelters": [{**to_dict(s), "remaining_capacity": s.remaining_capacity} for s in self.shelters.values() if s.country_id == country_id],
            "animals": [to_dict(a) for a in self.animals.values() if a.country_id == country_id],
            "disasters": [to_dict(d) for d in self.disasters.values() if d.country_id == country_id and d.status == "ACTIVE"],
        }

    def _advance_detailed_civilization(self, dt_seconds: float) -> None:
        """Shelter consumption + warehouse resupply, fire unit suppression, and dynamic country readiness."""
        dt_days = dt_seconds / 86400.0

        # 1. Shelter food/water consumption & automatic warehouse resupply
        wh_by_city: Dict[str, WarehouseInventory] = {w.city_id: w for w in self.warehouses.values()}
        for s in self.shelters.values():
            if s.current_occupancy > 0:
                food_used = int(round(s.current_occupancy * 2.0 * dt_days))
                water_used = round(s.current_occupancy * 4.5 * dt_days, 2)
                s.food_packages = max(0, s.food_packages - food_used)
                s.water_liters = max(0.0, round(s.water_liters - water_used, 1))
                # Resupply from city warehouse if below threshold
                wh = wh_by_city.get(s.city_id)
                if wh and s.food_packages < s.max_occupancy:
                    transfer_food = min(wh.food_packages, s.max_occupancy)
                    if transfer_food > 0:
                        wh.food_packages -= transfer_food
                        s.food_packages += transfer_food
                if wh and s.water_liters < s.max_occupancy * 3.0:
                    transfer_water = min(wh.water_liters, float(s.max_occupancy * 3))
                    if transfer_water > 0:
                        wh.water_liters -= transfer_water
                        s.water_liters += transfer_water

        # 2. Fire & Rescue unit suppression on active fires
        active_fires = [ev for ev in self.disasters.values() if ev.status == "ACTIVE" and ev.disaster_type in (DisasterType.FIRE, DisasterType.WILDFIRE)]
        for fu in self.fire_units.values():
            c_fires = [f for f in active_fires if f.country_id == fu.country_id]
            if c_fires and fu.water_liters > 100.0:
                target_f = c_fires[0]
                fu.status = "ON_SCENE"
                fu.assigned_event_id = target_f.event_id
                move_ratio = min(1.0, 0.25 * max(0.0, dt_seconds / 60.0))
                fu.location.lat = self._clamp_lat(fu.location.lat + (target_f.origin.lat - fu.location.lat) * move_ratio)
                fu.location.lon = self._clamp_lon(fu.location.lon + (target_f.origin.lon - fu.location.lon) * move_ratio)
                fu.water_liters = max(0.0, round(fu.water_liters - 120.0 * (dt_seconds / 60.0), 1))
                # Suppress nearby terrain fire cells
                for cell in self.terrain.values():
                    if cell.country_id == fu.country_id and cell.fire_intensity > 0.0:
                        if haversine_km(fu.location, cell.center) <= 25.0:
                            cell.fire_intensity = max(0.0, round(cell.fire_intensity - 0.08 * max(0.0, dt_seconds / 60.0), 3))
            elif fu.status == "ON_SCENE" and not c_fires:
                fu.status = "AVAILABLE"
                fu.assigned_event_id = None
                fu.water_liters = 4000.0

        # 3. Dynamic country readiness score from live hospital beds, road access, and drone availability
        for cid, c in self.countries.items():
            c_dists = [d for d in self.districts.values() if d.country_id == cid]
            c_hosp = [h for h in self.hospitals.values() if h.country_id == cid]
            c_drn = [d for d in self.drones.values() if d.country_id == cid]
            avg_road = sum(d.road_accessibility for d in c_dists) / max(1, len(c_dists))
            power_ok = sum(1 for d in c_dists if d.power_available) / max(1, len(c_dists))
            bed_ratio = sum(h.available_beds for h in c_hosp) / max(1, sum(h.total_beds for h in c_hosp))
            drone_ok = sum(1 for d in c_drn if d.status != "DESTROYED") / max(1, len(c_drn))
            c.power_grid_pct = round(power_ok * 100.0, 1)
            c.readiness_score = round((avg_road * 0.30 + power_ok * 0.25 + bed_ratio * 0.25 + drone_ok * 0.20) * 100.0, 1)
