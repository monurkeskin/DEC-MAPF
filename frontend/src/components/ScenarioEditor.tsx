import { useState } from "react";
import { post } from "../api/client";
import type { ScenarioDetail } from "../api/types";
import { scenarioDraftInput } from "../scenarioDraft";
import { ScenarioJsonEditor } from "./ScenarioJsonEditor";
import { MovingAIImport } from "./MovingAIImport";
import { AgentCoordinateEditor } from "./AgentCoordinateEditor";
interface Props {
  scenario: ScenarioDetail;
  onChange: (s: ScenarioDetail) => void;
  onSaved: (s: ScenarioDetail) => void;
  onError: (e: unknown) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
}
export function ScenarioEditor(p: Props) {
  const [validation, setValidation] = useState("Draft not checked");
  const input = () => scenarioDraftInput(p.scenario);
  const check = async (save = false) => {
    try {
      const v = await post<{ is_valid: boolean; errors: string[] }>(
        "/scenarios/validate",
        input(),
      );
      setValidation(v.is_valid ? "Scenario valid" : v.errors.join("; "));
      if (save && v.is_valid) {
        const s = await post<ScenarioDetail>("/scenarios", input());
        p.onSaved(s);
      }
    } catch (e) {
      p.onError(e);
    }
  };
  return (
    <section aria-label="Scenario editor">
      <h3>Edit a new draft</h3>
      <p className="muted">
        Obstacle mode edits cells on the grid. Existing run scenarios stay
        immutable.
      </p>
      <div className="button-row">
        <button onClick={p.undo} disabled={!p.canUndo}>
          Undo
        </button>
        <button onClick={p.redo} disabled={!p.canRedo}>
          Redo
        </button>
      </div>
      <label>
        Scenario name
        <input
          value={p.scenario.name}
          onChange={(e) => p.onChange({ ...p.scenario, name: e.target.value })}
        />
      </label>
      <div className="two-cols">
        {(["grid_width", "grid_height"] as const).map((k) => (
          <label key={k}>
            {k === "grid_width" ? "Width" : "Height"}
            <input
              type="number"
              min="1"
              max="64"
              value={p.scenario[k]}
              onChange={(e) =>
                p.onChange({ ...p.scenario, [k]: Number(e.target.value) })
              }
            />
          </label>
        ))}
      </div>
      <AgentCoordinateEditor
        scenario={p.scenario}
        onChange={(next) => {
          p.onChange(next);
          setValidation("Draft changed; validate before running");
        }}
      />
      <button onClick={() => check()}>Validate draft</button>
      <button onClick={() => check(true)}>Save new scenario</button>
      <p role="status">{validation}</p>
      <ScenarioJsonEditor
        scenario={p.scenario}
        onChange={p.onChange}
        onStatus={setValidation}
        onError={p.onError}
      />
      <MovingAIImport
        setting={p.scenario.setting}
        onSaved={p.onSaved}
        onError={p.onError}
      />
    </section>
  );
}
