import { useCallback, useState } from "react";
import { useJobMonitor } from "./useJobMonitor";
import { useRunLibrary } from "./useRunLibrary";
import { useWorkspaceCatalog } from "./useWorkspaceCatalog";
import type { useScenarioDraft } from "./useScenarioDraft";

export function useWorkspaceRuntime(
  draft: ReturnType<typeof useScenarioDraft>,
) {
  const [initialLink] = useState(() => new URLSearchParams(location.search));
  const [initialJobId] = useState(
    initialLink.has("run") ? "" : localStorage.getItem("mapf-job") || "",
  );
  const [jobId, setJobId] = useState(initialJobId);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const reportError = useCallback((e: unknown) => {
    setError(e instanceof Error ? e.message : String(e));
    setLoading(false);
  }, []);
  const library = useRunLibrary(reportError);
  const onLoaded = useCallback(() => setLoading(false), []);
  const { loadRun, loadScenario, loadedRun } = draft;
  const catalog = useWorkspaceCatalog({
    initialLink,
    initialJobId,
    loadRun,
    loadScenario,
    refreshLibrary: library.refresh,
    reportError,
    onLoaded,
  });
  const monitor = useJobMonitor({
    jobId,
    loadedRun,
    loadRun,
    refresh: catalog.refresh,
    reportError,
    setNotice,
    setError,
  });
  function detachJob() {
    setJobId("");
    monitor.setJob(null);
    localStorage.removeItem("mapf-job");
  }
  return {
    ...catalog,
    ...monitor,
    library,
    loading,
    error,
    notice,
    setError,
    setNotice,
    reportError,
    setJobId,
    detachJob,
  };
}
