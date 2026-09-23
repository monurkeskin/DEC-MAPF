# Use the supported Python boundary

Import `mapf.api` to compose a study without depending on the GUI or private persistence methods. API version `1` supports the existing planning, execution, storage and export contracts.

```python
from mapf.api import (
    API_VERSION, MAPFInstance, Point, SimulationConfig,
    check_solver, get_solver,
)

instance = MAPFInstance(
    grid_width=3, grid_height=3,
    starts={"a": Point(0, 0)}, goals={"a": Point(2, 0)},
)
receipt = check_solver(get_solver("CBS"), instance,
                       SimulationConfig(grid_width=3, grid_height=3))
assert receipt["status"] == "valid_solution"
```

This check executes **one tiny fixture synchronously**. A legitimate unsuccessful result with no candidate paths is `not_checked`, not a valid prefix or proof of infeasibility. It checks input mutation, solver identity, physical trajectories, successful claims and canonical costs. It does not impose a process deadline or prove optimality/completeness. For expensive or untrusted extensions, use `ExperimentService` and its process supervisor with declared budgets.

| Public surface | Responsibility |
| --- | --- |
| `MAPFInstance`, `MAPFSolution`, `MAPFSolverProtocol`, `Point`, `Path`, `SimulationConfig`, `SimulationSetting`, `CommitmentType` | Domain inputs and results |
| `register_solver`, `get_solver` | Named factory registration and construction |
| `JobSubmissionRequest`, `compile_experiment`, `verify_manifest` | Validated requests, frozen plans and identity checks |
| `RunRepository`, `ExperimentService` | Workspace reads, supervised execution and explicit resume |
| `create_study`, `experiment_card` | Safe project initialization and all-outcome metadata cards |
| `export_bundle`, `check_run_bundle`, `check_solver` | Portable run artifacts and conformance checks on supplied inputs |

Register top-level factories in an importable module; multiprocessing spawn must execute that registration in each worker. Protect execution with `if __name__ == "__main__"`. The [registered CBS example](../examples/05_registered_solver_study.py) wraps an existing solver unchanged and demonstrates worker composition, validation and export.

`check_run_bundle(bundle)` uses the production versioned importer in a disposable workspace, then reads the saved result. It rejects unknown formats, changed checksums and inconsistent trajectories/frames/metrics. Integrity is not source authentication. Keep the original bundle; an import receives a new local run ID with its ancestry retained.

Only documented members are stable. Underscore-prefixed methods, internal SQLite tables and implementation classes remain internal. Additive releases preserve this public surface; breaking changes require a new API version and migration notes. Existing module imports remain available in this release.

Next: run the [installed extension walkthrough](EXTENDING.md), then consult [version compatibility](COMPATIBILITY.md).
