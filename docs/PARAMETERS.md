# Parameters and effective inputs

[Documentation index](README.md) · [Scientific interpretation](SCIENCE.md) · [Experiment reference](EXPERIMENTS.md)

This table is generated from `JobSubmissionRequest` and `ExperimentBudget` in the current source. Regenerate with `uv run --no-sync python scripts/documentation_reference.py`; check drift with `--check`. These are application/API defaults, not an article protocol or the defaults of the separate direct `mapf solve` command.

## One job or one expanded matrix trial

| Field | Default | Schema constraint |
| --- | --- | --- |
| `grid_width` | `8` | integer; min 1, max 64 |
| `grid_height` | `8` | integer; min 1, max 64 |
| `obstacles` | `"empty collection"` | array; max items 4096 |
| `starts` | `"empty collection"` | object |
| `goals` | `"empty collection"` | object |
| `setting` | `"SETTING_1"` | `SETTING_1`, `SETTING_2`, `SETTING_3`, `SETTING_4` |
| `name` | `"Custom scenario"` | string; max characters 160 |
| `solver_id` | `"Decentralized-HeatMap"` | string |
| `scenario_id` | `null` | string; max characters 100 or null |
| `max_steps` | `100` | integer; min 1, max 10000 |
| `timeout_sec` | `5.0` | number; min 0.1, max 600.0 or null |
| `negotiation_deadline_sec` | `60.0` | number; min 0.01, max 600.0 |
| `fov_size` | `3` | integer; min 3, max 15 |
| `broadcast_horizon` | `null` | integer; min 1, max 100 or null |
| `negotiation_horizon` | `null` | integer; min 1, max 100 or null |
| `negotiation_protocol` | `"taop-v2"` | `taop-v2`, `taop-v1`, `legacy-alternating-v1` |
| `negotiation_round_limit` | `30` | integer; min 1, max 500 |
| `verification_pass_limit` | `5` | integer; min 1, max 20 |
| `max_astar_expansions` | `1500` | integer; min 100, max 100000 |
| `initial_tokens` | `10` | integer; min 0, max 100 |
| `commitment_type` | `"SC"` | `SC`, `DC`, `ZC` |
| `random_seed` | `42` | integer; min 0, max 4294967295 |
| `recording_level` | `"full-trace"` | `metrics-only`, `events`, `full-trace` |
| `heat_recording_limit` | `250000` | integer; min 0, max 2000000 |
| `suboptimality` | `1.1` | number; min 1.0, max 3.0 |

Scenario dictionaries use integer `[x, y]` coordinates. Starts/goals need the same IDs and at least one agent; semantic validation follows schema validation. A built-in or workspace-owned `scenario_id` resolves a snapshot; portable external batches should carry inline coordinates. Grid shape, starts, goals, obstacles and name are scenario data, not solver parameters.

FoV is an **odd square width** (3, 5, 7, 9, 11, 13 or 15); the radius is floor(width/2). Null temporal horizons are resolved to the FoV width in the effective plan. Those horizons count states, including the current position; they are not distances or seconds. The interactive GUI form caps `max_steps` at 500; the application/headless schema permits up to 10,000.

`timeout_sec: null` is accepted only for decentralized jobs. Centralized jobs require a number. The bilateral deadline resets for a new session, never for an offer. In TAOP v2 the round limit is a diagnostic checkpoint, not a hard terminal offer count. Heat values are recorded only for applicable full-trace HeatMap decisions, bounded by the declared value budget and internal record-count guard.

`suboptimality` is active only for solvers/profiles that support it. It is not a general guarantee for a solver with a familiar name. Native catalogs also constrain the setting and freeze executable provenance. Preview reports canonical solver identity and `inactive_parameters`; consult `/api/v1/capabilities` for controls supported by your installed catalog.

## Whole experiment

| Field | Default | Schema constraint |
| --- | --- | --- |
| `workers` | `2` | integer; min 1, max 6 |
| `wall_seconds` | `900` | number; min 1, max 86400 |
| `max_trials` | `10000` | integer; min 1, max 100000 |
| `disk_mb` | `2048` | integer; min 64, max 65536 |
| `threads_per_worker` | `1` | integer; min 1, max 1 |
| `resources` | `null` | object or null |

The product of scenario count and matrix-axis lengths is checked against `max_trials` before exclusions. Fixed admission allows up to four workers; an explicit `resources` policy allows up to six. The GUI defaults to two workers and accepts an explicit `--workers` / `--resource-policy` configuration. Its experiment worker/policy settings must match the owning supervisor; the queue contains at most 32 pending/active jobs. Numerical-library thread caps are one per worker; they are not an OS memory guarantee.

Wall time is charged across resume. Disk limits stop work/admission when exhausted; do not treat them as a promise about the eventual compressed artifact size. The default interactive repository quota is 512 MiB; the batch runner applies its declared experiment disk budget. A GUI experiment must fit its existing workspace quota.

## Optional resource policy

| Field | Default | Schema constraint |
| --- | --- | --- |
| `centralized_slots` | `2` | integer; min 1, max 6 |
| `decentralized_slots` | `4` | integer; min 1, max 6 |
| `max_cpu_percent` | `90` | number; max 100 |
| `free_memory_mb` | `1024` | integer; min 0 |
| `max_owned_memory_mb` | `18432` | integer; min 1 |
| `optimal_reserve_mb` | `10240` | integer; min 1 |
| `bounded_reserve_mb` | `2048` | integer; min 1 |
| `decentralized_reserve_mb` | `256` | integer; min 1 |
| `idle_timeout_sec` | `300` | number; min 0.1, max 86400 |

Set `budget.resources` to opt in; null retains fixed admission. These are admission estimates and thresholds, not solver limits or OS memory guarantees. See [resource-aware batches](RESOURCE-ADMISSION.md) for blocked-state, resume and GUI policy semantics.

## Recording choice

| Level | Retained evidence | Intended use |
| --- | --- | --- |
| `metrics-only` | Paths, validation, measured counters, run/configuration provenance; no detailed replay frames/events/local heat | Broad batches and compact outcome analysis |
| `events` | Replay frames and recorded telemetry events; no full local decision/heat payloads | Movement and event inspection |
| `full-trace` | Available local observations, plans, commitments and applicable heat records, plus replay/events | Detailed explanations and debugging |

Recording limits and omissions are explicit. No later export can recreate a local decision that was never recorded. Replay is a visual artifact, not an exact-resume solver checkpoint.
