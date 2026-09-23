# Mechanism contract and source limits

Method identifier: `dec-mapf-token-concession`; default application protocol: `taop-v2`. Every application plan records the effective protocol. The low-level `BilateralNegotiationSession` constructor also supports alternate protocol modes; select the protocol explicitly when using it directly. Full Java or published-score equivalence is not claimed. See [algorithm semantics](ALGORITHM.md) for the execution model.

## Concession before token exhaustion

The article requires concession when no tokens remain. It also permits ending without consensus and describes failed settlement, so finite tokens alone do not prove agreement for every constrained instance. Java's `run_concede` accepts an opponent allocation whenever a response path is feasible, even when longer.

`taop-v2` accepts legal longer responses when the strategy concedes. Before acknowledging an unaffordable repeat, the protocol attempts a feasible concession, then an unoffered allocation. A zero-token responder likewise takes a feasible concession. Searches retain local observations, commitments, waiting rules and declared search/step budgets. Fallback proposal search considers eight candidates with at most `max(2, negotiation_horizon)` extra actions: an explicit modern finite bid space, not exhaustive Java equivalence. An unsuccessful bounded search is not proof of impossibility and cannot create an agreement.

Failed attempts remain inside the same absolute session deadline. The offer-count field is a diagnostic checkpoint in the default protocol. Token refusal does not reset the clock. Only deadline expiry stops a stalled default-protocol negotiation; malformed participant output and infrastructure exceptions remain explicit errors. Trial/batch budgets and physical execution stopping conditions are separate. Alternate protocol modes have distinct stopping rules and must not be pooled as the same method.

Hard timeout diagnostics persist phase, participant, round, balances, acknowledgements, concession/repeat counts, search status, declared limits and the last 16 decisions. They identify the last observation and its age, without inferring unobserved execution. Cooperative expiry also emits `NEGOTIATION_STOP` and restores both participants before movement. Token settlement remains the positive usage difference, not the entire initial balance or a payment at each offer. The article's initial free offer and Java's charge for the initial broadcast remain an explicit source difference.

## Source interpretation

