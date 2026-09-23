import type { RunDetail } from "../api/types";
import { useReplayFrame } from "../useReplayFrame";
import { GridViewport } from "./GridViewport";
export function ComparisonReplay({
  label,
  run,
  tick,
}: {
  label: string;
  run: RunDetail | null;
  tick: number;
}) {
  const replay = useReplayFrame(run, tick);
  if (!run) return null;
  const last = Math.max(0, run.metadata.frame_count - 1);
  const instance = run.metadata.instance;
  return (
    <div>
      <h3>
        {label} · {run.metadata.solver_name}
      </h3>
      <p>
        Showing tick {Math.min(tick, last)} of {last}
        {tick >= run.metadata.frame_count ? " · final frame held" : ""}
      </p>
      <GridViewport
        gridWidth={instance.grid_width}
        gridHeight={instance.grid_height}
        obstacles={instance.obstacles}
        starts={instance.starts}
        goals={instance.goals}
        currentFrame={replay.frame}
        paths={run.result.paths}
        showPaths
      />
    </div>
  );
}
