# Read and change the code

Start with the [public API](PUBLIC-API.md) and one small executable example.
Then follow the owner of the behavior you want to change. The table below is a
reading order, not a requirement to learn every implementation module first.

| Task | Read in order | Contract to preserve |
| --- | --- | --- |
| Run a study | `examples/04_supervised_study.py` → `application/experiments.py:ExperimentService` → `application/experiment_execution.py:ExperimentExecutor` | Frozen manifest, all planned outcomes, one process owner |
| Import a map or roster | `core/movingai.py` → `application/movingai.py` or `application/article_suite.py` | Parse once, preserve order and raw-byte hashes, apply explicit selection policy |
| Change low-level search | `core/space_time_grid.py:SpaceTimeAStar` → `core/_space_time_search.py` | Movement order, heap ties, temporal reservations, absorbing arrival and bounded-search receipt |
| Understand a tick | `engine/world.py:WorldSimulation` → `engine/pipeline.py:SimulationPipeline` → relevant stage module | Observe before mutation; authorize a joint move before advancing time |
| Add a negotiation strategy | `core/protocols.py:AgentProtocol` → `agents/base.py:BaseAgent` → `agents/path_aware.py` or `agents/heatmap.py` | Recipient-local knowledge, owned state, transactional proposals and commitments |
| Change negotiation accounting | `negotiation/session.py` → selected protocol → `negotiation/ledger.py:OfferLedger` | Session deadline, acknowledgement budget, conservation and atomic settlement |
| Inspect storage or replay | `application/runs.py:RunRepository` → `application/_frame_archive.py` / `application/_replay_assessment.py` / `application/_replay_frames.py` | Publish before journal reference; physical assessment stays independent of rendering |
| Change HTTP or GUI behavior | `gui/app.py` → `gui/_services.py:WorkspaceServices` → relevant `gui/_api_*.py` route; `frontend/src/App.tsx` → workflow hook/component | Shared application services, cleanup, explicit unavailable evidence |

Paths in the table are relative to `src/mapf/` unless they begin with `examples/`
or `frontend/`. The [project map](PROJECT-MAP.md) covers the rest of the repository.
The [architecture guide](ARCHITECTURE.md) explains why these boundaries exist;
[extension contracts](EXTENDING.md) describe where another method plugs in.

## Ownership before patterns

Use a class when it owns a lifecycle, evolving state or a coherent contract.
`JobSupervisor` owns processes; `RunRepository` owns storage; `OfferLedger` owns
one session's accounting. Keep pure conversions and validation functions as
functions. A dataclass can carry named values without a service hierarchy.

Use structural protocols at an actual replaceable boundary: solvers,
environments, resource probes and experiment stores. Prefer composition for
those collaborators. `BaseAgent` is shared implementation for the included
negotiation strategies; another coordination protocol does not have to inherit it.
Avoid a factory, abstract base class or single-method wrapper without a concrete
consumer or lifecycle it simplifies.

Private modules group responsibilities, rather than splitting every method into
a file. `SearchFrontier` owns dominance and priority updates; `SpaceTimeSearch`
owns legal successors and stopping. Their hot-loop closures bind lookups once;
they are deliberately colocated and must be measured before further extraction.
`movingai.py` owns file syntax and metadata; `sampling.py` owns seeded synthetic
generation. The original generator imports from `core.movingai` remain available.

Long keyword signatures can be compatibility boundaries. Preserve documented
calls such as `article_spec`, `archived_article_spec` and `SpaceTimeAStar.search`.
Do not replace typed parameters with unchecked `**kwargs` merely to remove a
static-analysis warning. Introduce a request object when it expresses a reusable
concept, with a deliberate migration if the public interface changes.

## Comments and names

Follow the project style and [PEP 8](https://peps.python.org/pep-0008/) /
[PEP 257](https://peps.python.org/pep-0257/). Use domain names such as roster,
reservation, arrival tick and attempt. A class docstring should explain what it
owns, what it may mutate, and when it must be closed if that is not obvious.
Simple schema records need clear typed fields, not comments repeating each name.

Document units, ordering, failure meaning, side effects and scientific assumptions
at boundaries. Comments should explain a constraint that a refactor might break:
wait is the last successor, arrival is absorbing, raw archive bytes must not change,
or a missing measurement is unavailable. Remove obsolete optimization labels and
claims such as “zero overhead” or “full-state checkpoint” when they do not describe
the actual contract. Keep private review history outside shipped documentation.

## Tests that support a change

1. Capture a reachable failure with an independently specified expected result.
2. Test the owning boundary and an affected caller. A parser fix also needs an
   import/admission check; a process fix needs real cancellation/cleanup evidence.
3. For search or simulation refactors, compare paths, ordering, status, limits and
   metric receipts against an unchanged reference. Finite equality is a regression
   witness, not proof of algorithm equivalence.
4. Measure performance with the same workload, environment and instrumentation.
   Keep real integration checks while making unit-level clock/queue failures
   deterministic. Do not omit slow cases or weaken assertions to improve averages.
5. Run the affected [contribution checks](../CONTRIBUTING.md), then review the
   exact commit's CI and external analysis. A high coverage or Code Health score
   does not establish simulation correctness by itself.

Read every retained warning in context. Public compatibility, a small value type
and an unmeasured file are different cases; no single score replaces that review.
