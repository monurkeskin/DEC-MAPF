import { useWorkspace } from "./hooks/useWorkspace";
import { WorkspaceHeader } from "./components/WorkspaceHeader";
import { WorkspaceStatus } from "./components/WorkspaceStatus";
import { WorkspaceSidebar } from "./components/WorkspaceSidebar";
import { WorkspacePanels } from "./components/WorkspacePanels";

export default function App() {
  const model = useWorkspace();
  const { screen, theme, setTheme, setScreen, playback, runtime, draft } =
    model;
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to workspace
      </a>
      <WorkspaceHeader
        {...{ screen, theme, setTheme }}
        onNavigate={(next) => {
          setScreen(next);
          playback.reset();
        }}
      />
      <WorkspaceStatus {...runtime} run={draft.run} />
      {runtime.loading && (
        <p role="status" className="loading">
          Loading local workspace…
        </p>
      )}
      <div className="workspace-container">
        <WorkspaceSidebar model={model} />
        <WorkspacePanels model={model} />
      </div>
    </>
  );
}
