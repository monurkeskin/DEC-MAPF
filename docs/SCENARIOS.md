# Maps, rosters and custom scenarios

[Documentation index](README.md) · [Headless tutorial](HEADLESS.md) · [Parameters](PARAMETERS.md)

A scenario consists of grid dimensions, blocked cells and an ordered mapping from agent IDs to starts/goals. The physical setting belongs to the run and is included in its instance identity. A filename, map picture or number of agents is not a sufficient scenario identifier.

## Coordinates and physical checks

Coordinates are integer `[x, y]` pairs: **x is the column, y is the row**, starting at zero at the upper left. Legal motion is one horizontal/vertical cell per simulation tick; diagonal motion is not allowed. Waiting depends on the selected setting. `t=0` contains the starts.

The application accepts 1–64 cells per dimension and 1–100 agents. Starts must be distinct, on traversable cells and in bounds. Every start must have a matching goal ID and an individual four-connected route through the static map. Permanent-goal settings reject shared goals; disappearance settings can allow them at different arrival ticks. Individual reachability does not establish joint MAPF solvability.

The roster order is preserved in the frozen snapshot's `agent_order`. Do not reorder IDs while assuming the run is unchanged: scheduling/priority behavior can depend on a deterministic ordering.

## Built-in teaching fixtures

| ID | Geometry | Use |
| --- | --- | --- |
| `crossing-2a` | 5×5, two crossing paths | First negotiation and t=0 cost semantics |
| `bottleneck-2a` | 7×7, one gap in a wall | Observe a constriction and yielding |
| `corridor-pocket-2a` | 9×3, head-on traffic with a side pocket | Inspect constrained movement |
| `grid-8x8-4a` | 8×8, four agents and four obstacles | First complete run/compare/export workflow |
| `grid-8x8-8a` | 8×8, eight agents and four obstacles | Local heat, messages and commitments |

These are software/teaching fixtures. Their names do not imply guaranteed success for every setting, policy and search limit. Choose `setting` explicitly when using a built-in ID in a batch.

## Portable JSON inputs

[`examples/custom-scenario.json`](../examples/custom-scenario.json) is a complete portable scenario:

```json
{
  "name": "Crossing with a clear bypass",
  "grid_width": 8,
  "grid_height": 8,
  "obstacles": [[3, 1], [3, 2], [3, 5], [3, 6]],
  "starts": {"agent_0": [0, 3], "agent_1": [7, 4]},
  "goals": {"agent_0": [7, 3], "agent_1": [0, 4]},
  "setting": "SETTING_4"
}
```

In a batch specification, put that object into `scenarios`. Keep solver/recording/budget controls outside the raw scenario or provide them as explicit scenario-level overrides. This small script creates a runnable specification without requiring a saved GUI ID:

```bash
uv run --no-sync python - <<'PY'
import json
from pathlib import Path
scenario = json.loads(Path("examples/custom-scenario.json").read_text())
spec = {
    "name": "My custom map pilot",
    "scenarios": [scenario],
    "defaults": {"solver_id": "Decentralized-HeatMap", "timeout_sec": 15,
                 "max_steps": 40, "recording_level": "full-trace"},
    "budget": {"workers": 1, "wall_seconds": 60, "max_trials": 1, "disk_mb": 128},
    "sampling": {"population": "One teaching map", "independent_unit": "scenario"}
}
folder = Path("runs/custom")
folder.mkdir(parents=True, exist_ok=True)
(folder / "spec.json").write_text(json.dumps(spec, indent=2))
PY
uv run --no-sync mapf batch plan runs/custom/spec.json --output runs/custom/manifest.json
uv run --no-sync mapf batch run runs/custom/manifest.json --workspace runs/custom/workspace
```

To validate/save the same scenario in an independently running local GUI workspace:

```bash
curl --fail-with-body -sS http://127.0.0.1:8000/api/v1/scenarios/validate -H 'Content-Type: application/json' --data-binary @examples/custom-scenario.json
curl --fail-with-body -sS http://127.0.0.1:8000/api/v1/scenarios -H 'Content-Type: application/json' --data-binary @examples/custom-scenario.json
```

The first endpoint returns `is_valid` and errors; the second creates an immutable saved snapshot. Reload the workspace's scenario list if it was already open. This does not alter scenarios embedded in existing runs.

## MovingAI import

