import { SolverParameter } from "./SolverParameter";
import { SimulationPlanPreview } from "./SimulationPlanPreview";
import { useState, type Dispatch, type SetStateAction } from "react";
import type {
  JobSubmissionRequest,
  ScenarioDetail,
  ScenarioSummary,
  SolverCapability,
  Plan,
} from "../api/types";

type Props = {
  busy: boolean;
  portableInput: JobSubmissionRequest | null;
  options: JobSubmissionRequest;
  setOptions: Dispatch<SetStateAction<JobSubmissionRequest>>;
  scenarioId: string;
  loadScenario: (id: string) => Promise<void>;
  scenarios: ScenarioSummary[];
  scenario: ScenarioDetail | null;
  changeDraft: (scenario: ScenarioDetail) => void;
  caps: SolverCapability[];
  plan: Plan | null;
  preview: () => Promise<void>;
  start: () => Promise<void>;
  reportError: (error: unknown) => void;
};
export function SimulationControls({
  busy,
  portableInput,
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
}: Props) {
  const selectedCap = caps.find((c) => c.solver_id === options.solver_id);
  const [advanced, setAdvanced] = useState(
    localStorage.getItem("mapf-advanced") === "true",
  );
  const basic = new Set([
    "fov_size",
    "commitment_type",
    "initial_tokens",
    "timeout_sec",
  ]);
  return (
    <fieldset disabled={busy}>
      <label>
        Scenario
        <select
          value={scenarioId}
          onChange={(e) => loadScenario(e.target.value).catch(reportError)}
        >
          <option value="" disabled>
            Draft / saved run scenario
          </option>
          {scenarios.map((s) => (
            <option key={s.scenario_id} value={s.scenario_id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>
      {scenario && (
        <>
          <label>
            Setting
            <select
              value={scenario.setting}
              onChange={(e) => {
                changeDraft({
                  ...scenario,
                  setting: e.target.value as ScenarioDetail["setting"],
                });
                setOptions((o) => ({
                  ...o,
                  setting: e.target.value as JobSubmissionRequest["setting"],
                }));
              }}
            >
              <option value="SETTING_1">1 · Stay at goal / no wait</option>
              <option value="SETTING_2">2 · Stay at goal / wait</option>
              <option value="SETTING_3">3 · Disappear / no wait</option>
              <option value="SETTING_4">4 · Disappear / wait</option>
            </select>
          </label>
          <p className="muted">
            {scenario.grid_width} × {scenario.grid_height} ·{" "}
            {Object.keys(scenario.starts).length} agents · t=0 is the initial
            state
          </p>
        </>
      )}
      <label>
        Solver
        <select
          value={options.solver_id}
          onChange={(e) =>
            setOptions((o) => ({ ...o, solver_id: e.target.value }))
          }
        >
          {caps.map((c) => (
            <option key={c.solver_id} value={c.solver_id}>
              {c.display_name}
            </option>
          ))}
        </select>
      </label>
      <p className="muted">{selectedCap?.description}</p>
      {selectedCap?.parameters
        .filter((p) => basic.has(p.name))
        .map((p) => (
          <SolverParameter key={p.name} {...{ p, options, setOptions }} />
        ))}
      <details
        open={advanced}
        onToggle={(event) => {
          const open = event.currentTarget.open;
          setAdvanced(open);
          localStorage.setItem("mapf-advanced", String(open));
        }}
      >
        <summary>Advanced solver parameters</summary>
        <p className="hint">
          Hidden values stay active. Preview lists every effective value and
          inactive control.
        </p>
        {selectedCap?.parameters
          .filter((p) => !basic.has(p.name))
          .map((p) => (
            <SolverParameter key={p.name} {...{ p, options, setOptions }} />
          ))}
      </details>
      <div className="two-cols">
        <label>
          Max steps
          <input
            type="number"
            min="1"
            max="500"
            value={options.max_steps}
            onChange={(e) =>
              setOptions((o) => ({
                ...o,
                max_steps: Number(e.target.value),
              }))
            }
          />
        </label>
      </div>
      <label>
        Random seed
        <input
          type="number"
          min="0"
          value={options.random_seed}
          onChange={(e) =>
            setOptions((o) => ({
              ...o,
              random_seed: Number(e.target.value),
            }))
          }
        />
      </label>
      <label>
        Recording
        <select
          value={options.recording_level}
          onChange={(e) =>
            setOptions((o) => ({
              ...o,
              recording_level: e.target
                .value as JobSubmissionRequest["recording_level"],
            }))
          }
        >
          <option value="full-trace">Full trace</option>
          <option value="events">Events</option>
          <option value="metrics-only">
            Metrics only (executed paths retained)
          </option>
        </select>
      </label>
      <button className="primary" onClick={preview} disabled={!scenario}>
        Preview effective inputs
      </button>
      {plan && <SimulationPlanPreview {...{ plan, portableInput, start }} />}
    </fieldset>
  );
}
