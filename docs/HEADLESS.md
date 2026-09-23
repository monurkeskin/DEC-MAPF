# Run a study without the GUI

[Documentation index](README.md) · Prerequisite: [Installation](INSTALLATION.md)

Use the CLI to plan scenario/configuration combinations, run isolated solver processes, validate trajectories and export every planned outcome. Each attempt remains in the experiment journal. You do not need FastAPI, a browser, Node, or a running GUI server.

## 1. Freeze a small method comparison

The [comparison specification](../examples/method-comparison.json) runs HeatMap, PathAware, CBS and Prioritized Planning on two scenarios: eight trials in total. All methods receive the same scenario and physical setting. Its one-worker, 120-second study budget and 15-second process caps are teaching settings, not article settings. The [negotiation-only example](../examples/negotiation-tutorial.json) retains a smaller four-trial study of HeatMap and PathAware.

```bash
uv sync --locked --python 3.12
mkdir -p runs/tutorial
uv run --no-sync mapf batch plan examples/method-comparison.json --output runs/tutorial/manifest.json
```

Planning does not run a solver. Read `trials[*].plan.scenario`, `effective_config`, `warnings`, `budget`, `sampling` and `excluded` in the manifest. Every scenario is an ordered coordinate snapshot. The manifest records the source hash, effective configuration and version metadata alongside these inputs.

```bash
uv run --no-sync python -m json.tool runs/tutorial/manifest.json
```

Keep that manifest. Edit the specification and plan a new study if an input is wrong; do not hand-edit a frozen manifest or its digest.

## 2. Execute and check outcomes

```bash
uv run --no-sync mapf batch run runs/tutorial/manifest.json --workspace runs/tutorial/workspace
uv run --no-sync mapf batch status --workspace runs/tutorial/workspace
```

The command waits for completion or a study budget/interrupt condition. When it stops, the summary includes `planned`, `counts`, `successful`, `success_rate` and elapsed driver time. `completed` means the job returned an artifact; inspect `success` and `validation_status` for the scientific result. Failed or timed-out trials remain part of the planned denominator.

If the exact experiment already exists, use the explicit resume command below. For another independent demonstration, use a new output directory. Reusing the same completed study is not a new replicate.

## 3. Export every planned trial

In a POSIX shell, read the ID rather than copying a sample ID from a guide:

```bash
EXPERIMENT_ID=$(uv run --no-sync python -c 'import json; print(json.load(open("runs/tutorial/manifest.json"))["experiment_id"])')
uv run --no-sync mapf batch status "$EXPERIMENT_ID" --workspace runs/tutorial/workspace
uv run --no-sync mapf batch export "$EXPERIMENT_ID" --workspace runs/tutorial/workspace --output runs/tutorial/all-trials.csv
uv run --no-sync mapf batch export "$EXPERIMENT_ID" --workspace runs/tutorial/workspace --output runs/tutorial/all-trials.json
```

The CSV includes unsuccessful trials and trials that never started, execution/validation states, attempt counts, run identities and effective parameters. Nested diagnostics are JSON values inside CSV fields. Do not read only completed run files and call their count the experiment's denominator.

## 4. Analyze matched strategies

Install analysis dependencies without changing the specification:

```bash
uv sync --locked --python 3.12 --extra analysis
uv run --no-sync mapf batch analyze "$EXPERIMENT_ID" --workspace runs/tutorial/workspace --left Decentralized-HeatMap --right CBS --figures runs/tutorial/analysis --output runs/tutorial/analysis-summary.json
```

The analysis folder contains canonical analysis JSON, paired data, LaTeX and figures, together with input/cohort receipts. Pairing requires the same scenario, seed, source, metric version and non-treatment configuration. Success uses all planned trials. Cost differences use the **common valid solved** cohort, with its coverage explicitly reported.

