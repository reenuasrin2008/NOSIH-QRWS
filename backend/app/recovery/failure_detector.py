from __future__ import annotations
from typing import Dict, List
from app.core.models import DroneState, DroneStatus


def scan_fleet_anomalies(drones: Dict[str, DroneState]) -> List[Dict[str, str]]:
    alerts: List[Dict[str, str]] = []
    for d in drones.values():
        if d.status == DroneStatus.DESTROYED:
            alerts.append({"drone_id": d.id, "severity": "CRITICAL", "reason": "Airframe destroyed"})
        elif d.status in (DroneStatus.DAMAGED, DroneStatus.COMMUNICATION_LOST):
            alerts.append({"drone_id": d.id, "severity": "HIGH", "reason": f"Telemetry fault: {d.status.value}"})
        elif d.battery_percent <= 20.0 and d.status == DroneStatus.IN_FLIGHT:
            alerts.append({"drone_id": d.id, "severity": "WARNING", "reason": f"Reserve breach ({d.battery_percent:.1f}%)"})
        elif d.battery_temp_c >= 52.0:
            alerts.append({"drone_id": d.id, "severity": "WARNING", "reason": f"High battery temp ({d.battery_temp_c:.1f}C)"})
    return alerts
