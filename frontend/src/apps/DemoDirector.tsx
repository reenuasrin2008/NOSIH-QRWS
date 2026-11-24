import React, { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clapperboard,
  CloudLightning,
  Cpu,
  Globe,
  Loader2,
  X,
} from "lucide-react";

interface DemoStepResult {
  id: string;
  label: string;
  detail: string;
}

interface DemoToast {
  title: string;
  body: string;
  isError?: boolean;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function callAiTool(toolName: string, args: Record<string, unknown>): Promise<any> {
  const res = await fetch(`/api/ai/tools/${toolName}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  const data = await res.json();
  if (
    data?.status === "ERROR" ||
    data?.result?.status === "ERROR" ||
    data?.error
  ) {
    throw new Error(
      data?.error ||
        data?.message ||
        data?.result?.error ||
        data?.result?.message ||
        `Tool ${toolName} returned status ERROR`
    );
  }
  return data;
}

async function approveDemoOperation(approvalId: string): Promise<any> {
  const res = await fetch(`/api/approvals/${approvalId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ auto_execute: true }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  const data = await res.json();
  if (data?.status === "ERROR" || data?.execution_result?.status === "ERROR") {
    throw new Error(
      data?.error ||
        data?.execution_result?.error ||
        `Approval ${approvalId} returned status ERROR`
    );
  }
  return data;
}

export const DemoDirector: React.FC = () => {
  const isEnabled = useMemo(() => {
    if (typeof window === "undefined") return false;
    return (
      import.meta.env.DEV ||
      new URLSearchParams(window.location.search).get("demo") === "1"
    );
  }, []);

  const [collapsed, setCollapsed] = useState(true);
  const [runningScenario, setRunningScenario] = useState<string | null>(null);
  const [statusLine, setStatusLine] = useState<string | null>(null);
  const [toast, setToast] = useState<DemoToast | null>(null);
  const [history, setHistory] = useState<DemoStepResult[]>([]);

  if (!isEnabled) return null;

  const pushHistory = (label: string, detail: string) => {
    setHistory((prev) => [
      { id: `${Date.now()}-${Math.random()}`, label, detail },
      ...prev.slice(0, 5),
    ]);
  };

  const runTyphoonVeridia = async () => {
    if (runningScenario) return;
    setRunningScenario("typhoon");
    setToast(null);
    try {
      setStatusLine("Preparing CYCLONE event on COUNTRY-03 (Veridia)...");
      const prep = await callAiTool("prepare_disaster_event", {
        country_id: "COUNTRY-03",
        disaster_type: "CYCLONE",
        severity: 0.86,
        radius_km: 14.0,
      });
      const approvalId: string | undefined =
        prep?.result?.approval_id || prep?.approval_id;
      if (!approvalId) {
        throw new Error("No approval_id returned by prepare_disaster_event.");
      }

      setStatusLine(`Approval ${approvalId} created · DEMO MODE — auto-approving in 1.5s...`);
      pushHistory("Typhoon Prepared", `Approval ${approvalId} (CYCLONE · COUNTRY-03)`);
      await sleep(1500);

      await approveDemoOperation(approvalId);
      setStatusLine(`Approval ${approvalId} executed · Prepping SURVIVOR_SEARCH swarm + ambulances...`);

      const [swarmPrep, ambPrep] = await Promise.all([
        callAiTool("prepare_swarm_operation", {
          country_id: "COUNTRY-03",
          mode: "SURVIVOR_SEARCH",
          drone_count: 8,
          formation: "SEARCH_GRID",
        }),
        callAiTool("prepare_ambulance_dispatch", {
          country_id: "COUNTRY-03",
          count: 6,
        }),
      ]);

      const swarmApr = swarmPrep?.result?.approval_id || "SWARM-READY";
      const ambApr = ambPrep?.result?.approval_id || "AMB-READY";

      const summary = `Cyclone live (${approvalId}). Queued SURVIVOR_SEARCH swarm (${swarmApr}) & ambulance dispatch (${ambApr}).`;
      setStatusLine(summary);
      pushHistory("Veridia Response Prepped", summary);
      setToast({
        title: "Typhoon hits Veridia — Response Queued",
        body: summary,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Typhoon scenario failed.";
      setStatusLine(`Error: ${msg}`);
      setToast({ title: "Demo Error", body: msg, isError: true });
    } finally {
      setRunningScenario(null);
    }
  };

  const runDroneDownRecovery = async () => {
    if (runningScenario) return;
    setRunningScenario("drone");
    setToast(null);
    try {
      setStatusLine("Selecting eligible active drone for failure injection...");
      let targetDroneId = "D-03-01";
      let targetCountryId = "COUNTRY-03";
      try {
        const fleetScan = await callAiTool("get_drone_fleet", {
          country_id: "COUNTRY-03",
        });
        const list: Array<{ drone_id?: string; country_id?: string; status?: string }> =
          fleetScan?.result?.drones || fleetScan?.drones || [];
        const eligible = list.find(
          (d) => (d.status || "").toUpperCase() !== "DESTROYED"
        );
        if (eligible?.drone_id) {
          targetDroneId = eligible.drone_id;
          targetCountryId = eligible.country_id || "COUNTRY-03";
        }
      } catch {
        // Fallback to default active Veridia drone if fleet listing tool is unavailable
      }

      const prep = await callAiTool("prepare_drone_failure", {
        country_id: targetCountryId,
        drone_id: targetDroneId,
      });
      const approvalId: string | undefined =
        prep?.result?.approval_id || prep?.approval_id;
      if (!approvalId) {
        throw new Error("No approval_id returned by prepare_drone_failure.");
      }

      setStatusLine(
        `Drone ${targetDroneId} failure (${approvalId}) · DEMO MODE — auto-approving in 1.5s...`
      );
      pushHistory("Drone Failure Prepped", `${targetDroneId} · ${approvalId}`);
      await sleep(1500);

      const executed = await approveDemoOperation(approvalId);
      const recoveryNote =
        executed?.execution_result?.recovery_summary ||
        (executed?.execution_result?.replacement_drone_id
          ? `Replacement ${executed.execution_result.replacement_drone_id} reassigned automatically.`
          : `Swarm auto-recovery completed for ${targetDroneId} (${targetCountryId}).`);

      setStatusLine(recoveryNote);
      pushHistory("Auto-Recovery Complete", recoveryNote);
      setToast({
        title: `Drone Down → Auto-Recovery (${targetDroneId})`,
        body: recoveryNote,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Drone recovery scenario failed.";
      setStatusLine(`Error: ${msg}`);
      setToast({ title: "Demo Error", body: msg, isError: true });
    } finally {
      setRunningScenario(null);
    }
  };

  const runCrossCountryMutualAid = async () => {
    if (runningScenario) return;
    setRunningScenario("aid");
    setToast(null);
    try {
      setStatusLine("Scanning neighboring nations for surplus ambulances...");
      const scan = await callAiTool("find_mutual_aid_options", {
        country_id: "COUNTRY-03",
        resource_type: "ambulances",
        quantity: 6,
      });
      const donors: any[] = scan?.result?.eligible_donors || [];
      const topDonor = donors[0] || {
        donor_country_id: "COUNTRY-05",
        donor_name: "Country 5",
        proposed_transfer: 6,
        estimated_arrival_hours: 2.1,
      };

      setStatusLine(
        `Top donor: ${topDonor.donor_name || topDonor.donor_country_id} · Preparing mutual aid transfer...`
      );
      const aidPrep = await callAiTool("prepare_cross_country_aid", {
        country_id: "COUNTRY-03",
        donor_country_id: topDonor.donor_country_id,
        resource_type: "ambulances",
        quantity: topDonor.proposed_transfer || 6,
      });
      const approvalId = aidPrep?.result?.approval_id || aidPrep?.approval_id || "AID-QUEUED";

      const summary = `Transfer ${topDonor.proposed_transfer || 6} ambulances from ${
        topDonor.donor_name || topDonor.donor_country_id
      } → COUNTRY-03 (ETA ${topDonor.estimated_arrival_hours ?? "~2"}h) · Approval ${approvalId}.`;
      setStatusLine(summary);
      pushHistory("Mutual Aid Prepared", summary);
      setToast({
        title: "Cross-Country Mutual Aid Ready",
        body: summary,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Mutual aid scenario failed.";
      setStatusLine(`Error: ${msg}`);
      setToast({ title: "Demo Error", body: msg, isError: true });
    } finally {
      setRunningScenario(null);
    }
  };

  return (
    <>
      {/* Recovery / Scenario Toast Notification */}
      {toast && (
        <div
          role={toast.isError ? "alert" : "status"}
          className={`fixed top-14 right-4 z-[60] max-w-sm rounded-xl bg-[#0B0C0E]/95 backdrop-blur-xl shadow-2xl p-3 text-[#FAFAFA] font-sans border ${
            toast.isError ? "border-red-500/60" : "border-white/20"
          }`}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-[#FAFAFA]">
              {toast.isError ? (
                <AlertTriangle className="w-3.5 h-3.5 text-red-400 shrink-0" />
              ) : (
                <CheckCircle2 className="w-3.5 h-3.5 text-[#FAFAFA] shrink-0" />
              )}
              <span>{toast.title}</span>
            </div>
            <button
              onClick={() => setToast(null)}
              className="text-[#A1A1AA] hover:text-[#FAFAFA]"
              aria-label="Dismiss toast"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <p className="mt-1 text-[11px] font-mono text-[#A1A1AA] leading-relaxed">{toast.body}</p>
        </div>
      )}

      {/* Collapsible Floating Demo Director Widget */}
      <aside className="fixed top-14 left-4 z-[55] w-80 max-w-[calc(100vw-2rem)] rounded-xl bg-[#0B0C0E]/95 backdrop-blur-xl border border-[#2A2D34] shadow-2xl text-[#FAFAFA] font-sans overflow-hidden">
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="w-full px-3 py-2 bg-[#0F1012] border-b border-[#2A2D34] flex items-center justify-between text-[11px] font-mono tracking-wider uppercase hover:bg-[#16181C] transition-colors"
        >
          <span className="flex items-center gap-2 text-[#FAFAFA] font-semibold">
            <Clapperboard className="w-3.5 h-3.5 text-[#FAFAFA]" />
            DEMO DIRECTOR
            {runningScenario && <Loader2 className="w-3 h-3 animate-spin text-[#A1A1AA]" />}
          </span>
          <span className="flex items-center gap-1 text-[10px] text-[#A1A1AA]">
            {collapsed ? "Expand" : "Hide"}
            {collapsed ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
          </span>
        </button>

        {!collapsed && (
          <div className="p-3 space-y-2.5">
            {/* Button 1: Typhoon hits Veridia */}
            <button
              onClick={runTyphoonVeridia}
              disabled={runningScenario !== null}
              className="w-full text-left p-2.5 rounded-lg bg-[#16181C] hover:bg-[#22252B] disabled:opacity-50 border border-[#2A2D34] transition-colors space-y-0.5"
            >
              <div className="flex items-center justify-between text-xs font-semibold text-[#FAFAFA]">
                <span className="flex items-center gap-1.5">
                  <CloudLightning className="w-3.5 h-3.5 text-[#FAFAFA]" />
                  Typhoon hits Veridia
                </span>
                {runningScenario === "typhoon" && (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-[#FAFAFA]" />
                )}
              </div>
              <div className="text-[10px] font-mono text-[#A1A1AA] leading-snug">
                Injects CYCLONE on COUNTRY-03, auto-approves in 1.5s, preps search swarm & ambulances.
              </div>
            </button>

            {/* Button 2: Drone down -> auto-recovery */}
            <button
              onClick={runDroneDownRecovery}
              disabled={runningScenario !== null}
              className="w-full text-left p-2.5 rounded-lg bg-[#16181C] hover:bg-[#22252B] disabled:opacity-50 border border-[#2A2D34] transition-colors space-y-0.5"
            >
              <div className="flex items-center justify-between text-xs font-semibold text-[#FAFAFA]">
                <span className="flex items-center gap-1.5">
                  <Cpu className="w-3.5 h-3.5 text-[#FAFAFA]" />
                  Drone down → auto-recovery
                </span>
                {runningScenario === "drone" && (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-[#FAFAFA]" />
                )}
              </div>
              <div className="text-[10px] font-mono text-[#A1A1AA] leading-snug">
                Triggers failure on an eligible drone, auto-approves, and confirms swarm handoff.
              </div>
            </button>

            {/* Button 3: Cross-country mutual aid */}
            <button
              onClick={runCrossCountryMutualAid}
              disabled={runningScenario !== null}
              className="w-full text-left p-2.5 rounded-lg bg-[#16181C] hover:bg-[#22252B] disabled:opacity-50 border border-[#2A2D34] transition-colors space-y-0.5"
            >
              <div className="flex items-center justify-between text-xs font-semibold text-[#FAFAFA]">
                <span className="flex items-center gap-1.5">
                  <Globe className="w-3.5 h-3.5 text-[#FAFAFA]" />
                  Cross-country mutual aid
                </span>
                {runningScenario === "aid" && (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-[#FAFAFA]" />
                )}
              </div>
              <div className="text-[10px] font-mono text-[#A1A1AA] leading-snug">
                Finds surplus ambulance donors and prepares a cross-border aid proposal.
              </div>
            </button>

            {statusLine && (
              <div className="p-2 rounded bg-[#050505] border border-[#2A2D34] text-[10px] font-mono text-[#E4E4E7] leading-relaxed">
                {statusLine}
              </div>
            )}

            {history.length > 0 && (
              <div className="pt-1 border-t border-[#2A2D34] space-y-1 max-h-24 overflow-y-auto">
                {history.map((h) => (
                  <div key={h.id} className="text-[10px] font-mono text-[#A1A1AA] truncate">
                    <span className="text-[#FAFAFA]">{h.label}:</span> {h.detail}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </aside>
    </>
  );
};
