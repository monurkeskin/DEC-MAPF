import type { ComponentProps } from "react";
import type { useScenarioDraft } from "../hooks/useScenarioDraft";
import type { ScenarioDetail } from "../api/types";
import { SimulationControls } from "./SimulationControls";
import { ScenarioEditor } from "./ScenarioEditor";
export function ScenarioConfiguration({
  configure,
  controls,
  draft,
  onSave,
  onCancel,
}: {
  configure: boolean;
  controls: ComponentProps<typeof SimulationControls>;
  draft: ReturnType<typeof useScenarioDraft>;
  onSave: (scenario: ScenarioDetail) => void;
  onCancel?: () => void;
}) {
  const { scenario, editing, setEditing, changeDraft } = draft;
  const { busy } = controls;
  return (
    <>
      <h2>{configure ? "Configure experiment" : "Workspace library"}</h2>
      <p className="hint">
        Interactive starter v1 · edit controls to customize. Saved runs restore
        their recorded settings.
      </p>
      {configure && !draft.run && (
        <section aria-label="First session guide" className="plan">
          <h3>Your first checked replay</h3>
          <ol>
            <li>Keep the two-agent crossing, or select the four-agent grid.</li>
            <li>Preview the inputs and problem assumptions, then run.</li>
            <li>
              Check validation, step through ticks in Inspect, then Export.
            </li>
          </ol>
          <p className="hint">
            This starter is a teaching fixture. Its short process guard and
            search limits are not the article benchmark configuration.
          </p>
        </section>
      )}
      <SimulationControls {...controls} />
      {busy && onCancel && (
        <button className="danger" onClick={onCancel}>
          Cancel computation
        </button>
      )}
      {configure && scenario && (
        <fieldset disabled={busy}>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={editing}
              onChange={(e) => setEditing(e.target.checked)}
            />
            Edit obstacles on grid
          </label>
          <ScenarioEditor
            scenario={scenario}
            onChange={changeDraft}
            onSaved={(s) => {
              onSave(s);
            }}
            onError={controls.reportError}
            canUndo={draft.canUndo}
            canRedo={draft.canRedo}
            undo={draft.undo}
            redo={draft.redo}
          />
        </fieldset>
      )}
    </>
  );
}
