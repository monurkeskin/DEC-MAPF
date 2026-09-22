# Design rationale

The initial alpha separates simulation semantics, experiment execution, independent validation and presentation. The following boundaries make the system inspectable and extensible without treating a software check as a scientific result.

| Boundary | Design | Verification and limits |
| --- | --- | --- |
| Independent validation | Validate roster, geometry and trajectories separately from solver success. | Reject missing/unknown agents, incorrect starts, illegal movement and goal departure. An unfinished legal prefix is not a solution. |
| Joint movement | Preserve legal greedy moves; bound repair while enforcing waiting permission, live commitments and future parked occupancy. | Refuse an unauthorized joint step atomically. Physical validation and protocol obligations remain separate. |
| Solver geometry | Use instance geometry for omitted defaults; reject explicitly conflicting configuration. | Entry-point witnesses check consistent behavior across built-in solvers. |
| Solver identity | Display SimplifiedFocalCBS for the Python focal implementation, including its `EECBS` aliases. | Registry/capability tests do not confer a published EECBS bound. |
| Commitments | Store per-contract reservations with explicit ownership and absolute time. | SC/DC/ZC witnesses cover finite expiry and simultaneous obligations to different partners. |
| Tentative decisions | Snapshot owned participant state; validate tentative proposals and apply settlement atomically. | Exception and token-conservation witnesses check rollback. External I/O inside strategy callbacks cannot be rolled back. |
| Information disclosure | Count actual delivered broadcasts and distinguish spatial disclosure from space-time/all-message metrics. | Missing receipt evidence remains unavailable; see [metrics](METRICS.md). |
| Identity and durability | Separate condition digests from job/run/attempt identities; use a SQLite journal, atomic artifact writes, directory ownership and a process watchdog. | Failure, cancellation, restart and idempotency tests exercise recovery boundaries. |
| Portable JSON | Canonicalize with RFC8785 across Python and JavaScript. | Round-trip and tampering checks cover numeric representation and checksum consistency. |
| Costs and comparison | Derive first-goal action costs from paths, retain solver-reported values and pair on declared identities. | Common-solved cost cohorts differ from all-planned success denominators. |
| Replay | Start at t=0 and retain observation timestamps, current plans and commitments. | Local received information and global hindsight use distinct visual layers; absent information is unavailable. |
| Renderer | Use React/TypeScript/Vite, Canvas 2D and native controls with a bounded frame cache. | Coordinate, workflow and accessibility checks qualify finite interactions. A retained renderer spike supports performance investigation. |
| Packaging | Lock dependencies and bundle the built GUI with Python source. | Installed-wheel checks run outside the checkout; Node is unnecessary at wheel runtime. |
| Research evidence | Keep synthetic correctness fixtures separate from empirical datasets and published results. | Acceptance tests neither supply the article's full experiment matrix nor establish numerical replication. |

For implementation responsibilities, read [architecture](ARCHITECTURE.md). For behavior, read [algorithm semantics](ALGORITHM.md). A passing test supports its declared stimulus and expectation, not universal collision freedom or equivalence to the complete published study.
