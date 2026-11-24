import React from "react";
import { X, Keyboard } from "lucide-react";
import { useSimStore } from "../../state/simulationStore";

const SHORTCUTS = [
  ["W / A / S / D  or  Arrows", "Pan 3D camera across the 4x4 km metropolis"],
  ["Q / E", "Lower / Raise camera altitude"],
  ["Shift (hold)", "2.4x camera pan & altitude boost"],
  ["Space", "Pause / Resume simulation"],
  ["1 / 2 / 3 / 4", "Switch Greedy / Classical / Quantum / Hybrid view"],
  ["[  /  ]", "Select previous / next drone and focus camera"],
  ["F", "Lock Follow Camera onto selected drone"],
  ["R", "Reset camera to Orbit overview"],
  ["Esc", "Cancel placement mode or close active dialog"],
  ["P", "Toggle full-bleed Presentation Stage Mode"],
  ["?", "Toggle this keyboard controls reference"],
];

export const ShortcutsModal: React.FC = () => {
  const open = useSimStore((s) => s.showShortcutsModal);
  const setOpen = useSimStore((s) => s.setShowShortcutsModal);
  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/75 flex items-center justify-center z-50 font-mono text-xs">
      <div className="w-[480px] bg-[#11161f] border border-[#2d3748] p-4 space-y-3">
        <div className="flex justify-between items-center border-b border-[#242c3a] pb-2">
          <div className="flex items-center gap-2 font-semibold text-zinc-100">
            <Keyboard className="w-4 h-4 text-zinc-400" /> OPERATOR CONTROLS & SHORTCUTS
          </div>
          <button onClick={() => setOpen(false)} className="text-zinc-400 hover:text-zinc-100"><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-1.5 text-[11px]">
          {SHORTCUTS.map(([k, desc]) => (
            <div key={k} className="flex items-center justify-between py-1 border-b border-[#1c2331] last:border-0">
              <span className="px-1.5 py-0.5 bg-[#0b0e14] border border-[#2d3748] text-zinc-100">{k}</span>
              <span className="text-zinc-400 text-right">{desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
