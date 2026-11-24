# Quantum Rescue — API & Demo Guide

## Key REST & WebSocket Endpoints (`http://localhost:8000`)
* **World & Countries**: `GET /api/world/overview`, `POST /api/world/tick`, `POST /api/world/emergency-stop`, `POST /api/world/emergency-resume`, `GET /api/countries`, `GET /api/countries/{id}`, `PATCH /api/countries/{id}`, `GET /api/countries/{id}/population`
* **Disasters & Cascades**: `GET /api/disasters`, `POST /api/disasters`, `POST /api/disasters/prepare`, `POST /api/disasters/{id}/stop`, `GET /api/disasters/cascade/{country_id}`
* **Medical & Logistics**: `GET /api/hospitals`, `GET /api/ambulances`, `GET /api/ambulances/requirements/{country_id}`, `GET /api/shelters`, `GET /api/inventory`, `GET /api/resources/shortages/{country_id}`
* **Drones, Swarms & Route Intelligence**: `GET /api/global/drones`, `POST /api/global/drones/{id}/destroy/prepare`, `GET /api/swarms`, `POST /api/swarms/prepare`, `POST /api/routes/explore`, `POST /api/routes/multistop`, `GET /api/routes/logs`
* **Innovations**: `POST /api/counterfactual/{country_id}`, `GET /api/mutual-aid/{country_id}`, `POST /api/mutual-aid/prepare`, `GET /api/equity/{country_id}`, `GET /api/playbooks`
* **JARVIS, Approvals & Providers**: `POST /api/ai/chat`, `POST /api/ai/chat/stream`, `GET /api/ai/providers/status`, `GET /api/ai/tools`, `GET /api/approvals`, `POST /api/approvals/{id}/approve`, `POST /api/approvals/{id}/reject`, `POST /api/approvals/{id}/modify`
* **Events, Sync & Exports**: `GET /api/events`, `GET /api/audit-logs`, `GET /api/frontend/commands`, `POST /api/frontend/commands/ack`, `GET /api/global/export/geojson`, `GET /api/global/export/zip`
* **WebSockets**: `ws://localhost:8000/ws/global?client=quantum-world|quantum-operations|quantum-jarvis` and `ws://localhost:8000/ws/simulation`

## 10-Scene Demonstration Sequence
1. Open **World Command (`:5173`)**, **Operations Command (`:5174`)**, and **JARVIS (`:5175`)** side by side.
2. Inspect the 7-country planetary globe in World Command and click **Veridia Basin (`COUNTRY-03`)** (active Cyclone Varuna).
3. In JARVIS, ask: `"Analyze the situation in Country 3"` — verify live exposed population, hospital beds, ambulance deficit, and supply forecast.
4. Ask: `"View Country 1 and find the best drones to reach the hospital"` — observe World Command focus `COUNTRY-01` and render candidate 3D routes while JARVIS displays the ranked comparison table and live execution trace.
5. Ask: `"Prepare a complete rescue plan for Country 3"` — inspect the pending Approval Card and click **Approve & Execute**.
6. In Operations Command, open **Approvals & Logs** and **Fleet, Swarms & Routes** to observe live deployed drones and ambulances.
7. Trigger a simulated drone destruction (`POST /api/global/drones/{id}/destroy/prepare` -> Approve) and verify automatic replacement assignment.
8. Ask JARVIS: `"Can another country provide additional ambulances?"` and approve the Seven-Country Mutual Aid transfer.
9. Run the **4-World Counterfactual Digital Twin** and the **4-Solver Benchmark Arena** in Operations Command.
10. Click **Export ZIP** in Operations Command to download the complete reproducible `QUANTUM_RESCUE_EXPERIMENT` archive.
