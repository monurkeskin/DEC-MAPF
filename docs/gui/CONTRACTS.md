# Workspace contracts

## Inputs and identity

The application layer owns request schemas (`application/contracts.py`), canonical plans and scenario snapshots. HTTP is an adapter. Coordinates are strict integer pairs, with origin at the top left; x increases right and y down. Valid requests have a nonempty matching start/goal roster, free in-bounds endpoints and reachable individual goals. Duplicate starts and shared noDaT goals are rejected. FoV size is an odd **width**, not a radius. Commitment values are Standard SC, Dynamic DC and Zero ZC.

Limits: grid dimensions 1..64, at most 100 agents, up to 10,000 explicitly requested API/headless steps (500 in the interactive form), and at most 600 seconds when an overall process cap is supplied. Decentralized jobs may explicitly use `timeout_sec: null`; centralized jobs require a numeric cap. `negotiation_deadline_sec` is a separate per-session limit (default 60 seconds). Null aggregate process time means there is no sum of per-trial caps, not an infinite experiment budget: the declared batch wall budget still applies. Hard timeout records distinguish `timeout_scope: process` and `timeout_scope: negotiation`. Every plan lists effective inputs, inactive solver parameters and explicit agent order. Selecting a setting overrides a template default and revalidates the scenario. Plans have content digests; submissions have unique job/run/attempt IDs. Identical intentional reruns cannot overwrite one another. An Idempotency-Key repeats the same command receipt; reuse with a different command is rejected.

Canonical JSON is RFC 8785, hashed with SHA-256. This avoids Python/JavaScript differences such as 1.0 versus 1. Bundle checksums establish integrity, not authenticity of a claimed source revision. Run provenance records source file hashes, Git identity/dirty state, seed, effective inputs and relevant environment versions.

## Independent outcome dimensions

| Dimension | Values | Meaning |
|---|---|---|
| Job state | pending, running, completed, failed, cancelled, timed_out, interrupted | Supervisor/infrastructure lifecycle |
| Solver outcome | solved, not_solved | Preserved solver claim |
| Validation | valid_solution, valid_prefix, invalid, not_checked | Independent trajectory receipt |
| Compatibility status | solved, failed, truncated, invalid | Legacy result summary |

A completed job can contain an invalid solver result. A timeout is a job event, not a valid solution. Only solver success with a valid full solution is admissible as successful. A failed centralized search without a complete candidate has validation `not_checked`, with missing-path diagnostics retained; a claimed success with missing paths remains invalid. A budget-limited incomplete result is not an unsolvability certificate.

## Replay and telemetry

`t=0` is the initial state. The engine's legacy post-move frame labelled t becomes replay frame t+1. Bid and negotiation events remain pre-move; MOVE and KEYFRAME events are shifted to the post-move tick and carry an explicit phase. Tokens at t=0 use the initial balance; missing later observations are omitted. Goals come from the scenario, not from the final recorded position.

Under settings 1/2, reached agents park. Under settings 3/4, they are present at the arrival tick and disappear afterward. A short incomplete trace retains its last position. Collided status is assigned from specific validator errors, not applied to every agent. Full-trace frames record initial plans and local observations at t=0, then actual remaining plans, commitment records and the decision observation's timestamp after movement. Missing observations in older or reduced traces remain unavailable; the UI does not infer them from future executed paths. The heat overlay is labelled hindsight.

Replay roots hold checksummed indexes for traces longer than 32 frames. The frame endpoint reads only overlapping 32-frame gzip chunks. The frontend loads run metadata separately and uses an LRU bounded to eight chunks and 8 MiB of serialized frame data, with abortable stale requests. Export deliberately materializes a complete portable trace. Playback is visual replay, not an exact-resume checkpoint.

## Supervision and persistence

One directory lease owns the SQLite journal and spawned worker processes. The v1 default is two concurrent workers, 32 total active/queued jobs, a 512 MiB workspace quota and 50 MiB per final artifact. Cancel terminates an owned worker; UI pause only affects playback. Parent death closes a watchdog pipe; workers exit rather than continue without an owner. Restart marks unfinished jobs interrupted. There is no automatic scientific rerun.

Artifacts are fsynced and atomically renamed before the database publishes their run row. Crashes can leave an undiscoverable orphan, which recovery quarantines; they must not create a false completed run. Reads check the saved artifact hash. Pinned runs reject deletion. Retention is explicit; there is no automatic removal of pinned evidence.

## REST and event transport

The generated contract is `docs/gui/openapi.json`; regenerate with `scripts/export_gui_schema.py` and `npm --prefix frontend run schema`. Jobs and JobEvent have explicit response models; several auxiliary views remain dictionary-shaped and use hand-written frontend view types. Do not describe the entire API as fully generated end to end.

SSE is `/api/v1/jobs/{job_id}/stream`, with persistent monotonically increasing per-job sequence IDs. Each observer has its own cursor. Last-Event-ID or the after query cursor resumes delivery; heartbeats keep a quiet connection alive. The frontend validates typed job events, polls on stream failure, and stops reconnecting after a terminal event. State survives browser reload.

Bundles export/import checked metadata, exact scenario, paths, frames and provenance without running a solver. Imports independently check trajectories, replay alignment, path-derived costs, effective-input identity and hash. JSON, CSV, LaTeX, SVG and standalone HTML have explicit provenance and metric scope. Unknown legacy text is quarantined with a content hash and missing-provenance fields; it is excluded from analysis cohorts.

## Compatibility boundary

The frontend uses `/api/v1`. The deprecated `/api/simulate` facade now delegates to the same process supervisor and retains its response shape. Legacy unbounded benchmark launch returns HTTP 410 with the manifest-based replacement; historical status/archive routes are read-only compatibility surfaces. New experiments use `/api/v1/experiments` or the independent `mapf batch` CLI.

## TAOP v2 and timeout diagnostics

New requests default to `taop-v2`; the protocol name participates in immutable
plan/run identity. Historical metadata retain their original protocol. The offer
count is a diagnostic checkpoint in v2. Job status exposes `timeout_diagnostics`
for a parent-enforced session timeout; cooperative expiry retains diagnostics in
the result's solver diagnostics and `NEGOTIATION_STOP` telemetry. The UI displays
these observations without calling them a confirmed deadlock or a valid solution.
