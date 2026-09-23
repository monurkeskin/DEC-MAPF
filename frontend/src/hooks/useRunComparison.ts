import { useRef, useState } from "react";
import { fetchRunDetails, post } from "../api/client";
import type { Comparison, RunDetail } from "../api/types";

export function useRunComparison(
  reportError: (error: unknown) => void,
  onCompared: () => void,
  setError: (message: string) => void,
) {
  const comparisonRevision = useRef(0);
  const [left, setLeft] = useState(""),
    [right, setRight] = useState(""),
    [comparison, setComparison] = useState<Comparison | null>(null);
  const [leftRun, setLeftRun] = useState<RunDetail | null>(null),
    [rightRun, setRightRun] = useState<RunDetail | null>(null),
    [treatments, setTreatments] = useState("solver_id");
  const [alignment, setAlignment] = useState<"tick" | "session">("tick");
  const compare = async () => {
    const revision = ++comparisonRevision.current;
    try {
      setError("");
      const c = await post<Comparison>("/comparisons", {
        left: [left],
        right: [right],
        treatment_keys: treatments.split(",").map((s) => s.trim()),
      });
      const [a, b] = await Promise.all([
        fetchRunDetails(left),
        fetchRunDetails(right),
      ]);
      if (revision !== comparisonRevision.current) return;
      setComparison(c);
      setLeftRun(a);
      setRightRun(b);
      setAlignment("tick");
      onCompared();
    } catch (e) {
      reportError(e);
    }
  };
  const sessionEvents = [leftRun, rightRun].map(
    (r) =>
      r?.result.telemetry_events?.filter(
        (e) => e.event_type === "NEGO_SESSION",
      ) || [],
  );
  const ticksAt = (tick: number) =>
    sessionEvents.map((events) =>
      alignment === "session"
        ? Number(events[Math.min(tick, events.length - 1)]?.tick || 0)
        : tick,
    );
  const maxTick =
    alignment === "session"
      ? Math.max(0, ...sessionEvents.map((events) => events.length - 1))
      : Math.max(
          (leftRun?.metadata.frame_count || 1) - 1,
          (rightRun?.metadata.frame_count || 1) - 1,
        );
  function invalidate(change: () => void) {
    comparisonRevision.current++;
    setComparison(null);
    change();
  }
  return {
    left,
    setLeft: (value: string) => invalidate(() => setLeft(value)),
    right,
    setRight: (value: string) => invalidate(() => setRight(value)),
    comparison,
    leftRun,
    rightRun,
    treatments,
    setTreatments: (value: string) => invalidate(() => setTreatments(value)),
    alignment,
    setAlignment,
    compare,
    sessionEvents,
    ticksAt,
    maxTick,
  };
}
