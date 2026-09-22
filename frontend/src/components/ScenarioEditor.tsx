import { useState } from "react";
import { post } from "../api/client";
import type { ScenarioDetail, ScenarioInput } from "../api/types";
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
  const [jsonText, setJsonText] = useState(""),
    [mapText, setMapText] = useState(""),
    [scenText, setScenText] = useState(""),
    [count, setCount] = useState(4),
    [validation, setValidation] = useState("Draft not checked");
  function input(): ScenarioInput {
    const s = p.scenario;
    return {
      grid_width: s.grid_width,
      grid_height: s.grid_height,
      obstacles: s.obstacles,
      starts: s.starts,
      goals: s.goals,
      setting: s.setting,
      name: s.name,
    };
  }
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
  const move = (
    agent: string,
    kind: "starts" | "goals",
    axis: number,
    value: number,
  ) => {
    const positions = { ...p.scenario[kind] },
      position = [...positions[agent]] as [number, number];
    position[axis] = value;
    positions[agent] = position;
    p.onChange({ ...p.scenario, [kind]: positions });
    setValidation("Draft changed; validate before running");
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
      <div className="table-scroll">
        <table>
          <caption>Agent coordinate editor</caption>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Start x/y</th>
              <th>Goal x/y</th>
            </tr>
          </thead>
          <tbody>
            {Object.keys(p.scenario.starts).map((id) => (
              <tr key={id}>
                <th>{id}</th>
                {(["starts", "goals"] as const).map((kind) => (
                  <td key={kind}>
                    {[0, 1].map((axis) => (
                      <input
                        key={axis}
                        className="coord-input"
                        aria-label={`${id} ${kind} ${axis === 0 ? "x" : "y"}`}
                        type="number"
                        value={p.scenario[kind][id][axis]}
                        onChange={(e) =>
                          move(id, kind, axis, Number(e.target.value))
                        }
                      />
                    ))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button onClick={() => check()}>Validate draft</button>
      <button onClick={() => check(true)}>Save new scenario</button>
      <p role="status">{validation}</p>
      <details>
        <summary>JSON import / keyboard obstacle editing</summary>
        <p>
          Import a scenario with dimensions, obstacles, starts, goals and
          setting. Coordinates use [x, y].
        </p>
        <textarea
          aria-label="Scenario JSON"
          value={jsonText}
          onChange={(e) => setJsonText(e.target.value)}
          placeholder="Paste scenario JSON"
        />
        <div className="button-row">
          <button onClick={() => setJsonText(JSON.stringify(input(), null, 2))}>
            Copy draft into editor
          </button>
          <button
            onClick={() => {
              try {
                const s = JSON.parse(jsonText);
                if (!s.starts || !s.goals || !Array.isArray(s.obstacles))
                  throw new Error("Missing scenario fields");
                p.onChange({ ...s, name: s.name || "Imported draft" });
                setValidation("Imported draft; validation required");
              } catch (e) {
                p.onError(e);
              }
            }}
          >
            Load JSON draft
          </button>
        </div>
      </details>
      <details>
        <summary>MovingAI map and scenario import</summary>
        <label>
          Map text
          <textarea
            value={mapText}
            onChange={(e) => setMapText(e.target.value)}
          />
        </label>
        <label>
          Scenario text
          <textarea
            value={scenText}
            onChange={(e) => setScenText(e.target.value)}
          />
        </label>
        <label>
          First N agents
          <input
            type="number"
            min="1"
            max="100"
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
          />
        </label>
        <button
          onClick={async () => {
            try {
              p.onSaved(
                await post<ScenarioDetail>("/scenarios/import-movingai", {
                  map_text: mapText,
                  scenario_text: scenText,
                  agent_count: count,
                  setting: p.scenario.setting,
                  name: "MovingAI import",
                }),
              );
            } catch (e) {
              p.onError(e);
            }
          }}
        >
          Import and save MovingAI
        </button>
      </details>
    </section>
  );
}
