# Python and local HTTP API

[Documentation index](README.md) · [Headless tutorial](HEADLESS.md) · [Parameters](PARAMETERS.md)

The durable application services are shared by the CLI and HTTP adapter. Direct solver calls remain useful for small integration examples, but they do not provide the parent watchdog and experiment journal of a supervised study.

## A supervised Python study

Run the complete [example](../examples/04_supervised_study.py):

```bash
uv run --no-sync python examples/04_supervised_study.py --workspace runs/python-study
```

It constructs a two-trial specification, compiles immutable inputs, executes one worker at a time, and writes the manifest and all-outcome JSON. It uses only core dependencies and refuses accidental reuse of an existing experiment. A terminal execution can contain unsolved cases; read the printed validation/outcome fields.

The essential service sequence is:

```python
from mapf.application.experiments import ExperimentService, compile_experiment
from mapf.application.runs import RunRepository

def run_study(spec, workspace):
    manifest = compile_experiment(spec)
    service = ExperimentService(RunRepository(workspace))
    summary = service.execute(manifest)
    rows = service.rows(manifest["experiment_id"])
    return manifest, summary, rows
```

Call this from a script guarded by `if __name__ == "__main__":`. Workers spawn fresh Python processes. In a notebook, prepare the JSON input and invoke `mapf batch` as a subprocess rather than creating a multiprocessing tree from an unguarded cell. Use explicit fresh workspace paths and archive stopped workspaces as complete units.

## Use the same named preset

The GUI starts from `interactive-v1`. Select it explicitly to reproduce those inputs through Python or a batch specification:

```python
from mapf.application.plans import preview
from mapf.application.presets import preset_request

plan = preview(preset_request("interactive-v1", scenario_id="crossing-2a"))
print(plan["definition_digest"], plan["semantics"])
```

HTTP clients obtain the same input model from `GET /api/v1/presets/interactive-v1`, then submit its `inputs` with a scenario to `/plans/preview`. A batch specification can set `"preset_id": "interactive-v1"`. Overrides apply in this order: preset, batch `defaults`, scenario fields, matrix treatment. Unknown preset IDs are errors. Explicit inputs in older specifications remain explicit; no named preset is silently added.

The interactive preset uses a 10-second process guard and three negotiation verification passes per tick. It preserves the original GUI starter, not the article protocol or every raw request-model default. Plans expose the actual effective inputs, inactive parameters and versioned problem assumptions. A new descriptive card does not change a trial's algorithm or parameter digest.

## Direct solver API

For a small in-process integration:

```python
from mapf import (
    CommitmentType, DecentralizedNegotiationSolver, MAPFInstance,
    Point, SimulationConfig, SimulationSetting,
)

instance = MAPFInstance(
    grid_width=5, grid_height=5,
    starts={"a": Point(0, 2), "b": Point(2, 0)},
    goals={"a": Point(4, 2), "b": Point(2, 4)},
)
config = SimulationConfig(
    grid_width=5, grid_height=5,
    setting=SimulationSetting.SETTING_4,
    commitment_type=CommitmentType.STANDARD,
    fov_size=5, initial_tokens=5, max_steps=40,
    negotiation_deadline_sec=60,
)
solution = DecentralizedNegotiationSolver(strategy="HeatMap").solve(instance, config)
print(solution.success, solution.metrics["independent_validation"])
if solution.success:
    print(solution.sum_of_costs, solution.makespan)
```

The built-in solver boundary performs independent validation and retains solver-reported values separately. This call is synchronous, has cooperative checks only, and does not automatically write an application replay bundle. Prefer supervised execution when you need hard preemption, retry lineage or portable artifacts. `mapf solve` is likewise an ad-hoc direct interface, not a replacement for `mapf batch`.

## Discover the HTTP contract

Start your independently owned local workspace using [Installation](INSTALLATION.md). Open `http://127.0.0.1:8000/docs` for interactive OpenAPI, or request:

```bash
curl --fail-with-body -sS http://127.0.0.1:8000/api/v1/health
curl --fail-with-body -sS http://127.0.0.1:8000/api/v1/capabilities
curl --fail-with-body -sS http://127.0.0.1:8000/api/v1/scenarios
```

The versioned schema is [openapi.json](gui/openapi.json). The frontend client types derive from it. Request models reject unknown fields; semantic checks additionally validate coordinates, supported settings and solver profiles.

For larger libraries, use `GET /api/v1/runs/page?limit=100`. It returns `items`, `total`, `next_cursor`, `solver_names` and `validation_statuses`; the default page size is 50. Filter with exact `solver_name`, `validation_status` or `experiment_id`. Forward `next_cursor` with the same filters. Ordering is by creation time and run ID, descending; a continuation excludes subsequently inserted records under ordinary append behavior. Refresh from the first page to include new arrivals. This is a paged live library, not a frozen analysis cohort. The `/runs?limit=...` list endpoint is also available.

