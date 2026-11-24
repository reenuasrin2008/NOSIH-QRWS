import { create } from "zustand";
import {
  ActiveSimState, CameraMode, CityEnvironment, GhostRoute,
  PlacementMode, ServerPayload, StrategyMetrics, StrategyType
} from "../types/simulation";

interface SimStore {
  connected: boolean;
  fps: number;
  mode: "single" | "benchmark";
  benchmarkId: string | null;
  activeView: StrategyType;
  city: CityEnvironment | null;
  activeState: ActiveSimState | null;
  leaderboard: StrategyMetrics[];
  ghostRoutes: Record<string, GhostRoute[]>;

  selectedDroneId: string | null;
  selectedTaskId: string | null;
  cameraMode: CameraMode;
  cameraFocusPoint: [number, number, number] | null;

  placementMode: PlacementMode;
  pendingLocation: [number, number, number] | null;
  showAddTargetModal: boolean;
  showFailureModal: boolean;
  showReplayModal: boolean;
  showHistoryModal: boolean;
  showSettingsModal: boolean;
  showShortcutsModal: boolean;
  showBriefingModal: boolean;
  stageMode: boolean;
  criticalAlert: { title: string; detail: string; kind: 'failure' | 'replan' | 'info' } | null;
  showDemoBar: boolean;
  leaderboardSort: string;
  replay3DActive: boolean;
  replay3DRunId: string | null;
  replay3DFrames: Array<{ t: number; drones: Record<string, { pos: [number, number, number]; status: string; bat: number; hdg: number }>; tasks: Record<string, string> }>;
  replay3DIndex: number;

  showRoads: boolean;
  showBuildings: boolean;
  showHazards: boolean;
  showRoutes: boolean;
  showGhostRoutes: boolean;
  enableFire: boolean;
  enableFlood: boolean;
  enableWind: boolean;

  rightTab: "ops" | "leaderboard" | "quantum" | "drone" | "analytics";
  eventFilter: string;
  toast: string | null;

  applyServerPayload: (payload: ServerPayload) => void;
  setConnected: (c: boolean) => void;
  setFps: (fps: number) => void;
  selectDrone: (id: string | null) => void;
  selectTask: (id: string | null) => void;
  setCameraMode: (m: CameraMode) => void;
  setCameraFocusPoint: (pt: [number, number, number] | null) => void;
  setPlacementMode: (m: PlacementMode) => void;
  setPendingLocation: (pt: [number, number, number] | null) => void;
  setShowAddTargetModal: (v: boolean) => void;
  setShowFailureModal: (v: boolean) => void;
  setShowReplayModal: (v: boolean) => void;
  setShowHistoryModal: (v: boolean) => void;
  setShowSettingsModal: (v: boolean) => void;
  setShowShortcutsModal: (v: boolean) => void;
  setShowBriefingModal: (v: boolean) => void;
  setStageMode: (v: boolean) => void;
  setCriticalAlert: (a: SimStore['criticalAlert']) => void;
  applyUiCommand: (action: string, payload: Record<string, unknown>) => void;
  setShowDemoBar: (v: boolean) => void;
  setLeaderboardSort: (s: string) => void;
  startReplay3D: (runId: string, frames: SimStore['replay3DFrames']) => void;
  setReplay3DIndex: (idx: number) => void;
  stopReplay3D: () => void;
  toggleLayer: (key: "showRoads" | "showBuildings" | "showHazards" | "showRoutes" | "showGhostRoutes" | "enableFire" | "enableFlood" | "enableWind") => void;
  setRightTab: (tab: SimStore["rightTab"]) => void;
  setEventFilter: (f: string) => void;
  setToast: (msg: string | null) => void;
}

