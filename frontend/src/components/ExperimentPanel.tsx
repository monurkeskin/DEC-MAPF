import { useEffect, useState } from "react";
import { PairExplorer } from "./PairExplorer";
import { post, request } from "../api/client";
import type { ExperimentAnalysis, SolverCapability } from "../api/types";

type Manifest = {
  experiment_id: string;
  manifest_digest: string;
  trials: unknown[];
  budget: { wall_seconds: number; workers: number };
  maximum_process_seconds: number | null;
};
type Summary = {
  experiment_id: string;
  state: string;
  planned: number;
  successful: number;
  counts: Record<string, number>;
  elapsed_seconds: number;
  driver_error?: string;
};
const example = {
  name: "Local four-setting verification",
  scenarios: [{ scenario_id: "crossing-2a" }, { scenario_id: "grid-8x8-4a" }],
  defaults: { max_steps: 40, timeout_sec: 5, recording_level: "metrics-only" },
  matrix: {
    solver_id: ["CBS", "Prioritized"],
    setting: ["SETTING_1", "SETTING_2", "SETTING_3", "SETTING_4"],
  },
  budget: {
    workers: 2,
    wall_seconds: 90,
    max_trials: 32,
    disk_mb: 256,
    threads_per_worker: 1,
  },
  sampling: {
    population:
      "Two declared regression fixtures; no population generalization",
    independent_unit: "scenario geometry and roster",
  },
};
function download(name: string, body: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(body, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
export function ExperimentPanel({
  capabilities,
}: {
  capabilities: SolverCapability[];
}) {
  const [spec, setSpec] = useState(JSON.stringify(example, null, 2));
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [id, setId] = useState(localStorage.getItem("mapf-experiment") || "");
  const [library, setLibrary] = useState<
    { experiment_id: string; name: string; state: string }[]
  >([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [left, setLeft] = useState("CBS"),
    [right, setRight] = useState("Prioritized");
  const [filters, setFilters] = useState("{}");
  const [analysis, setAnalysis] = useState<ExperimentAnalysis | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fail = (e: unknown) => setError(String(e));
  async function refresh() {
    setLibrary(await request<typeof library>("/experiments"));
  }
  useEffect(() => {
    const controller = new AbortController();
    request<typeof library>("/experiments", { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setLibrary(value);
      })
      .catch((e) => {
        if (!controller.signal.aborted) fail(e);
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!id) return;
    localStorage.setItem("mapf-experiment", id);
    const controller = new AbortController();
    let polling = false;
    const update = async () => {
      if (polling) return;
      polling = true;
      try {
        const value = await request<Summary>(
          `/experiments/${encodeURIComponent(id)}`,
          { signal: controller.signal },
        );
        if (!controller.signal.aborted) setSummary(value);
      } catch (e) {
        if (!controller.signal.aborted) fail(e);
      } finally {
        polling = false;
      }
    };
    update();
    const timer = window.setInterval(update, 1500);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [id]);
  async function preview() {
    setBusy(true);
    setError("");
    setManifest(null);
    try {
      setManifest(
        await post<Manifest>("/experiments/preview", JSON.parse(spec)),
      );
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function execute(resume = false, retry_failed = false) {
    setBusy(true);
    setError("");
    try {
      const frozen = resume
        ? await request<Manifest>(`/experiments/${id}/manifest`)
        : manifest;
      const result = await post<{ experiment_id: string }>("/experiments", {
        manifest: frozen,
        resume,
        retry_failed,
      });
      setId(result.experiment_id);
      setAnalysis(null);
      await refresh();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function analyze() {
    setBusy(true);
    setError("");
    setAnalysis(null);
    try {
      setAnalysis(
        await post<ExperimentAnalysis>(`/experiments/${id}/analysis`, {
          left,
          right,
          filters: JSON.parse(filters),
        }),
      );
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function exportFigures() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/v1/experiments/${id}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          left,
          right,
          filters: JSON.parse(filters),
          expected_cohort_sha256: analysis?.cohort_sha256,
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "experiment-analysis.zip";
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card" aria-label="Comprehensive experiments">
      <h2>Complete experiments</h2>
      <p>
        Freeze a Cartesian matrix with explicit exclusions and local budgets.
        The same manifest runs with <code>mapf batch run</code> without the GUI.
      </p>
      {error && <p role="alert">{error}</p>}
      <details>
        <summary>Configure experiment matrix</summary>
        <label>
          Experiment specification JSON
          <textarea
            rows={12}
            value={spec}
            disabled={busy}
            onChange={(e) => {
              setSpec(e.target.value);
              setManifest(null);
            }}
          />
        </label>
        <button disabled={busy} onClick={preview}>
          Preview experiment manifest
        </button>
        {manifest && (
          <div>
            <p>
              {manifest.trials.length} planned trials ·{" "}
              {manifest.budget.workers} workers · wall budget{" "}
              {manifest.budget.wall_seconds}s · worst-case process time{" "}
              {manifest.maximum_process_seconds === null
                ? "No per-trial time cap; experiment budget applies"
                : `${manifest.maximum_process_seconds}s`}
            </p>
            <div className="button-row">
              <button disabled={busy} onClick={() => execute()}>
                Run frozen experiment
              </button>
              <button
                onClick={() => download("experiment-manifest.json", manifest)}
              >
                Download frozen manifest
              </button>
            </div>
            <details>
              <summary>Exact manifest and exclusions</summary>
              <pre tabIndex={0}>{JSON.stringify(manifest, null, 2)}</pre>
            </details>
          </div>
        )}
      </details>
      <label>
        Saved experiment
        <select
          value={id}
          disabled={busy}
          onChange={(e) => {
            setId(e.target.value);
            setSummary(null);
            setAnalysis(null);
          }}
        >
          <option value="">Select an experiment</option>
          {library.map((e) => (
            <option key={e.experiment_id} value={e.experiment_id}>
              {e.name} · {e.state}
            </option>
          ))}
        </select>
      </label>
      <button onClick={() => refresh().catch(fail)}>Refresh experiments</button>
      {id && summary && (
        <>
          <p data-testid="experiment-status">
            {summary.state} · {summary.successful}/{summary.planned} planned
            trials independently solved · {summary.elapsed_seconds.toFixed(1)}s
            charged
          </p>
          <pre tabIndex={0}>{JSON.stringify(summary.counts, null, 2)}</pre>
          {summary.driver_error && <p role="alert">{summary.driver_error}</p>}
          <div className="button-row">
            <button
              disabled={busy || summary.state === "running"}
              onClick={() => execute(true)}
            >
              Resume unfinished experiment
            </button>
            <button
              disabled={busy || summary.state === "running"}
              onClick={() => execute(true, true)}
            >
              Retry failed trials as new attempts
            </button>
            <button
              disabled={summary.state !== "running"}
              onClick={() => post(`/experiments/${id}/stop`, {}).catch(fail)}
            >
              Stop experiment
            </button>
            <button
              onClick={() =>
                request(`/experiments/${id}/rows`)
                  .then((rows) => download("all-planned-trials.json", rows))
                  .catch(fail)
              }
            >
              Download all planned outcomes
            </button>
          </div>
          <div className="two-cols">
            <label>
              Left method
              <select
                value={left}
                disabled={busy}
                onChange={(e) => {
                  setLeft(e.target.value);
                  setAnalysis(null);
                }}
              >
                {capabilities.map((c) => (
                  <option key={c.solver_id} value={c.solver_id}>
                    {c.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Right method
              <select
                value={right}
                disabled={busy}
                onChange={(e) => {
                  setRight(e.target.value);
                  setAnalysis(null);
                }}
              >
                {capabilities.map((c) => (
                  <option key={c.solver_id} value={c.solver_id}>
                    {c.display_name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            Cohort filters JSON (field to allowed values)
            <input
              value={filters}
              disabled={busy}
              onChange={(e) => {
                setFilters(e.target.value);
                setAnalysis(null);
              }}
            />
          </label>
          <button disabled={busy || left === right} onClick={analyze}>
            Analyze all planned trials
          </button>
          {analysis && (
            <>
              <table>
                <caption>
                  Planned-trial denominator; intervals resample scenario blocks
                </caption>
                <thead>
                  <tr>
                    <th>Method</th>
                    <th>Solved / planned</th>
                    <th>Scenario-weighted success</th>
                    <th>95% interval</th>
                    <th>Independent units</th>
                  </tr>
                </thead>
                <tbody>
                  {(["left", "right"] as const).map((side) => {
                    const s = analysis[side];
                    return (
                      <tr key={side}>
                        <th>{analysis[`${side}_solver`]}</th>
                        <td>
                          {s.solved}/{s.planned}
                        </td>
                        <td>
                          {s.scenario_weighted_success_rate === null
                            ? "Unavailable"
                            : `${(s.scenario_weighted_success_rate * 100).toFixed(1)}%`}
                        </td>
                        <td>
                          {s.interval
                            ?.map((v) => `${(100 * v).toFixed(1)}%`)
                            .join(" – ") || "Insufficient independent units"}
                        </td>
                        <td>{s.independent_units}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p>
                Common solved: {analysis.coverage.both_solved} · left only:{" "}
                {analysis.coverage.left_only} · right only:{" "}
                {analysis.coverage.right_only} · neither:{" "}
                {analysis.coverage.neither} · unpaired:{" "}
                {analysis.coverage.unpaired}
              </p>
              <p>
                Cost difference (right − left, common solved):{" "}
                {String(
                  analysis.cost.mean_delta_right_minus_left ?? "Unavailable",
                )}
              </p>
              <p className="muted">
                {analysis.scope} {analysis.runtime_policy}
              </p>
              <PairExplorer analysis={analysis} />
              <button disabled={busy} onClick={exportFigures}>
                Export tables and figures (CSV / LaTeX / SVG / PDF)
              </button>
              <details>
                <summary>Analysis method, cohort identity and pairs</summary>
                <pre tabIndex={0}>{JSON.stringify(analysis, null, 2)}</pre>
              </details>
            </>
          )}
        </>
      )}
    </section>
  );
}
