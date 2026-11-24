from __future__ import annotations
import copy
import math
import threading
from typing import Callable, Dict, List, Optional, Set

from app.core.models import CityEnvironment, DroneState, Station


class ChargingPadManager:
    """Thread-safe charging capacity, reservations, diversion, and queues."""

    def __init__(self, city: CityEnvironment):
        self._lock = threading.RLock()
        self.slots: Dict[str, Set[str]] = {s.id: set() for s in city.stations}
        self.queues: Dict[str, List[str]] = {s.id: [] for s in city.stations}

    def __deepcopy__(self, memo):
        cloned = object.__new__(ChargingPadManager)
        memo[id(self)] = cloned
        cloned._lock = threading.RLock()
        with self._lock:
            cloned.slots = copy.deepcopy(self.slots, memo)
            cloned.queues = copy.deepcopy(self.queues, memo)
        return cloned

    def sync_stations(self, city: CityEnvironment) -> None:
        with self._lock:
            for s in city.stations:
                self.slots.setdefault(s.id, set())
                self.queues.setdefault(s.id, [])

    def select_available_station(self, drone: DroneState, city: CityEnvironment) -> Optional[Station]:
        with self._lock:
            self.sync_stations(city)
            active = [s for s in city.stations if s.active]
            if not active:
                return None
            ordered = sorted(
                active,
                key=lambda s: math.hypot(drone.position[0] - s.position[0], drone.position[2] - s.position[2]),
            )
            for st in ordered:
                if len(self.slots[st.id]) < st.capacity or drone.id in self.slots[st.id]:
                    return st
            return ordered[0]

    def reserve_station(
        self,
        drone: DroneState,
        city: CityEnvironment,
        route_check: Optional[Callable[[Station], bool]] = None,
    ) -> Optional[Station]:
        """Atomically choose an active station and reserve an open pad.

        ``route_check`` lets the caller reject unsafe stations before a pad is
        committed. The check runs under the same lock as capacity admission.
        """
        with self._lock:
            self.sync_stations(city)
            active = [s for s in city.stations if s.active]
            for reserved in active:
                if drone.id in self.slots.get(reserved.id, set()):
                    if route_check is None or route_check(reserved):
                        return reserved
                    self.release_pad(drone.id)
            ordered = sorted(
                active,
                key=lambda s: math.hypot(drone.position[0] - s.position[0], drone.position[2] - s.position[2]),
            )
            for st in ordered:
                if drone.id not in self.slots[st.id] and len(self.slots[st.id]) >= st.capacity:
                    continue
                if route_check is not None and not route_check(st):
                    continue
                if self.request_pad(drone.id, st):
                    for sid, queue in self.queues.items():
                        if sid != st.id and drone.id in queue:
                            queue.remove(drone.id)
                    return st
            return None

    def request_pad(self, drone_id: str, station: Station) -> bool:
        with self._lock:
            if not station.active:
                return False
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

    def has_reservation(self, drone_id: str, station_id: Optional[str] = None) -> bool:
        with self._lock:
            if station_id is not None:
                return drone_id in self.slots.get(station_id, set())
            return any(drone_id in occupied for occupied in self.slots.values())

    def queued_station(self, drone_id: str) -> Optional[str]:
        with self._lock:
            return next((sid for sid, queue in self.queues.items() if drone_id in queue), None)

    def release_pad(self, drone_id: str) -> None:
        with self._lock:
            for sid, occ in self.slots.items():
                if drone_id in occ:
                    occ.remove(drone_id)
                    queue = self.queues.get(sid, [])
                    if queue:
                        nxt = queue.pop(0)
                        occ.add(nxt)
                elif drone_id in self.queues.get(sid, []):
                    self.queues[sid].remove(drone_id)

    def release_all(self, drone_id: str) -> None:
        self.release_pad(drone_id)

    def get_utilization(self, city: CityEnvironment) -> Dict[str, Dict[str, int]]:
        with self._lock:
            self.sync_stations(city)
            return {
                s.id: {
                    "occupied": len(self.slots.get(s.id, set())),
                    "capacity": s.capacity,
                    "queued": len(self.queues.get(s.id, [])),
                }
                for s in city.stations
            }
