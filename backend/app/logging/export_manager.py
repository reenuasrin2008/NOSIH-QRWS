from __future__ import annotations
import csv
import html
import io
import json
import time
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.core.config import CONFIG
from app.core.models import StrategyMetrics
from app.simulation.world import SimulationWorld


def _dicts_to_csv(rows: List[Dict[str, Any]], fieldnames: List[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()


def build_summary_payload(world: SimulationWorld, leaderboard: Optional[List[StrategyMetrics]] = None) -> Dict[str, Any]:
    m = world.get_metrics()
    return {
        "schema_version": "1.0.0",
        "project_name": "QUANTUM RESCUE",
        "run_id": world.run_id,
        "scenario_id": world.city.scenario_id,
        "scenario_name": world.city.scenario_name,
        "seed": world.seed,
        "strategy": world.strategy.value,
        "started_at": world.started_at_iso,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "simulation_duration_s": round(world.sim_time_s, 2),
        "wall_clock_duration_s": round(time.perf_counter() - world.wall_start_ts, 2),
        "num_drones": len(world.drones),
        "num_tasks": len(world.tasks),
        "metrics": m.model_dump(),
        "leaderboard": [item.model_dump() for item in leaderboard] if leaderboard else [m.model_dump()],
    }


def build_replay_payload(world: SimulationWorld) -> Dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "run_id": world.run_id,
        "scenario_id": world.city.scenario_id,
        "seed": world.seed,
        "strategy": world.strategy.value,
        "city": world.city.model_dump(),
        "frames": world.replay_frames,
        "events": [e.model_dump() for e in world.events],
    }


def build_experiment_zip(world: SimulationWorld, leaderboard: Optional[List[StrategyMetrics]] = None) -> bytes:
    summary = build_summary_payload(world, leaderboard)
    replay = build_replay_payload(world)
    lb_rows = [item.model_dump() for item in (leaderboard or [world.get_metrics()])]

    drones_rows = [
        {
            "drone_id": d.id, "drone_class": d.drone_type,
            "home_position": json.dumps(list(d.home_position)),
            "final_position": json.dumps(list(d.position)),
            "battery_before_pct": 100.0, "battery_after_pct": d.battery_percent,
            "total_distance_m": d.total_distance_m, "total_energy_wh": d.total_energy_used_wh,
            "tasks_completed": d.tasks_completed, "tasks_failed": d.tasks_failed,
            "flight_duration_s": d.total_flight_time_s, "status": d.status.value,
            "failure_count": len(d.failure_history),
        }
        for d in world.drones.values()
    ]

    tasks_rows = [
        {
            "task_id": t.id, "name": t.name, "type": t.task_type, "priority": t.priority.value,
            "location": json.dumps(list(t.location)), "assigned_drone": t.assigned_drone_id or "",
            "created_at_s": t.created_at_sim_s,
            "assigned_at_s": t.assigned_at_sim_s if t.assigned_at_sim_s is not None else "",
            "started_at_s": t.started_at_sim_s if t.started_at_sim_s is not None else "",
            "completed_at_s": t.completed_at_sim_s if t.completed_at_sim_s is not None else "",
            "deadline_s": t.deadline_seconds, "deadline_violated": t.deadline_violated,
            "status": t.status.value, "reassignment_count": t.reassignment_count,
            "response_time_s": round(t.completed_at_sim_s - t.created_at_sim_s, 1) if t.completed_at_sim_s is not None else "",
        }
        for t in world.tasks.values()
    ]

    html_report = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Quantum Rescue Experiment Report — {world.run_id}</title>
<style>
  body {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: #0b0e14; color: #e2e8f0; margin: 32px; }}
  h1, h2 {{ color: #f8fafc; border-bottom: 1px solid #242c3a; padding-bottom: 6px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 12px; }}
  th, td {{ border: 1px solid #242c3a; padding: 8px 10px; text-align: left; }}
  th {{ background: #141923; color: #94a3b8; }}
  .kpi {{ display: inline-block; background: #11161f; border: 1px solid #242c3a; padding: 10px 16px; margin: 4px; }}
</style>
</head>
<body>
  <h1>QUANTUM RESCUE — EXPERIMENT REPORT</h1>
  <p>Run ID: <b>{html.escape(world.run_id)}</b> | Scenario: <b>{html.escape(world.city.scenario_name)}</b> | Seed: <b>{world.seed}</b> | Strategy: <b>{world.strategy.value.upper()}</b></p>
  <div>
    <div class="kpi">COMPLETED: <b>{summary['metrics']['missions_completed']} / {len(world.tasks)}</b></div>
    <div class="kpi">ENERGY: <b>{summary['metrics']['total_energy_wh']} Wh</b></div>
    <div class="kpi">SIM TIME: <b>{summary['simulation_duration_s']} s</b></div>
    <div class="kpi">SCORE: <b>{summary['metrics']['score']} / 100</b></div>
  </div>
  <h2>STRATEGY LEADERBOARD</h2>
  <table>
    <tr><th>RANK</th><th>STRATEGY</th><th>COMPLETED</th><th>ENERGY (Wh)</th><th>AVG RESPONSE (s)</th><th>SOLVER (ms)</th><th>SCORE</th></tr>
    {''.join(f"<tr><td>#{r['rank']}</td><td>{r['strategy'].upper()}</td><td>{r['missions_completed']}</td><td>{r['total_energy_wh']}</td><td>{r['avg_response_time_s']}</td><td>{r['solver_runtime_ms']}</td><td><b>{r['score']}</b></td></tr>" for r in lb_rows)}
  </table>
</body>
</html>"""

    readme_txt = (
        f"QUANTUM RESCUE EXPERIMENT ARCHIVE\nRun ID: {world.run_id}\n"
        f"Scenario: {world.city.scenario_name} (Seed: {world.seed})\nExported: {summary['exported_at']}\n"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("summary.json", json.dumps(summary, indent=2))
        zf.writestr("simulation_config.json", json.dumps(asdict(CONFIG), indent=2))
        zf.writestr("drones.csv", _dicts_to_csv(drones_rows, list(drones_rows[0].keys()) if drones_rows else ["drone_id"]))
        zf.writestr("tasks.csv", _dicts_to_csv(tasks_rows, list(tasks_rows[0].keys()) if tasks_rows else ["task_id"]))
        zf.writestr("routes.json", json.dumps(world.route_history, indent=2))
        zf.writestr("telemetry.csv", _dicts_to_csv(world.analytics_series, ["t", "completed", "energy_wh", "avg_response_s", "avg_battery_pct", "distance_m", "score"]))
        zf.writestr("failure_events.csv", _dicts_to_csv(world.failure_logs, ["sim_time_s", "drone_id", "failure_type", "position", "tasks_affected", "recovery_duration_ms", "recovery_success"]))
        zf.writestr("task_reassignments.csv", _dicts_to_csv(world.reassignment_logs, ["sim_time_s", "task_id", "new_drone_id", "strategy", "reason"]))
        zf.writestr("optimizer_results.json", json.dumps([o.model_dump() for o in world.optimization_history], indent=2))
        zf.writestr("leaderboard.csv", _dicts_to_csv(lb_rows, ["rank", "strategy", "missions_completed", "missions_pending", "total_energy_wh", "avg_response_time_s", "operational_risk", "solver_runtime_ms", "tasks_recovered", "score"]))
        zf.writestr("event_timeline.json", json.dumps([e.model_dump() for e in world.events], indent=2))
        zf.writestr("replay.json", json.dumps(replay))
        zf.writestr("experiment_report.html", html_report)
        zf.writestr("README.txt", readme_txt)

    return buf.getvalue()
