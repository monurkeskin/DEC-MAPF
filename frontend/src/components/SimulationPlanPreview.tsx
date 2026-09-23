import type { JobSubmissionRequest, Plan } from "../api/types";
import { HeadlessStudyExport } from "./HeadlessStudyExport";
import { ProblemAssumptions } from "./ProblemAssumptions";
export function SimulationPlanPreview({
  plan,
  portableInput,
  start,
}: {
  plan: Plan;
  portableInput: JobSubmissionRequest | null;
  start: () => Promise<void>;
}) {
  return (
    <section className="plan">
      <strong>
        {plan.count} run ·{" "}
        {plan.maximum_process_seconds === null
          ? "No per-trial time cap"
          : `≤${plan.maximum_process_seconds}s process`}
        budget
      </strong>
      <p>
        Inactive controls:{" "}
        {plan.plans[0].inactive_parameters.join(", ") || "none"}
      </p>
      {plan.plans[0].semantics && (
        <ProblemAssumptions semantics={plan.plans[0].semantics} />
      )}
      <details>
        <summary>Exact effective configuration</summary>
        <pre tabIndex={0}>{JSON.stringify(plan.plans[0], null, 2)}</pre>
      </details>
      {portableInput && <HeadlessStudyExport portableInput={portableInput} />}
      <button className="primary" onClick={start}>
        Run simulation
      </button>
    </section>
  );
}