export const useSimStore = create<SimStore>((set) => ({
  connected: false,
  fps: 60,
  mode: "single",
  benchmarkId: null,
  activeView: "hybrid",
  city: null,
  activeState: null,
  leaderboard: [],
  ghostRoutes: {},

  selectedDroneId: null,
  selectedTaskId: null,
  cameraMode: "orbit",
  cameraFocusPoint: null,

  placementMode: "none",
  pendingLocation: null,
  showAddTargetModal: false,
  showFailureModal: false,
  showReplayModal: false,
  showHistoryModal: false,
  showSettingsModal: false,
  showShortcutsModal: false,
  showBriefingModal: false,
  stageMode: false,
  criticalAlert: null,
  showDemoBar: false,
  leaderboardSort: 'score',
  replay3DActive: false,
  replay3DRunId: null,
  replay3DFrames: [],
  replay3DIndex: 0,

  showRoads: true,
  showBuildings: true,
  showHazards: true,
  showRoutes: true,
  showGhostRoutes: false,
  enableFire: true,
  enableFlood: true,
  enableWind: true,

  rightTab: "leaderboard",
  eventFilter: "all",
  toast: null,

  applyServerPayload: (payload) =>
    set((prev) => ({
      mode: payload.mode,
      benchmarkId: payload.benchmark.benchmark_id,
      activeView: payload.benchmark.active_view,
      leaderboard: payload.benchmark.leaderboard,
      activeState: payload.benchmark.active_state,
      ghostRoutes: payload.benchmark.ghost_routes || {},
      city: payload.benchmark.active_state.city ? payload.benchmark.active_state.city : prev.city,
    })),

  setConnected: (connected) => set({ connected }),
  setFps: (fps) => set({ fps }),
  selectDrone: (selectedDroneId) =>
    set((s) => ({ selectedDroneId, selectedTaskId: null, rightTab: selectedDroneId ? "drone" : s.rightTab })),
  selectTask: (selectedTaskId) => set({ selectedTaskId }),
  setCameraMode: (cameraMode) => set({ cameraMode }),
  setCameraFocusPoint: (cameraFocusPoint) => set({ cameraFocusPoint }),
  setPlacementMode: (placementMode) => set({ placementMode, pendingLocation: null }),
  setPendingLocation: (pendingLocation) => set({ pendingLocation }),
  setShowAddTargetModal: (showAddTargetModal) => set({ showAddTargetModal }),
  setShowFailureModal: (showFailureModal) => set({ showFailureModal }),
  setShowReplayModal: (showReplayModal) => set({ showReplayModal }),
  setShowHistoryModal: (showHistoryModal) => set({ showHistoryModal }),
  setShowSettingsModal: (showSettingsModal) => set({ showSettingsModal }),
  setShowShortcutsModal: (showShortcutsModal) => set({ showShortcutsModal }),
  setShowBriefingModal: (showBriefingModal) => set({ showBriefingModal }),
  setStageMode: (stageMode) => set({ stageMode }),
  setCriticalAlert: (criticalAlert) => set({ criticalAlert }),
  applyUiCommand: (action, payload) =>
    set((s) => {
      if (action === "select_drone") return { selectedDroneId: (payload.id as string | null) ?? null, selectedTaskId: null };
      if (action === "select_task") return { selectedTaskId: (payload.id as string | null) ?? null };
      if (action === "focus_point") return { cameraFocusPoint: (payload.point as [number, number, number]) ?? null };
      if (action === "camera_mode") return { cameraMode: (payload.mode as CameraMode) || "orbit" };
      if (action === "placement_mode") return { placementMode: (payload.mode as PlacementMode) || "none", pendingLocation: null };
      if (action === "toggle_layer") {
        const key = payload.key as keyof SimStore;
        if (typeof s[key] === "boolean") return { [key]: !s[key] } as Partial<SimStore>;
      }
      if (action === "set_layer") {
        const key = payload.key as keyof SimStore;
        if (typeof s[key] === "boolean") return { [key]: Boolean(payload.value) } as Partial<SimStore>;
      }
      if (action === "start_replay") {
        return {
          replay3DActive: true,
          replay3DRunId: (payload.runId as string) || "REPLAY",
          replay3DFrames: (payload.frames as SimStore["replay3DFrames"]) || [],
          replay3DIndex: 0,
        };
      }
      if (action === "stop_replay") return { replay3DActive: false, replay3DRunId: null, replay3DFrames: [], replay3DIndex: 0 };
      if (action === "critical_alert") return { criticalAlert: (payload.alert as SimStore["criticalAlert"]) ?? null };
      return {};
    }),
  setShowDemoBar: (showDemoBar) => set({ showDemoBar }),
  setLeaderboardSort: (leaderboardSort) => set({ leaderboardSort }),
  startReplay3D: (replay3DRunId, replay3DFrames) => set({ replay3DActive: true, replay3DRunId, replay3DFrames, replay3DIndex: 0 }),
  setReplay3DIndex: (replay3DIndex) => set({ replay3DIndex }),
  stopReplay3D: () => set({ replay3DActive: false, replay3DRunId: null, replay3DFrames: [], replay3DIndex: 0 }),
  toggleLayer: (key) => set((s) => ({ [key]: !s[key] } as Partial<SimStore>)),
  setRightTab: (rightTab) => set({ rightTab }),
  setEventFilter: (eventFilter) => set({ eventFilter }),
  setToast: (toast) => set({ toast }),
}));
