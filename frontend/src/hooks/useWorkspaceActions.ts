import { cancelJob, fetchScenarios, post } from "../api/client";
import type { ScenarioDetail } from "../api/types";
import { scenarioRequest } from "../study";
import { terminal } from "./useJobMonitor";
import { useSimulationSubmission } from "./useSimulationSubmission";
import type { useWorkspaceDraft } from "./useWorkspaceDraft";
import type { useWorkspaceRuntime } from "./useWorkspaceRuntime";

type State = ReturnType<typeof useWorkspaceDraft>;
type Runtime = ReturnType<typeof useWorkspaceRuntime>;

export function useWorkspaceSubmission(
  state: State,
  runtime: Runtime,
  reset: () => void,
) {
  const { draft, plan, onPreview } = state;
  function input() {
    if (!draft.scenario) throw new Error("Load a scenario first");
    return scenarioRequest(draft.options, draft.scenario);
  }
  const submission = useSimulationSubmission({
    plan,
    input,
    onPreview,
    reportError: runtime.reportError,
    setError: runtime.setError,
    onStarted: async (next) => {
      runtime.setJob(next);
      runtime.setJobId(next.job_id);
      draft.clearRun();
      reset();
      await runtime.refresh();
    },
  });
  const busy =
    submission.submitting ||
    (!!runtime.job && !terminal.has(runtime.job.state));
  return { ...submission, input, busy };
}

export function workspaceActions(state: State, runtime: Runtime) {
  const { draft } = state;
  const { reportError, refresh, setNotice } = runtime;
  async function saved(s: ScenarioDetail) {
    draft.setScenario(s);
    draft.setScenarioId(s.scenario_id || "");
    runtime.setScenarios(await fetchScenarios());
    setNotice("Saved a new immutable scenario snapshot");
  }
  async function importReplay(file: File) {
    try {
      if (file.size > 16 * 1024 * 1024)
        throw new Error("Import exceeds 16 MiB");
      const r = await post<{ run_id: string }>(
        "/runs/import",
        JSON.parse(await file.text()),
      );
      runtime.detachJob();
      await draft.loadRun(r.run_id);
      await refresh();
      setNotice("Bundle integrity and trajectory receipt verified");
    } catch (e) {
      reportError(e);
    }
  }
  function selectRun(id: string) {
    runtime.detachJob();
    draft.loadRun(id).catch(reportError);
  }
  const onSave = (s: ScenarioDetail) => {
    saved(s).catch(reportError);
  };
  const { job } = runtime;
  const onCancel = job
    ? () => {
        cancelJob(job.job_id).then(refresh).catch(reportError);
      }
    : undefined;
  return { importReplay, selectRun, onSave, onCancel };
}
