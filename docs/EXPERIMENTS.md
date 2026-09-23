# Reproducible local experiments

The GUI is optional. Core execution needs Python and the core package; plots need the `analysis` extra. Node, FastAPI and the GUI server are unnecessary for headless execution. Use Python 3.12 and the checked lockfile for the recorded environment. For a step-by-step start, read [Headless experiments](HEADLESS.md); this page is the detailed execution reference.

```bash
uv sync --locked --python 3.12 --extra analysis --extra dev
.venv/bin/mapf batch plan examples/headless-smoke.json --output /tmp/mapf-manifest.json
.venv/bin/mapf batch run /tmp/mapf-manifest.json --workspace /tmp/mapf-study
.venv/bin/mapf batch status --workspace /tmp/mapf-study
# Substitute the experiment ID returned by planning/execution:
.venv/bin/mapf batch export EXPERIMENT_ID --workspace /tmp/mapf-study --output /tmp/trials.csv
.venv/bin/mapf batch analyze EXPERIMENT_ID --workspace /tmp/mapf-study --left CBS --right Prioritized --figures /tmp/mapf-analysis
```

The example is a software smoke test. It is not a historical JAAMAS sample. Real studies must declare their sampling population and independent scenario unit, freeze development/held-out membership before observing results, and preserve source map/scenario files and hashes.

## Specification and identity

A specification has `name`, `scenarios`, `defaults`, `matrix`, `exclude`, `budget`, and `sampling`. Each scenario supplies grid dimensions, obstacle coordinates, ordered agent start/goal dictionaries, or a built-in scenario ID. Saved scenario IDs also resolve when the service receives their owning repository, as in the GUI; standalone CLI planning should use portable inline coordinates for custom scenarios. An optional `sampling_unit` identifies related repetitions as one cluster. Matrix values override scenario values, which override defaults. Exclusion rules are conjunctions of exact field matches; matching any rule excludes that combination explicitly. Expansion is bounded before exclusions.

The generated manifest contains all effective inputs, source/lock identity, explicit excluded combinations, immutable ordered scenario snapshots, trial identities and resource bounds. Editing code after planning is rejected; plan a new experiment. Source identity covers Python source bytes; a dirty working tree is disclosed. Record the frozen commit and retain the manifest, not just its filename. `definition_identity` names a condition; `trial_id` names a planned trial; `job_id`/`attempt_id`/`run_id` identify an actual execution attempt.

Optional [native solver profiles](NATIVE-BASELINES.md) additionally freeze binary,
source patch and qualification receipt hashes in each effective configuration.
The local `MAPF_NATIVE_SOLVER_CATALOG` selects available profiles at planning time;
execution cannot silently switch to a changed catalog entry or executable. The
core installation and ordinary Python batch jobs do not require this catalog.

Run the same manifest through `/api/v1/experiments` or the GUI's **Compare → Complete experiments** panel. The UI uses the same application service and process supervisor. It neither starts a second pool nor changes requested budgets silently. A running GUI owns its workspace directory: do not launch a separate CLI supervisor in that directory simultaneously. Stop the server before resuming headlessly, or use its API.

## Bounds, interruptions and retries

Fixed admission permits 1–4 CLI workers; an explicit resource policy permits up to six. The default GUI supervisor permits two. Native worker pools are limited to one thread. Wall budget includes admission and recovery overhead and persists across resumes. An individual timeout includes child startup and solving. Disk budget applies conservatively to the workspace, including journals and retained results. A completed execution can still be unsolved or invalid.

Process deadlines are explicit per trial. A numeric `timeout_sec` permits at most 600 seconds; centralized jobs require a numeric value. Decentralized jobs additionally permit `timeout_sec: null`, meaning no total per-trial wall-clock cap.

`negotiation_deadline_sec` defaults to 60 seconds for each bilateral session and does not reset with each offer. The `article-rosters` builder defaults to this 60-second session deadline and no overall trial cap; passing `--timeout-sec` opts into an administrative cap. The `article-spec` builder and interactive/smoke fixtures retain their explicit shorter/bounded profiles.

Batch wall/disk budgets and cancellation still apply, and unfinished budget-stopped trials are censored executions, not proofs of algorithmic failure. Step, search-expansion and verification-pass guards remain separately declared modern limits.

In default `taop-v2`, `negotiation_round_limit` is a diagnostic checkpoint; the alternative protocol modes use it as a hard offer cap. Token refusal requires legal concession or an unoffered allocation and never renews the session deadline.

Changing any limit creates a new experiment identity; never overwrite earlier outcomes or selectively replace timeouts in a mixed-protocol cohort.

