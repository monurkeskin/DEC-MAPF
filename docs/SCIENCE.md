# Simulation and scientific interpretation

[Documentation index](README.md) · [Protocol details](TAOP-CONFORMANCE.md) · [Metrics](METRICS.md)

The application distinguishes an execution, a solver claim, a checked trajectory and an experimental comparison. Keeping these separate makes the GUI useful for explanation and the batch outputs suitable for later scientific analysis.

## Time, movement and arrival

At t=0 every agent occupies its start. A joint move advances time by one. Vertex collisions and opposite traversals of the same edge are illegal. Following and rotations with at least three agents can be legal when the destination and edge conditions hold. Moving diagonally is illegal.

| Setting | Waiting before arrival | Goal occupancy |
| --- | --- | --- |
| `SETTING_1` | Forbidden | Permanent |
| `SETTING_2` | Allowed | Permanent |
| `SETTING_3` | Forbidden | Removed after the arrival tick |
| `SETTING_4` | Allowed | Removed after the arrival tick |

First arrival is absorbing: an agent cannot visit its goal, leave, then call a later visit its first completion. Disappearance does not erase collisions at the arrival tick. An unfinished path is not an agent that has disappeared. Padding a reached goal for display/occupancy does not add action cost.

For a valid solved example with first-arrival times 3 and 5, sum of costs is 8 actions and makespan is 5 ticks. The t=0 states cost zero. A failed partial trace can contain fewer actions without being a better solution.

## Negotiations and commitments

This section describes the included decentralized negotiation methods. Physical trajectory checks and common outcome/cost metrics also apply to centralized solvers; protocol-specific token, commitment and negotiation measurements apply only to methods that implement and record them.

Each agent plans from its local observation. The engine detects conflicts, conducts bilateral negotiations, verifies commitments and resolves legal joint movement. The world-level safety/progress resolver and reached-state checks can use information beyond an individual agent's observation; this implementation detail must remain explicit when discussing decentralization. A global replay view does not expose its full state to the bidding agent.

The default protocol is **TAOP v2**. Repeating an offer increases acknowledgement usage; settlement transfers `max(proposer_usage - acceptor_usage, 0)` tokens only when an agreement commits. A repeat that cannot be afforded triggers a legal concession or a new allocation. Token pressure constrains the bargaining process, but does not prove that a geometrically feasible, commitment-compatible response exists under the movement/search limits.

The protocol may accept a longer feasible concession. Failed bounded concession searches stay inside the same bilateral session, with one absolute deadline. A new offer does not restart that timer. `negotiation_round_limit` is a diagnostic checkpoint in v2, while older protocol modes use it as a hard offer cap.

| Commitment | Retained obligation |
| --- | --- |
| SC (standard commitment) | The finite allocated subpath, represented as absolute vertices and edges |
| DC (dynamic commitment) | The allocation through the conflicting state, including the end of a conflicting edge transition |
| ZC (zero commitment) | The full allocation during the agreement tick; released after that tick's movement |

The acceptor owns the obligation to avoid the allocated opponent route. A subsequent agreement cannot overwrite a still-live promise. Zero commitment therefore does not permit the acceptor to undo the agreement before that same tick moves. These are the current executable semantics; see the [conformance document](TAOP-CONFORMANCE.md) for paper/Java interpretation and declared modern variants.

## Obstacle knowledge

Static map obstacles are known from the scenario. In settings 1/2, an agent also
remembers the parked cells it has actually observed, including after they leave
its FoV. This memory belongs to that recipient; it excludes unseen parked agents,
other recipients' observations and moving agents. Settings 3/4 create no
parked-cell memory. Detours, concession searches and replanning after a forced move
use the same known obstacles. Current visibility and remembered cells remain
separate in saved observations and the GUI.

## Five different limits

