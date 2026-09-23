import { REQUEST_FIELDS, STARTER_INPUTS } from "./api/presets.generated";
import type { JobSubmissionRequest, ScenarioDetail } from "./api/types";

/** Restore accepted request fields without leaking run-only metadata into an API request. */
export function restoreJobOptions(
  config: Record<string, unknown>,
): JobSubmissionRequest {
  return {
    ...STARTER_INPUTS,
    ...Object.fromEntries(
      REQUEST_FIELDS.filter((key) => Object.hasOwn(config, key)).map((key) => [
        key,
        config[key],
      ]),
    ),
    broadcast_horizon: config.broadcast_horizon ?? undefined,
    negotiation_horizon: config.negotiation_horizon ?? undefined,
  } as JobSubmissionRequest;
}

/** Use explicit geometry and preserve the persisted roster order across canonical JSON. */
export function scenarioRequest(
  options: JobSubmissionRequest,
  scenario: ScenarioDetail,
): JobSubmissionRequest {
  const ids = [
    ...new Set([
      ...(scenario.agent_order ?? []).filter((id) =>
        Object.hasOwn(scenario.starts, id),
      ),
      ...Object.keys(scenario.starts),
    ]),
  ];
  return {
    ...restoreJobOptions(options),
    scenario_id: null,
    setting: scenario.setting,
    grid_width: scenario.grid_width,
    grid_height: scenario.grid_height,
    starts: Object.fromEntries(ids.map((id) => [id, scenario.starts[id]])),
    goals: scenario.goals,
    obstacles: scenario.obstacles,
    name: scenario.name,
  };
}

/** A portable explicit scenario, validated by the shared backend planner on import. */
export function portableStudy(input: JobSubmissionRequest) {
  // Geometry is in the payload: a workspace-local scenario ID must not override it.
  const request = { ...restoreJobOptions(input), scenario_id: null };
  return {
    name: `${input.name || "GUI"} single-scenario study`,
    scenarios: [request],
    budget: {
      workers: 1,
      wall_seconds: Math.max(60, (input.timeout_sec ?? 600) + 30),
      max_trials: 1,
      disk_mb: 256,
      threads_per_worker: 1,
    },
    sampling: {
      population: "one explicitly selected GUI scenario",
      independent_unit: "scenario geometry and roster",
      generalization: "none from one illustrative run",
    },
  };
}
