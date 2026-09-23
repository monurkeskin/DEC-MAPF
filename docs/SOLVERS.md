# Solver identities and selection

[Documentation index](README.md) · [Parameters](PARAMETERS.md) · [Centralized conformance](CENTRALIZED-CONFORMANCE.md)

Decentralized and centralized methods share scenario inputs, supervised execution, trajectory validation and result analysis. Start with the [eight-trial comparison](../examples/method-comparison.json), then choose a solver by its actual implementation and supported physical settings. A familiar label or a solved toy example does not establish equivalence with a published algorithm.

| Batch/API ID | GUI name / role | Interpretation |
| --- | --- | --- |
| `Decentralized-HeatMap` | HeatMap | Local negotiation with recorded congestion-aware planning weights |
| `Decentralized-PathAware` | PathAware | Local negotiation using path-related preferences |
| `Decentralized-Greedy` | Greedy | Rejects voluntary concession; the protocol still requires feasible concession when tokens are exhausted |
| `Decentralized-Conceder` | Conceder | Accepts an opponent allocation when local replanning finds a feasible response |
| `CBS` | CBS | Python conflict-tree search; resource limits and low-level truncation matter |
| `Prioritized` | Prioritized Planning | Centralized sequential planning; order dependent and incomplete |
| `EECBS`, `EECBS-1.0`, `EECBS-1.1` | Simplified focal CBS | Legacy names for the simplified Python variant; not qualified published EECBS |
| Catalog-specific native IDs | Native EECBS / CBSH2-RTC | Separate executables, source/build receipts, setting-specific profiles and licenses |

`mapf solvers` lists the core registry. `GET /api/v1/capabilities` lists application IDs, parameter metadata and any configured native profiles. The application accepts the core decentralized aliases and canonicalizes them in the effective plan; use the explicit `Decentralized-*` IDs in portable batch examples.

## Begin with the question you want to inspect

Use the common experiment matrix to compare decentralized and centralized methods. HeatMap with a small full trace exposes local congestion-aware decisions; PathAware provides another strategy within the same negotiation protocol. Prioritized Planning offers a centralized sequential planner. A successful illustrative case does not make Prioritized a complete algorithm or the selected map representative.

Use Python CBS for small controlled comparisons and semantic tests. A bounded failure is not an impossibility result; an optimality claim also requires that the relevant search was not truncated. Raising a nominal focal weight on SimplifiedFocalCBS does not establish a published EECBS suboptimality guarantee.

## Optional native comparators

Native EECBS profiles distinguish stay/disappear semantics and all four movement settings. Qualified CBSH2-RTC profiles cover Settings 1/2 only. The registered catalog binds an executable hash, invocation, setting and qualification scope. Wrong-setting requests fail instead of silently running a different physical model.

The native reconstruction includes documented correctness patches and deterministic tie handling. Those changes, native seed, selected weight and full command receipt belong in any paper comparison. The binaries are not byte-identical recovery of the historical Windows executables. Follow [Native baselines](NATIVE-BASELINES.md) for pinning, build, qualification and licenses.

## Stable comparison inputs

Keep scenario roster/order, physical setting, seed, source and all non-treatment configuration fixed. GUI fields that do not apply to a centralized solver are listed as inactive in preview; their presence in a request is not evidence that the solver used negotiation. Some input fields are retained for identity even when inactive, so inconsistent defaults can prevent a strict pair match. Start from the same request and change only the declared treatment.

Run both methods under a declared budget policy. If the policy changes, freeze a new study and preserve original terminal outcomes. Use [all-planned analysis](HEADLESS.md#4-analyze-matched-strategies) and show common-solved coverage before interpreting cost differences.

## Add a method

Use the [extension guide](EXTENDING.md) to register a centralized planner, develop a strategy within TAOP, or integrate another decentralized coordination protocol. The shared solver contract returns physical trajectories and common results; additional protocol behavior, parameters and diagnostics belong to the method's implementation.
