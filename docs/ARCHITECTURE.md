# Quantum Rescue — Architecture & Design Specification

## 1. Core Separation of Concerns
The platform strictly separates four layers:
1. **JARVIS LLM Layer (`backend/app/providers/ai_providers.py`)**: Six-key Gemini (3 keys) + Grok (3 keys) provider adapter pool with LRU selection, exponential backoff, primary/fallback failover, and grounded local deterministic fallback.
2. **Command Orchestrator (`backend/app/ai/jarvis_agent.py` & `backend/app/approvals/engine.py`)**: Dynamic tool registry, structured session context service (`active_country_id`, `selected_hospital_id`, `pending_approval_id`), permission checks (`backend/app/auth/rbac.py`), approval lifecycle, and live execution tracing.
3. **Authoritative Simulation Engine (`backend/app/world/global_engine.py`, `backend/app/navigation/route_explorer.py`, `backend/app/simulation/world.py`)**: Single source of truth for the 7-country continuous planetary world (`GLOBAL_DISASTER_7NATIONS_001`), hierarchical 4-level synthetic population & households, domestic/livestock/wildlife groups, terrain-aware Flood/Cyclone/Fire/Cascade models, Yen's K-shortest multi-objective 3D drone route explorer, classical OR-Tools & Qiskit/NumPy QAOA optimization, counterfactual twin runner, seven-country mutual aid, and rescue equity engine.
4. **Event Bus & Frontend Command Bus (`backend/app/events/bus.py`, `/ws/global`, `/ws/simulation`)**: Ordered monotonic `world_version` events and structured frontend commands (`camera.focus_country`, `camera.focus_world`, `camera.show_candidate_routes`) with client acknowledgment tracking across `:5173`, `:5174`, and `:5175`.

## 2. Accurate Quantum Positioning
* **Classical Multi-Agent Control**: Real-time drone flight paths, battery/payload constraints, collision avoidance, Yen's K-shortest route exploration, ambulance routing, and emergency recovery run deterministically in classical engines.
* **Quantum QAOA Simulation**: Reduced fleet-assignment QUBO/Ising subproblems are solved via Qiskit Aer (with exact NumPy statevector fallback) and validated/repaired by classical feasibility checks in the 4-strategy Benchmark Arena (`greedy`, `classical`, `quantum`, `hybrid`).
