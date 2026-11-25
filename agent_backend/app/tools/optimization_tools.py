"""Greedy, Classical OR-Tools, Quantum QAOA, and Hybrid optimization tools."""
from __future__ import annotations

from typing import Any, Dict, List

from app.models.messages import PermissionLevel
from app.services.simulation_client import SimulationClient
from app.tools.schemas import ToolDefinition

_EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}


def build_optimization_tools() -> List[ToolDefinition]:
    def _runner(strategy: str):
        async def _fn(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
            return await sim.post("/api/optimizer/run", json_body={"strategy": strategy, "reason": f"agent_{strategy}_run"})
        return _fn

    async def compare_optimization_strategies(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        lb = await sim.get("/api/leaderboard")
        return {"leaderboard": lb}

    async def get_optimization_results(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        hist = await sim.get("/api/optimizer/history")
        return {"count": len(hist), "latest": hist[-1] if hist else None, "history": hist[-5:]}

    async def get_optimizer_metrics(sim: SimulationClient, args: Dict[str, Any]) -> Dict[str, Any]:
        m = await sim.get("/api/world/metrics")
        hist = await sim.get("/api/optimizer/history")
        return {"metrics": m.get("metrics"), "last_solver_run": hist[-1] if hist else None}

    return [
        ToolDefinition("run_greedy_optimizer", "optimization", "Run the fast Greedy rescue assignment optimizer.", _EMPTY, _runner("greedy"), PermissionLevel.OPERATIONAL),
        ToolDefinition("run_classical_optimizer", "optimization", "Run the OR-Tools Classical rescue assignment optimizer.", _EMPTY, _runner("classical"), PermissionLevel.OPERATIONAL),
        ToolDefinition("run_quantum_optimizer", "optimization", "Run the QAOA Quantum circuit rescue optimizer.", _EMPTY, _runner("quantum"), PermissionLevel.OPERATIONAL),
        ToolDefinition("run_hybrid_optimizer", "optimization", "Run the Hybrid Classical+Quantum QAOA rescue optimizer.", _EMPTY, _runner("hybrid"), PermissionLevel.OPERATIONAL),
        ToolDefinition("compare_optimization_strategies", "optimization", "Retrieve the strategy comparison leaderboard.", _EMPTY, compare_optimization_strategies),
        ToolDefinition("get_optimization_results", "optimization", "Retrieve recent optimizer run results and assignments.", _EMPTY, get_optimization_results),
        ToolDefinition("get_optimizer_metrics", "optimization", "Retrieve solver runtime, score, and feasibility metrics.", _EMPTY, get_optimizer_metrics),
    ]