The GUI import accepts a `type octile` map with explicit width/height and a `version 1` or `version 1.0` scenario text. Cells `@`, `O`, `T` and `W` are obstacles in this parser. Scenario rows name the map and include dimensions and start/goal coordinates. The dimension metadata must agree with the selected map. Duplicate dimensions, unknown header fields and repeated version headers inside the roster are rejected. Blank lines and `#` comments preserve row ordering. All rows are validated, including rows beyond the selected prefix.

The general GUI/API importer selects the first requested number of scenario rows in source order. It records the map/scenario content hashes and that selection. It does not silently shuffle, distance-filter or replace invalid rows. Keep the raw source files and describe your selection before analyzing outcomes.

The HTTP endpoint is `POST /api/v1/scenarios/import-movingai`, with `map_text`, `scenario_text`, `agent_count`, `setting` and `name`. See the [API guide](API.md) and live OpenAPI schema for the exact contract.

A tiny synthetic [5×3 map](../examples/maps/teaching-rectangular.map) and [two-agent roster](../examples/maps/teaching-rectangular.scen) are included so you can try import without downloading a dataset. In **MovingAI map and scenario import**, paste their contents into **Map text** and **Scenario text**, set **First N agents** to 2, then choose **Import and save MovingAI**. For the local API, prepare a payload and submit it:

```bash
uv run --no-sync python - <<'PY'
import json
from pathlib import Path
folder = Path("runs/movingai")
folder.mkdir(parents=True, exist_ok=True)
payload = {
    "name": "Synthetic rectangular import",
    "map_text": Path("examples/maps/teaching-rectangular.map").read_text(),
    "scenario_text": Path("examples/maps/teaching-rectangular.scen").read_text(),
    "agent_count": 2,
    "setting": "SETTING_4"
}
(folder / "import.json").write_text(json.dumps(payload))
PY
curl --fail-with-body -sS http://127.0.0.1:8000/api/v1/scenarios/import-movingai -H 'Content-Type: application/json' --data-binary @runs/movingai/import.json
```

The response is the saved immutable snapshot and its scenario ID. Rectangular examples help expose x/y or width/height swaps that are harder to notice on square grids. These files are teaching fixtures, not part of the article archive.

The [MovingAI format](https://www.movingai.com/benchmarks/formats.html) stores
reference distances that may assume diagonal motion. DEC-MAPF uses four-connected
motion and independently recomputes distances where required. It treats `.`, `G`
and `S` as free and `@`, `O`, `T`, `W` as blocked; terrain-specific water/swamp
movement is not modeled. This is an explicit MAPF interpretation of the file.

For Python integrations, `parse_movingai_rows` retains named map dimensions,
coordinates and source distance metadata; `parse_movingai_scen` retains its
start/goal-pair return type. `format_movingai_scen` writes Manhattan lower bounds
for synthetic fixtures, not certified octile-optimal distances. The compatibility
`export_planviz_json` payload uses a DEC-MAPF coordinate dialect (`MAPF_POST`);
it is not an upstream PlanViz action-stream guarantee. Use checked run bundles
and the supplied GUI for supported replay/import.

## Article rosters are a distinct import

Use `mapf batch article-rosters` for complete archived rosters, choosing **main-16** or **appendix-32**. The 16×16 main design and 32×32 appendix design have different density and distance assumptions. Do not apply the main 4–24 action distance filter to the appendix just because an old Java field or directory label contains it.

Archived empty maps can also use a `width,height` header. Stale scenario dimension columns are rejected by default. `--repair-dimensions-from-map` is an explicit, recorded metadata correction using verified map dimensions; it preserves coordinates and source bytes. Shortest-path distances are recomputed from the map rather than trusted from a historical distance column. Invalid full rosters are not silently shortened to obtain a successful case. Repeating a file through a symbolic-link alias is rejected by both article builders; an alias is not a second source population.

`article-spec` creates fresh filtered main-map prefixes. It is not interchangeable with exact archived roster import. See [Reproducibility](../REPRODUCIBILITY.md#article-derived-inputs) for commands and reporting requirements.

## Generate synthetic examples

```bash
uv run --no-sync python scripts/documentation_examples.py --output runs/documentation
```

This only prepares inputs. It writes 32×32/80-agent crossings, 32×32/80-agent warehouse aisles and 64×64/100-agent warehouse aisles, plus a bounded six-trial specification. Run the generated specification through the [headless workflow](HEADLESS.md). These synthetic teaching inputs are separate from the article examples shown in the gallery. The supplied generator seeds control coordinate generation; the constructed teaching scenarios are not a representative research sample.
