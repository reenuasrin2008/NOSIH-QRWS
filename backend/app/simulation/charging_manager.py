from __future__ import annotations
import math
from typing import Dict, List, Optional, Set
from app.core.models import CityEnvironment, DroneState, Station


class ChargingPadManager:
    """
    Enforces realistic charging hub capacities and waiting queues.
    When a hub is full, incoming low-battery drones are diverted to the
    next nearest hub with open pads, or placed in a holding queue.
    """

    def __init__(self, city: CityEnvironment):
        self.slots: Dict[str, Set[str]] = {s.id: set() for s in city.stations}
        self.queues: Dict[str, List[str]] = {s.id: [] for s in city.stations}

    def sync_stations(self, city: CityEnvironment) -> None:
        for s in city.stations:
            self.slots.setdefault(s.id, set())
            self.queues.setdefault(s.id, [])

    def select_available_station(self, drone: DroneState, city: CityEnvironment) -> Optional[Station]:
        self.sync_stations(city)
        active = [s for s in city.stations if s.active]
        if not active:
            return None

        ordered = sorted(
            active,
            key=lambda s: math.hypot(drone.position[0] - s.position[0], drone.position[2] - s.position[2]),
        )
        # Prefer nearest station with open pad capacity
        for st in ordered:
            if len(self.slots[st.id]) < st.capacity or drone.id in self.slots[st.id]:
                return st
        # All hubs saturated -> return nearest hub (drone will queue)
        return ordered[0]

    def request_pad(self, drone_id: str, station: Station) -> bool:
        self.slots.setdefault(station.id, set())
        self.queues.setdefault(station.id, [])
        if drone_id in self.slots[station.id]:
            return True
        if len(self.slots[station.id]) < station.capacity:
            self.slots[station.id].add(drone_id)
            if drone_id in self.queues[station.id]:
                self.queues[station.id].remove(drone_id)
            return True
        if drone_id not in self.queues[station.id]:
            self.queues[station.id].append(drone_id)
        return False

    def release_pad(self, drone_id: str) -> None:
        for sid, occ in self.slots.items():
            if drone_id in occ:
                occ.remove(drone_id)
                # Promote next queued drone if waiting
                q = self.queues.get(sid, [])
                if q:
                    nxt = q.pop(0)
                    occ.add(nxt)
            elif drone_id in self.queues.get(sid, []):
                self.queues[sid].remove(drone_id)

    def get_utilization(self, city: CityEnvironment) -> Dict[str, Dict[str, int]]:
        self.sync_stations(city)
        return {
            s.id: {
                "occupied": len(self.slots.get(s.id, set())),
                "capacity": s.capacity,
                "queued": len(self.queues.get(s.id, [])),
            }
            for s in city.stations
        }
