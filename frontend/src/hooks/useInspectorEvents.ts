import { useState } from "react";
import type { SolverRunResult } from "../api/types";
export function useInspectorEvents(result: SolverRunResult | null) {
  const [session, setSession] = useState(""),
    [filter, setFilter] = useState("all");
  const [page, setPage] = useState(0);
  const events = result?.telemetry_events || [];
  const sessions = events.filter((e) => e.event_type === "NEGO_SESSION");
  const selectedEvents = events.filter(
    (e) =>
      (!session || e.session_id === session) &&
      (filter === "all" || e.event_type === filter),
  );
  return {
    session,
    setSession,
    filter,
    setFilter,
    page,
    setPage,
    sessions,
    selectedEvents,
  };
}
