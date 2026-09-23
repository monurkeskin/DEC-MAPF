from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mapf.solvers.base import MAPFSolverProtocol


@dataclass(frozen=True)
class SolverMetadata:
    """Metadata describing a registered MAPF solver."""

    name: str
    is_centralized: bool
    description: str
    factory: Callable[..., MAPFSolverProtocol]
    constructor_inputs: tuple[tuple[str, str], ...] = ()
    supports_suboptimality: bool = False
    display_name: str | None = None
    resource_class: str = "optimal"


_REGISTRY: dict[str, SolverMetadata] = {}


def register_solver(
    name: str,
    is_centralized: bool = False,
    description: str = "",
    *,
    constructor_inputs: tuple[tuple[str, str], ...] = (),
    supports_suboptimality: bool = False,
    display_name: str | None = None,
    resource_class: str = "optimal",
) -> Callable[[Callable[..., MAPFSolverProtocol]], Callable[..., MAPFSolverProtocol]]:
    """Register a named solver factory or class.

    Example:
        @register_solver("CustomSolver", is_centralized=False)
        class CustomSolver(MAPFSolverProtocol):
            ...
    """

    def decorator(
        factory: Callable[..., MAPFSolverProtocol],
    ) -> Callable[..., MAPFSolverProtocol]:
        if not name.strip() or name != name.strip() or name.lower() in _REGISTRY:
            raise ValueError(
                f"Solver name is empty, padded or already registered: {name!r}"
            )
        if len({target for _, target in constructor_inputs}) != len(constructor_inputs):
            raise ValueError("Constructor parameter destinations must be unique")
        _REGISTRY[name.lower()] = SolverMetadata(
            name=name,
            is_centralized=is_centralized,
            description=description,
            factory=factory,
            constructor_inputs=constructor_inputs,
            supports_suboptimality=supports_suboptimality,
            display_name=display_name,
            resource_class=resource_class,
        )
        return factory

    return decorator


def solver_metadata(name: str) -> SolverMetadata:
    key = name.lower()
    if key not in _REGISTRY:
        available = ", ".join(sorted(meta.name for meta in _REGISTRY.values()))
        raise KeyError(
            f"Solver '{name}' not found in registry. Available solvers: {available}"
        )
    return _REGISTRY[key]


def create_from_inputs(name: str, inputs: dict[str, Any]) -> MAPFSolverProtocol:
    """Bind reviewed inputs using declared constructor metadata, never name guesses."""
    meta = solver_metadata(name)
    return meta.factory(
        **{target: inputs[source] for source, target in meta.constructor_inputs}
    )


def get_solver(name: str, **kwargs: Any) -> MAPFSolverProtocol:
    """Retrieve and instantiate a solver by registered name (case-insensitive).

    Args:
        name: Core registry ID (e.g. 'HeatMap' or 'CBS'); see list_solvers().
        **kwargs: Optional initialization arguments passed to solver factory.

    Returns:
        Instantiated object implementing MAPFSolverProtocol.
    """
    return solver_metadata(name).factory(**kwargs)


def list_solvers() -> dict[str, dict[str, Any]]:
    """Return dictionary of all registered solvers with metadata."""
    return {
        meta.name: {
            "name": meta.name,
            "is_centralized": meta.is_centralized,
            "description": meta.description,
        }
        for meta in _REGISTRY.values()
    }


def _register_builtins() -> None:
    """Register core built-in centralized and decentralized solvers."""
    from mapf.solvers.cbs import CentralizedCBSSolver
    from mapf.solvers.decentralized import DecentralizedNegotiationSolver
    from mapf.solvers.eecbs import CentralizedEECBSSolver
    from mapf.solvers.prioritized import CentralizedPrioritizedSolver

    # Decentralized Automated Negotiation Solvers (JAAMAS 2024)
    register_solver(
        name="HeatMap",
        is_centralized=False,
        description="Decentralized bilateral negotiation with spatial congestion heat awareness (JAAMAS 2024)",
    )(lambda **kw: DecentralizedNegotiationSolver(strategy="HeatMap", **kw))

    register_solver(
        name="PathAware",
        is_centralized=False,
        description="Decentralized bilateral negotiation with trajectory intersection avoidance",
    )(lambda **kw: DecentralizedNegotiationSolver(strategy="PathAware", **kw))

    register_solver(
        name="Greedy",
        is_centralized=False,
        description="Rejects voluntary concessions; TAOP-v2 can require a feasible concession",
    )(lambda **kw: DecentralizedNegotiationSolver(strategy="Greedy", **kw))

    register_solver(
        name="Conceder",
        is_centralized=False,
        description="Concedes when local replanning finds a feasible response",
    )(lambda **kw: DecentralizedNegotiationSolver(strategy="Conceder", **kw))

    # Centralized Solvers
    register_solver(
        name="CBS",
        is_centralized=True,
        description="Conflict-Based Search with Space-Time A*; optimality requires untruncated search",
        constructor_inputs=(("timeout_sec", "time_limit_sec"),),
    )(lambda **kw: CentralizedCBSSolver(**kw))

    register_solver(
        name="EECBS",
        is_centralized=True,
        description="Simplified Python focal CBS; legacy EECBS identifier, no certified bound",
        constructor_inputs=(
            ("timeout_sec", "time_limit_sec"),
            ("suboptimality", "suboptimality"),
        ),
        supports_suboptimality=True,
        display_name="Simplified focal CBS",
    )(lambda **kw: CentralizedEECBSSolver(**kw))

    register_solver(
        name="EECBS-1.1",
        is_centralized=True,
        description="Simplified Python focal CBS with weight 1.1; no certified EECBS bound",
        constructor_inputs=(("timeout_sec", "time_limit_sec"),),
        display_name="Simplified focal CBS-1.1",
        resource_class="bounded",
    )(lambda **kw: CentralizedEECBSSolver(suboptimality=1.1, **kw))

    register_solver(
        name="EECBS-1.0",
        is_centralized=True,
        description="Simplified Python focal CBS with weight 1.0",
        constructor_inputs=(("timeout_sec", "time_limit_sec"),),
        display_name="Simplified focal CBS-1.0",
    )(lambda **kw: CentralizedEECBSSolver(suboptimality=1.0, **kw))

    register_solver(
        name="Prioritized",
        is_centralized=True,
        resource_class="bounded",
        description="Sequential prioritized planning with reservation table constraint propagation",
    )(lambda **kw: CentralizedPrioritizedSolver(**kw))


# Initialize registry on import
_register_builtins()
