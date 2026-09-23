import { useCallback, useEffect, useState } from "react";
import { fetchCapabilities, fetchScenarios, request } from "../api/client";
import type {
  JobStatusResponse,
  ScenarioSummary,
  SolverCapability,
} from "../api/types";

type Options = {
  initialLink: URLSearchParams;
  initialJobId: string;
  loadRun: (id: string, current?: () => boolean) => Promise<void>;
  loadScenario: (id: string) => Promise<void>;
  refreshLibrary: () => Promise<void>;
  reportError: (error: unknown) => void;
  onLoaded: () => void;
};
export function useWorkspaceCatalog({
  initialLink,
  initialJobId,
  loadRun,
  loadScenario,
  refreshLibrary,
  reportError,
  onLoaded,
}: Options) {
  const [caps, setCaps] = useState<SolverCapability[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [jobs, setJobs] = useState<JobStatusResponse[]>([]);
  const refresh = useCallback(async () => {
    const [, js] = await Promise.all([
      refreshLibrary(),
      request<JobStatusResponse[]>("/jobs"),
    ]);
    setJobs(js);
  }, [refreshLibrary]);
  useEffect(() => {
    let alive = true;
    Promise.all([
      fetchCapabilities(),
      fetchScenarios(),
      request<JobStatusResponse[]>("/jobs"),
    ])
      .then(async ([c, s, js]) => {
        if (!alive) return;
        setCaps(c);
        setScenarios(s);
        setJobs(js);
        const linkedRun = initialLink.get("run");
        if (linkedRun) await loadRun(linkedRun, () => alive);
        else if (!initialJobId) await loadScenario("crossing-2a");
        onLoaded();
      })
      .catch(reportError);
    return () => {
      alive = false;
    };
  }, [initialJobId, initialLink, loadRun, loadScenario, reportError, onLoaded]);
  return { caps, scenarios, setScenarios, jobs, refresh };
}
