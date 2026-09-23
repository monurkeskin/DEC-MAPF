# Contributing to DEC-MAPF

Start from a current small fixture and a clear behavior you can verify. Keep simulation semantics, research-method changes, execution infrastructure and presentation separate. Read the [researcher documentation](docs/README.md), [algorithm semantics](docs/ALGORITHM.md) and the working diff before editing.

## Development environment

```bash
uv sync --locked --python 3.12 --extra gui --extra analysis --extra dev
npm --prefix frontend ci
```

Use a separate branch/worktree and independent workspace directory when another experiment is running. Never edit that experiment's frozen source or environment. Keep existing dependency locks unless the task requires an intentional dependency update.

The framework uses typed Python and explicit data contracts. Centralized planners and decentralized coordination methods enter through `MAPFSolverProtocol`. Strategies within the included negotiation engine use `AgentProtocol` and `BaseAgent`; their bidding callbacks must not acquire global world state or modify outside resources, and token acknowledgement belongs to the session ledger. Follow [Extending](docs/EXTENDING.md) for registration, method-specific configuration and telemetry integration.

## Readability and design

Use the [code reading and design guide](docs/CODE-GUIDE.md) to locate the owner
of a behavior before extracting another helper. Preserve documented import paths
and signatures. Prefer cohesive classes, named data values and explicit replaceable
protocols; avoid layers that only forward a call. Docstrings should explain
ownership, side effects and invariants. Comments explain why ordering, time or
scientific meaning must be preserved, rather than restating the next line.

Write documentation around the reader's task: what to run, what is saved and how
to interpret the result. Name the responsible module instead of repeating an
architecture slogan. Give the scope and denominator of a numerical claim; use
measured evidence for performance claims. Keep useful scientific limitations
beside the affected result, and link to the full contract for details. Avoid
promotional adjectives, repeated introductions and private development milestones.
Check prose against current behavior whenever a function is moved or split.

Format touched Python code with `uv run --no-sync ruff format PATH...`, then run
Ruff and mypy. Avoid unrelated repository-wide formatting churn. Keep focused
behavior tests when extracting code; retain paired performance measurements for
hot loops. Score improvements do not justify removing checks or changing scope.

## What to verify

For research behavior changes, first capture a reachable failing case with an independent expectation. Check physical settings, commitment lifetimes, rollback, token conservation, failed/cancelled outcomes and metric eligibility where relevant. A test that repeats the implementation formula is not independent evidence. Preserve original run artifacts and describe any source/algorithm/metric identity change.

Each test should identify a behavior that can break and show a useful failure.
Use hand-calculated examples or an independent oracle for scientific results.
Keep parametrized cases when they represent distinct settings, boundary values or
failure modes; hiding those cases in a loop only makes failures harder to locate.
Combine repeated setup, and remove duplicate assertions when another test checks
the same contract. Keep real HTTP, CLI and process tests where they verify a
boundary that a unit test cannot exercise.

Before removing tests, map their assertions to the retained checks and compare
covered lines and branches. For critical contracts, deliberately introduce a small
fault in an isolated checkout and confirm that the retained tests reject it.
Examples include early commitment expiry, a missed collision, a wrong token
transfer or a changed analysis denominator. A passing mutation check supports that
specific contract; it does not prove that every possible defect will be detected.
Neither the test count nor a coverage percentage is a reason to add a redundant
test or delete a useful one.

For observation and planning changes, `test_obstacle_memory.py` checks recipient
isolation, stay/disappear semantics, planner entry points and live reservations.
For native execution, `test_native_diagnostics.py` checks real pipe drainage,
bounded output, process cleanup and snapshot recovery after a hard deadline.
Keep these boundary checks when changing the corresponding owners; a mocked
solver return cannot exercise process or stream behavior.

Run the relevant Python gates:

```bash
uv run --no-sync python -m ruff check src tests
uv run --no-sync python -m mypy src
mkdir -p runs
uv run --no-sync python -m pytest -n 2 --dist loadfile --max-worker-restart=0 --junitxml=runs/python-results.xml
uv run --no-sync python scripts/check_acceptance.py runs/python-results.xml
```

To measure Python line and branch coverage, including spawned workers and CLI
subprocesses:

