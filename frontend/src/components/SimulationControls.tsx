import { useState, type Dispatch, type SetStateAction } from "react";
import { saveJson } from "../artifacts";
import { portableStudy } from "../study";
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
  const renderParameter = (
    p: NonNullable<typeof selectedCap>["parameters"][number],
  ) => (
    <label key={p.name} title={p.description}>
      {p.display_name}
      {p.param_type === "select" ? (
        <select
          value={String(options[p.name] ?? p.default)}
          onChange={(e) =>
            setOptions((o) => ({ ...o, [p.name]: e.target.value }))
          }
        >
          {p.options?.map((v) => (
            <option key={v} value={v}>
              {v === "SC"
                ? "SC — Standard"
                : v === "DC"
                  ? "DC — Dynamic"
                  : v === "ZC"
                    ? "ZC — Zero"
                    : v}
            </option>
          ))}
        </select>
      ) : (
        <input
          type="number"
          min={p.min_value}
          max={p.max_value}
          step={p.step || 1}
          value={
            options[p.name] === null ||
            (options[p.name] === undefined && p.default === null)
              ? ""
              : Number(options[p.name] ?? p.default)
          }
          placeholder={p.default === null ? "Follow FoV width" : undefined}
          onChange={(e) =>
            setOptions((o) => ({
              ...o,
              [p.name]:
                e.target.value === "" && p.default === null
                  ? null
                  : Number(e.target.value),
            }))
          }
        />
      )}
    </label>
  );
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
        .map(renderParameter)}
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
          .map(renderParameter)}
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
      {plan && (
        <section className="plan">
          <strong>
            {plan.count} run ·{" "}
            {plan.maximum_process_seconds === null
              ? "No per-trial time cap"
              : `≤${plan.maximum_process_seconds}s process`}
            budget
          </strong>
          <p>
            Inactive controls:{" "}
            {plan.plans[0].inactive_parameters.join(", ") || "none"}
          </p>
          {plan.plans[0].semantics && (
            <aside aria-label="Problem assumptions">
              <strong>Problem assumptions</strong>
              <p>{plan.plans[0].semantics.motion}</p>
              <p>
                Waiting before the goal:{" "}
                {plan.plans[0].semantics.wait_before_goal
                  ? "allowed"
                  : "forbidden"}
                . Goal policy: {plan.plans[0].semantics.goal_policy}.{" "}
                {plan.plans[0].semantics.goal_timing}
              </p>
              <p>
                {plan.plans[0].semantics.coordinates}{" "}
                {plan.plans[0].semantics.time_origin}
              </p>
              <p>
                Forbidden conflicts:{" "}
                {plan.plans[0].semantics.forbidden_conflicts.join("; ")}.
              </p>
              <p>{plan.plans[0].semantics.cost}</p>
              <p className="hint">{plan.plans[0].semantics.scope}</p>
            </aside>
          )}
          <details>
            <summary>Exact effective configuration</summary>
            <pre tabIndex={0}>{JSON.stringify(plan.plans[0], null, 2)}</pre>
          </details>
          {portableInput && (
            <details>
              <summary>Run these inputs without the GUI</summary>
              <p>
                The exported scenario is self-contained. Planning on your
                machine records its own source identity. The study has one trial
                and a separate finite batch budget.
              </p>
              <button
                onClick={() =>
                  saveJson("study.json", portableStudy(portableInput))
                }
              >
                Download headless study
              </button>
              <pre tabIndex={0}>
                mapf batch plan study.json --output manifest.json{"\n"}mapf
                batch run manifest.json --workspace runs/my-study
              </pre>
            </details>
          )}
          <button className="primary" onClick={start}>
            Run simulation
          </button>
        </section>
      )}
    </fieldset>
  );
}
