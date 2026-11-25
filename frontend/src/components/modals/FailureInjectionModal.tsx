import React, { useState } from "react";
import { useSimStore } from "../../state/simulationStore";
import { api } from "../../api/client";

const FAILURE_TYPES = [
  "COMPLETE_DRONE_DESTRUCTION",
  "MOTOR_FAILURE",
  "BATTERY_FAILURE",
  "GPS_FAILURE",
  "COMMUNICATION_LOSS",
  "LOW_BATTERY",
  "SENSOR_FAILURE",
  "FLIGHT_CONTROL_FAILURE",
];

export const FailureInjectionModal: React.FC = () => {
  const open = useSimStore((s) => s.showFailureModal);
  const setOpen = useSimStore((s) => s.setShowFailureModal);
  const selectedDroneId = useSimStore((s) => s.selectedDroneId) || "D-04";
  const mode = useSimStore((s) => s.mode);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setToast = useSimStore((s) => s.setToast);
  const setCriticalAlert = useSimStore((s) => s.setCriticalAlert);

  const [failureType, setFailureType] = useState("COMPLETE_DRONE_DESTRUCTION");
  const [scope, setScope] = useState<"all" | "selected">("all");

  if (!open) return null;

  const confirm = async () => {
    const res = await api.injectFailure(selectedDroneId, failureType, scope);
    applyServerPayload(res.state);
    setOpen(false);
    const alertObj = {
      title: `UNIT ${selectedDroneId} — ${failureType.replace(/_/g, " ")}`,
      detail: "Unfinished missions transferred to recovery queue. Automatic fleet reallocation complete — inspect amber 3D handoff arcs.",
      kind: "failure" as const,
    };
    setCriticalAlert(alertObj);
    api.syncUi("critical_alert", { alert: alertObj });
  };

  return (
    <div className="fixed inset-0 bg-black/75 flex items-center justify-center z-50 font-mono text-xs">
      <div className="w-[400px] bg-[#11161f] border border-red-900 p-4 space-y-3">
        <div className="border-b border-[#242c3a] pb-2 font-semibold text-red-400">
          FAILURE INJECTION — UNIT {selectedDroneId}
        </div>
        <p className="text-[11px] text-zinc-400">
          Software simulation only. Triggering destruction halts the selected unit, moves its incomplete tasks to the recovery queue, and executes automatic reassignment.
        </p>

        <label className="block">
          <span className="text-[10px] text-zinc-400">FAILURE MODE</span>
          <select value={failureType} onChange={(e) => setFailureType(e.target.value)} className="mt-1 w-full bg-[#0b0e14] border border-[#242c3a] px-2 py-1.5 text-zinc-100">
            {FAILURE_TYPES.map((f) => <option key={f} value={f}>{f.replace(/_/g, " ")}</option>)}
          </select>
        </label>

        {mode === "benchmark" && (
          <label className="block">
            <span className="text-[10px] text-zinc-400">BENCHMARK SCOPE</span>
            <select value={scope} onChange={(e) => setScope(e.target.value as "all" | "selected")} className="mt-1 w-full bg-[#0b0e14] border border-[#242c3a] px-2 py-1.5 text-zinc-100">
              <option value="all">Broadcast identically to ALL 4 strategies (Fair Comparison)</option>
              <option value="selected">Apply to currently viewed strategy only</option>
            </select>
          </label>
        )}

        <div className="flex justify-end gap-2 pt-2 border-t border-[#242c3a]">
          <button onClick={() => setOpen(false)} className="px-3 py-1.5 bg-[#171d28] border border-[#2d3748] text-zinc-300">CANCEL</button>
          <button onClick={confirm} className="px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white font-semibold">CONFIRM FAILURE</button>
        </div>
      </div>
    </div>
  );
};
