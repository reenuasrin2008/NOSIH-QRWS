import { useEffect } from "react";
import { useSimStore } from "../state/simulationStore";
import { api } from "../api/client";
import { StrategyType } from "../types/simulation";

export function useKeyboardShortcuts() {
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setCameraMode = useSimStore((s) => s.setCameraMode);
  const setToast = useSimStore((s) => s.setToast);

  useEffect(() => {
    const onKeyDown = async (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      const store = useSimStore.getState();

      if (e.key === "Escape") {
        if (store.placementMode !== "none") {
          store.setPlacementMode("none");
          setToast("Placement cancelled.");
        } else {
          store.setShowAddTargetModal(false);
          store.setShowFailureModal(false);
          store.setShowSettingsModal(false);
          store.setShowHistoryModal(false);
          store.setShowReplayModal(false);
          store.setShowShortcutsModal(false);
          store.setShowBriefingModal(false);
          store.selectDrone(null);
        }
        return;
      }

      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || target?.isContentEditable) return;

      if (e.key === "p" || e.key === "P") {
        store.setStageMode(!store.stageMode);
        setToast(store.stageMode ? "Exited Presentation Stage Mode" : "Presentation Stage Mode active [P]");
        return;
      }

      if (e.key === "?") {
        store.setShowShortcutsModal(!store.showShortcutsModal);
        return;
      }

      if (e.key === "[" || e.key === "]") {
        const drones = store.activeState?.drones || [];
        if (!drones.length) return;
        const curIdx = drones.findIndex((d) => d.id === store.selectedDroneId);
        const dir = e.key === "]" ? 1 : -1;
        const next = drones[(curIdx + dir + drones.length) % drones.length];
        store.selectDrone(next.id);
        store.setCameraFocusPoint(next.position);
        return;
      }

      if (e.code === "Space") {
        if (target?.closest("button, a, [role='button'], [contenteditable='true']")) return;
        e.preventDefault();
        const st = store.activeState?.status;
        if (st === "RUNNING") {
          applyServerPayload(await api.pauseSim());
          setToast("Simulation paused [Space]");
        } else {
          applyServerPayload(await api.resumeSim());
          setToast("Simulation resumed [Space]");
        }
      } else if (e.key === "r" || e.key === "R") {
        setCameraMode("orbit");
      } else if (e.key === "f" || e.key === "F") {
        setCameraMode("follow");
      } else if (["1", "2", "3", "4"].includes(e.key)) {
        const map: Record<string, StrategyType> = { "1": "greedy", "2": "classical", "3": "quantum", "4": "hybrid" };
        const strat = map[e.key];
        applyServerPayload(await api.switchView(strat));
        setToast(`Switched viewport to ${strat.toUpperCase()} [${e.key}]`);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [applyServerPayload, setCameraMode, setToast]);
}
