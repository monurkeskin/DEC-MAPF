import type { WorkspaceModel } from "../hooks/useWorkspace";
import { ReplayViewport } from "./ReplayViewport";
import { ComparisonPanel } from "./ComparisonPanel";
import { BatchControls } from "./BatchControls";
import { ArtifactPanel } from "./ArtifactPanel";
import { InspectorPanel } from "./InspectorPanel";

export function WorkspacePanels({ model }: { model: WorkspaceModel }) {
  const { screen, draft, runtime, playback, replay, layerState, decision } =
    model;
  const { scenario, run, options, editing, editCell } = draft;
  const { agent, setAgent, setPlaying, seek, tick } = playback;
  const { setNotice, reportError } = runtime;
  const inspect = screen === "Configure" || screen === "Inspect";
  return (
    <>
      <main id="main" className="viewport-area" tabIndex={-1}>
        {inspect && (
          <ReplayViewport
            {...{
              scenario,
              run,
              replay,
              agent,
              layerState,
              decision,
              playback,
            }}
            fovSize={options.fov_size}
            onSelectAgent={setAgent}
            onEditCell={
              editing && screen === "Configure" ? editCell : undefined
            }
          />
        )}
        {screen === "Compare" && (
          <section className="content-scroll">
            <ComparisonPanel
              model={model.comparison}
              runs={runtime.library.items}
              {...playback}
            />
            <BatchControls
              state={model.batchState}
              caps={runtime.caps}
              input={model.submission.input}
              refresh={runtime.refresh}
              {...{ reportError, setNotice }}
            />
          </section>
        )}
        {screen === "Export" && (
          <ArtifactPanel
            {...{ run, tick, setNotice, reportError }}
            importReplay={model.actions.importReplay}
          />
        )}
      </main>
      {inspect && (
        <InspectorPanel
          runResult={run?.result || null}
          currentFrame={replay.frame}
          selectedAgent={agent}
          onSelectAgent={setAgent}
          onSeek={(t) => {
            setPlaying(false);
            seek(t);
          }}
        />
      )}
    </>
  );
}
