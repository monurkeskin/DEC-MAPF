import { useCallback, useRef, useState } from "react";
import { fetchRunDetails, fetchScenario } from "../api/client";
import { STARTER_INPUTS } from "../api/presets.generated";
import type {
  JobSubmissionRequest,
  RunDetail,
  ScenarioDetail,
} from "../api/types";
import { restoreJobOptions } from "../study";

type Callbacks = {
  onRunLoaded: (run: RunDetail) => void;
  onScenarioLoaded: () => void;
  onDraftChanged: () => void;
};

export function useScenarioDraft({
  onRunLoaded,
  onScenarioLoaded,
  onDraftChanged,
}: Callbacks) {
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [scenarioId, setScenarioId] = useState("crossing-2a");
  const [options, setOptions] = useState<JobSubmissionRequest>(STARTER_INPUTS);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [history, setHistory] = useState<ScenarioDetail[]>([]);
  const [future, setFuture] = useState<ScenarioDetail[]>([]);
  const [editing, setEditing] = useState(false);
  const loadedRun = useRef("");
  const selectionRevision = useRef(0);
  const selectionRequest = useRef<AbortController | null>(null);
  const loadRun = useCallback(
    async (id: string, isCurrent: () => boolean = () => true) => {
      const revision = ++selectionRevision.current;
      selectionRequest.current?.abort();
      const controller = new AbortController();
      selectionRequest.current = controller;
      let data: RunDetail;
      try {
        data = await fetchRunDetails(id, controller.signal);
      } catch (e) {
        if (controller.signal.aborted) return;
        throw e;
      }
      if (revision !== selectionRevision.current || !isCurrent()) return;
      loadedRun.current = id;
      setRun(data);
      setScenario(data.metadata.instance);
      setOptions(restoreJobOptions(data.metadata.effective_config));
      setScenarioId("");
      setEditing(false);
      onRunLoaded(data);
    },
    [onRunLoaded],
  );
  const loadScenario = useCallback(
    async (id: string) => {
      const revision = ++selectionRevision.current;
      selectionRequest.current?.abort();
      const data = await fetchScenario(id);
      if (revision !== selectionRevision.current) return;
      setScenario(data);
      setScenarioId(id);
      setOptions((o) => ({ ...o, setting: data.setting }));
      setRun(null);
      loadedRun.current = "";
      onScenarioLoaded();
      setHistory([]);
      setFuture([]);
    },
    [onScenarioLoaded],
  );
  const changeDraft = (next: ScenarioDetail) => {
    selectionRevision.current++;
    if (scenario) setHistory((h) => [...h.slice(-49), scenario]);
    setFuture([]);
    setScenario(next);
    setRun(null);
    loadedRun.current = "";
    setScenarioId("");
    onDraftChanged();
  };
  const undo = () => {
    if (!history.length || !scenario) return;
    selectionRevision.current++;
    setFuture((f) => [scenario, ...f]);
    setScenario(history[history.length - 1]);
    setHistory((h) => h.slice(0, -1));
    setRun(null);
  };
  const redo = () => {
    if (!future.length || !scenario) return;
    selectionRevision.current++;
    setHistory((h) => [...h, scenario]);
    setScenario(future[0]);
    setFuture((f) => f.slice(1));
    setRun(null);
  };
  const editCell = (x: number, y: number) => {
    if (!scenario) return;
    const exists = scenario.obstacles.some((p) => p[0] === x && p[1] === y);
    changeDraft({
      ...scenario,
      obstacles: exists
        ? scenario.obstacles.filter((p) => p[0] !== x || p[1] !== y)
        : [...scenario.obstacles, [x, y]],
    });
  };
  const clearRun = () => {
    setRun(null);
    loadedRun.current = "";
  };
  return {
    scenario,
    setScenario,
    scenarioId,
    setScenarioId,
    options,
    setOptions,
    run,
    clearRun,
    loadedRun,
    loadRun,
    loadScenario,
    changeDraft,
    canUndo: !!history.length,
    canRedo: !!future.length,
    undo,
    redo,
    editCell,
    editing,
    setEditing,
  };
}
