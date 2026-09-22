"""Movement resolution engine for multi-agent path finding."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mapf.core.models import Point

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
        """Compute conflict-free resolved positions for all active agents.

        Guarantees zero vertex collisions and zero edge swap collisions via
        iterative dependency-aware joint resolution with priority ordering.
        """
        if max_repair_nodes < 0:
            raise ValueError("Movement repair budget must be nonnegative")
        if not active_agents:
            return {}

        cur_positions: dict[str, Point] = {aid: a.current_pos for aid, a in active_agents.items()}
        current_cells = {aid: (point.x, point.y) for aid, point in cur_positions.items()}
        current_owners = {cell: aid for aid, cell in current_cells.items()}

        def is_cell_passable(pt: Point, aid: str) -> bool:
            return (
                env.is_within_bounds(pt)
                and not env.is_obstacle(pt)
                and (pt not in occupied_permanent or occupied_permanent[pt] == aid)
            )

        # Build candidate preference lists for each agent
        candidates: dict[str, list[Point]] = {}
        for aid, agent in active_agents.items():
            cur = cur_positions[aid]
            cand_list: list[Point] = []

            # 1. Primary candidate: desired move
            desired = desired_moves.get(aid, cur)
            is_adj = (abs(desired.x - cur.x) + abs(desired.y - cur.y) <= 1)
            if is_adj and is_cell_passable(desired, aid) and (allow_wait or desired != cur):
                cand_list.append(desired)

            # 2. Secondary candidates:
            if allow_wait:
                if cur not in cand_list:
                    cand_list.append(cur)
            else:
                # Lateral evasion candidates for noWait mode
                lateral: list[Point] = []
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    neighbor = Point(cur.x + dx, cur.y + dy)
                    if is_cell_passable(neighbor, aid) and neighbor not in cand_list:
                        lateral.append(neighbor)

                # Sort lateral options by distance to target
                lateral.sort(
                    key=lambda p: abs(p.x - agent.target_pos.x) + abs(p.y - agent.target_pos.y)
                )
                cand_list.extend(lateral)

                # Emergency fallback if all lateral neighbors fail
                if cur not in cand_list:
                    cand_list.append(cur)

            if not cand_list:
                cand_list.append(cur)

            candidates[aid] = cand_list

        # Priority ranking: (-tokens, agent_id)
        priority_order = sorted(
            active_agents.keys(),
            key=lambda aid: (-active_agents[aid].tokens, aid),
        )
        priority_rank = {aid: idx for idx, aid in enumerate(priority_order)}

        # Track active candidate index per agent
        cand_indices = {aid: 0 for aid in active_agents}
        candidate_cells = {aid: [(point.x, point.y) for point in points] for aid, points in candidates.items()}

        # Iterative joint conflict resolution loop
        max_iterations = len(active_agents) * 10 + 50
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            proposals = {aid: candidate_cells[aid][cand_indices[aid]] for aid in active_agents}

            # 1. Check edge conflicts: (A wants cur_B and B wants cur_A)
            edge_conflict_found = False
            for aid_a in active_agents:
                tgt_a = proposals[aid_a]
                cur_a = current_cells[aid_a]
                # With unique current occupancy, at most one peer can swap with
                # this agent. Preserve the original outer/lexicographic pair order.
                aid_b = current_owners.get(tgt_a)
                if aid_b is not None and aid_a < aid_b and proposals[aid_b] == cur_a:
                    edge_conflict_found = True
                    yield_aid = aid_b if priority_rank[aid_b] > priority_rank[aid_a] else aid_a
                    if cand_indices[yield_aid] + 1 < len(candidates[yield_aid]):
                        cand_indices[yield_aid] += 1
                if edge_conflict_found:
                    break

            if edge_conflict_found:
                continue

            # 2. Check vertex conflicts: multiple agents proposing the same cell
            target_claims: dict[tuple[int, int], list[str]] = {}
            for aid, tgt in proposals.items():
                target_claims.setdefault(tgt, []).append(aid)

            vertex_conflict_found = False
            for tgt, claimants in target_claims.items():
                if len(claimants) > 1:
                    vertex_conflict_found = True
                    # Check if one of the claimants is currently staying in place at tgt
                    staying_claimant = next((c for c in claimants if current_cells[c] == tgt), None)

                    if staying_claimant is not None:
                        # The stationary agent retains its cell; all incoming agents must yield
                        for c in claimants:
                            if c != staying_claimant and cand_indices[c] + 1 < len(candidates[c]):
                                cand_indices[c] += 1
                    else:
                        # Both incoming: highest priority agent gets the cell, others yield
                        sorted_claimants = sorted(claimants, key=lambda c: priority_rank[c])
                        for c in sorted_claimants[1:]:
                            if cand_indices[c] + 1 < len(candidates[c]):
                                cand_indices[c] += 1
                    break

            if vertex_conflict_found:
                continue

            # No edge or vertex conflicts remain: verified collision-free assignment reached
            break

        resolved = {aid: candidates[aid][cand_indices[aid]] for aid in active_agents}

        from mapf.core.space_time_grid import ReservationTable

        tables: dict[str, ReservationTable] = {}
        for aid, agent in active_agents.items():
            table = ReservationTable()
            reserve = getattr(agent, "reserve_commitments", None)
            if callable(reserve):
                reserve(table, current_time)
            tables[aid] = table

        def authorized(aid: str, point: Point) -> bool:
            table = tables[aid]
            if not allow_wait and point == cur_positions[aid]:
                return False
            if (table.is_vertex_reserved(point, current_time + 1, aid)
                    or table.is_edge_conflict(cur_positions[aid], point, current_time, aid)):
                return False
            if point == active_agents[aid].target_pos and not env.config.setting.disappear_at_target:
                # Arrival parks permanently. Check the still-live future
                # allocation now, before the agent leaves the active roster.
                if any(x == point.x and y == point.y and tick >= current_time + 1 and owner != aid
                       for (x, y, tick), owner in table._vertex_reservations.items()):
                    return False
                permanent = table._permanent_reservations.get((point.x, point.y))
                if permanent and permanent[1] != aid:
                    return False
            return True

        blocked = {aid for aid in active_agents if not authorized(aid, resolved[aid])}
        forced_holds = {aid for aid in active_agents
                        if resolved[aid] == cur_positions[aid]
                        and desired_moves.get(aid, cur_positions[aid]) != cur_positions[aid]}
        progress_recovery = (not blocked and allow_wait and bool(forced_holds)
                             and all(resolved[aid] == cur_positions[aid] for aid in active_agents))
        if blocked or progress_recovery:
            # Waiting permission does not prohibit lateral movement. Add legal
            # adjacent alternatives only for this semantic recovery; the ordinary
            # greedy resolution and its priorities otherwise remain unchanged.
            for aid, agent in active_agents.items():
                cur = cur_positions[aid]
                alternatives = [Point(cur.x + dx, cur.y + dy)
                                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]]
                alternatives.sort(key=lambda p: abs(p.x-agent.target_pos.x) + abs(p.y-agent.target_pos.y))
                candidates[aid].extend(p for p in alternatives if p not in candidates[aid] and is_cell_passable(p, aid))
                if progress_recovery:
                    # A greedy cascade of forced holds can hide a legal rotation.
                    # Prefer movement only in this all-stationary recovery. Agents
                    # that all deliberately planned waits never enter this path.
                    candidates[aid].sort(key=lambda p: p == cur)
            admissible = {aid: [p for p in points if authorized(aid, p)]
                          for aid, points in candidates.items()}
            repair = MovementResolver._repair_joint(
                candidates, admissible, cur_positions, resolved, priority_order, max_repair_nodes,
                blocked or forced_holds, require_progress=progress_recovery,
            )
            repair["cause"] = "progress" if progress_recovery else "semantic"
            repair["remaining_blocked_agents"] = [aid for aid in priority_order if not authorized(aid, resolved[aid])]
            if diagnostics is not None:
                diagnostics["joint_repair"] = repair
            if repair["remaining_blocked_agents"]:
                reason = "movement_repair_budget" if any(
                    c["status"] == "budget_exhausted" for c in repair["components"]
                ) else "movement_constraints_infeasible"
                raise JointMoveFailure(reason, repair)

        # Final safety verification
        assert len(set(resolved.values())) == len(resolved), (
            f"MovementResolver invariant violated: multiple agents sharing cells: {resolved}"
        )
        assert not any(
            (peer := current_owners.get((target.x, target.y))) is not None
            and peer != aid and resolved[peer] == cur_positions[aid]
            for aid, target in resolved.items()
        ), "MovementResolver invariant violated: reverse-edge collision"
        return resolved

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
        so neither shared destinations nor reverse edges cross components. A
        Exhaustive failure certifies only *this immediate step*. No partial repair
        can authorize movement if any component remains blocked.
        """
        rank = {aid: index for index, aid in enumerate(priority_order)}
        cells = {aid: {(p.x, p.y) for p in points} | {(current[aid].x, current[aid].y)}
                 for aid, points in candidates.items()}
        owners: dict[tuple[int, int], set[str]] = {}
        for aid, points in cells.items():
            for point in points:
                owners.setdefault(point, set()).add(aid)
        remaining = set(candidates)
        components: list[list[str]] = []
        for first in priority_order:
            if first not in remaining:
                continue
            stack, component = [first], []
            remaining.remove(first)
            while stack:
                aid = stack.pop()
                component.append(aid)
                neighbors = {peer for point in cells[aid] for peer in owners[point]}
                for peer in sorted(neighbors & remaining, key=rank.__getitem__):
                    remaining.remove(peer)
                    stack.append(peer)
            components.append(sorted(component, key=rank.__getitem__))

        nodes = 0
        outcomes: list[dict[str, Any]] = []
        current_cells = {aid: (p.x, p.y) for aid, p in current.items()}
        for component in components:
            if not blocked.intersection(component):
                continue
            before = nodes
            exhausted = False
            domains = {aid: [(p.x, p.y) for p in admissible[aid]]
                       for aid in component}

            def search(
                pending: dict[str, list[tuple[int, int]]],
                moved: bool = False,
            ) -> dict[str, tuple[int, int]] | None:
                nonlocal nodes, exhausted
                if not pending:
                    return {} if moved or not require_progress else None
                if any(not points for points in pending.values()):
                    return None
                if len({p for points in pending.values() for p in points}) < len(pending):
                    return None
                aid = min(pending, key=lambda a: (len(pending[a]), rank[a]))
                for target in pending[aid]:
                    if nodes >= max_nodes:
                        exhausted = True
                        return None
                    nodes += 1
                    rest = {
                        peer: [p for p in points if p != target and not (
                            target == current_cells[peer] and p == current_cells[aid]
                        )]
                        for peer, points in pending.items() if peer != aid
                    }
                    answer = search(rest, moved or target != current_cells[aid])
                    if answer is not None:
                        return {aid: target, **answer}
                    if exhausted:
                        return None
                return None

            answer = search(domains)
            if answer is not None:
                resolved.update({aid: Point(*p) for aid, p in answer.items()})
            outcomes.append({
                "agents": component,
                "status": "repaired" if answer is not None else
                          "budget_exhausted" if exhausted else
                          "progress_unavailable" if require_progress else "immediate_infeasible",
                "search_nodes": nodes - before,
            })
        return {
            "node_limit": max_nodes,
            "search_nodes": nodes,
            "components": outcomes,
            "remaining_holds": [aid for aid in priority_order if resolved[aid] == current[aid]],
        }
