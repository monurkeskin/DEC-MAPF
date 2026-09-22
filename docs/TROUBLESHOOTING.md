# Troubleshooting

[Documentation index](README.md) · [Installation](INSTALLATION.md) · [Scientific interpretation](SCIENCE.md)

Start with the exact command, effective input manifest, job state and validation/termination receipt. A failure to launch, a solver's bounded failure and a physically invalid trajectory require different fixes. Preserve the original outcome while investigating.

## Setup and startup

| Symptom | Check and next action |
| --- | --- |
| `mapf` is not found | Run from the project root after `uv sync`; use `uv run --no-sync mapf --help` |
| FastAPI/uvicorn missing | Install the `gui` extra; core-only execution intentionally omits the server |
| Analysis/plot import fails | Install the `analysis` extra; keep any other extras you need in the sync command |
| The old dashboard appears | Run `npm --prefix frontend ci` and `npm --prefix frontend run build`; the current UI has Configure/Inspect/Compare/Export |
| Address is already in use | Choose another explicit port or stop the server you own; do not kill unrelated processes |
| Wrong Python was selected | Use `uv sync --locked --python 3.12` in an isolated environment |
| Offline install lacks a wheel | A lockfile records versions, not installed bytes; populate the dependency cache while connected |
| Clone fails | Check the repository URL, network connection and Git configuration; never add tokens to documentation/specifications |
| Playwright cannot find a browser | Use installed Chrome on macOS or install Playwright Chromium; the capture script has `--channel` |
| A manifest output path fails | Create its parent first, for example `mkdir -p runs/tutorial` |

## Inputs and admission

**Unknown solver:** inspect `/api/v1/capabilities` or [Solvers](SOLVERS.md). Optional native IDs appear only when their local catalog is configured and valid. Python `EECBS-*` aliases are not native EECBS.

**Invalid scenario:** check x/column and y/row order, matching IDs, bounds, duplicate starts, obstacles and individual connectivity. Shared goals are incompatible with permanent occupancy. A square map can conceal a transposed coordinate mistake, so test a rectangular input too.

**Setting does not match a native profile:** select a profile declared for that setting. Do not force an unsupported flag or silently convert a disappear-at-goal experiment to stay-at-goal.

**Scenario ID is missing:** saved IDs belong to a workspace. Use an inline portable scenario for a standalone batch, or import/save the snapshot in the receiving workspace. Built-in IDs are listed in [Scenarios](SCENARIOS.md).

**Queue/workspace conflict:** use one active owner per workspace. Stop the CLI driver before serving its completed study in a GUI, or use a separate directory. The GUI defaults to two workers; fixed admission supports up to four. An explicit resource policy supports up to six. A GUI experiment must fit its configured owner limit and use the same resource policy. See [resource-aware batches](RESOURCE-ADMISSION.md).

**Resource-blocked study:** inspect `resource-status.json` for CPU, free-memory, owned-memory or unavailable-telemetry reasons. This is an administrative stop, not a solver timeout or infeasibility result. Once resources are available, explicitly resume the same manifest; changed policies require a new manifest. `resources` is an optional installation extra, and missing process visibility must not be interpreted as zero RAM usage.

## Timeouts and incomplete solutions

Read `timeout_scope`, `timeout_session_id`, `timeout_diagnostics`, `termination_reason` and `solver_diagnostics` when present. Not every failure has all these fields.

| Evidence | Meaning | Useful investigation |
| --- | --- | --- |
| Process timeout | Whole attempt exceeded its wall budget | Startup/solver load, process cap, elapsed computation and hardware contention |
| Negotiation timeout | One bilateral session exceeded its absolute deadline | Last phase, agents, token acknowledgements, last search/replan and recent actions |
| `low_level_limit` | Search exhausted a node/horizon bound | Effective `max_astar_expansions`, max steps/horizon and the failed search status |
| `priority_order_failed` | Prioritized Planning could not complete this ordering | Preserve failure; an incomplete algorithm failing does not prove no MAPF solution exists |
| Step guard reached | Execution remains unfinished at `max_steps` | Inspect the trajectory, commitments, movement and negotiation diagnostics |
| `permanent_goal_disconnection` | Reached permanent-goal configuration blocks remaining reachability | Distinguish this reached state from initial-instance feasibility |
| `valid_prefix` | Recorded moves are legal but unfinished | Report unsolved; do not compare its partial path length as a solved cost |
| `invalid` | Independent trajectory rule failed | Use first-violation tick and exact validation errors; retain the offending trace |
| `not_checked` | No usable candidate for the requested validation | Inspect solver termination; this is not a valid solution or an observed collision |

