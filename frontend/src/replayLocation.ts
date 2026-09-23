import type { RunDetail } from "./api/types";

export function restoredTick(run: RunDetail): number {
  const id = run.metadata.run_id;
  const query = new URLSearchParams(location.search);
  const stored =
    query.get("run") === id
      ? query.get("tick") || 0
      : sessionStorage.getItem(`tick-${id}`) || 0;
  return Math.min(
    Math.max(0, Number(stored) || 0),
    Math.max(0, run.metadata.frame_count - 1),
  );
}
