import { useCallback, useEffect, useRef, useState } from "react";
import { request } from "../api/client";
import type { RunPage, RunSummary } from "../api/types";

export type LibraryFilters = {
  solver_name?: string;
  validation_status?: string;
  experiment_id?: string;
};

export function useRunLibrary(onError: (error: unknown) => void) {
  const [filters, setFilters] = useState<LibraryFilters>({});
  const [items, setItems] = useState<RunSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [next, setNext] = useState<string | null>(null);
  const [solverNames, setSolverNames] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const revision = useRef(0);
  const active = useRef<AbortController | null>(null);
  const load = useCallback(
    async (cursor: string | null) => {
      const current = ++revision.current;
      active.current?.abort();
      const controller = new AbortController();
      active.current = controller;
      setLoading(true);
      if (!cursor) {
        setItems([]);
        setNext(null);
      }
      const query = new URLSearchParams({ limit: "100" });
      for (const [key, value] of Object.entries(filters)) {
        if (value) query.set(key, value);
      }
      if (cursor) query.set("cursor", cursor);
      try {
        const page = await request<RunPage>(`/runs/page?${query}`, {
          signal: controller.signal,
        });
        if (current !== revision.current || controller.signal.aborted) return;
        setItems((old) =>
          cursor
            ? [
                ...new Map(
                  [...old, ...page.items].map((r) => [r.run_id, r]),
                ).values(),
              ]
            : page.items,
        );
        setTotal(page.total);
        setNext(page.next_cursor);
        setSolverNames(page.solver_names);
        setStatuses(page.validation_statuses);
      } catch (error) {
        if (!controller.signal.aborted && current === revision.current)
          throw error;
      } finally {
        if (!controller.signal.aborted && current === revision.current)
          setLoading(false);
      }
    },
    [filters],
  );
  const refresh = useCallback(() => load(null), [load]);
  const loadMore = useCallback(
    () => (next ? load(next) : Promise.resolve()),
    [load, next],
  );
  useEffect(() => {
    // Synchronize with the remote library after render, with unmount cancellation.
    const timer = window.setTimeout(() => refresh().catch(onError), 0);
    return () => {
      window.clearTimeout(timer);
      active.current?.abort();
    };
  }, [refresh, onError]);
  return {
    items,
    total,
    next,
    filters,
    setFilters,
    solverNames,
    statuses,
    loading,
    refresh,
    loadMore,
  };
}
