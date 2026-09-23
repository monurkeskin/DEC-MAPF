import type { SolverRunResult } from "../api/types";
export function RunMetrics({ result: r }: { result: SolverRunResult }) {
  return (
    <>
      <dl className="metrics">
        <dt>Solver outcome</dt>
        <dd>{r.solver_outcome}</dd>
        <dt>Independent check</dt>
        <dd data-testid="validation-status">
          {r.validation?.status || "not_checked"}
        </dd>
        <dt>Makespan</dt>
        <dd>{r.makespan} ticks</dd>
        <dt>Sum of costs</dt>
        <dd>{r.sum_of_costs} actions</dd>
        <dt>Solver time</dt>
        <dd>{r.runtime_ms.toFixed(2)} ms</dd>
        <dt>Negotiations</dt>
        <dd>
          {r.metric_availability.negotiation_count
            ? r.negotiation_count
            : "Unavailable"}
        </dd>
        <dt>Measured sharing</dt>
        <dd>
          {r.metric_availability.information_sharing_rate
            ? `${(100 * r.information_sharing_rate).toFixed(2)}%`
            : "Unavailable"}
        </dd>
        <dt>Delivered messages / bytes</dt>
        <dd>
          {String(r.measured_metrics?.message_count ?? "Unavailable")} /{" "}
          {String(r.measured_metrics?.payload_bytes ?? "Unavailable")}
        </dd>
      </dl>
      <details>
        <summary>Metric scope</summary>
        <p>
          Solved costs count actions until first goal arrival. Only
          independently valid solved runs enter cost comparisons. Sharing uses
          actual delivered recipient payloads; spatial and space-time
          definitions are stored separately. Historical proxy estimates remain
          separate from measured values.
        </p>
      </details>
    </>
  );
}
