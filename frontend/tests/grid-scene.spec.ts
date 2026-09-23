import { test, expect } from "@playwright/test";
import type { FrameSnapshot } from "../src/api/types";
import type { GridViewportProps } from "../src/grid/types";
import { paintGrid } from "../src/grid/painter";
import { pickAgent, visiblePositions } from "../src/grid/scene";

function fixture(): GridViewportProps {
  const frame: FrameSnapshot = {
    tick: 4,
    phase: "post_move",
    positions: { a: [0, 0], b: [3, 3], c: [2, 2] },
    statuses: { a: "active", b: "disappeared", c: "active" },
    targets: {},
    tokens: {},
    active_agents: 2,
    solved_agents: 1,
    is_unsolvable: false,
    telemetry_available: true,
    heat_provenance: "hindsight",
    local_heat_omitted: 0,
    local_observations: {
      a: {
        agent_id: "a",
        tick: 4,
        position: [0, 0],
        obstacles: [],
        messages: [
          {
            event_type: "MESSAGE",
            acknowledgement: 0,
            kind: "BROADCAST",
            payload_bytes: 1,
            points: [
              [1, 0],
              [2, 0],
            ],
            recipient: "a",
            sender: "b",
            tick: 3,
          },
        ],
      },
    },
  };
  return {
    gridWidth: 4,
    gridHeight: 4,
    obstacles: [],
    starts: { a: [0, 0], b: [1, 0], c: [2, 2] },
    goals: { a: [3, 0], b: [3, 3], c: [3, 2] },
    currentFrame: frame,
    selectedAgent: "a",
    localView: true,
  };
}

test("local selection uses a received position without consulting hidden global disappearance", () => {
  const props = fixture();
  expect(visiblePositions(props)).toEqual({ a: [0, 0], b: [1, 0] });
  expect(pickAgent(props, 1, 0)).toBe("b");
  expect(pickAgent(props, 3, 3)).toBeNull();
  expect(pickAgent(props, 2, 2)).toBeNull();
});

test("global selection omits disappeared agents", () => {
  const props = { ...fixture(), localView: false };
  expect(pickAgent(props, 3, 3)).toBeNull();
  expect(pickAgent(props, 2, 2)).toBe("c");
});

test("missing local observation reveals no global positions", () => {
  const props = { ...fixture(), selectedAgent: "c" };
  expect(visiblePositions(props)).toEqual({});
  expect(pickAgent(props, 2, 2)).toBeNull();
});

test("remembered parked cells render only from the selected recipient's record", () => {
  const props = fixture();
  props.currentFrame!.local_observations!.a.remembered_obstacles = [[3, 1]];
  const local = recordedCanvas();
  paintGrid(local.context, props, 32);
  expect(local.operations).toContainEqual(["strokeRect", 99, 35, 26, 26]);
  const other = recordedCanvas();
  paintGrid(other.context, { ...props, selectedAgent: "c" }, 32);
  expect(other.operations).not.toContainEqual(["strokeRect", 99, 35, 26, 26]);
  expect(visiblePositions(props)).toEqual({ a: [0, 0], b: [1, 0] });
});

function recordedCanvas() {
  const operations: unknown[][] = [];
  const context = new Proxy(
    {},
    {
      get:
        (_, name) =>
        (...args: unknown[]) =>
          operations.push([name, ...args]),
      set: (_, name, value) => {
        operations.push([name, value]);
        return true;
      },
    },
  ) as CanvasRenderingContext2D;
  return { context, operations };
}

test("a local view cannot disclose a global collision absent from its messages", () => {
  const props = fixture();
  props.currentFrame!.statuses.b = "collided";
  const { context, operations } = recordedCanvas();
  paintGrid(context, props, 32);
  expect(operations).not.toContainEqual(["strokeStyle", "#fb7185"]);
  expect(operations.filter((entry) => entry[0] === "arc")).toHaveLength(2);
});

test("recorded local view never paints hindsight heat or other agents global goals", () => {
  const props = fixture();
  props.showHeat = true;
  props.currentFrame!.heat_grid = { "3-3": 1 };
  const { context, operations } = recordedCanvas();
  paintGrid(context, props, 32);
  expect(
    operations.some((entry) => String(entry[1]).startsWith("rgba(244,114,182")),
  ).toBe(false);
  expect(operations).not.toContainEqual([
    "strokeRect",
    (3 + 0.23) * 32,
    (3 + 0.23) * 32,
    32 * 0.54,
    32 * 0.54,
  ]);
});
