import { useCallback } from "react";
import { useBatchDraft } from "./useBatchDraft";
import { useRunComparison } from "./useRunComparison";
import { useReplayLayers } from "./useReplayLayers";
import { useDecisionHeat } from "./useDecisionHeat";
import { useReplayFrame } from "../useReplayFrame";
import {
  useWorkspacePlayback,
  useReplayLocation,
} from "./useWorkspacePlayback";
import { useWorkspaceDraft } from "./useWorkspaceDraft";
import { useWorkspaceRuntime } from "./useWorkspaceRuntime";
import {
  useWorkspaceSubmission,
  workspaceActions,
} from "./useWorkspaceActions";

/** Compose independently owned draft, worker, and replay state for the workspace. */
export function useWorkspace() {
  const playback = useWorkspacePlayback();
  const state = useWorkspaceDraft(playback);
  const runtime = useWorkspaceRuntime(state.draft);
  const submission = useWorkspaceSubmission(state, runtime, playback.reset);
  const actions = workspaceActions(state, runtime);
  const comparison = useRunComparison(
    runtime.reportError,
    playback.reset,
    runtime.setError,
  );
  const { run } = state.draft;
  const maxTick =
    state.screen === "Compare"
      ? comparison.maxTick
      : (run?.metadata.frame_count || 1) - 1;
  const { setTick, tick, agent } = playback;
  const seek = useCallback(
    (t: number) => {
      setTick(Math.max(0, Math.min(t, maxTick)));
    },
    [maxTick, setTick],
  );
  const replay = useReplayFrame(run, tick);
  const layerState = useReplayLayers();
  const decision = useDecisionHeat(
    replay.frame,
    agent,
    layerState.layers.localHeat,
  );
  const batchState = useBatchDraft();
  useReplayLocation(run, tick, runtime.loading);
  return {
    ...state,
    runtime,
    submission,
    actions,
    comparison,
    replay,
    layerState,
    decision,
    batchState,
    playback: { ...playback, maxTick, seek },
  };
}

export type WorkspaceModel = ReturnType<typeof useWorkspace>;
