import React, { useEffect } from "react";
import { AlertTriangle, RefreshCw, X } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";

export const RecoveryBanner: React.FC = () => {
  const alert = useSimStore((s) => s.criticalAlert);
  const setAlert = useSimStore((s) => s.setCriticalAlert);

  useEffect(() => {
    if (!alert) return;
    const t = setTimeout(() => setAlert(null), 7500);
    return () => clearTimeout(t);
  }, [alert, setAlert]);

  if (!alert) return null;

  const isFailure = alert.kind === "failure";
  const borderCls = isFailure ? "border-red-600 bg-red-950/90 text-red-100" : "border-amber-500 bg-[#171d28]/95 text-amber-100";

  return (
    <div className={`absolute top-14 left-1/2 -translate-x-1/2 z-30 max-w-xl px-4 py-2 border font-mono shadow-2xl flex items-center gap-3 ${borderCls}`}>
      {isFailure ? <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" /> : <RefreshCw className="w-4 h-4 text-amber-400 shrink-0" />}
      <div className="min-w-0">
        <div className="text-xs font-bold tracking-wider uppercase">{alert.title}</div>
        <div className="text-[11px] opacity-90">{alert.detail}</div>
      </div>
      <button onClick={() => setAlert(null)} className="ml-2 p-0.5 opacity-75 hover:opacity-100">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};
