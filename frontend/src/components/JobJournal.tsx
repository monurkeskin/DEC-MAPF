import { cancelJob, post } from "../api/client";
import type { JobStatusResponse } from "../api/types";
import { terminal } from "../hooks/useJobMonitor";

type Props = {
  jobs: JobStatusResponse[];
  setJobId: (id: string) => void;
  refresh: () => Promise<void>;
  reportError: (error: unknown) => void;
};
export function JobJournal({ jobs, setJobId, refresh, reportError }: Props) {
  return (
    <details>
      <summary>Job journal ({jobs.length})</summary>
      {jobs.map((j) => (
        <div className="library-row" key={j.job_id}>
          <button onClick={() => setJobId(j.job_id)}>
            {j.solver_id}
            <small>
              {j.state} · {j.job_id.slice(-8)}
            </small>
          </button>
          {terminal.has(j.state) && j.state !== "completed" && (
            <button
              onClick={() =>
                post<JobStatusResponse>(`/jobs/${j.job_id}/retry`, {})
                  .then((next) => {
                    setJobId(next.job_id);
                    return refresh();
                  })
                  .catch(reportError)
              }
            >
              Retry as new attempt
            </button>
          )}
          {!terminal.has(j.state) && (
            <button
              onClick={() =>
                cancelJob(j.job_id).then(refresh).catch(reportError)
              }
            >
              Cancel
            </button>
          )}
        </div>
      ))}
    </details>
  );
}