| Limit | Unit/scope | Consequence |
| --- | --- | --- |
| `timeout_sec` | Wall seconds for one owned process, including startup | Administrative process timeout; numeric up to 600, or null for decentralized jobs |
| `negotiation_deadline_sec` | Wall seconds for one bilateral session | Session timeout with scope/diagnostic evidence; default 60 |
| `max_steps` | Joint simulation ticks | Stops an unfinished execution at its declared step guard |
| `max_astar_expansions` | Nodes in one low-level search | Bounded search exhaustion; not proof of infeasibility |
| Experiment `wall_seconds` / `disk_mb` | Whole study execution/storage | Admission/continuation stops when the study budget is exhausted |

Centralized processes require a numeric cap. A decentralized `timeout_sec: null` removes only the whole-process cap; bilateral deadlines and study/step/search guards still apply. A longer wall deadline cannot fix a search that already stopped at a node limit. Conversely, a step cap does not limit how expensive one negotiation can be.

The raw API request model defaults to a five-second process cap; the GUI starts from the explicitly selected `interactive-v1` preset with a ten-second cap. Tutorial specifications set their own guards. Article-related profiles and study-specific settings are separate explicit configurations. Never infer the effective limit from a README example: inspect the frozen manifest.

## Validation and failure interpretation

Independent validation checks the exact roster, starts/goals, coordinates, obstacles, adjacency, waiting, vertex/edge collisions and absorbing arrival. It does not certify that the implementation matches every historical Java tie-break or that a numerical paper result was reproduced.

`valid_solution` is a complete valid trajectory. `valid_prefix` is an incomplete but physically legal trace. `invalid` includes a violating candidate. `not_checked` indicates unavailable candidate/trajectory evidence. A solver failure with no complete route need not be a collision bug; inspect the termination reason, diagnostic counters and configured bounds.

`permanent_goal_disconnection` proves that the reached state cannot finish because already arrived permanent agents disconnect a remaining goal in the static free-space graph. It does not prove the initial instance was impossible: earlier choices might have avoided that state. Disappeared agents and finite reservations are not permanent obstacles for this argument.

## Measurements and comparisons

| Question | Appropriate evidence |
| --- | --- |
| How often did a method solve the declared workload? | Valid solved trials divided by all planned trials, including timeouts and missing artifacts |
| Which method uses shorter paths when both solve? | Paired action costs on the explicitly common valid solved cohort, plus coverage |
| Is a route globally optimal? | A qualified optimal solution/certificate for the identical instance and semantics |
| How much information was delivered? | Recorded recipient-message receipts and the declared spatial or space-time definition |
| Is a runtime improvement established? | Matched hardware/load/budgets, all outcomes and a stated treatment of failures/censoring |
| Has the published experiment been reproduced? | Matched source/configuration/roster/protocol/analysis evidence for the claimed paper population |

Broadcast-only spatial sharing, all-message disclosure, space-time disclosure and payload bytes are separate quantities. Canonical JSON payload bytes are not measured network transport overhead. A centralized solver's global input is not an observed 100% decentralized broadcast-sharing score. Unavailable metrics remain unavailable.

The individual detour above static single-agent shortest paths is neither a certified joint optimality gap nor paper Eq. 2. The Eq. 2 form requires the named reference method set and a declared common-solved cohort. See [Metric definitions](METRICS.md) before assigning historical names to modern output columns.

## Repetition, sampling and uncertainty

The built-in policies/scheduler are deterministic for fixed effective inputs. Repeating a seed can measure execution variability but does not create a new independent policy sample. Generated geometry uses an owned seeded random generator; preserve the resulting coordinates as well as the seed.

Agents and ticks within one scenario share dependencies. Nested roster sizes, settings and solver treatments drawn from the same source scenario also need a common analysis unit. The experiment analyzer can use scenario-level summaries and a fixed-seed cluster bootstrap; finite sample intervals do not establish representative sampling, equivalence or superiority. Missing outcomes and common-solved selection can materially change interpretation.

Treat tutorial runs as software demonstrations, current declared cohorts as current measurements, archived aggregates as historical evidence, and the article's reported statistics as published results. [Reproducibility](../REPRODUCIBILITY.md) explains what is needed to connect them without changing their meaning.
