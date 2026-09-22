import { RunLibraryPanel } from "./components/RunLibraryPanel";
import { useRunLibrary } from "./hooks/useRunLibrary";
import { STARTER_INPUTS } from "./api/presets.generated";
import { ComparisonPanel } from "./components/ComparisonPanel";
import { BatchControls } from "./components/BatchControls";
import { useBatchDraft } from "./hooks/useBatchDraft";
import { ArtifactPanel } from "./components/ArtifactPanel";
import { SimulationControls } from "./components/SimulationControls";
import { useJobMonitor, terminal } from "./hooks/useJobMonitor";
import { useRunComparison } from "./hooks/useRunComparison";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelJob,
  fetchCapabilities,
  fetchRunDetails,
  fetchScenario,
  fetchScenarios,
  post,
  request,
  submitSimulationJob,
} from "./api/client";
import type {
  JobStatusResponse,
  JobSubmissionRequest,
  Plan,
  RunDetail,
  ScenarioDetail,
  ScenarioSummary,
  SolverCapability,
} from "./api/types";
import { GridViewport } from "./components/GridViewport";
import { DecisionHeatPanel } from "./components/DecisionHeatPanel";
import { InspectorPanel } from "./components/InspectorPanel";
import { ScenarioEditor } from "./components/ScenarioEditor";
import { TimelineScrubber } from "./components/TimelineScrubber";
import { useReplayFrame } from "./useReplayFrame";
import { restoreJobOptions, scenarioRequest } from "./study";

const defaults: JobSubmissionRequest = STARTER_INPUTS;
const workflows = ["Configure", "Inspect", "Compare", "Export"] as const;
type Workflow = (typeof workflows)[number];

