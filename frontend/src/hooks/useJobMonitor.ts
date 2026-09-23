import { useEffect, useState } from "react";
import type { RefObject } from "react";
import { fetchJobStatus, subscribeToJobStream } from "../api/client";
import type { JobStatusResponse } from "../api/types";

export const terminal = new Set([
  "completed",
  "failed",
  "cancelled",
  "timed_out",
  "interrupted",
]);

type Options = {
  jobId: string;
  loadedRun: RefObject<string>;
  loadRun: (id: string, current?: () => boolean) => Promise<void>;
  refresh: () => Promise<void>;
  reportError: (error: unknown) => void;
  setNotice: (message: string) => void;
  setError: (message: string) => void;
};
export function useJobMonitor({
  jobId,
  loadedRun,
  loadRun,
  refresh,
  reportError,
  setNotice,
  setError,
}: Options) {
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [connection, setConnection] = useState("Not connected");
  useEffect(() => {
    if (!jobId) return;
    localStorage.setItem("mapf-job", jobId);
    let disposed = false,
      running = false;
    const update = async () => {
      if (running) return;
      running = true;
      try {
        const state = await fetchJobStatus(jobId);
        if (disposed) return;
        setJob(state);
        if (state.state === "completed" && loadedRun.current !== state.run_id) {
          await loadRun(state.run_id, () => !disposed);
          if (!disposed) await refresh();
        }
        if (terminal.has(state.state)) {
          unsubscribe();
          clearInterval(timer);
          setConnection("Journal complete");
        }
        if (terminal.has(state.state) && state.state !== "completed") {
          setNotice(
            `Execution ${state.state}: ${state.error || "No complete solution artifact"}`,
          );
          await refresh();
        }
      } catch (e) {
        if (!disposed) reportError(e);
      } finally {
        running = false;
      }
    };
    update();
    const timer = window.setInterval(update, 1000);
    const cursor = Number(sessionStorage.getItem(`cursor-${jobId}`) || 0);
    const unsubscribe = subscribeToJobStream(
      jobId,
      cursor,
      (e) => {
        sessionStorage.setItem(`cursor-${jobId}`, String(e.sequence));
        update();
      },
      (status) => {
        setConnection(status);
        if (/schema|journal gap|different job/i.test(status)) setError(status);
      },
    );
    return () => {
      disposed = true;
      clearInterval(timer);
      unsubscribe();
    };
  }, [jobId, loadedRun, loadRun, refresh, reportError, setNotice, setError]);
  return { job, setJob, connection };
}
