# Algorithm and execution semantics

This guide describes the simulation execution model. The method identifier is `dec-mapf-token-concession`; application plans select `taop-v2` by default. A method name alone does not identify an experiment: retain source checksums, effective inputs, dependency locks and the execution manifest. The [protocol contract](TAOP-CONFORMANCE.md) explains the interpretation of the article and Java sources.

## Physical model and independent validation

| Setting | Wait before goal | Occupancy after arrival |
| --- | --- | --- |
| 1 | No | Remain |
| 2 | Yes | Remain |
| 3 | No | Disappear after the arrival tick |
| 4 | Yes | Disappear after the arrival tick |

Paths start at t=0. Independent validation checks the roster, starts/goals, adjacency, bounds, obstacles, waiting permission, vertex and reverse-edge collisions, and departure after arrival. Following and rotations of three or more agents are legal when destinations and edges are legal. Trailing goal padding adds no action cost. An unfinished path does not disappear just because its recording ends. A claimed solution with missing paths is invalid; an unsuccessful search without a complete candidate has unavailable solution validation.

## Negotiation and commitments

HeatMap and PathAware act on immutable recipient-local observations. Their concession trigger uses remaining-token and remaining-path fractions relative to their initial values. In the default protocol, an unaffordable repeated offer triggers feasible concession or unoffered-allocation search. Concession may accept a longer legal response path. An unsuccessful bounded search does not establish impossibility or create an agreement.

SC retains the finite agreed allocation. DC binds through the conflicting state, including the arrival endpoint of an edge swap. ZC protects the full allocation during the agreement tick and expires after its movement. Obligations belong to the accepting agent and accumulate across contracts. Becoming a proposer in another negotiation does not erase them. A new agreement must respect outstanding obligations. Proposal/response evaluation is tentative; settlement callbacks execute atomically over owned agent state with token conservation checks.

The bilateral deadline defaults to 60 seconds and includes preparation, offers, responses and settlement. Offers and diagnostic checkpoints do not reset it. Process, batch, simulation-step, search and verification-pass limits are separate declared controls. The supervisor can terminate an unresponsive owned worker; direct in-process calls have cooperative checks only. See [experiment bounds](EXPERIMENTS.md#bounds-interruptions-and-retries).

## Planning, movement and bounded recovery

Incomplete non-goal plans are replanned at the beginning of a tick using observed parked obstacles, absolute reservation times and the remaining declared budgets. A failed bounded search does not move an agent, fabricate a route or count as arrival. Search rejects a starting state covered by another agent's permanent reservation. Incomplete paths retain occupancy in conflict detection under disappear-at-goal settings.

Every joint move must satisfy adjacency, obstacles, distinct destinations, reverse-edge safety, waiting permission and outstanding commitments. Permanent goal arrival also checks future reservations. Ordinary legal greedy moves are preserved. Otherwise, bounded repair searches legal neighboring actions in affected components, with a shared limit of 10,000 assignments per tick. Exhausted domains yield `movement_constraints_infeasible`; an exhausted search budget yields `movement_repair_budget`. The entire joint step stops before movement or time advances if it cannot be authorized. Neither reason proves that a different execution history could not solve the instance.

When every active agent is held despite a request to move, bounded recovery also searches for legal progress under the same obligations. Intentionally planned joint waits are preserved. If progress cannot be found, a permitted wait remains legal. `MOVEMENT_REPAIR.cause` separates progress repair from semantic repair; `progress_unavailable` does not mean every legal action is infeasible.

Movement authorization uses world-level information. It is a separate simulation safeguard from the agents' local negotiation policy and does not establish decentralized completeness. Physical trajectory validity and compliance with negotiated obligations are distinct checks.

## Permanent disconnection in a reached state

For stay-at-goal settings, static obstacles and permanently arrived agents can separate a remaining agent from its goal. The world checks this condition before another decision/movement step and records `permanent_goal_disconnection` with a `REACHED_STATE` diagnostic. Component labels change only when the complete set of permanent occupied cells changes. Movable agents, finite reservations and disappearing arrivals are excluded.

Disconnection proves that this reached state has no continuation under absorbing-goal semantics. It does not prove that the initial instance was infeasible; connectedness does not establish a MAPF solution. The check does not disclose global information to an agent, release a commitment or choose a new action. Incomplete-prefix metrics must remain separate from solved-path costs.

## Search, scheduling and observation reuse

HeatMap uses a finite Manhattan congestion kernel with center weight 1, excludes the negotiation opponent, and indexes other agents' broadcasts by relative time. Candidate generation, normalized path-plus-congestion ranking, length tie breaks, deterministic partner ordering and bounded verification passes are explicit implementation choices. They are not claims of identical Java search or stochastic scheduling.

Unchanged conflict queries reuse immutable results. Rosters smaller than 16, or changes to more than half the plans, use a full scan; sparse changes in larger rosters update occupancy buckets. The full detector and public observation queries remain reference implementations. Recipient observations reuse immutable messages while checking custom-agent state changes. These cache rules preserve the declared query semantics.

Generation uses owned seeded random generators. Built-in policies and scheduling are deterministic and do not consume that stream or reseed the caller's global RNG. A stochastic extension must declare its own policy/scheduler seed. Repeating an identical deterministic configuration does not create independent policy samples.

The fixtures in `tests/fixtures/engineering*-confirmation-v1.json` cover nonconflicting motion and simultaneous crossings across SC/DC/ZC and Settings 1–4. They compare paths, costs, delivered-message metrics, balances, observations and commitment frames; per-run session UUID labels are normalized. `scripts/confirm_engineering.py` preserves every outcome. These are bounded software regressions, not a held-out article generalization study.

## Centralized comparators and interpretation

CBS is checked against an independent tiny joint-state oracle. Pruning a bounded low-level branch suppresses its optimality certificate. SimplifiedFocalCBS uses action counts and has no certified published-EECBS bound; its `EECBS` aliases identify that implementation only. Prioritized Planning is order-sensitive and incomplete.

Optional native profiles distinguish EECBS from CBSH2-RTC, declare physical settings and coordinate order, record executable/source hashes, and independently validate returned paths. CBSH2-RTC profiles are limited to Settings 1/2. A parser fixture, declaration or binary checksum alone does not qualify an optimal oracle. See [native baselines](NATIVE-BASELINES.md) and [centralized semantics](CENTRALIZED-CONFORMANCE.md).

Read [metrics](METRICS.md) and [comparison boundaries](REPRODUCIBILITY-NOTES.md) before interpreting scores. No finite software test establishes universal correctness, published-score equivalence or completeness.
