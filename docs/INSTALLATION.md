# Installation

[Documentation index](README.md) · Next: [Headless](HEADLESS.md) or [GUI](GUI-GUIDE.md)

Use a separate checkout and workspace for each study whose inputs must stay frozen. Commands here assume the repository root. The verified development interpreter is Python 3.12; CI also targets Python 3.13. The recorded toolchain is uv 0.11.18 and Node 25.8.2. Exact dependency resolutions live in [`uv.lock`](../uv.lock) and [`frontend/package-lock.json`](../frontend/package-lock.json).

## Choose an installation

| Need | Install command | Browser or Node needed? |
| --- | --- | --- |
| Simulate, supervise batches, validate and export outcome rows | `uv sync --locked --python 3.12` | No |
| Also analyze experiments and generate figures | `uv sync --locked --python 3.12 --extra analysis` | No |
| Admit batches according to CPU/RAM headroom | `uv sync --locked --python 3.12 --extra resources` | No; optional psutil probe |
| Local GUI, replay, single-run exports and experiment analysis | `uv sync --locked --python 3.12 --extra gui --extra analysis` | Browser; Node to build from source |
| Develop and run the complete test tools | `uv sync --locked --python 3.12 --extra gui --extra analysis --extra dev` | Node for frontend work |

`uv sync` synchronizes the environment to the requested extras. Include all the extras you want to keep when running it again. `uv run --no-sync` below uses the environment you already installed. GUI dependencies are optional; the core batch workflow does not import FastAPI.

Clone the repository:

```bash
git clone https://github.com/monurkeskin/DEC-MAPF.git
cd DEC-MAPF
uv sync --locked --python 3.12
uv run --no-sync mapf --help
uv run --no-sync mapf solvers
```

Scenarios and results remain local; cloud compute is not required. Do not put credentials into specifications, shell examples or committed configuration.

## Check your environment

```bash
uv run --no-sync mapf doctor
uv run --no-sync mapf doctor --require gui --require analysis
uv run --no-sync mapf doctor --workspace runs/my-study/workspace
```

The first command requires only the core. Missing optional extras do not make a headless installation fail. Add `--require resources` or `--require native` for the workflow you intend to use. The GUI check includes built UI assets; run it after building the frontend. Native verification checks configured executable identities without running a solver. Output is JSON, with exit status 1 for a missing required component or incompatible/missing workspace.

Workspace inspection is read-only: it does not acquire the execution lease, recover jobs or migrate a schema. A misspelled path creates nothing. Original unversioned workspaces (schema 0) remain readable; new workspaces declare schema 1. Unknown future schemas are rejected explicitly.

## Build and start the GUI

```bash
uv sync --locked --python 3.12 --extra gui --extra analysis
npm --prefix frontend ci
npm --prefix frontend run build
uv run --no-sync mapf dashboard --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. The current application has **Configure, Inspect, Compare and Export** navigation. Its viewport uses Canvas 2D. React/TypeScript own the application interface; the rendering loop is separate from React state. PixiJS is an experimental renderer comparison dependency, not the shipped viewport.

The source server reads `frontend/dist`. Rebuild after changing frontend code. If you see the historical interface, the current frontend build is missing. The server also knows how to serve UI assets packaged inside an installed wheel.

Select an independent data directory before launching:

```bash
MAPF_WORKSPACE_DIR=runs/my-study/workspace uv run --no-sync mapf dashboard --host 127.0.0.1 --port 8000
```

The default is `data/workspace/`. Keep the server on loopback for the supported local workflow. This application is not a configured multi-user hosting service. Stop it with Ctrl+C when finished; stopping replay in the browser is a separate action.

## Headless first, GUI later

Run a batch with only core dependencies. When the CLI driver has exited, install the GUI extra, build the frontend and point the GUI at the completed batch's workspace. Saved runs appear in the library. Do not start two owners on the same workspace: an active CLI runner and a GUI server need separate workspace directories. A GUI-owned experiment should be controlled through that GUI/API.

Choose `full-trace` or `events` before execution if you need detailed replay. Installing a GUI later cannot reconstruct unrecorded local decisions from a `metrics-only` run.

## Python without uv

The supported repeatable source setup uses the lockfile commands above. A standard editable install is also possible in your own Python 3.12 environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
# Optional:
python -m pip install -e '.[gui,analysis]'
```

A plain pip install resolves version ranges and is not a replay of `uv.lock`. Record the installed versions if you use it for an experiment. Do not replace an existing experiment environment with a new unpinned install.

## Installed wheel and native tools

When a wheel is available under [GitHub Releases](https://github.com/monurkeskin/DEC-MAPF/releases), download the `.whl` file into an empty directory and create a fresh environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
# Headless installation:
python -m pip install ./dec_mapf-0.1.0a2-py3-none-any.whl
mapf doctor
# Add the GUI and analysis dependencies to the same wheel:
python -m pip install './dec_mapf-0.1.0a2-py3-none-any.whl[gui,analysis]'
mapf dashboard --host 127.0.0.1 --port 8000
```

Choose the filename belonging to the release you downloaded. PyPI availability is not assumed. A wheel includes the built UI; Node is only needed for developing or building the frontend. For dependency-exact experiments, use the source archive and its `uv.lock` instead of resolving pip ranges.

A maintainer can build a wheel containing the UI:

```bash
uv sync --locked --python 3.12 --extra gui --extra analysis --extra dev
npm --prefix frontend ci
npm --prefix frontend run build
uv run --no-sync python scripts/package_gui.py
uv build --out-dir runs/distribution-check
uv run --no-sync python scripts/check_distributions.py runs/distribution-check
```

Install the chosen wheel with the `gui` and optionally `analysis` extras. A wheel that was built after `package_gui.py` serves the UI without Node or the source checkout. A core-only install of the same package remains headless. [Contributing](../CONTRIBUTING.md) describes installed-wheel checks.

Native EECBS and CBSH2-RTC executables are **separate optional tools**, with their own source receipts, build dependencies and licenses. Follow [Native baselines](NATIVE-BASELINES.md). The built-in Python examples do not require them. Use `MAPF_NATIVE_SOLVER_CATALOG` to select a prepared local catalog; arbitrary executable paths are not accepted in GUI job submissions.

## Shell and platform notes

The repository is named **DEC-MAPF**, the distribution name is
`dec-mapf`, and imports/commands use `mapf`. Installed-wheel run
receipts record actual source hashes and package versions; Git revision and dirty
status are unavailable when no owning source repository exists. A surrounding
project's Git commit is not treated as the wheel's origin.

The instructions and screenshots were checked on macOS/Apple Silicon. The project CI defines macOS and Linux Python checks. In PowerShell, use `uv run --no-sync ...` in the same way and set the workspace with `$env:MAPF_WORKSPACE_DIR = "runs/my-study/workspace"` before the start command. POSIX command substitution and backslash line continuations in the analysis examples need the corresponding PowerShell syntax. A Windows end-to-end run is not established by these documentation checks.

For a missing dependency, unavailable port, browser setup or source mismatch, continue with [Troubleshooting](TROUBLESHOOTING.md).
