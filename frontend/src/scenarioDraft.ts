import type { ScenarioDetail, ScenarioInput } from "./api/types";

type Coordinate = [number, number];

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function point(value: unknown): value is Coordinate {
  return (
    Array.isArray(value) && value.length === 2 && value.every(Number.isInteger)
  );
}

function positions(value: unknown): value is Record<string, Coordinate> {
  return object(value) && Object.values(value).every(point);
}

function roster(
  starts: Record<string, Coordinate>,
  goals: Record<string, Coordinate>,
  order: unknown,
): string[] {
  const ids = Object.keys(starts);
  if (
    ids.length !== Object.keys(goals).length ||
    ids.some((id) => !Object.hasOwn(goals, id))
  )
    throw new Error("Starts and goals must have the same agent roster");
  if (order === undefined) return ids;
  if (!Array.isArray(order) || order.length !== ids.length)
    throw new Error("Agent order must list the complete roster once");
  if (
    new Set(order).size !== ids.length ||
    order.some((id) => typeof id !== "string" || !Object.hasOwn(starts, id))
  )
    throw new Error("Agent order must list the complete roster once");
  return order;
}

/** Check editable JSON shape; geometry and scientific validity remain backend checks. */
export function parseScenarioDraft(text: string): ScenarioDetail {
  const value: unknown = JSON.parse(text);
  if (!object(value)) throw new Error("Scenario JSON must be an object");
  const { grid_width, grid_height, starts, goals, obstacles, setting } = value;
  if (!Number.isInteger(grid_width) || !Number.isInteger(grid_height))
    throw new Error("Grid dimensions must be integers");
  if (!positions(starts) || !positions(goals))
    throw new Error("Agent positions must contain integer [x, y] coordinates");
  if (!Array.isArray(obstacles) || !obstacles.every(point))
    throw new Error("Obstacles must contain integer [x, y] coordinates");
  if (
    !["SETTING_1", "SETTING_2", "SETTING_3", "SETTING_4"].includes(
      String(setting),
    )
  )
    throw new Error("Choose a known MAPF setting");
  return {
    grid_width: grid_width as number,
    grid_height: grid_height as number,
    starts,
    goals,
    obstacles,
    setting: setting as ScenarioDetail["setting"],
    name:
      typeof value.name === "string" && value.name
        ? value.name
        : "Imported draft",
    agent_order: roster(starts, goals, value.agent_order),
    scenario_id: null,
    instance_hash: "",
  };
}

/** Request order carries roster semantics; persisted IDs/hashes do not describe a new draft. */
export function scenarioDraftInput(scenario: ScenarioDetail): ScenarioInput {
  const ids = [
    ...new Set([
      ...(scenario.agent_order ?? []).filter((id) =>
        Object.hasOwn(scenario.starts, id),
      ),
      ...Object.keys(scenario.starts),
    ]),
  ];
  return {
    grid_width: scenario.grid_width,
    grid_height: scenario.grid_height,
    obstacles: scenario.obstacles,
    starts: Object.fromEntries(ids.map((id) => [id, scenario.starts[id]])),
    goals: scenario.goals,
    setting: scenario.setting,
    name: scenario.name,
  };
}
