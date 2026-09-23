# Runnable examples

Use the repository's installed Python environment from the repository root. The [headless tutorial](../docs/HEADLESS.md) is the recommended first experiment. These examples are teaching/regression fixtures, not published benchmark evidence.

| File | Purpose | Execution/evidence |
| --- | --- | --- |
| [method-comparison.json](method-comparison.json) | Two scenarios × HeatMap/PathAware/CBS/Prioritized Planning | Eight supervised decentralized/centralized trials with full traces; works without GUI extras |
| [negotiation-tutorial.json](negotiation-tutorial.json) | Two scenarios × HeatMap/PathAware | Four supervised trials with full traces; works without GUI extras |
| [headless-smoke.json](headless-smoke.json) | Two scenarios × two centralized solvers × four settings | Sixteen supervised regression trials; metrics-only |
| [custom-scenario.json](custom-scenario.json) | Portable 8×8 geometry and two-agent roster | Input only; see [Scenarios](../docs/SCENARIOS.md) to wrap it in a study |
| [teaching-rectangular.map](maps/teaching-rectangular.map) + [teaching-rectangular.scen](maps/teaching-rectangular.scen) | Synthetic 5×3 MovingAI import | Two-agent roster for GUI/API import and coordinate inspection |
| [04_supervised_study.py](04_supervised_study.py) | Python application-service entry point | Durable two-trial run, manifest and all-outcome JSON; guarded multiprocessing entry point |
| [05_registered_solver_study.py](05_registered_solver_study.py) | Existing CBS registration under a teaching alias | Real spawned worker, validation, bundle export and resume; no new research method |
| [resource-aware-study.json](resource-aware-study.json) | Four tiny jobs with an explicit resource policy | Requires the resources extra; see [admission guide](../docs/RESOURCE-ADMISSION.md) |
| [01_basic_simulation.py](01_basic_simulation.py) | Direct solver integration on a generated 16×16/10-agent case | In-process execution, independent check; no parent watchdog or automatic journal |
| [03_centralized_vs_decentralized.py](03_centralized_vs_decentralized.py) | Direct HeatMap/CBS comparison on one generated 12×12/6-agent case | Descriptive paired costs only if both solve; no invented centralized sharing measurement |
| [02_custom_negotiation_agent.py](02_custom_negotiation_agent.py) | Minimal subclass sketch | Initializes an object only; not a registered, executed or TAOP-v2-qualified policy |

## First study

```bash
uv sync --locked --python 3.12
mkdir -p runs/tutorial
uv run --no-sync mapf batch plan examples/method-comparison.json --output runs/tutorial/manifest.json
uv run --no-sync mapf batch run runs/tutorial/manifest.json --workspace runs/tutorial/workspace
```

For the Python service example:

```bash
uv run --no-sync python examples/04_supervised_study.py --workspace runs/python-study
```

Use a fresh workspace or the explicit CLI resume operation if the study already exists. A completed batch need not contain only successful solutions; inspect validation and all planned outcomes.

## Direct integrations

```bash
uv run --no-sync python examples/01_basic_simulation.py
uv run --no-sync python examples/03_centralized_vs_decentralized.py
```

Direct examples illustrate the API and cooperative guards. Use `mapf batch` for hard process deadlines, persistence and large experiments. The historical custom-agent sketch should not be used as a recipe for protocol acknowledgement; read [current extension contracts](../docs/EXTENDING.md).

## Recorded gallery and synthetic illustrations

The [gallery](../docs/GALLERY.md#recreate-the-gallery) uses saved, validated
80-agent runs on 16×16 and 32×32 article inputs. Recreating those images requires
the corresponding recorded workspace and provenance receipt. The separate
`scripts/documentation_examples.py` helper creates synthetic teaching inputs;
those examples do not reproduce the gallery's maps, rosters or results. Store
new run data under ignored `runs/` and review captures before publishing them.

## Portable complete workflows

The [experiment capsules](capsules/README.md) pair explicit specs with run/validation/export and an interpretation guide. `mapf study init` generates a fresh editable project; see [New study](../docs/NEW-STUDY.md).