A token protocol cannot manufacture a collision-free concession when constraints make its bounded search fail. In TAOP v2, an unaffordable repeat prompts concession/new allocation; the offer checkpoint does not terminate the negotiation. A real session deadline produces diagnostics rather than a fabricated agreement.

Raise a limit only when the study's design justifies it, with a new explicit configuration/manifest. Keep prior timed-out and failed outcomes. Do not selectively tune each failed trial and merge the successes into the old cohort as if nothing changed.

## Resume, source changes and storage

**Experiment already exists:** use `batch resume EXPERIMENT_ID --workspace DIR` or a new workspace. Resume reattempts unfinished work and keeps terminal evidence. `--retry-failed` is a separate explicit decision with attempt lineage.

**Source changed since planning:** the frozen Python source hash no longer matches. Return to the preserved source/environment for that study, or plan a new experiment. Do not bypass the source check or hand-edit the manifest hash.

**Manifest digest mismatch:** investigate whether input bytes were edited or truncated. Re-plan the intended new specification. A manually repaired checksum cannot establish the identity of an old run.

**Wall budget exhausted immediately after resume:** elapsed driver time is charged across continuations. Resume does not silently grant more time. A revised budget is a new study definition.

**Disk budget exhausted:** inspect actual workspace size and trace settings. Back up the stopped workspace as a whole before cleanup. Detailed events/local heat can dominate storage. A pin is a library affordance, not an external backup.

**Missing artifact:** retain the journal outcome and report missingness. A deleted run does not become a success and must not disappear from the planned denominator. Copying only the SQLite file or only the artifacts directory is not a complete archive.

## Replay and visual layers

- **No replay:** metrics-only recording deliberately omits detailed frames/events. Paths and counters do not reconstruct local observations.
- **No heat:** select HeatMap, full trace, an agent and a frame containing a recorded negotiation decision. Initial planning does not create these heat records. Check recorded omissions/budget exhaustion.
- **Heat and frame ticks differ:** decisions are pre-move and appear beside the following post-move frame. The panel reports the decision tick separately.
- **FoV seems to show an unobserved agent:** FoV geometry is a spatial outline over the current display. Enable recorded local view and inspect the stored recipient observation to reason about actual information.
- **Agents disappear:** Settings 3/4 remove agents after arrival; their final goals remain as outlines. A roster size of 100 does not require 100 active circles at every tick.
- **Colors repeat:** use the numbered circles, exact-ID table and selection; zoom for crowded grids. Select one agent to dim other executed routes.
- **Execution idle / stream disconnected while replay works:** you opened a saved artifact rather than a live job. The saved validation receipt is still authoritative for that run.
- **Imported bundle rejected:** retain the original file, inspect the integrity error and the 16 MiB request cap. Do not remove checksum fields to force import.

## Comparison and interpretation

For an unmatched pair, compare instance hash, source hash, seed, metric version and effective non-treatment parameters. Declare the parameter you intentionally changed, not every mismatch discovered after the fact. Metrics-only and full-trace differences can also affect matching when recording is not the declared treatment.

A common-solved cost table excludes cases unsolved by either method, but those cases still count in success outcomes. Report coverage alongside cost. Missing communication values are not zero; global centralized input is not measured 100% broadcast disclosure. Runtime numbers in screenshots are demonstration readouts, not hardware-normalized performance claims.

For a useful bug report, include a small portable scenario, the effective manifest/source revision, the exact command, state/validation/termination receipts and relevant minimal trace. Exclude private datasets and credentials. See [Contributing](../CONTRIBUTING.md).
