# Contributing to DEC-MAPF

Start from a current small fixture and a clear behavior you can verify. Keep simulation semantics, research-method changes, execution infrastructure and presentation separate. Read the [researcher documentation](docs/README.md), [algorithm semantics](docs/ALGORITHM.md) and the working diff before editing.

## Development environment

```bash
uv sync --locked --python 3.12 --extra gui --extra analysis --extra dev
npm --prefix frontend ci
```

Use a separate branch/worktree and independent workspace directory when another experiment is running. Never edit that experiment's frozen source or environment. Keep existing dependency locks unless the task requires an intentional dependency update.

The framework uses typed Python and explicit data contracts. Centralized planners and decentralized coordination methods enter through `MAPFSolverProtocol`. Strategies within the included negotiation engine use `AgentProtocol` and `BaseAgent`; their bidding callbacks must not acquire global world state or modify outside resources, and token acknowledgement belongs to the session ledger. Follow [Extending](docs/EXTENDING.md) for registration, method-specific configuration and telemetry integration.

## What to verify

For research behavior changes, first capture a reachable failing case with an independent expectation. Check physical settings, commitment lifetimes, rollback, token conservation, failed/cancelled outcomes and metric eligibility where relevant. A test that repeats the implementation formula is not independent evidence. Preserve original run artifacts and describe any source/algorithm/metric identity change.

Run the relevant Python gates:

```bash
uv run --no-sync python -m ruff check src tests
uv run --no-sync python -m mypy src
mkdir -p runs
uv run --no-sync python -m pytest --junitxml=runs/python-results.xml
uv run --no-sync python scripts/check_acceptance.py runs/python-results.xml
```

For frontend or HTTP contract changes:

```bash
uv run --no-sync python scripts/export_gui_schema.py
npm --prefix frontend run schema
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend test
```

Browser tests create a private temporary server/workspace. Local macOS tests use installed Chrome; CI uses Playwright Chromium. Do not point acceptance tests at a real experiment workspace. For hot reload, run the local API and `npm --prefix frontend run dev`; the Vite configuration proxies API calls.

For user-facing documentation/examples:

```bash
uv run --no-sync python scripts/documentation_reference.py --check
uv run --no-sync python scripts/check_documentation.py
uv run --no-sync python -m ruff check scripts/documentation_examples.py scripts/documentation_reference.py scripts/check_documentation.py examples
```

Execute changed runnable examples with their declared bounds. Validate links, parameter defaults and screenshot provenance. A documentation-only change does not require a scientific tournament. See [Documentation checks](docs/DOCUMENTATION-CHECKS.md) for the actual qualification of this guide and [Gallery](docs/GALLERY.md#recreate-the-gallery) for capture instructions.

The core CI workflow also checks the generated parameter reference, guide links/image integrity, and example/helper lint. It does not regenerate screenshots or launch the gallery experiment during every CI run.

## Packaging

Build the frontend, copy it into generated package data and build the wheel:

```bash
npm --prefix frontend run build
uv run --no-sync python scripts/package_gui.py
uv build --out-dir runs/distribution-check
uv run --no-sync python scripts/check_distributions.py runs/distribution-check
```

Check the installed wheel from outside the source checkout. The repository supplies [GUI wheel smoke](scripts/smoke_installed_wheel.py) and [headless wheel smoke](scripts/smoke_headless_wheel.py) scripts; execute the appropriate file with the separately installed wheel's interpreter from a temporary working directory. The core-only check requires FastAPI and psutil to be absent. In a separate environment with the `resources` extra, run the headless script with `--resources` to check real CPU/RAM observation, centralized/decentralized execution and completed-study resume. The GUI check requires GUI/analysis dependencies and the HTTP test client. All three installed-package checks run in CI. Merely importing the editable source does not qualify a distribution. Bundled UI assets do not make FastAPI a core dependency.

## Review and artifact boundaries

Use the [reproducible bug form](.github/ISSUE_TEMPLATE/bug_report.yml) or [PR template](.github/pull_request_template.md) to connect the trigger, expected behavior and evidence. [CI and distribution qualification](docs/RELEASE-CHECKS.md) describes the exact gates and their limits. The repository ships a tested package path; automatic public publication is not configured.

A useful PR describes the concrete trigger, resulting behavior, evidence/tests and any scientific limitation. Preserve stable citation keys and published numbers. Do not call finite tests proof of universal solver correctness, historical Java equivalence or article reproduction.

Commit source, small declared fixtures, schemas and reviewed documentation assets. Keep experiment databases, raw private datasets, run bundles, native binaries, credentials and assistant histories outside Git. `runs/` and `data/workspace/` are ignored for local work. Optional native solver licenses remain distinct from the Python project's MIT license.

Do not silently retry failed scientific trials or delete them from a denominator. Use explicit attempt lineage and a declared analysis policy. See [Reproducibility](REPRODUCIBILITY.md), [Metrics](docs/METRICS.md) and the [integration policy](docs/gui/INTEGRATION_POLICY.md).

## Choose a bounded first contribution

[Scoped starting tasks](docs/CONTRIBUTOR-TASKS.md) identify useful files and acceptance checks. Read [maintenance/support scope](docs/MAINTENANCE.md) and the [public API](docs/PUBLIC-API.md) before changing behavior. For guide/visual changes, apply the [glossary and caption standard](docs/GLOSSARY.md).