The [published JAAMAS article](https://link.springer.com/article/10.1007/s10458-024-09639-8), section 4 and Fig. 2, describes cumulative acknowledgement usage when an agent repeats an earlier offer. `OfferLedger` checks *any* prior own offer, charges one further acknowledgement, refuses an overdraft, and transfers only on agreement. The acceptor receives `max(proposer_usage - acceptor_usage, 0)`. The printed `min` expression conflicts with the prose/example and archived Java settlement; the positive-difference interpretation is explicit here.

First new offer usage is zero; archived Java also charges repetition of the initial broadcast. This difference must accompany cross-implementation comparisons.

Commitment obligations belong to the acceptor and reserve the proposer's allocated subpath. SC retains the finite allocation. DC ends at the absolute conflicting state, inclusive; an edge conflict recorded at departure t therefore binds through arrival t+1. ZC protects the entire offered allocation during the current decision tick and releases it only after the tick's movement.

The proposer can subsequently replan, but becoming a proposer does not erase obligations from earlier acceptor roles. New contracts are checked against those obligations before settlement. Unit tests use nonzero absolute start ticks and inspect both parties' reservations.

Both settlement callbacks execute atomically over owned strategy state: if either raises or violates token conservation, both agents' state is restored. External I/O inside callbacks cannot be rolled back and is outside the strategy contract.

The original Java `HeatMapAgentMC0`/`PathAwareAgentMC0` store allocations in `PostNegotiation` and clear memory in `OnMove`, after advancing position and the clock. `HeatMapAgentMCDyn` includes `index+1` for a swap. SC/DC Java memory can also be discarded after an observed change in the beneficiary's broadcast; the paper does not explicitly state that release rule.

The modern implementation retains the finite agreed allocation, following section 4.1's resource obligation, even if the beneficiary replans. This explicit interpretation can be stricter than that Java behavior. Commitments to distinct contracts accumulate; expiry of one does not erase another.

Proposal/response evaluation is side-effect-free at the session boundary. A rejected proposal does not commit a plan or balance. Strategy plugins should return a `BidDecision`/candidate and keep mutable state in the owned agent object; avoid external/global side effects. Paths are immutable tuples of immutable coordinates, while JSON still uses arrays.

## Observations, horizons and execution

Spatial FoV is an odd square width. Broadcast and allocation horizons are independently recorded counts of path points, defaulting to FoV width. Conflict detection cannot inspect a transition beyond the available broadcast/allocation horizon. Each strategy receives an immutable recipient observation and owned static configuration through `LocalEnvironment`, without a world/agent registry reference. Static obstacles are known; dynamic parked agents and other paths require an actual observation. Before physical movement, every fallback view is captured at the same simulation phase.

Actual deliveries record sender, recipient, tick, finite payload, bytes and session linkage. Duplicate queries for an unchanged payload at one tick do not invent transmissions. Initial plans and observations are captured at t=0. Post-move frames retain the timestamp of the local observation used for decisions. Global hindsight heat and executed paths are separate from received beliefs in the UI.

Protocol diagnostics distinguish agreement, invalid contracts, malformed bidders and the stopping conditions of the selected mode. Process timeouts are execution failures, not protocol proofs. A bounded replan failure does not prove the instance unsolvable. Safety overrides record desired/actual movement. The movement resolver checks live obligations and waiting permission before authorizing every joint move; infeasibility or repair exhaustion stops that joint step atomically. Independent trajectory validation controls physical success and catches malformed strategy output. Physical validity and protocol conformance are separate evidence boundaries.

## Explicit modern variants

HeatMap excludes the negotiating opponent from congestion and indexes the other agents' broadcasts by relative time. It uses a finite Manhattan kernel with center weight 1. The archived Java code also sets the agent-center weight to 1; its CAP=999 applies to obstacles, not ordinary agent centers. The kernel construction and bounded deterministic candidate generator are explicit implementation choices; matching the center alone does not establish heat-field equivalence.

HeatMap ranks normalized path-plus-congestion costs with an explicit length tie break. The `taop-v1` alternative rejects longer responses; `legacy-alternating-v1` uses bounded-detour acceptance. These selectors describe different protocol behaviors, not software releases.

The concession trigger uses remaining-token and remaining-path fractions relative to their initial values, following the archived Java strategy structure. Printed Algorithm 1 instead compares absolute remaining quantities. The modern implementation also guards zero denominators and counts path actions rather than stored vertices. This source difference is retained explicitly; it is not an exact implementation of every printed pseudocode expression.

Partner ordering is deterministic. Sessions are disjoint within one conflict snapshot; completed sessions release their lock before the next verification pass, so one agent can negotiate with multiple partners before movement. The finite pass limit and the global movement resolver remain modern variants of Java's re-verification loop.

The article repeated randomized partner/suboptimal-bid selection five times; repeating an identical modern deterministic configuration is a reproducibility check, not five independent policy samples. Original Java candidate generation and historical scenario selection also remain different. These differences must accompany comparisons, even if the new scores happen to match.

The article's 60-second bilateral negotiation deadline is separate from an optional whole-process administrative cap. The clock begins before session preparation and renews only for a new session, including another session at the same world tick. Cooperative checks surround proposal/response work and settlement; expiry restores both owned agent states and stops the scenario before movement.

The application supervisor additionally watches session lifecycle over its private worker pipe and terminates an unresponsive owned worker, recording the distinct timeout scope without inventing a validated prefix. Direct in-process calls do not have that external hard-preemption boundary.

The article-roster builder sets 60 seconds per session and no overall per-trial wall cap unless explicitly configured. The experiment wall budget, world-step/search/offer-count/pass guards remain explicit and do not establish impossibility when exhausted. Other non-deadline negotiation failures follow the declared re-verification behavior; the article's broader scenario-on-negotiation-failure statement is not an equivalence claim for those paths.

CBS checks independent output validity and reports optimality as unavailable after a bounded low-level branch was pruned. The simplified focal solver has `EECBS` aliases but no certified EECBS bound. External adapters require declared settings/coordinate order, record binary SHA and validate paths; a parser fixture or binary hash alone does not qualify an optimal oracle.
