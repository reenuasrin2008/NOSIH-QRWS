import React, { useEffect } from "react";
import { SceneVisualApp } from "./apps/SceneVisualApp";
import { ControlPanelApp } from "./apps/ControlPanelApp";
import { AgentConsoleApp } from "./apps/AgentConsoleApp";
import { useSimStore } from "./state/simulationStore";
import { api, createSimWebSocket } from "./api/client";

export const App: React.FC = () => {
  const applyServerPayload = useSimStore((s) => s.applyServerPayload);
  const setConnected = useSimStore((s) => s.setConnected);
  const applyUiCommand = useSimStore((s) => s.applyUiCommand);

  useEffect(() => {
    api.getScenario().then(applyServerPayload).catch(() => {});
    const disconnect = createSimWebSocket(
      applyServerPayload,
      setConnected,
      (cmd) => applyUiCommand(cmd.action, cmd.payload)
    );
    return disconnect;
  }, [applyServerPayload, setConnected, applyUiCommand]);

  const urlMode = new URLSearchParams(window.location.search).get("mode");
  const mode = urlMode || (typeof __APP_MODE__ !== "undefined" ? __APP_MODE__ : "scene");

  if (mode === "control") return <ControlPanelApp />;
  if (mode === "jarvis" || mode === "agent") return <AgentConsoleApp />;
  return <SceneVisualApp />;
};

export default App;
