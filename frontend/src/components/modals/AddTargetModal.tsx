import React, { useState } from "react";
import { useSimStore } from "../../state/simulationStore";
import { api } from "../../api/client";

export const AddTargetModal: React.FC = () => {
  const open = useSimStore((s) => s.showAddTargetModal);
  const setOpen = useSimStore((s) => s.setShowAddTargetModal);
  const pendingLocation = useSimStore((s) => s.pendingLocation);
  const activeState = useSimStore((s) => s.activeState);
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setToast = useSimStore((s) => s.setToast);

  const [name, setName] = useState("Critical Trauma Airlift");
  const [taskType, setTaskType] = useState("medical_delivery");
  const [priority, setPriority] = useState("critical");
  const [payloadKg, setPayloadKg] = useState(1.2);
  const [deadline, setDeadline] = useState(360);
  const [serviceTime, setServiceTime] = useState(20);
  const [risk, setRisk] = useState(0.75);
  const [assignDroneId, setAssignDroneId] = useState("");

  if (!open || !pendingLocation) return null;

  const capMap: Record<string, string[]> = {
    medical_delivery: ["medical_payload"],
    missing_person: ["survivor_search"],
    water_supply: ["water_supply"],
    equipment_delivery: ["equipment_delivery"],
    fire_monitoring: ["thermal_scan"],
    flood_inspection: ["surveillance"],
  };

  const submit = async (autoAssign: boolean) => {
    const res = await api.createTask({
      name,
      task_type: taskType,
      location: pendingLocation,
      priority,
      payload_required_kg: payloadKg,
      required_capabilities: capMap[taskType] || ["medical_payload"],
      deadline_seconds: deadline,
      service_time_seconds: serviceTime,
      risk_level: risk,
      assign_drone_id: autoAssign ? null : (assignDroneId || null),
      auto_assign: autoAssign,
    });
    applyServerPayload(res.state);
    setOpen(false);
    setToast(`Target "${name}" injected at (${pendingLocation[0]}, ${pendingLocation[2]}).`);
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 font-mono text-xs">
      <div className="w-[420px] bg-[#11161f] border border-[#2d3748] p-4 space-y-3">
        <div className="flex justify-between items-center border-b border-[#242c3a] pb-2">
          <span className="font-semibold text-zinc-100">CREATE RESCUE TARGET</span>
          <span className="text-[10px] text-zinc-400">POS: ({pendingLocation[0]}, {pendingLocation[2]})</span>
        </div>

        <div className="space-y-2">
          <label className="block">
            <span className="text-[10px] text-zinc-400">TARGET NAME</span>
            <input value={name} onChange={(e) => setName(e.target.value)} className="mt-0.5 w-full bg-[#0b0e14] border border-[#242c3a] px-2 py-1 text-zinc-100" />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label>
              <span className="text-[10px] text-zinc-400">TASK TYPE</span>
              <select value={taskType} onChange={(e) => setTaskType(e.target.value)} className="mt-0.5 w-full bg-[#0b0e14] border border-[#242c3a] px-2 py-1 text-zinc-100">
                <option value="medical_delivery">Medical Delivery</option>
                <option value="missing_person">Missing Person</option>
                <option value="water_supply">Water Supply</option>
                <option value="equipment_delivery">Equipment Delivery</option>
                <option value="fire_monitoring">Fire Monitoring</option>
                <option value="flood_inspection">Flood Inspection</option>
              </select>
            </label>
            <label>
              <span className="text-[10px] text-zinc-400">PRIORITY</span>
              <select value={priority} onChange={(e) => setPriority(e.target.value)} className="mt-0.5 w-full bg-[#0b0e14] border border-[#242c3a] px-2 py-1 text-zinc-100">
                <option value="critical">CRITICAL</option>
                <option value="high">HIGH</option>
                <option value="medium">MEDIUM</option>
                <option value="low">LOW</option>
              </select>
            </label>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <label><span className="text-[10px] text-zinc-400">PAYLOAD (kg)</span><input type="number" step="0.2" value={payloadKg} onChange={(e) => setPayloadKg(parseFloat(e.target.value))} className="mt-0.5 w-full bg-[#0b0e14] border border-[#242c3a] px-2 py-1 text-zinc-100" /></label>
            <label><span className="text-[10px] text-zinc-400">DEADLINE (s)</span><input type="number" value={deadline} onChange={(e) => setDeadline(parseInt(e.target.value))} className="mt-0.5 w-full bg-[#0b0e14] border border-[#242c3a] px-2 py-1 text-zinc-100" /></label>
            <label><span className="text-[10px] text-zinc-400">RISK (0-1)</span><input type="number" step="0.05" value={risk} onChange={(e) => setRisk(parseFloat(e.target.value))} className="mt-0.5 w-full bg-[#0b0e14] border border-[#242c3a] px-2 py-1 text-zinc-100" /></label>
          </div>
          <label className="block">
            <span className="text-[10px] text-zinc-400">OPTIONAL SPECIFIC DRONE</span>
            <select value={assignDroneId} onChange={(e) => setAssignDroneId(e.target.value)} className="mt-0.5 w-full bg-[#0b0e14] border border-[#242c3a] px-2 py-1 text-zinc-100">
              <option value="">Auto-Optimize Fleet</option>
              {(activeState?.drones || []).filter((d) => d.status !== "DESTROYED").map((d) => (
                <option key={d.id} value={d.id}>{d.id} ({d.drone_type}, {d.battery_percent.toFixed(0)}%)</option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex justify-end gap-2 pt-2 border-t border-[#242c3a]">
          <button onClick={() => setOpen(false)} className="px-3 py-1.5 bg-[#171d28] border border-[#2d3748] text-zinc-300">CANCEL</button>
          {assignDroneId && (
            <button onClick={() => submit(false)} className="px-3 py-1.5 bg-blue-700 text-white">ASSIGN {assignDroneId}</button>
          )}
          <button onClick={() => submit(true)} className="px-3 py-1.5 bg-zinc-100 text-zinc-950 font-semibold">CREATE & OPTIMIZE</button>
        </div>
      </div>
    </div>
  );
};
