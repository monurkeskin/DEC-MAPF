import type { Dispatch, SetStateAction } from "react";
import type { RunSummary } from "../api/types";
import type { useRunComparison } from "../hooks/useRunComparison";
import { GridViewport } from "./GridViewport";
import { TimelineScrubber } from "./TimelineScrubber";
import { useReplayFrame } from "../useReplayFrame";
import { saveJson } from "../artifacts";
type Props = {
  model: ReturnType<typeof useRunComparison>;
  runs: RunSummary[];
  tick: number;
  playing: boolean;
  speed: number;
  setTick: Dispatch<SetStateAction<number>>;
  setPlaying: Dispatch<SetStateAction<boolean>>;
  setSpeed: Dispatch<SetStateAction<number>>;
  seek: (tick: number) => void;
};
export function ComparisonPanel({
  model,
  runs,
  tick,
  playing,
  speed,
  setTick,
  setPlaying,
  setSpeed,
  seek,
}: Props) {
  const {
    left,
    setLeft,
    right,
    setRight,
    comparison,
    leftRun,
    rightRun,
    treatments,
    setTreatments,
    alignment,
    setAlignment,
    compare,
    sessionEvents,
    maxTick,
  } = model;
  const alignedTicks = model.ticksAt(tick);
  const leftReplay = useReplayFrame(leftRun, alignedTicks[0]);
  const rightReplay = useReplayFrame(rightRun, alignedTicks[1]);
  return (
    <>
      <h1>Matched comparison</h1>
      <p>
        Pairing uses scenario, seed, all non-treatment inputs, metric version
        and source hash. Costs use common valid solved runs.
      </p>
      <div className="two-cols">
        {[
          ["Left run", left, setLeft],
          ["Right run", right, setRight],
        ].map(([label, value, set]) => (
          <label key={String(label)}>
            {String(label)}
            <select
              value={String(value)}
              onChange={(e) => {
                (set as (v: string) => void)(e.target.value);
              }}
            >
              <option value="">Select a saved run</option>
              {value && !runs.some((run) => run.run_id === value) && (
                <option value={String(value)}>
                  Selected run · {String(value).slice(-8)} (outside current
                  library filter)
                </option>
              )}
              {runs.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.solver_name} · {r.run_id.slice(-8)}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <label>
        Declared treatment keys (comma-separated)
        <input
          value={treatments}
          onChange={(e) => {
            setTreatments(e.target.value);
          }}
        />
      </label>
      <button className="primary" disabled={!left || !right} onClick={compare}>
        Build matched cohort
      </button>
      {comparison && (
        <>
          <label>
            Replay alignment
            <select
              value={alignment}
              onChange={(e) => {
                setAlignment(e.target.value as "tick" | "session");
                setTick(0);
                setPlaying(false);
              }}
            >
              <option value="tick">Same simulation tick</option>
              <option
                value="session"
                disabled={sessionEvents.some((events) => !events.length)}
              >
                Negotiation ordinal
              </option>
            </select>
          </label>
          {alignment === "session" && (
            <p>
              Session order is descriptive: the two sessions can involve
              different agents. Each viewport shows its actual recorded
              simulation tick.
            </p>
          )}
          <p role="status">
            Paired: {comparison.paired} · Common solved:{" "}
            {comparison.common_solved} · Unmatched: {comparison.unmatched.left}{" "}
            left / {comparison.unmatched.right} right · Excluded from costs:{" "}
            {comparison.excluded_from_costs}
          </p>
          <div className="comparison-view">
            {[leftRun, rightRun].map(
              (r, i) =>
                r && (
                  <div key={r.metadata.run_id}>
                    <h3>
                      {i === 0 ? "Left" : "Right"} · {r.metadata.solver_name}
                    </h3>
                    <p>
                      Showing tick{" "}
                      {Math.min(
                        alignedTicks[i],
                        Math.max(0, r.metadata.frame_count - 1),
                      )}{" "}
                      of {Math.max(0, r.metadata.frame_count - 1)}
                      {alignedTicks[i] >= r.metadata.frame_count
                        ? " · final frame held"
                        : ""}
                    </p>
                    <GridViewport
                      gridWidth={r.metadata.instance.grid_width}
                      gridHeight={r.metadata.instance.grid_height}
                      obstacles={r.metadata.instance.obstacles}
                      starts={r.metadata.instance.starts}
                      goals={r.metadata.instance.goals}
                      currentFrame={(i === 0 ? leftReplay : rightReplay).frame}
                      paths={r.result.paths}
                      showPaths
                    />
                  </div>
                ),
            )}
          </div>
          <TimelineScrubber
            indexLabel={alignment === "session" ? "session" : "t"}
            currentTick={tick}
            totalTicks={Math.max(0, maxTick)}
            isPlaying={playing}
            speed={speed}
            onSeek={seek}
            onTogglePlay={() => setPlaying((p) => !p)}
            onChangeSpeed={setSpeed}
          />
          <table>
            <caption>Right minus left · common-solved pairs</caption>
            <thead>
              <tr>
                <th>Metric</th>
                <th>Mean delta</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(comparison.means_right_minus_left).map(
                ([m, v]) => (
                  <tr key={m}>
                    <th>{m}</th>
                    <td>{v == null ? "Unavailable" : v.toFixed(3)}</td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
          <p>{comparison.uncertainty}</p>
          <p className="muted">{comparison.denominator_policy}</p>
          <details>
            <summary>Effective input differences and pair records</summary>
            <pre tabIndex={0}>{JSON.stringify(comparison.rows, null, 2)}</pre>
          </details>
          <button
            onClick={() => saveJson("decmapf-comparison.json", comparison)}
          >
            Export cohort JSON
          </button>
        </>
      )}
    </>
  );
}