export default function App() {
  const [initialLink] = useState(() => new URLSearchParams(location.search));
  const [screen, setScreen] = useState<Workflow>("Configure"),
    [theme, setTheme] = useState(localStorage.getItem("mapf-theme") || "dark");
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]),
    [caps, setCaps] = useState<SolverCapability[]>([]);
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null),
    [scenarioId, setScenarioId] = useState("crossing-2a");
  const [options, setOptions] = useState<JobSubmissionRequest>(defaults),
    [planDraft, setPlan] = useState<Plan | null>(null),
    [planFor, setPlanFor] = useState("");
  const [history, setHistory] = useState<ScenarioDetail[]>([]),
    [future, setFuture] = useState<ScenarioDetail[]>([]),
    [editing, setEditing] = useState(false);
  const [initialJobId] = useState(
    initialLink.has("run") ? "" : localStorage.getItem("mapf-job") || "",
  );
  const [jobId, setJobId] = useState(initialJobId);
  const [jobs, setJobs] = useState<JobStatusResponse[]>([]),
    [run, setRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true),
    [submitting, setSubmitting] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [tick, setTick] = useState(0),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1),
    [agent, setAgent] = useState<string | null>(null);
  const [paths, setPaths] = useState(true),
    [heat, setHeat] = useState(false),
    [fov, setFov] = useState(false),
    [localView, setLocalView] = useState(false),
    [reservations, setReservations] = useState(false);
  const [localHeat, setLocalHeat] = useState(false);
  const [heatDecision, setHeatDecision] = useState("");
  const [heatOffset, setHeatOffset] = useState(-1);
  const batchState = useBatchDraft();
  const submitKey = useRef<string | null>(null),
    loadedRun = useRef(""),
    selectionRevision = useRef(0),
    selectionRequest = useRef<AbortController | null>(null);
  const inputSignature = JSON.stringify([options, scenario]);
  const plan = planFor === inputSignature ? planDraft : null;
  const reportError = useCallback((e: unknown) => {
    setError(e instanceof Error ? e.message : String(e));
    setLoading(false);
  }, []);
  const library = useRunLibrary(reportError);
  const runs = library.items;
  const refreshLibrary = library.refresh;
  const refresh = useCallback(async () => {
    const [, js] = await Promise.all([
      refreshLibrary(),
      request<JobStatusResponse[]>("/jobs"),
    ]);
    setJobs(js);
  }, [refreshLibrary]);
  const loadRun = useCallback(
    async (id: string, isCurrent: () => boolean = () => true) => {
      const revision = ++selectionRevision.current;
      selectionRequest.current?.abort();
      const controller = new AbortController();
      selectionRequest.current = controller;
      let data: RunDetail;
      try {
        data = await fetchRunDetails(id, controller.signal);
      } catch (e) {
        if (controller.signal.aborted) return;
        throw e;
      }
      if (revision !== selectionRevision.current || !isCurrent()) return;
      loadedRun.current = id;
      setRun(data);
      setScenario(data.metadata.instance);
      setOptions(restoreJobOptions(data.metadata.effective_config));
      setScenarioId("");
      setAgent(null);
      setPlaying(false);
      setEditing(false);
      setPlan(null);
      setTick(
        Math.min(
          Math.max(
            0,
            Number(
              new URLSearchParams(location.search).get("run") === id
                ? new URLSearchParams(location.search).get("tick") || 0
                : sessionStorage.getItem(`tick-${id}`) || 0,
            ) || 0,
          ),
          Math.max(0, data.metadata.frame_count - 1),
        ),
      );
      setScreen("Inspect");
    },
    [],
  );
  const loadScenario = useCallback(async (id: string) => {
    const revision = ++selectionRevision.current;
    selectionRequest.current?.abort();
    const data = await fetchScenario(id);
    if (revision !== selectionRevision.current) return;
    setScenario(data);
    setScenarioId(id);
    setOptions((o) => ({ ...o, setting: data.setting }));
    setRun(null);
    loadedRun.current = "";
    setTick(0);
    setAgent(null);
    setPlaying(false);
    setPlan(null);
    setHistory([]);
    setFuture([]);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("mapf-theme", theme);
  }, [theme]);
  useEffect(() => {
    let alive = true;
    Promise.all([
      fetchCapabilities(),
      fetchScenarios(),
      request<JobStatusResponse[]>("/jobs"),
    ])
      .then(async ([c, s, js]) => {
        if (!alive) return;
        setCaps(c);
        setScenarios(s);
        setJobs(js);
        const linkedRun = initialLink.get("run");
        if (linkedRun) await loadRun(linkedRun, () => alive);
        else if (!initialJobId) await loadScenario("crossing-2a");
        setLoading(false);
      })
      .catch(reportError);
    return () => {
      alive = false;
    };
  }, [initialJobId, initialLink, loadRun, loadScenario, reportError]);
  const { job, setJob, connection } = useJobMonitor({
    jobId,
    loadedRun,
    loadRun,
    refresh,
    reportError,
    setNotice,
    setError,
  });
  const busy = submitting || (!!job && !terminal.has(job.state));
  useEffect(() => {
    if (run) {
      sessionStorage.setItem(`tick-${run.metadata.run_id}`, String(tick));
      const link = new URL(location.href);
      link.searchParams.set("run", run.metadata.run_id);
      link.searchParams.set("tick", String(tick));
      window.history.replaceState(null, "", link);
    } else if (!loading) {
      const link = new URL(location.href);
      link.searchParams.delete("run");
      link.searchParams.delete("tick");
      window.history.replaceState(null, "", link);
    }
  }, [tick, run, loading]);

  const changeDraft = (next: ScenarioDetail) => {
    selectionRevision.current++;
    if (scenario) setHistory((h) => [...h.slice(-49), scenario]);
    setFuture([]);
    setScenario(next);
    setRun(null);
    loadedRun.current = "";
    setScenarioId("");
    setPlaying(false);
    setTick(0);
  };
  const saved = async (s: ScenarioDetail) => {
    setScenario(s);
    setScenarioId(s.scenario_id || "");
    setScenarios(await fetchScenarios());
    setNotice("Saved a new immutable scenario snapshot");
  };
  function input(): JobSubmissionRequest {
    if (!scenario) throw new Error("Load a scenario first");
    return scenarioRequest(options, scenario);
  }
  const preview = async () => {
    setError("");
    submitKey.current = null;
    try {
      setPlan(await post<Plan>("/plans/preview", { jobs: [input()] }));
      setPlanFor(inputSignature);
    } catch (e) {
      reportError(e);
    }
  };
  const start = async () => {
    if (!plan || submitting) return;
    setSubmitting(true);
    setError("");
    submitKey.current ??= crypto.randomUUID();
    try {
      const result = await submitSimulationJob(input(), submitKey.current);
      setJob(result);
      setJobId(result.job_id);
      setRun(null);
      loadedRun.current = "";
      setPlaying(false);
      setTick(0);
      await refresh();
    } catch (e) {
      reportError(e);
    } finally {
      setSubmitting(false);
    }
  };
  const resetComparisonPlayback = useCallback(() => {
    setTick(0);
    setPlaying(false);
  }, []);
  const comparisonModel = useRunComparison(
    reportError,
    resetComparisonPlayback,
    setError,
  );
  const result = run?.result || null;
  const solverDiagnostics = result?.measured_metrics?.solver_diagnostics;
  const stoppedNegotiation =
    solverDiagnostics &&
    typeof solverDiagnostics === "object" &&
    "last_negotiation_failure" in solverDiagnostics
      ? solverDiagnostics.last_negotiation_failure
      : null;
  const timeoutDiagnostics =
    job?.timeout_diagnostics ||
    (stoppedNegotiation &&
    typeof stoppedNegotiation === "object" &&
    "diagnostics" in stoppedNegotiation
      ? stoppedNegotiation.diagnostics
      : null);
  const maxTick =
    screen === "Compare"
      ? comparisonModel.maxTick
      : (run?.metadata.frame_count || 1) - 1;
  const seek = useCallback(
    (t: number) => {
      setTick(Math.max(0, Math.min(t, maxTick)));
    },
    [maxTick],
  );
  const replay = useReplayFrame(run, tick);
  const currentFrame = replay.frame;
  const heatDecisions = (currentFrame?.local_heat || []).filter(
    (record) => record.agent_id === agent,
  );
  const currentHeat =
    heatDecisions.find((record) => record.record_id === heatDecision) ||
    heatDecisions.at(-1);
  const selectedHeatOffset =
    currentHeat && heatOffset < currentHeat.fields.length ? heatOffset : -1;
  const localHeatGrid =
    localHeat && currentHeat?.status === "recorded"
      ? selectedHeatOffset < 0
        ? currentHeat.aggregate
        : currentHeat.fields[selectedHeatOffset] || {}
      : undefined;
  const importReplay = async (file: File) => {
    try {
      if (file.size > 16 * 1024 * 1024)
        throw new Error("Import exceeds 16 MiB");
      const r = await post<{ run_id: string }>(
        "/runs/import",
        JSON.parse(await file.text()),
      );
      setJobId("");
      setJob(null);
      localStorage.removeItem("mapf-job");
      await loadRun(r.run_id);
      await refresh();
      setNotice("Bundle integrity and trajectory receipt verified");
    } catch (e) {
      reportError(e);
    }
  };
  const editCell = (x: number, y: number) => {
    if (!scenario) return;
    const exists = scenario.obstacles.some((p) => p[0] === x && p[1] === y);
    changeDraft({
      ...scenario,
      obstacles: exists
        ? scenario.obstacles.filter((p) => p[0] !== x || p[1] !== y)
        : [...scenario.obstacles, [x, y]],
    });
  };
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to workspace
      </a>
      <header className="app-header">
        <div>
          <strong>DEC-MAPF</strong>
          <span className="brand-sub">Alpha · Research workspace</span>
          <a
            className="brand-sub"
            href="/THIRD_PARTY_NOTICES.txt"
            target="_blank"
            rel="noopener noreferrer"
          >
            Open-source notices
          </a>
        </div>
        <nav aria-label="Workflow">
          {workflows.map((w) => (
            <button
              key={w}
              aria-current={screen === w ? "page" : undefined}
              onClick={() => {
                setScreen(w);
                setPlaying(false);
                setTick(0);
              }}
            >
              {w}
            </button>
          ))}
        </nav>
        <button
          aria-label="Toggle light or dark theme"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark" ? "Light theme" : "Dark theme"}
        </button>
      </header>
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
      {loading && (
        <p role="status" className="loading">
          Loading local workspace…
        </p>
      )}
      <div className="workspace-container">
        <aside className="sidebar-panel" aria-label="Experiment controls">
          <h2>
            {screen === "Configure"
              ? "Configure experiment"
              : "Workspace library"}
          </h2>
          <p className="hint">
            Interactive starter v1 · edit controls to customize. Saved runs
            restore their recorded settings.
          </p>
          {screen === "Configure" && !run && (
            <section aria-label="First session guide" className="plan">
              <h3>Your first checked replay</h3>
              <ol>
                <li>
                  Keep the two-agent crossing, or select the four-agent grid.
                </li>
                <li>Preview the inputs and problem assumptions, then run.</li>
                <li>
                  Check validation, step through ticks in Inspect, then Export.
                </li>
              </ol>
              <p className="hint">
                This starter is a teaching fixture. Its short process guard and
                search limits are not the article benchmark configuration.
              </p>
            </section>
          )}
          <SimulationControls
            portableInput={scenario ? input() : null}
            {...{
              busy,
              options,
              setOptions,
              scenarioId,
              loadScenario,
              scenarios,
              scenario,
              changeDraft,
              caps,
              plan,
              preview,
              start,
              reportError,
            }}
          />
          {busy && job && (
            <button
              className="danger"
              onClick={() =>
                cancelJob(job.job_id).then(refresh).catch(reportError)
              }
            >
              Cancel computation
            </button>
          )}
          {screen === "Configure" && scenario && (
            <fieldset disabled={busy}>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={editing}
                  onChange={(e) => setEditing(e.target.checked)}
                />
                Edit obstacles on grid
              </label>
              <ScenarioEditor
                scenario={scenario}
                onChange={changeDraft}
                onSaved={(s) => {
                  saved(s).catch(reportError);
                }}
                onError={reportError}
                canUndo={!!history.length}
                canRedo={!!future.length}
                undo={() => {
                  if (!history.length) return;
                  setFuture((f) => [scenario, ...f]);
                  setScenario(history[history.length - 1]);
                  setHistory((h) => h.slice(0, -1));
                  setRun(null);
                }}
                redo={() => {
                  if (!future.length) return;
                  setHistory((h) => [...h, scenario]);
                  setScenario(future[0]);
                  setFuture((f) => f.slice(1));
                  setRun(null);
                }}
              />
            </fieldset>
          )}
          <RunLibraryPanel
            library={library}
            open={screen !== "Configure"}
            reportError={reportError}
            select={(id) => {
              setJobId("");
              setJob(null);
              localStorage.removeItem("mapf-job");
              loadRun(id).catch(reportError);
            }}
          />
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
        </aside>
        <main id="main" className="viewport-area" tabIndex={-1}>
          {(screen === "Configure" || screen === "Inspect") && (
            <>
              <div className="view-heading">
                <div>
                  <h1>
                    {run
                      ? "Replay & diagnostics"
                      : scenario?.name || "Load a scenario"}
                  </h1>
                  <p className="muted">
                    {run
                      ? `${run.metadata.run_id} · ${run.metadata.validation_status}`
                      : "Draft scenario · independent validation runs after solving"}
                  </p>
                </div>
              </div>
              <div className="layer-bar">
                {(
                  [
                    ["Executed paths", paths, setPaths],
                    ["Hindsight heat", heat, setHeat],
                    ["Recorded local heat", localHeat, setLocalHeat],
                    ["FoV geometry", fov, setFov],
                    ["Recorded local view", localView, setLocalView],
                    ["Recorded reservations", reservations, setReservations],
                  ] as const
                ).map(([label, checked, set]) => (
                  <label className="checkbox" key={label}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        set(e.target.checked);
                        if (e.target.checked && label === "Hindsight heat")
                          setLocalHeat(false);
                        if (e.target.checked && label === "Recorded local heat")
                          setHeat(false);
                      }}
                    />
                    {label}
                  </label>
                ))}
              </div>
              <p className="legend">
                ● Agent · □ Goal · ■ Obstacle. Paths and hindsight heat use
                executed history; teal local heat uses recorded strategy
                weights. Amber dashed cells show recorded opponent reservations
                with absolute ticks (full trace, selected owner or all). Local
                view shows the selected recipient's recorded observation and
                static map.
              </p>
              {replay.loading && <p role="status">Loading replay frames…</p>}
              {replay.error && <p role="alert">{replay.error}</p>}
              {localHeat && (
                <DecisionHeatPanel
                  records={heatDecisions}
                  selected={currentHeat}
                  offset={selectedHeatOffset}
                  omitted={currentFrame?.local_heat_omitted || 0}
                  onSelect={(id) => {
                    setHeatDecision(id);
                    setHeatOffset(-1);
                  }}
                  onOffset={setHeatOffset}
                />
              )}
              {localView && (
                <p role="status">
                  {agent && currentFrame?.local_observations?.[agent]
                    ? `Observation for ${agent} at t=${currentFrame.local_observations[agent].tick}; received paths are beliefs at that observation time.`
                    : "Select an agent with a recorded local observation. No global agent state is shown in local view."}
                </p>
              )}
              {scenario && (
                <GridViewport
                  gridWidth={scenario.grid_width}
                  gridHeight={scenario.grid_height}
                  obstacles={scenario.obstacles}
                  starts={scenario.starts}
                  goals={scenario.goals}
                  currentFrame={currentFrame}
                  paths={result?.paths}
                  selectedAgent={agent}
                  onSelectAgent={setAgent}
                  onEditCell={
                    editing && screen === "Configure" ? editCell : undefined
                  }
                  showPaths={paths}
                  showHeat={heat}
                  localHeatGrid={localHeatGrid}
                  showFov={fov}
                  showReservations={reservations}
                  localView={localView}
                  fovSize={options.fov_size}
                />
              )}
              <TimelineScrubber
                currentTick={tick}
                totalTicks={Math.max(0, maxTick)}
                isPlaying={playing}
                speed={speed}
                onSeek={seek}
                onTogglePlay={() => setPlaying((p) => !p)}
                onChangeSpeed={setSpeed}
                onJumpToFirstViolation={
                  result?.validation?.first_violation_tick != null
                    ? () => {
                        setPlaying(false);
                        seek(result.validation!.first_violation_tick!);
                      }
                    : undefined
                }
              />
            </>
          )}
          {screen === "Compare" && (
            <section className="content-scroll">
              <ComparisonPanel
                model={comparisonModel}
                {...{
                  runs,
                  tick,
                  playing,
                  speed,
                  setTick,
                  setPlaying,
                  setSpeed,
                  seek,
                }}
              />
              <BatchControls
                state={batchState}
                {...{ caps, input, refresh, reportError, setNotice }}
              />
            </section>
          )}
          {screen === "Export" && (
            <ArtifactPanel
              {...{ run, tick, importReplay, setNotice, reportError }}
            />
          )}
        </main>
        {(screen === "Configure" || screen === "Inspect") && (
          <InspectorPanel
            runResult={result}
            currentFrame={currentFrame}
            selectedAgent={agent}
            onSelectAgent={setAgent}
            onSeek={(t) => {
              setPlaying(false);
              seek(t);
            }}
          />
        )}
      </div>
    </>
  );
}
