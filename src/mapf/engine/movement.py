"""Movement resolution engine for multi-agent path finding."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mapf.core.models import Point
from mapf.engine._movement_resolution import (
    GreedyResolution,
    JointRepair,
    MoveAuthorization,
    MoveCandidates,
    candidate_components,
)

if TYPE_CHECKING:
    from mapf.core.protocols import AgentProtocol, EnvironmentProtocol


class JointMoveFailure(RuntimeError):
    """No authorized joint action was found; callers must not advance time."""

    def __init__(self, reason: str, receipt: dict[str, Any]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.receipt = receipt


class MovementResolver:
    """Resolves step-level agent movements preventing vertex and edge collisions.

    Provides deterministic collision-free movement resolution:
    - Eliminates vertex collisions (no two agents enter the same cell).
    - Eliminates edge swap collisions (no two agents pass each other in opposite directions).
    - Prioritizes agents by token balance (higher tokens take priority), then deterministic agent_id.
    - Under allow_wait = False, if an agent's preferred next step is contested, it evaluates
      the 4 adjacent neighbors and takes a lateral evasive step to the free cell closest to its goal.
    - Bounded repair revisits greedy choices that violate no-wait or live
      commitments. If no authorized joint action is found, no move is returned.
      Failed immediate-step repair is not global MAPF infeasibility.
    """

    @staticmethod
    def resolve_step(
        active_agents: dict[str, AgentProtocol],
        desired_moves: dict[str, Point],
        occupied_permanent: dict[Point, str],
        allow_wait: bool,
        env: EnvironmentProtocol,
        *,
        diagnostics: dict[str, Any] | None = None,
        max_repair_nodes: int = 10000,
        current_time: int = 0,
    ) -> dict[str, Point]:
        """Return a collision-free joint step obeying movement and commitment rules.

        Raise JointMoveFailure when bounded repair cannot authorize
        a step. Callers must leave physical time and positions unchanged.
        """
        if max_repair_nodes < 0:
            raise ValueError("Movement repair budget must be nonnegative")
        if not active_agents:
            return {}

        choices = MoveCandidates(active_agents, occupied_permanent, env)
        current = choices.current
        candidates = {aid: choices.preferred(aid, desired_moves.get(aid, current[aid]), allow_wait)
                      for aid in active_agents}
        priority = sorted(active_agents, key=lambda aid: (-active_agents[aid].tokens, aid))
        resolved = GreedyResolution(candidates, current, priority).resolve()
        authorization = MoveAuthorization(active_agents, allow_wait, env, current_time)
        assessment = _MoveAssessment(current, desired_moves, resolved, authorization)
        assessment.recover(choices, candidates, priority, max_repair_nodes, diagnostics)
        MovementResolver._verify_safety(current, resolved)
        return resolved

    @staticmethod
    def _verify_safety(current: dict[str, Point], resolved: dict[str, Point]) -> None:
        assert len(set(resolved.values())) == len(resolved), (
            f"MovementResolver invariant violated: multiple agents sharing cells: {resolved}"
        )
        owners = {(point.x, point.y): aid for aid, point in current.items()}
        assert not any(
            (peer := owners.get((target.x, target.y))) is not None
            and peer != aid and resolved[peer] == current[aid]
            for aid, target in resolved.items()
        ), "MovementResolver invariant violated: reverse-edge collision"

    @staticmethod
    def _repair_joint(
        candidates: dict[str, list[Point]],
        admissible: dict[str, list[Point]],
        current: dict[str, Point],
        resolved: dict[str, Point],
        priority_order: list[str],
        max_nodes: int,
        blocked: set[str],
        *,
        require_progress: bool = False,
    ) -> dict[str, Any]:
        """Find authorized assignments only in components with a blocked move.

        Components include current cells as well as all possible destinations,
        so neither shared destinations nor reverse edges cross components.
        Exhaustive failure certifies only *this immediate step*. No partial repair
        can authorize movement if any component remains blocked.
        """
        components = candidate_components(candidates, current, priority_order)
        search = JointRepair(current, priority_order, max_nodes, require_progress)
        return search.resolve(components, admissible, resolved, blocked)


class _MoveAssessment:
    """Authorize a greedy result and recover only an identified semantic hold."""

    def __init__(self, current: dict[str, Point], desired: dict[str, Point],
                 resolved: dict[str, Point], authorization: MoveAuthorization) -> None:
        self.current, self.desired = current, desired
        self.resolved, self.authorization = resolved, authorization
        self.blocked = {aid for aid in current if not authorization.allowed(aid, resolved[aid])}
        self.forced_holds = self._forced_holds()
        self.progress_recovery = self._requires_progress()

    def _forced_holds(self) -> set[str]:
        return {aid for aid, point in self.current.items()
                if self.resolved[aid] == point and self.desired.get(aid, point) != point}

    def _requires_progress(self) -> bool:
        if self.blocked or not self.authorization.allow_wait:
            return False
        return bool(self.forced_holds) and all(
            self.resolved[aid] == point for aid, point in self.current.items()
        )

    def recover(self, choices: MoveCandidates, candidates: dict[str, list[Point]],
                priority: list[str], max_nodes: int, diagnostics: dict[str, Any] | None) -> None:
        if not self.blocked and not self.progress_recovery:
            return
        # Expand choices only for recovery; ordinary priorities stay intact.
        choices.recovery(candidates, self.progress_recovery)
        admissible = {aid: [p for p in points if self.authorization.allowed(aid, p)]
                      for aid, points in candidates.items()}
        repair = MovementResolver._repair_joint(
            candidates, admissible, self.current, self.resolved, priority, max_nodes,
            self.blocked or self.forced_holds, require_progress=self.progress_recovery,
        )
        repair["cause"] = "progress" if self.progress_recovery else "semantic"
        repair["remaining_blocked_agents"] = [aid for aid in priority
                                              if not self.authorization.allowed(aid, self.resolved[aid])]
        if diagnostics is not None:
            diagnostics["joint_repair"] = repair
        self._require_authorized(repair)

    @staticmethod
    def _require_authorized(repair: dict[str, Any]) -> None:
        if not repair["remaining_blocked_agents"]:
            return
        exhausted = any(c["status"] == "budget_exhausted" for c in repair["components"])
        reason = "movement_repair_budget" if exhausted else "movement_constraints_infeasible"
        raise JointMoveFailure(reason, repair)
