# Add solvers and coordination protocols

DEC-MAPF provides shared experiment infrastructure for decentralized and centralized methods. Start with the [method comparison](../examples/method-comparison.json) and [experiment workflow](EXPERIMENTS.md), then choose the boundary that fits your method. Scenario loading, batch scheduling, independent trajectory validation, result storage and common metrics can remain shared.

| Extension | Integration boundary | Method-specific work |
| --- | --- | --- |
| Centralized planner | `MAPFSolverProtocol` and an importable registered factory | Planning algorithm, constructor inputs, supported settings and termination behavior |
| Strategy within the existing negotiation protocol | `AgentProtocol` / `BaseAgent` and the decentralized solver's strategy composition | Proposal/response policy compatible with TAOP, local observations and commitment rules |
| Auction-based or another decentralized coordination protocol | Its own `MAPFSolverProtocol` implementation and coordination engine | Allocation/communication rules, declared information access, configuration, capabilities and optional diagnostic events |

Centralized and decentralized adapters both receive `MAPFInstance` and `SimulationConfig`, and return `MAPFSolution`. Set `is_centralized` to describe the method's actual information/control model. The Python protocol unifies execution and results; an adapter supplies the algorithm.

## A new coordination protocol

An auction-based method can use the shared experiment workflow by implementing and registering its own solver adapter. Develop and qualify it in these steps:

1. Declare the physical settings, agent observations, communication, allocation rules and stopping conditions. Return paths with the initial positions at `t=0`, canonical action costs and an honest success state.
2. Implement the coordination inside the adapter or a dedicated engine. The included `WorldSimulation` pipeline, `NegotiationStage`, token ledger and commitment callbacks implement the existing negotiation approach. A different protocol needs its own coordination logic; changing a negotiation mode label does not supply that logic.
3. Register a top-level factory, including constructor bindings, and import it in every process entry point that should expose the method. Use the working registration example below to verify spawned-worker composition.
4. Define any new request fields, defaults, validation and effective-input identity. The current application derives FoV/token/commitment/negotiation controls for every non-centralized registration. Adapt those capability descriptors and method/version metadata for a protocol with different requirements, then regenerate API/client contracts.
5. Return trajectories through the common validator and result format. Generic path replay and physical metrics use that boundary. New bid, allocation or communication diagnostics require explicit event schemas and readers; the existing negotiation inspector cannot interpret an auction transcript automatically. Distinguish unrecorded measurements from measured zeros.
6. Start with small independent correctness and failure fixtures, then exercise the real supervisor, cancellation, export/import and installed-package workflow. Compare methods on declared matched scenarios and budgets.

This describes the integration route for additional methods. The included decentralized implementations currently use negotiation; an auction mechanism must be supplied by the extension.

## A strategy within the existing negotiation protocol

Agents implement `core/protocols.py:AgentProtocol`; `agents/base.py` supplies path application, movement, owned state and commitment handling. `make_bid` receives an immutable `LocalEnvironment`; a bid contains `bidder_id`, `proposed_path`, `token_offered`, and `round_num` as declared by `core/models.py`. Inspect the actual model before implementing a callback. `propose_response` returns a decision and proposed own path; the session validates and applies it. Never use global world state or external side effects inside proposal/settlement callbacks. TAOP acknowledgement is owned by the session ledger, not fabricated by a strategy.

## Register a solver for shared experiments

Solvers implement `solvers/base.py:MAPFSolverProtocol`. Register a solver in `solvers/registry.py` and apply `solvers/validation.py:validated_solver` at its public boundary. Registration alone does not import a plugin in a spawned worker: make its module import explicit in the package's registration composition. Add capability metadata, exact parameters and physical/termination fixtures before exposing it through the application. Do not infer optimality from the solver name.

## A complete registration example

```bash
uv sync --locked --python 3.12
uv run --no-sync python examples/05_registered_solver_study.py --workspace runs/registered-study
uv run --no-sync python examples/05_registered_solver_study.py --workspace runs/registered-study --resume
```

This registers **TutorialCBS**, an alias of the existing validated CBS method,
then plans, executes a fresh spawned worker, independently validates its path and
exports all outcome rows plus a checked replay bundle. Resume preserves the
completed attempt. It introduces no new strategy or algorithm claim. Registration
at module scope is deliberately re-executed by multiprocessing spawn; the actual
study is guarded by `if __name__ == "__main__"`.

The alias declares `constructor_inputs=(("timeout_sec", "time_limit_sec"),)`.
The application binds those fields through registry metadata instead of recognizing
the class by name. Case-insensitive duplicate names cannot overwrite an existing
method. UI parameter defaults, ranges and choices derive from the request schema.
Built-in direct agent strategy names are case sensitive and validated at runtime;
the general solver registry remains case insensitive.

The teaching alias is available in that script's process family. It is not
automatically installed into unrelated CLI/GUI processes. A maintained extension
must be imported by their registration composition and included in source/version
provenance. Changing an algorithm requires its own scientific identity and
qualification, even when it implements the same Python protocol. Do not use the
historical `02_custom_negotiation_agent.py` initialization sketch as a qualified
TAOP-v2 implementation. See [Architecture](ARCHITECTURE.md) for the service and
persistence boundaries.

Current telemetry is a discriminated `telemetry-2` union in `telemetry/schema.py`; it is exported to `docs/gui/telemetry.schema.json`. New event kinds require schema/hook/reader compatibility and explicit phase, identity, optional-value and backpressure semantics. Preserve old artifacts, version changes and regenerate OpenAPI/client models. A missing utility is null, not zero.

Meaningful acceptance covers the method's declared physical settings, information boundary, bounded execution, cancelled/failed outcomes and all-planned analysis. For negotiation extensions, also cover rejection rollback, token conservation and commitments; another protocol needs checks for its own allocation and communication invariants. Use the repository's locked interpreter, Ruff, Mypy and pytest commands from the README. Installed-wheel and real-browser checks are required for package or UI changes; source-only imports are insufficient evidence.

## Supported imports and consumer checks

Use [mapf.api](PUBLIC-API.md) for the supported surface and `check_solver` / `check_run_bundle` for finite consumer witnesses. The installed [registration example](../examples/05_registered_solver_study.py) verifies that an unchanged existing method can be registered at module scope and used by spawned workers.

Next: retain a minimal failure test with any extension change.
