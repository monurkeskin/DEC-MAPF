import type { Dispatch, SetStateAction } from "react";
import type { RunDetail, ScenarioDetail } from "../api/types";
import type { useReplayFrame } from "../useReplayFrame";
import type { useDecisionHeat } from "../hooks/useDecisionHeat";
import type { useReplayLayers } from "../hooks/useReplayLayers";
import { ReplayLayerControls } from "./ReplayLayerControls";
import { DecisionHeatPanel } from "./DecisionHeatPanel";
import { GridViewport } from "./GridViewport";
import { TimelineScrubber } from "./TimelineScrubber";

type Playback = {
  tick: number;
  maxTick: number;
  playing: boolean;
  speed: number;
  seek: (tick: number) => void;
  setPlaying: Dispatch<SetStateAction<boolean>>;
  setSpeed: (value: number) => void;
};
type Props = {
  scenario: ScenarioDetail | null;
  run: RunDetail | null;
  fovSize: number;
  replay: ReturnType<typeof useReplayFrame>;
  agent: string | null;
  onSelectAgent: (id: string | null) => void;
  onEditCell?: (x: number, y: number) => void;
  playback: Playback;
  layerState: ReturnType<typeof useReplayLayers>;
  decision: ReturnType<typeof useDecisionHeat>;
};
export function ReplayViewport({
  scenario,
  run,
  fovSize,
  replay,
  agent,
  onSelectAgent,
  onEditCell,
  playback,
  layerState,
  decision,
}: Props) {
  const { tick, maxTick, playing, speed, seek, setPlaying, setSpeed } =
    playback;
  const { layers, toggle } = layerState;
  const { paths, heat, localHeat, fov, localView, reservations } = layers;
  const currentFrame = replay.frame;
  const result = run?.result || null;
  return (
    <>
      <div className="view-heading">
        <div>
          <h1>
            {run ? "Replay & diagnostics" : scenario?.name || "Load a scenario"}
          </h1>
          <p className="muted">
            {run
              ? `${run.metadata.run_id} · ${run.metadata.validation_status}`
              : "Draft scenario · independent validation runs after solving"}
          </p>
        </div>
      </div>
      <ReplayLayerControls layers={layers} toggle={toggle} />
      <p className="legend">
        ● Agent · □ Goal · ■ Obstacle. Paths and hindsight heat use executed
        history; teal local heat uses recorded strategy weights. Amber dashed
        cells show recorded opponent reservations with absolute ticks (full
        trace, selected owner or all). Local view shows the selected recipient's
        recorded observation and static map.
      </p>
      {replay.loading && <p role="status">Loading replay frames…</p>}
      {replay.error && <p role="alert">{replay.error}</p>}
      {localHeat && (
        <DecisionHeatPanel
          records={decision.records}
          selected={decision.selected}
          offset={decision.offset}
          omitted={currentFrame?.local_heat_omitted || 0}
          onSelect={decision.select}
          onOffset={decision.setOffset}
        />
      )}
      {localView && (
        <p role="status">
          {agent && currentFrame?.local_observations?.[agent]
            ? `Observation for ${agent} at t=${currentFrame.local_observations[agent].tick}; received paths are beliefs at that observation time.`
            : "Select an agent with a recorded local observation. No global agent state is shown in local view."}
        </p>
      )}
      {scenario && (
        <GridViewport
          gridWidth={scenario.grid_width}
          gridHeight={scenario.grid_height}
          obstacles={scenario.obstacles}
          starts={scenario.starts}
          goals={scenario.goals}
          currentFrame={currentFrame}
          paths={result?.paths}
          selectedAgent={agent}
          onSelectAgent={onSelectAgent}
          onEditCell={onEditCell}
          showPaths={paths}
          showHeat={heat}
          localHeatGrid={decision.grid}
          showFov={fov}
          showReservations={reservations}
          localView={localView}
          fovSize={fovSize}
        />
      )}
      <TimelineScrubber
        currentTick={tick}
        totalTicks={Math.max(0, maxTick)}
        isPlaying={playing}
        speed={speed}
        onSeek={seek}
        onTogglePlay={() => setPlaying((p) => !p)}
        onChangeSpeed={setSpeed}
        onJumpToFirstViolation={
          result?.validation?.first_violation_tick != null
            ? () => {
                setPlaying(false);
                seek(result.validation!.first_violation_tick!);
              }
            : undefined
        }
      />
    </>
  );
}
