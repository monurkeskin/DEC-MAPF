import { post, request } from "../api/client";
import type {
  Plan,
  JobSubmissionRequest,
  SolverCapability,
} from "../api/types";
import type { useBatchDraft } from "../hooks/useBatchDraft";
import { saveJson } from "../artifacts";
import { ExperimentPanel } from "./ExperimentPanel";
type Props = {
  state: ReturnType<typeof useBatchDraft>;
  caps: SolverCapability[];
  input: () => JobSubmissionRequest;
  refresh: () => Promise<void>;
  reportError: (error: unknown) => void;
  setNotice: (message: string) => void;
};
export function BatchControls({
  state,
  caps,
  input,
  refresh,
  reportError,
  setNotice,
}: Props) {
  const {
    batchText,
    setBatchText,
    batchPlan,
    setBatchPlan,
    batchId,
    setBatchId,
  } = state;
  return (
    <>
      <h2>Bounded batch</h2>
      <ExperimentPanel capabilities={caps} />
      <div className="button-row">
        {["smoke-v1", "settings-smoke-v1"].map((id) => (
          <button
            key={id}
            onClick={async () => {
              try {
                const p = await request<
                  Plan & { jobs: JobSubmissionRequest[] }
                >(`/profiles/${id}`);
                setBatchText(JSON.stringify(p.jobs, null, 2));
                setBatchPlan(p);
              } catch (e) {
                reportError(e);
              }
            }}
          >
            Load {id}
          </button>
        ))}
      </div>
      <p className="muted">
        Each profile contains small software test scenarios. Article comparisons
        require a separately defined study and scenario selection.
      </p>
      <p>Up to 32 local jobs. Preview the expanded inputs before running.</p>
      <button
        onClick={() =>
          setBatchText(
            JSON.stringify(
              [input(), { ...input(), solver_id: "Prioritized" }],
              null,
              2,
            ),
          )
        }
      >
        Draft current scenario × two solvers
      </button>
      <label>
        Batch jobs JSON
        <textarea
          value={batchText}
          onChange={(e) => {
            setBatchText(e.target.value);
            setBatchPlan(null);
          }}
        />
      </label>
      <button
        onClick={async () => {
          try {
            setBatchPlan(
              await post<Plan>("/plans/preview", {
                jobs: JSON.parse(batchText),
              }),
            );
          } catch (e) {
            reportError(e);
          }
        }}
      >
        Preview batch
      </button>
      {batchPlan && (
        <>
          <p>
            {batchPlan.count} jobs · ≤
            {batchPlan.maximum_process_seconds === null
              ? "No per-trial time cap"
              : `${batchPlan.maximum_process_seconds}s total process budget`}
          </p>
          <details>
            <summary>Exact batch manifest</summary>
            <pre tabIndex={0}>{JSON.stringify(batchPlan, null, 2)}</pre>
          </details>
          <button
            onClick={() => saveJson("decmapf-batch-plan.json", batchPlan)}
          >
            Export plan
          </button>
          <button
            onClick={async () => {
              try {
                const b = await post<{ batch_id: string }>(
                  "/batches",
                  {
                    jobs: JSON.parse(batchText),
                    plan_digest: batchPlan.plan_digest,
                  },
                  crypto.randomUUID(),
                );
                setBatchId(b.batch_id);
                setBatchPlan(null);
                await refresh();
                setNotice("Batch admitted to the bounded local queue");
              } catch (e) {
                reportError(e);
              }
            }}
          >
            Run previewed batch
          </button>
        </>
      )}
      {batchId && (
        <button
          onClick={() =>
            post(`/batches/${batchId}/cancel`, {})
              .then(refresh)
              .catch(reportError)
          }
        >
          Cancel unfinished batch jobs
        </button>
      )}
    </>
  );
}
