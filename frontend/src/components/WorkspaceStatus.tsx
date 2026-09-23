import type { JobStatusResponse, RunDetail } from "../api/types";
import { terminal } from "../hooks/useJobMonitor";

type Props = {
  job: JobStatusResponse | null;
  run: RunDetail | null;
  connection: string;
  error: string;
  notice: string;
  setError: (value: string) => void;
  setNotice: (value: string) => void;
};

function timeoutEvidence(job: JobStatusResponse | null, run: RunDetail | null) {
  if (job?.timeout_diagnostics) return job.timeout_diagnostics;
  const evidence = run?.result.measured_metrics?.solver_diagnostics;
  if (
    !evidence ||
    typeof evidence !== "object" ||
    !("last_negotiation_failure" in evidence)
  )
    return null;
  const failure = evidence.last_negotiation_failure;
  return failure && typeof failure === "object" && "diagnostics" in failure
    ? failure.diagnostics
    : null;
}

export function WorkspaceStatus({
  job,
  run,
  connection,
  error,
  notice,
  setError,
  setNotice,
}: Props) {
  const result = run?.result;
  const timeoutDiagnostics = timeoutEvidence(job, run);
  return (
    <>
      <div className="status-strip" role="status">
        <span>
          Execution:{" "}
          <b>{job && !terminal.has(job.state) ? job.state : "idle"}</b>
        </span>
        <span>
          Solver: <b>{result?.solver_outcome || "not available"}</b>
        </span>
        <span>
          Validation: <b>{result?.validation?.status || "not checked"}</b>
        </span>
        <span data-testid="evidence-mode">
          {run
            ? "Saved replay · recorded evidence"
            : job && !terminal.has(job.state)
              ? `Live job · ${connection}`
              : "Ready to configure"}
        </span>
      </div>
      {error && (
        <div role="alert" className="error">
          {error}
          <button onClick={() => setError("")} aria-label="Dismiss error">
            Dismiss
          </button>
        </div>
      )}
      {!!timeoutDiagnostics && (
        <details
          className="notice"
          data-testid="negotiation-timeout-diagnostics"
        >
          <summary>Negotiation timeout diagnostics</summary>
          <p>Last recorded worker activity before the deadline.</p>
          <pre tabIndex={0}>{JSON.stringify(timeoutDiagnostics, null, 2)}</pre>
        </details>
      )}
      {notice && (
        <div className="notice">
          {notice}
          <button onClick={() => setNotice("")} aria-label="Dismiss notice">
            Dismiss
          </button>
        </div>
      )}
    </>
  );
}
