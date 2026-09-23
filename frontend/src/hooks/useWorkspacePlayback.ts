import { useCallback, useEffect, useState } from "react";
import type { RunDetail } from "../api/types";

export function useWorkspacePlayback() {
  const [tick, setTick] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [agent, setAgent] = useState<string | null>(null);
  const reset = useCallback(() => {
    setPlaying(false);
    setTick(0);
  }, []);
  return {
    tick,
    setTick,
    playing,
    setPlaying,
    speed,
    setSpeed,
    agent,
    setAgent,
    reset,
  };
}

export function useReplayLocation(
  run: RunDetail | null,
  tick: number,
  loading: boolean,
) {
  useEffect(() => {
    if (run) {
      sessionStorage.setItem(`tick-${run.metadata.run_id}`, String(tick));
      const link = new URL(location.href);
      link.searchParams.set("run", run.metadata.run_id);
      link.searchParams.set("tick", String(tick));
      window.history.replaceState(null, "", link);
    } else if (!loading) {
      const link = new URL(location.href);
      link.searchParams.delete("run");
      link.searchParams.delete("tick");
      window.history.replaceState(null, "", link);
    }
  }, [tick, run, loading]);
}
