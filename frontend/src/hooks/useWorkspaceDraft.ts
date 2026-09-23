import { useCallback, useEffect, useState } from "react";
import type { Plan, RunDetail } from "../api/types";
import type { Workflow } from "../components/WorkspaceHeader";
import { restoredTick } from "../replayLocation";
import { useScenarioDraft } from "./useScenarioDraft";
import type { useWorkspacePlayback } from "./useWorkspacePlayback";

export function useWorkspaceDraft(
  playback: ReturnType<typeof useWorkspacePlayback>,
) {
  const [screen, setScreen] = useState<Workflow>("Configure");
  const [theme, setTheme] = useState(
    localStorage.getItem("mapf-theme") || "dark",
  );
  const [planDraft, setPlan] = useState<Plan | null>(null);
  const [planFor, setPlanFor] = useState("");
  const { reset, setAgent, setPlaying, setTick } = playback;
  const onScenarioLoaded = useCallback(() => {
    reset();
    setAgent(null);
    setPlan(null);
  }, [reset, setAgent]);
  const onRunLoaded = useCallback(
    (data: RunDetail) => {
      setAgent(null);
      setPlaying(false);
      setPlan(null);
      setTick(restoredTick(data));
      setScreen("Inspect");
    },
    [setAgent, setPlaying, setTick],
  );
  const draft = useScenarioDraft({
    onRunLoaded,
    onScenarioLoaded,
    onDraftChanged: reset,
  });
  const inputSignature = JSON.stringify([draft.options, draft.scenario]);
  const plan = planFor === inputSignature ? planDraft : null;
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("mapf-theme", theme);
  }, [theme]);
  function onPreview(next: Plan) {
    setPlan(next);
    setPlanFor(inputSignature);
  }
  return { draft, plan, onPreview, screen, setScreen, theme, setTheme };
}
