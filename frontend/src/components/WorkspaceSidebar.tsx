import type { WorkspaceModel } from "../hooks/useWorkspace";
import { ScenarioConfiguration } from "./ScenarioConfiguration";
import { RunLibraryPanel } from "./RunLibraryPanel";
import { JobJournal } from "./JobJournal";

export function WorkspaceSidebar({ model }: { model: WorkspaceModel }) {
  const { screen, draft, runtime, actions, submission, plan } = model;
  const {
    scenario,
    options,
    setOptions,
    scenarioId,
    loadScenario,
    changeDraft,
  } = draft;
  const { caps, scenarios, reportError } = runtime;
  const { input, busy, preview, start } = submission;
  return (
    <aside className="sidebar-panel" aria-label="Experiment controls">
      <ScenarioConfiguration
        configure={screen === "Configure"}
        draft={draft}
        onSave={actions.onSave}
        onCancel={actions.onCancel}
        controls={{
          portableInput: scenario ? input() : null,
          busy,
          options,
          setOptions,
          scenarioId,
          loadScenario,
          scenarios,
          scenario,
          changeDraft,
          caps,
          plan,
          preview,
          start,
          reportError,
        }}
      />
      <RunLibraryPanel
        library={runtime.library}
        open={screen !== "Configure"}
        reportError={reportError}
        select={actions.selectRun}
      />
      <JobJournal
        jobs={runtime.jobs}
        setJobId={runtime.setJobId}
        refresh={runtime.refresh}
        reportError={reportError}
      />
    </aside>
  );
}