The headless batch/API worker uses both cooperative checks and a parent-process negotiation watch. Cooperative expiry yields an independently checked incomplete trajectory with `termination_reason: negotiation_deadline`; expiry inside a stuck callback terminates only the owned process group, records `timeout_scope: negotiation`, and makes no trajectory-validity claim. A whole-process administrative kill uses `timeout_scope: process`. Direct in-process solver calls have cooperative checks only; use the supervisor-backed batch workflow when hard preemption is required.

`solver_diagnostics` is included in saved results and all-planned batch exports, including metrics-only recording: bounded no-wait repair counts/nodes, immediate-step infeasibility versus repair-budget exhaustion, pre-update search outcomes, the last failed replan with static connectivity, negotiation terminal reasons and the longest consecutive no-motion streak. Event/full recordings also contain `MOVEMENT_REPAIR` and `REPLAN` receipts. Static connectivity is evaluated from known permanent obstacles at the current state, not used as proof that the original instance has no solution. These counters are engineering diagnostics, not replacements for independently validated success.

The engine records `permanent_goal_disconnection` when static cells
plus arrived permanent agents disconnect a remaining goal. This is an independent
world-level stopping condition, not a message or new planning input for agents.
`last_reachability_failure` and the typed `REACHED_STATE` event record the tick,
blocked goal cells and affected agents. It proves only reached-state impossibility;
no claim about initial-instance infeasibility follows. Disappearing arrivals and
finite commitments are never treated as permanent blockers by this check.

Movement authorization enforces live commitments in every setting and records `last_movement_failure`. `movement_constraints_infeasible` and `movement_repair_budget` stop before an unauthorized action. `remaining_agent_holds` is a diagnostic count of candidate holds, including permitted waits and blocked proposals; it is not an executed violation metric. Inspect `remaining_blocked_agents`, the stopping reason and the independently validated executed prefix. A refusal is an incomplete outcome; it must not be counted as a solved case.

`termination_reason` records the physical stopping condition separately from validation. `all_arrived` means that every agent reached its goal; an earlier illegal wait can still make the trajectory invalid and `success` false. Preserve the physical stopping reason, trajectory validation and success classification as separate fields.

`SIGINT` and `SIGTERM` stop owned work. A process crash leaves interrupted attempts; restart never labels them solved. Use `mapf batch resume EXPERIMENT_ID --workspace DIR` to attempt unfinished trials. A resume does not restore solver internals, increase the wall budget, or silently rerun completed trials. `--retry-failed` explicitly creates one further attempt per failed/timed-out/cancelled trial with parent lineage. All attempts remain in the journal. Analyses select the latest explicit attempt and say so. A larger/different budget or changed source requires a new manifest/study identity.

Resume retains the checked artifact of each completed trial without executing it again. Missing/deleted artifacts are reported separately and remain in the denominator.

Within one local observation, repeated bounded candidate-path queries may reuse immutable paths. The key includes topology, all reservations and owners, time, endpoints, weights and search bounds. The per-view LRU holds at most 16 entries and 16,384 path points, returns a fresh list, and bypasses custom planner/reservation implementations. Search-status receipts are preserved; `last_candidate_cache_hit` distinguishes reuse from fresh expansion work. This is an internal exact-query optimization, not reuse of a completed experiment or a change to strategy selection. Immutable heat fields can similarly be shared across transaction snapshots; mutable strategy extensions remain subject to rollback.

## Analysis and exports

Every planned trial contributes to the success denominator, including not-admitted, timeout, cancellation, interruption and infrastructure failure. Costs are compared only for common independently valid solved instances. Pairing includes exact scenario identity, seed, non-treatment parameters, source hash and metric version. Duplicate analysis units are rejected.

The primary independent unit is a scenario, not an agent, tick or repeated treatment. Estimates can show equal-weight scenario summaries and a fixed-seed, 2,000-draw percentile cluster bootstrap. With fewer than two units, intervals are unavailable. Intervals do not prove representative sampling, equivalence or superiority. Runtime distributions for solved runs are shown separately from failures; no uncensored speed-ranking claim is inferred.

`batch analyze` produces one canonical analysis JSON plus paired CSV, LaTeX and SVG/PDF/PNG success figures, with checksums and a cohort digest. The GUI exports the same analysis. Always retain the original manifest and all-outcome CSV alongside the analysis.

Empirical datasets are supplied separately from the software. A summary label alone cannot establish scenario, source, method or denominator identity; retain the full manifest and validation evidence for each study.
