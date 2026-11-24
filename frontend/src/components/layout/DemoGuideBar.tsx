import React, { useState } from "react";
import { Check, Play, X } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";
import { api } from "../../api/client";

export const DemoGuideBar: React.FC = () => {
  const open = useSimStore((s) => s.showDemoBar);
  const setOpen = useSimStore((s) => s.setShowDemoBar);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setPlacementMode = useSimStore((s) => s.setPlacementMode);
  const selectDrone = useSimStore((s) => s.selectDrone);
  const setCameraFocusPoint = useSimStore((s) => s.setCameraFocusPoint);
  const setShowFailureModal = useSimStore((s) => s.setShowFailureModal);
  const setCriticalAlert = useSimStore((s) => s.setCriticalAlert);
  const setToast = useSimStore((s) => s.setToast);

  const [done, setDone] = useState<Record<number, boolean>>({});
  const [autoRunning, setAutoRunning] = useState(false);

  if (!open) return null;

  const mark = (i: number) => setDone((prev) => ({ ...prev, [i]: true }));

  const runStep = async (idx: number) => {
    mark(idx);
    if (idx === 0) {
      applyServerPayload(await api.resetSim());
      setToast("Step 1/6: 4x4 km Chennai Metropolitan Digital Twin initialized.");
    } else if (idx === 1) {
      applyServerPayload(await api.startBenchmark());
      setCriticalAlert({
        title: "4-STRATEGY BENCHMARK LAUNCHED",
        detail: "Greedy, Classical OR-Tools, Quantum QAOA, and Hybrid running on isolated copies of Seed 20261121.",
        kind: "info",
      });
    } else if (idx === 2) {
      setPlacementMode("add_target");
      setToast("Step 3/6: Click anywhere on the city ground to inject a critical emergency.");
    } else if (idx === 3) {
      const drones = useSimStore.getState().activeState?.drones || [];
      const d04 = drones.find((d) => d.id === "D-04") || drones[0];
      if (d04) {
        selectDrone(d04.id);
        setCameraFocusPoint(d04.position);
      }
      setShowFailureModal(true);
    } else if (idx === 4) {
      const r = await api.injectEnvEvent("expand_fire");
      applyServerPayload(r.state);
      setCameraFocusPoint([1380, 40, 1420]);
      setCriticalAlert({
        title: "FIRE ZONE EXPANDED — AIRSPACE REROUTED",
        detail: "Affected flight paths invalidated; 3D A* computed safe high-altitude detours across all benchmarks.",
        kind: "replan",
      });
    } else if (idx === 5) {
      await api.saveExperiment();
      window.open(api.exportZipUrl(), "_blank");
      setToast("Step 6/6: Exporting 14-artifact reproducible experiment ZIP.");
    }
  };

  const runAutoDemo = async () => {
    if (autoRunning) return;
    setAutoRunning(true);
    try {
      await runStep(0);
      await new Promise((r) => setTimeout(r, 1200));
      await runStep(1);
      await api.setSpeed(2);
      await new Promise((r) => setTimeout(r, 4500));
      // Inject critical trauma task automatically across all 4 strategies
      mark(2);
      const tRes = await api.createTask({
        name: "Auto-Demo Critical Trauma Airlift",
        task_type: "medical_delivery",
        location: [2040, 4, 1680],
        priority: "critical",
        payload_required_kg: 1.2,
        required_capabilities: ["medical_payload"],
        deadline_seconds: 340,
        service_time_seconds: 18,
        risk_level: 0.85,
        auto_assign: true,
      });
      applyServerPayload(tRes.state);
      setCameraFocusPoint([2040, 20, 1680]);
      setCriticalAlert({
        title: "NEW CRITICAL EMERGENCY INJECTED",
        detail: "Broadcasted to all 4 strategies at identical sim timestamp. Re-optimization triggered.",
        kind: "replan",
      });
      await new Promise((r) => setTimeout(r, 4500));
      // Destroy D-04 across all 4 benchmarks & focus camera on wreckage
      mark(3);
      const dRes = await api.injectFailure("D-04", "COMPLETE_DRONE_DESTRUCTION", "all");
      applyServerPayload(dRes.state);
      const d04 = dRes.state.benchmark.active_state.drones.find((d) => d.id === "D-04");
      if (d04) {
        selectDrone("D-04");
        setCameraFocusPoint(d04.position);
      }
      setCriticalAlert({
        title: "UNIT D-04 DESTROYED — AUTOMATIC RECOVERY ACTIVE",
        detail: "Unfinished missions reallocated to eligible fleet units. Observe amber 3D handoff arcs.",
        kind: "failure",
      });
      await new Promise((r) => setTimeout(r, 5000));
      await runStep(4);
    } finally {
      setAutoRunning(false);
    }
  };

  const labels = [
    "1. INIT CITY",
    "2. RUN ALL 4",
    "3. ADD TARGET",
    "4. DESTROY D-04",
    "5. EXPAND FIRE",
    "6. EXPORT ZIP",
  ];

  return (
    <div className="h-9 bg-[#141a24] border-b border-[#242c3a] px-3 flex items-center justify-between font-mono text-[10px] shrink-0">
      <div className="flex items-center gap-1.5 overflow-x-auto">
        <span className="text-zinc-400 mr-1 uppercase font-semibold">DEMO DIRECTOR:</span>
        <button
          onClick={runAutoDemo}
          disabled={autoRunning}
          className={`px-2.5 py-1 font-semibold flex items-center gap-1 whitespace-nowrap ${
            autoRunning ? "bg-amber-600 text-zinc-950" : "bg-zinc-100 hover:bg-white text-zinc-950"
          }`}
        >
          <Play className="w-3 h-3 fill-current" /> {autoRunning ? "AUTO-DEMO RUNNING..." : "AUTO-DEMO"}
        </button>
        <span className="text-zinc-700 mx-0.5">|</span>
        {labels.map((lbl, i) => (
          <button
            key={lbl}
            onClick={() => runStep(i)}
            className={`px-2 py-1 border transition whitespace-nowrap flex items-center gap-1 ${
              done[i]
                ? "bg-emerald-950/50 border-emerald-700 text-emerald-300"
                : "bg-[#0b0e14] hover:bg-[#1c2433] border-[#2d3748] text-zinc-200"
            }`}
          >
            {done[i] && <Check className="w-3 h-3" />}
            {lbl}
          </button>
        ))}
      </div>
      <button onClick={() => setOpen(false)} className="p-1 text-zinc-400 hover:text-zinc-100"><X className="w-3.5 h-3.5" /></button>
    </div>
  );
};