```bash
uv run --no-sync python -m pytest -n 2 --dist loadfile --max-worker-restart=0 --cov --cov-config=pyproject.toml --cov-report=term:skip-covered --cov-report=xml:coverage.xml
```

Two pytest workers run independent test files concurrently. Keeping a file on
one worker preserves module fixture reuse; each mutating test still owns its
workspace. `make test` uses the same schedule. On a busy machine, use
`make test TEST_WORKERS=0` or replace `-n 2` with `-n 0` in either command above.
These are test-runner workers, separate from the solver processes exercised by
integration tests. Worker crashes fail the run without automatic retries.

Coverage combines both workers and their instrumented subprocesses. When changing
test scheduling or fixtures, compare the complete test IDs and outcomes and the
covered line/branch sets against a serial run. Report whole-suite elapsed time
separately from JUnit test durations: parallel execution can shorten the suite
while contention increases individual test times. Use repeated measurements on
the same environment before claiming a speedup. `--durations=25` locates expensive
tests; real deadline, resource and process-ownership checks must remain bounded
and must not be replaced by sleeps or mocked execution to improve that table.

Core CI collects this report and JUnit test results on Linux with Python 3.12 and uploads them to
[Codecov](https://app.codecov.io/gh/monurkeskin/DEC-MAPF) using GitHub OIDC; no upload
secret is needed. Test Analytics records test durations and failures, including
failed CI runs that produced a JUnit report. The project coverage check requires
95%; the patch status is informational. Coverage measures Python
test execution, not frontend coverage, solver success or article reproduction.
Import-isolation and resource-profiling probes disable instrumentation inside
their child processes so startup dependencies and measured budgets remain meaningful.
Fork pull requests run the same coverage measurement; their upload step is skipped
because they do not receive the upstream job's write permissions.

The Codecov `python` flag identifies this report. Components group its files into
grid/search, coordination, solvers, application services, GUI backend, analytics,
telemetry and public API/CLI boundaries. Open the relevant component, then inspect
both missed lines and partially covered branches before adding a regression test.
Use short, descriptive `ids` for parametrized tests so large or encoded inputs do
not obscure individual cases in Test Analytics.

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

Check the installed wheel from outside the source checkout. The repository supplies [GUI wheel smoke](scripts/smoke_installed_wheel.py) and [headless wheel smoke](scripts/smoke_headless_wheel.py) scripts; execute the appropriate file with the separately installed wheel's interpreter from a temporary working directory. The core-only check requires FastAPI and psutil to be absent. In a separate environment with the `resources` extra, run the headless script with `--resources` to check real CPU/RAM observation, centralized/decentralized execution and completed-study resume. The GUI check requires GUI/analysis dependencies and the HTTP test client. These installed-package checks and the registered-solver adoption workflow run in CI. Merely importing the editable source does not qualify a distribution. Bundled UI assets do not make FastAPI a core dependency.

## Review and artifact boundaries

Use the [reproducible bug form](.github/ISSUE_TEMPLATE/bug_report.yml) or [PR template](.github/pull_request_template.md) to connect the trigger, expected behavior and evidence. [CI and distribution qualification](docs/RELEASE-CHECKS.md) describes the exact gates and their limits. The repository ships a tested package path; automatic public publication is not configured.

A useful PR describes the concrete trigger, resulting behavior, evidence/tests and any scientific limitation. Preserve stable citation keys and published numbers. Do not call finite tests proof of universal solver correctness, historical Java equivalence or article reproduction.

Commit source, small declared fixtures, schemas and reviewed documentation assets. Keep experiment databases, raw private datasets, run bundles, native binaries, credentials and assistant histories outside Git. `runs/` and `data/workspace/` are ignored for local work. Optional native solver licenses remain distinct from the Python project's MIT license.

Do not silently retry failed scientific trials or delete them from a denominator. Use explicit attempt lineage and a declared analysis policy. See [Reproducibility](REPRODUCIBILITY.md), [Metrics](docs/METRICS.md) and the [integration policy](docs/gui/INTEGRATION_POLICY.md).

## Choose a bounded first contribution

[Scoped starting tasks](docs/CONTRIBUTOR-TASKS.md) identify useful files and acceptance checks. Read [maintenance/support scope](docs/MAINTENANCE.md) and the [public API](docs/PUBLIC-API.md) before changing behavior. For guide/visual changes, apply the [glossary and caption standard](docs/GLOSSARY.md).
