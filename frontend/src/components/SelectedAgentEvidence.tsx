import type { FrameSnapshot, SolverRunResult } from "../api/types";
export function SelectedAgentEvidence({
  frame: f,
  result: r,
  selectedAgent,
}: {
  frame?: FrameSnapshot;
  result: SolverRunResult;
  selectedAgent: string;
}) {
  return (
    <section className="card">
      <h3>{selectedAgent}</h3>
      <p>Tokens: {f?.tokens[selectedAgent] ?? "Unavailable at this tick"}</p>
      <details>
        <summary>Recorded local observation</summary>
        <pre tabIndex={0}>
          {JSON.stringify(
            f?.local_observations?.[selectedAgent] ??
              "Unavailable at this tick",
            null,
            2,
          )}
        </pre>
      </details>
      <p>Goal: {f?.targets[selectedAgent]?.join(", ")}</p>
      <p>
        Recorded local observations:{" "}
        {f?.local_observations ? "Available in bundle" : "Unavailable"}
      </p>
      <details>
        <summary>Recorded current plan and commitments</summary>
        <pre tabIndex={0}>
          {JSON.stringify(
            {
              planned_path:
                f?.planned_paths[selectedAgent] ?? "Unavailable at this tick",
              commitments:
                f?.commitments?.[selectedAgent] ?? "Unavailable at this tick",
            },
            null,
            2,
          )}
        </pre>
      </details>
      <details>
        <summary>Executed trajectory (hindsight)</summary>
        <pre tabIndex={0}>
          {JSON.stringify(r.paths[selectedAgent], null, 2)}
        </pre>
      </details>
    </section>
  );
}
