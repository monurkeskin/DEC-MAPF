# Metric definitions

Current metric identifier: `delivered-metrics-v2`. Old artifacts keep their recorded version. A zero measurement and an unavailable measurement are different states.

| Quantity | Definition and eligibility |
| --- | --- |
| Success rate | Independently valid solved trials / **all planned trials**. Never divide only by completed runs. |
| Sum of costs / makespan | First-goal arrival action counts; t=0 costs zero. Waiting at an absorbing goal does not inflate cost. Valid solved runs only for cost comparison. |
| Recorded action count | All recorded transitions, separately retained for failed prefixes and diagnostics. |
| Individual detour | Cost above the sum of static individual BFS shortest paths, divided by that sum. It is not paper Eq. 2 or a joint optimality gap. |
| Conditional Eq. 2 form | Per-instance excess over the shortest valid solution among the explicitly selected decentralized methods, averaged on the declared common-solved cohort. The available reference set must be named. A general two-method export labels its selected reference and does not imply an optimal baseline. |
| Certified optimality gap | Requires a qualified optimal solution for the exact same instance and semantics. Missing baseline means unavailable. A lower candidate cost than the alleged optimum is an error to investigate. |
| Information sharing | For each ordered sender/recipient pair, intersection of actually delivered **broadcast** coordinates with the final executed spatial set, divided by final spatial-set size, then averaged across all ordered pairs. Repeated locations collapse. Single-agent value is zero. |
| All-message disclosure | Same spatial definition including negotiation offers. Kept distinct from broadcast-only sharing. |
| Space-time disclosure | Uses absolute `(tick, x, y)` states for actual broadcasts/offers; revisits remain distinct. This is an explicitly different metric. |
| Messages / bytes / cells | Actual delivery receipts. Byte count is the canonical JSON message payload, not transport overhead or a guessed network packet size. |
| Token exchanges | Actual transferred amount on successful atomic settlements. Zero-token agreements add no transferred volume. |
| Token balances / Gini | Signed before/after receipts and complete roster. No clipping of negative balances or assumption that the initiator paid. Old session-only logs cannot recover balances reliably. |
| Safety interventions | Actual changes to desired movement, including an explicit semantic-violation flag. An intervention count alone does not establish physical validity. |
| Runtime | Solver wall time, validation/replay, queue and process wall time are separate. Process timeout includes spawn overhead. No cross-hardware or failure-conditioned speed-superiority inference. |

The legacy reconstructed sharing proxy is not computed for new experiments. It remains readable in historical bundles when present, explicitly labeled as a proxy. Offered utility/heat is `null` if the strategy did not provide it; response decision components are nested under their actual actor and are not relabeled as the proposer's utility. Telemetry events carry schema, sequence, phase, and available source/attempt/session linkage.

Online communication and settlement accounting runs independently of trace retention. Metrics-only retains executed paths and counters but omits event/frame histories. Events mode records event/replay data; full trace additionally includes local observations, plans and commitments. Trace overflow is visible in its receipt. Disk telemetry uses a bounded queue and checked gzip chunks: a completed prefix can be read after a crash, but queued/unpublished events may be lost. This is not an exact solver resume log.

Per-tick negotiation counts are retained in metrics-only runs as `negotiations_by_tick`, alongside total and successful session counts. Keys are simulation ticks (t=0 included when a session occurred). A missing key within a recorded run means zero sessions at that tick; an unavailable curve for an uninstrumented solver is omitted, not fabricated as zeros. Cross-run curves must declare their solved cohort, denominator and handling of finished runs.

## Event-derived diagnostic summaries

Negotiation success in an event report is conditional on recorded bilateral sessions, not the experiment-wide solution success rate. With no recorded sessions, the rate is `null` and `available` is false. The wait ratio is likewise unavailable without recorded moves. Token summaries require a roster or actual balance receipts; absent balances and ambiguous legacy session records remain unavailable. The CLI and HTML report display these values as **Unavailable**; a measured zero stays zero. Token statistics reconstructed without a full roster describe only the recorded participants (`roster_complete: false`).
