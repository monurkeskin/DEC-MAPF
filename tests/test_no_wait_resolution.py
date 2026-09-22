"""Independent one-tick oracles for the forbidden-wait fallback defect."""

import random
from itertools import combinations, product

import pytest

from mapf.agents.path_aware import PathAwareAgent
from mapf.core.commitments import CommitmentReservation
from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.engine.movement import JointMoveFailure, MovementResolver
from mapf.engine.world import WorldSimulation
from mapf.telemetry.events import DiagnosticEvent
from mapf.telemetry.schema import normalize


def legal_joint_move(starts, moves, world, *, allow_wait=False):
    if len(set(moves.values())) != len(moves):
        return False
    for aid, dest in moves.items():
        distance = abs(starts[aid].x - dest.x) + abs(starts[aid].y - dest.y)
        if distance not in ({0, 1} if allow_wait else {1}):
            return False
        if not world.is_within_bounds(dest) or world.is_obstacle(dest):
            return False
    return not any(
        moves[a] == starts[b] and moves[b] == starts[a]
        for a, b in combinations(starts, 2)
    )


def oracle(starts, world):
    # Exhaustive Cartesian product, independent of resolver priorities/search.
    domains = []
    for start in starts.values():
        domains.append([
            Point(start.x + dx, start.y + dy)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
            if world.is_within_bounds(Point(start.x + dx, start.y + dy))
            and not world.is_obstacle(Point(start.x + dx, start.y + dy))
        ])
    return next((dict(zip(starts, values, strict=True)) for values in product(*domains)
                 if legal_joint_move(starts, dict(zip(starts, values, strict=True)), world)), None)


def test_reachable_four_agent_no_wait_assignment_is_not_discarded():
    world = WorldSimulation(SimulationConfig(
        grid_width=3, grid_height=3, setting=SimulationSetting.SETTING_3, max_steps=15,
    ))
    starts = [(0, 0), (1, 2), (1, 1), (0, 2)]
    goals = [(2, 2), (0, 1), (0, 2), (1, 1)]
    for i, (start, goal) in enumerate(zip(starts, goals, strict=True)):
        world.add_agent(PathAwareAgent(str(i), Point(*start), Point(*goal)))
    expected_legal = dict(zip(world.agents,
        (Point(*p) for p in [(1, 0), (0, 2), (2, 1), (0, 1)]), strict=True))
    initial = {aid: a.current_pos for aid, a in world.agents.items()}
    assert legal_joint_move(initial, expected_legal, world)
    world.initialize()
    world.step()
    actual = {aid: a.current_pos for aid, a in world.agents.items()}
    assert legal_joint_move(initial, actual, world), actual


def test_small_obstacle_cases_match_exhaustive_no_wait_feasibility():
    rng = random.Random(20260920)
    cells = [Point(x, y) for x in range(3) for y in range(3)]
    for _ in range(160):
        obstacles = set(rng.sample(cells, rng.randrange(3)))
        free = [p for p in cells if p not in obstacles]
        starts = dict(enumerate(rng.sample(free, rng.randrange(2, 6))))
        agents = {str(i): PathAwareAgent(str(i), p, rng.choice(free), initial_tokens=i % 3)
                  for i, p in starts.items()}
        starts = {aid: a.current_pos for aid, a in agents.items()}
        world = WorldSimulation(SimulationConfig(
            grid_width=3, grid_height=3, obstacles=obstacles,
            setting=SimulationSetting.SETTING_3,
        ))
        desired = {aid: rng.choice(free) for aid in agents}
        expected = oracle(starts, world)
        if expected is None:
            with pytest.raises(JointMoveFailure, match='movement_constraints_infeasible'):
                MovementResolver.resolve_step(agents, desired, {}, False, world)
        else:
            result = MovementResolver.resolve_step(agents, desired, {}, False, world)
            assert legal_joint_move(starts, result, world), (starts, desired, result)


def test_infeasible_immediate_move_is_refused_without_fabricating_solution():
    world = WorldSimulation(SimulationConfig(
        grid_width=2, grid_height=1, setting=SimulationSetting.SETTING_3,
    ))
    agents = {"a": PathAwareAgent("a", Point(0, 0), Point(1, 0)),
              "b": PathAwareAgent("b", Point(1, 0), Point(0, 0))}
    starts = {aid: a.current_pos for aid, a in agents.items()}
    assert oracle(starts, world) is None
    diagnostic = {}
    with pytest.raises(JointMoveFailure, match='movement_constraints_infeasible'):
        MovementResolver.resolve_step(agents, {aid: a.target_pos for aid, a in agents.items()}, {}, False, world,
                                       diagnostics=diagnostic)
    assert {aid: a.current_pos for aid, a in agents.items()} == starts
    assert all(not a.reached_goal for a in agents.values())
    assert diagnostic["joint_repair"]["components"][0]["status"] == "immediate_infeasible"


def test_repair_budget_and_commitments_are_observable_and_not_relaxed():
    world = WorldSimulation(SimulationConfig(grid_width=3, grid_height=3,
                                             setting=SimulationSetting.SETTING_3))
    starts = [(0, 0), (1, 2), (1, 1), (0, 2)]
    goals = [(2, 2), (0, 1), (0, 2), (1, 1)]
    agents = {str(i): PathAwareAgent(str(i), Point(*s), Point(*g))
              for i, (s, g) in enumerate(zip(starts, goals, strict=True))}
    desired = {str(i): Point(*p) for i, p in enumerate([(1, 0), (0, 2), (0, 1), (0, 1)])}
    blocked = Point(1, 2)
    agents["2"]._commitments["live"] = CommitmentReservation(
        "live", "2", "peer", 8, (blocked,), "SC"
    )
    for bound in (0, 1, 10000):
        diagnostic = {}
        if bound < 2:
            with pytest.raises(JointMoveFailure, match='movement_repair_budget'):
                MovementResolver.resolve_step(agents, desired, {}, False, world,
                    diagnostics=diagnostic, max_repair_nodes=bound, current_time=7)
        else:
            result = MovementResolver.resolve_step(agents, desired, {}, False, world,
                diagnostics=diagnostic, max_repair_nodes=bound, current_time=7)
            assert legal_joint_move({aid: a.current_pos for aid, a in agents.items()}, result, world)
            assert result['2'] != blocked
        receipt = diagnostic["joint_repair"]
        assert receipt["search_nodes"] <= bound
        if bound < 2:
            assert receipt["remaining_holds"]
            assert any(c["status"] == "budget_exhausted" for c in receipt["components"])
        else:
            assert not receipt["remaining_holds"]
        event = normalize(DiagnosticEvent("MOVEMENT_REPAIR", 7, receipt), 1)
        assert event["tick"] == 7 and event["phase"] == "pre_move"


def test_legal_rotation_and_wait_permitted_resolution_are_unchanged():
    world = WorldSimulation(SimulationConfig(grid_width=2, grid_height=2))
    points = [Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 1)]
    agents = {str(i): PathAwareAgent(str(i), p, points[(i + 1) % 4]) for i, p in enumerate(points)}
    desired = {aid: a.target_pos for aid, a in agents.items()}
    for allow_wait in (False, True):
        diagnostic = {}
        assert MovementResolver.resolve_step(agents, desired, {}, allow_wait, world,
                                               diagnostics=diagnostic) == desired
        assert diagnostic == {}