This compares a decentralized method with a centralized solver. Use `--right Decentralized-PathAware` to compare the included negotiation strategies instead. Method-specific negotiation and communication measurements remain unavailable for centralized methods; they are not zero-valued observations. See [solver comparison inputs](SOLVERS.md#stable-comparison-inputs).

These two teaching scenarios cannot establish general performance or reproduce a paper. Scenario-block intervals, when available, describe the supplied sample and assumptions. Agents, ticks and repeated parameter settings are not independent experimental replicates. See [Scientific interpretation](SCIENCE.md) and [Experiment reference](EXPERIMENTS.md).

## 5. Build your own matrix

Copy the tutorial specification, then change explicit fields. For example:

```json
{
  "name": "Declared local pilot",
  "scenarios": [{"scenario_id": "grid-8x8-4a"}],
  "defaults": {
    "setting": "SETTING_4",
    "initial_tokens": 5,
    "max_steps": 100,
    "timeout_sec": 60,
    "negotiation_deadline_sec": 60,
    "recording_level": "metrics-only",
    "random_seed": 42
  },
  "matrix": {
    "solver_id": ["Decentralized-HeatMap", "Decentralized-PathAware"],
    "fov_size": [3, 5, 7],
    "commitment_type": ["SC", "DC", "ZC"]
  },
  "exclude": [],
  "budget": {"workers": 2, "wall_seconds": 1800, "max_trials": 18, "disk_mb": 512, "threads_per_worker": 1},
  "sampling": {"population": "One development fixture", "independent_unit": "scenario", "generalization": "none"}
}
```

This declares 1 × 2 × 3 × 3 = **18 trials**, but only one scenario unit. Defaults are overridden by each scenario, then by matrix values. Matrix axes form a Cartesian product. Each exclusion is a conjunction of field/value matches; matching any exclusion removes that combination and records why. `max_trials` bounds expansion **before exclusions**.

Use inline coordinates from [Scenarios](SCENARIOS.md) for external inputs. Do not assume a saved GUI scenario ID exists in an unrelated batch workspace: the portable CLI specification should carry the actual snapshot. If several treatments or nested agent rosters derive from one source scenario, declare their common `sampling_unit` rather than treating them as independent geometry samples.

The [generated parameter reference](PARAMETERS.md) lists actual request bounds. `mapf solvers` lists the core registry; persisted batch/API solver IDs use the application names shown in [Solvers](SOLVERS.md).

## 6. Interrupt, resume and retry deliberately

Ctrl+C stops the current CLI driver and its owned processes. The journal records interrupted work. Resume unfinished trials with:

```bash
uv run --no-sync mapf batch resume "$EXPERIMENT_ID" --workspace runs/tutorial/workspace
```

Resume keeps completed attempts; it does **not** restore an internal solver checkpoint or reset the study's elapsed wall budget. To explicitly retry failed, timed-out or cancelled trials:

```bash
uv run --no-sync mapf batch resume "$EXPERIMENT_ID" --workspace runs/tutorial/workspace --retry-failed
```

This creates new attempts with lineage. All attempts remain stored; the exported row uses the latest explicit attempt. Define retry/analysis policy before looking for favorable outcomes. A changed source or larger study budget requires a new manifest; never relabel an old experiment or overwrite its original outcomes.

## 7. Inspect visually when useful

Choose `events` or `full-trace` in advance for replay. Once the CLI runner has exited:

```bash
uv sync --locked --python 3.12 --extra gui --extra analysis
npm --prefix frontend ci
npm --prefix frontend run build
MAPF_WORKSPACE_DIR=runs/tutorial/workspace uv run --no-sync mapf dashboard --host 127.0.0.1 --port 8000
```

Load a saved run, replay its actual trajectory and export a checked bundle. Both interfaces read the same journal/artifacts. Keep one active owner per workspace; use a different directory for a concurrent GUI demonstration.

## Scaling responsibly

For read-only inspection, `mapf batch status`, `export` and `analyze` require an existing compatible workspace; a misspelled path creates no empty study. `mapf doctor --workspace PATH` inspects schema and record counts without acquiring the execution lease. A second driver is rejected before registering its manifest when another owner is active.

Progress queries read a small summary of current attempts and reuse verified success counts while the underlying artifacts remain unchanged. Full attempt histories and artifacts remain available for export. Missing artifacts stay in the planned denominator. This reduces monitoring I/O without changing the solver's search or deadline.

Fixed batch admission supports one to four workers, with one numerical-library thread per worker. An explicit resource policy supports up to six and admits work according to measured CPU/RAM and family limits; follow [resource-aware batches](RESOURCE-ADMISSION.md). More workers can reduce throughput when a solver's memory use or competing applications cause contention. The declared wall/disk budgets and per-process deadline serve different purposes. `maximum_process_seconds` in a plan is the sum of declared caps, not a runtime estimate; it is unavailable when any process cap is null.

Use `metrics-only` for broad studies and full traces for a declared diagnostic subset when storage matters. Recording settings are part of the experiment configuration and must be disclosed. Raw-byte volume depends heavily on event count, path length and heat recording; measure a pilot rather than infer it from agent count alone. Archive the complete stopped workspace before removing anything from it.

For article-related rosters and native centralized comparators, follow [Reproducibility](../REPRODUCIBILITY.md) and [Native baselines](NATIVE-BASELINES.md). `mapf batch` is the supported experiment controller.

## Start with a self-contained study

`mapf study init my-study` creates a four-trial project without running it. Follow [New study](NEW-STUDY.md) for execution, all-outcome export and metadata cards, or use a [complete experiment capsule](../examples/capsules/README.md). GUI previews can also download the same explicit scenario as `study.json`; `mapf batch plan` applies the shared planner.
