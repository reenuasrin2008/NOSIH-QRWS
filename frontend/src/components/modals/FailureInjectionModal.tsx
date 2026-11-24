import React, { useEffect, useRef, useState } from "react";
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

interface FailureInjectionModalProps {
  selectedDroneId: string | null;
}

function isRecord(value: unknown): value is Record<string, any> {
  return !!value && typeof value === "object";
}

export const FailureInjectionModal: React.FC<FailureInjectionModalProps> = ({ selectedDroneId }) => {
  const open = useSimStore((s) => s.showFailureModal);
  const setOpen = useSimStore((s) => s.setShowFailureModal);
  const mode = useSimStore((s) => s.mode);
  const activeView = useSimStore((s) => s.activeView);
  const activeState = useSimStore((s) => s.activeState);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setToast = useSimStore((s) => s.setToast);
  const setCriticalAlert = useSimStore((s) => s.setCriticalAlert);

  const [failureType, setFailureType] = useState("COMPLETE_DRONE_DESTRUCTION");
  const [scope, setScope] = useState<"all" | "selected">("all");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  const validTarget = !!selectedDroneId &&
    !!activeState?.drones.some((drone) => drone.id === selectedDroneId);

  useEffect(() => {
    if (!open) return;
    setError(null);
    const previousFocus = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();
    return () => previousFocus?.focus();
  }, [open]);

  if (!open) return null;

  const close = () => {
    if (!submitting) setOpen(false);
  };

  const confirm = async () => {
    if (!selectedDroneId || !validTarget || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.injectFailure(selectedDroneId, failureType, scope);
      const result = res?.result;
      const targetedResults = mode === "benchmark" && isRecord(result)
        ? (scope === "all" ? Object.values(result) : [result[activeView]])
        : [result];
      const succeeded = targetedResults.length > 0 && targetedResults.every((entry) => {
        if (!isRecord(entry) || entry.ok !== true || !isRecord(entry.failure)) return false;
        return entry.failure.drone_id === selectedDroneId &&
          entry.failure.failure_type === failureType;
      });

      if (!succeeded || !res?.state?.benchmark?.active_state) {
        throw new Error(`The backend did not confirm ${failureType.replace(/_/g, " ")} for ${selectedDroneId}.`);
      }

      applyServerPayload(res.state);
      setOpen(false);
      setToast(`${selectedDroneId} failure confirmed.`);
      const alertObj = {
        title: `UNIT ${selectedDroneId} — ${failureType.replace(/_/g, " ")}`,
        detail: "Unfinished missions transferred to recovery queue. Automatic fleet reallocation complete — inspect amber 3D handoff arcs.",
        kind: "failure" as const,
      };
      setCriticalAlert(alertObj);
      void api.syncUi("critical_alert", { alert: alertObj });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failure injection was not confirmed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/75 flex items-center justify-center z-50 font-mono text-xs"
      onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="failure-modal-title"
        aria-describedby="failure-modal-description"
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.stopPropagation();
            close();
          }
          if (e.key !== "Tab") return;
          const focusable = dialogRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled), select:not(:disabled)");
          if (!focusable?.length) return;
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }}
        className="w-[400px] max-w-[calc(100vw-2rem)] bg-[#11161f] border border-red-900 p-4 space-y-3"
      >
        <div id="failure-modal-title" className="border-b border-[#242c3a] pb-2 font-semibold text-red-400">
          FAILURE INJECTION — UNIT {selectedDroneId || "NOT SELECTED"}
        </div>
        <p id="failure-modal-description" className="text-[11px] text-zinc-400">
          Software simulation only. Triggering destruction halts the selected unit, moves its incomplete tasks to the recovery queue, and executes automatic reassignment.
        </p>
        {!validTarget && (
          <p role="alert" className="text-[11px] text-amber-300">Select a valid drone before injecting a failure.</p>
        )}
        {error && <p role="alert" className="text-[11px] text-red-300">{error}</p>}

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
          <button ref={cancelRef} onClick={close} disabled={submitting} className="px-3 py-1.5 bg-[#171d28] border border-[#2d3748] text-zinc-300 disabled:opacity-50">CANCEL</button>
          <button onClick={confirm} disabled={!validTarget || submitting} className="px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white font-semibold disabled:opacity-40 disabled:cursor-not-allowed">
            {submitting ? "CONFIRMING..." : "CONFIRM FAILURE"}
          </button>
        </div>
      </div>
    </div>
  );
};
