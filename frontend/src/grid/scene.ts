/** Resolve recorded local positions independently from omniscient replay state. */
import type { GridViewportProps } from "./types";

export function localObservation(props: GridViewportProps) {
  return props.currentFrame?.local_observations?.[props.selectedAgent || ""];
}

export function visiblePositions(
  props: GridViewportProps,
): Record<string, number[]> {
  if (!props.localView) return props.currentFrame?.positions || props.starts;
  const observation = localObservation(props);
  const positions: Record<string, number[]> = {};
  if (!observation) return positions;
  positions[observation.agent_id] = observation.position;
  for (const message of observation.messages) {
    if (message.points.length) positions[message.sender] = message.points[0];
  }
  return positions;
}

export function pickAgent(
  props: GridViewportProps,
  x: number,
  y: number,
): string | null {
  const positions = visiblePositions(props);
  return (
    Object.keys(props.starts).find(
      (id) =>
        positions[id]?.[0] === x &&
        positions[id]?.[1] === y &&
        (props.localView || props.currentFrame?.statuses[id] !== "disappeared"),
    ) || null
  );
}
