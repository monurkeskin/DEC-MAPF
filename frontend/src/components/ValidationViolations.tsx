import type { SolverRunResult } from "../api/types";
export function ValidationViolations({
  result: r,
  onSeek,
}: {
  result: SolverRunResult;
  onSeek?: (tick: number) => void;
}) {
  return (
    <>
      <h3>Validation violations</h3>
      {(r.validation?.errors.length || 0) === 0 ? (
        <p className="muted">No validator errors recorded.</p>
      ) : (
        <ul>
          {r.validation?.errors.map((e, i) => (
            <li key={i}>
              <button onClick={() => onSeek?.(Number(e.time_step || 0))}>
                {String(e.error_type)} · {String(e.agent_a)} · t=
                {String(e.time_step ?? "n/a")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
