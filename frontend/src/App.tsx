import React, { lazy, Suspense, useEffect } from "react";
import { useSimStore } from "./state/simulationStore";
import { api, createSimWebSocket } from "./api/client";

const WorldCommandApp = lazy(() => import("./apps/WorldCommandApp").then((m) => ({ default: m.WorldCommandApp })));
const OperationsCommandApp = lazy(() => import("./apps/OperationsCommandApp").then((m) => ({ default: m.OperationsCommandApp })));
const JarvisCommandApp = lazy(() => import("./apps/JarvisCommandApp").then((m) => ({ default: m.JarvisCommandApp })));
const DemoDirector = lazy(() => import("./apps/DemoDirector").then((m) => ({ default: m.DemoDirector })));
const CinematicDirector = lazy(() => import("./apps/CinematicDirector").then((m) => ({ default: m.CinematicDirector })));

export const App: React.FC = () => {
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setConnected = useSimStore((s) => s.setConnected);
  const applyUiCommand = useSimStore((s) => s.applyUiCommand);
  const urlMode = new URLSearchParams(window.location.search).get("mode");
  const mode = urlMode || (typeof __APP_MODE__ !== "undefined" ? __APP_MODE__ : "scene");

  useEffect(() => {
    if (mode === "jarvis") return;
    let disconnect = () => {};
    api.getScenario().then(applyServerPayload).catch(() => {});
    disconnect = createSimWebSocket(
      applyServerPayload,
      setConnected,
      (cmd) => applyUiCommand(cmd.action, cmd.payload)
    );
    return () => disconnect();
  }, [mode, applyServerPayload, setConnected, applyUiCommand]);

  return (
    <Suspense fallback={<div className="h-screen w-screen bg-[#090d14] text-zinc-100 grid place-items-center font-mono">Loading command center…</div>}>
      {mode === "jarvis" ? (
        <JarvisCommandApp />
      ) : mode === "control" || mode === "operations" ? (
        <OperationsCommandApp />
      ) : (
        <WorldCommandApp />
      )}
      {mode !== "jarvis" && <DemoDirector />}
      <CinematicDirector />
    </Suspense>
  );
};

export default App;
