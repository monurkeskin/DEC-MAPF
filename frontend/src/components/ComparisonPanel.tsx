import { ComparisonRunSelect } from "./ComparisonRunSelect";
import { ComparisonReplay } from "./ComparisonReplay";
import { CohortEvidence } from "./CohortEvidence";
import type { Dispatch, SetStateAction } from "react";
import type { RunSummary } from "../api/types";
import type { useRunComparison } from "../hooks/useRunComparison";
import { TimelineScrubber } from "./TimelineScrubber";
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
  return (
    <>
      <h1>Matched comparison</h1>
      <p>
        Pairing uses scenario, seed, all non-treatment inputs, metric version
        and source hash. Costs use common valid solved runs.
      </p>
      <div className="two-cols">
        <ComparisonRunSelect
          label="Left run"
          value={left}
          onChange={setLeft}
          runs={runs}
        />
        <ComparisonRunSelect
          label="Right run"
          value={right}
          onChange={setRight}
          runs={runs}
        />
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
            <ComparisonReplay
              label="Left"
              run={leftRun}
              tick={alignedTicks[0]}
            />
            <ComparisonReplay
              label="Right"
              run={rightRun}
              tick={alignedTicks[1]}
            />
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
          <CohortEvidence comparison={comparison} />
        </>
      )}
    </>
  );
}