## Preview, submit, poll and export

The following standalone standard-library client demonstrates one small supervised job. Save it as a script and run it against your own local server. A constant idempotency key intentionally refers to the same submission if the client is retried with identical inputs; choose a new key for a deliberately new execution.

```python
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

base = "http://127.0.0.1:8000/api/v1"

def api(path, payload=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Idempotency-Key"] = key
    request = Request(base + path,
                      data=None if payload is None else json.dumps(payload).encode(),
                      headers=headers)
    with urlopen(request, timeout=20) as response:
        return json.load(response)

job_input = {"scenario_id": "crossing-2a", "solver_id": "Decentralized-HeatMap",
             "setting": "SETTING_4", "fov_size": 5, "initial_tokens": 5,
             "max_steps": 40, "timeout_sec": 15, "recording_level": "full-trace"}
print(api("/plans/preview", {"jobs": [job_input]}))
job = api("/jobs", job_input, key="documentation-crossing-1")
terminal = {"completed", "failed", "timed_out", "cancelled", "interrupted"}
until = time.monotonic() + 45
while job["state"] not in terminal:
    if time.monotonic() >= until:
        api(f"/jobs/{job['job_id']}/cancel", {})
        raise RuntimeError("Client wait guard reached; inspect the job journal")
    time.sleep(0.2)
    job = api(f"/jobs/{job['job_id']}")
print(job["state"])
if job["state"] == "completed":
    run = api(f"/runs/{job['run_id']}")
    print(run["result"]["validation"])
    bundle = api(f"/runs/{job['run_id']}/export/json")
    Path("runs").mkdir(exist_ok=True)
    Path("runs/api-example-bundle.json").write_text(json.dumps(bundle))
```

The client wait guard is not the solver's deadline. If execution times out, retain the job's scope/diagnostic fields; do not request an absent completed run as though it were a solved artifact. A conflicting reuse of an idempotency key returns a conflict instead of silently submitting another computation.

## Common endpoints

| Operation | Endpoint |
| --- | --- |
| Validate/save a scenario | `POST /api/v1/scenarios/validate`, `POST /api/v1/scenarios` |
| MovingAI import | `POST /api/v1/scenarios/import-movingai` |
| Preview job inputs | `POST /api/v1/plans/preview` |
| Submit/read/cancel/retry a job | `POST /api/v1/jobs`, `GET /api/v1/jobs/{id}`, `POST .../{id}/cancel`, `POST .../{id}/retry` |
| Read durable job events | `GET /api/v1/jobs/{id}/events?cursor=N` |
| Subscribe to job progress | `GET /api/v1/jobs/{id}/stream` |
| List/read runs | `GET /api/v1/runs`, `GET /api/v1/runs/{id}` |
| Read replay slices | `GET /api/v1/runs/{id}/frames?offset=0&limit=50` |
| Export a run | `GET /api/v1/runs/{id}/export/{json,csv,tex,svg,html}`; SVG accepts `tick` |
| Import a checked bundle | `POST /api/v1/runs/import` |
| Build a matched comparison | `POST /api/v1/comparisons` |
| Preview/start an experiment | `POST /api/v1/experiments/preview`, `POST /api/v1/experiments` |
| Read outcomes/analyze/export | `GET /api/v1/experiments/{id}/rows`, `POST .../{id}/analysis`, `POST .../{id}/export` |

SSE event IDs are monotonically sequenced in the job journal. Reconnect using `Last-Event-ID` or the supported cursor; do not invent completion after a dropped connection. The authoritative job/run state remains available through ordinary GET requests. Frames are fetched in slices of at most 100; a recording without frames cannot become a detailed replay by paging it.

API batch admission and full experiments have distinct request models. A `/batches` submission requires a reviewed plan digest and idempotency header. An `/experiments` submission takes the frozen manifest. Consult OpenAPI instead of reusing a payload from the legacy simulation endpoints.

## Extension boundaries

Centralized planners and decentralized coordination methods implement `MAPFSolverProtocol`. Strategies within the included negotiation engine use `AgentProtocol` with `BaseAgent` support; their proposal callbacks preserve observation isolation, commitment validity and transactional settlement, and the TAOP session owns acknowledgement accounting. [`02_custom_negotiation_agent.py`](../examples/02_custom_negotiation_agent.py) is an initialization sketch, not a tested strategy implementation. Follow [Extending](EXTENDING.md) for solver registration, new protocols and method-specific configuration or telemetry.
