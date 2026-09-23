"""An authorized cyclic joint move must not become a greedy all-agent hold."""
import pytest

from mapf.agents.path_aware import PathAwareAgent
from mapf.core.commitments import CommitmentReservation
from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.engine.movement import MovementResolver
from mapf.engine.world import WorldSimulation


@pytest.mark.parametrize('setting', [SimulationSetting.SETTING_2, SimulationSetting.SETTING_4])
def test_greedy_all_hold_recovers_a_legal_rotation(setting):
    world = WorldSimulation(SimulationConfig(grid_width=4, grid_height=4, setting=setting))
    starts = [Point(1, 1), Point(1, 2), Point(2, 1), Point(2, 2)]
    goals = [Point(1, 2), Point(1, 0), Point(0, 1), Point(0, 2)]
    agents = {str(i): PathAwareAgent(str(i), p, g) for i, (p, g) in enumerate(zip(starts, goals, strict=True))}
    desired = dict(zip(agents, [starts[1], starts[3], starts[0], starts[1]], strict=True))
    # Independent constructive witness: four agents rotate; no wait or edge swap.
    witness = [starts[1], starts[3], starts[0], starts[2]]
    assert len(set(witness)) == 4
    assert all(p != q for p, q in zip(starts, witness, strict=True))
    assert not any(witness[i] == starts[j] and witness[j] == starts[i]
                   for i in range(4) for j in range(i))
    moves = MovementResolver.resolve_step(agents, desired, {}, True, world)
    assert any(moves[aid] != agent.current_pos for aid, agent in agents.items())
    assert len(set(moves.values())) == 4
    assert not any(moves[str(i)] == starts[j] and moves[str(j)] == starts[i]
                   for i in range(4) for j in range(i))


def test_intentionally_planned_waits_are_preserved():
    world = WorldSimulation(SimulationConfig(grid_width=3, grid_height=2, setting=SimulationSetting.SETTING_4))
    agent = PathAwareAgent('a', Point(0, 0), Point(2, 0))
    assert MovementResolver.resolve_step({'a': agent}, {'a': agent.current_pos}, {}, True, world) == {'a': agent.current_pos}


def test_temporary_reservations_can_require_waiting_without_failure():
    world = WorldSimulation(SimulationConfig(grid_width=2, grid_height=1, setting=SimulationSetting.SETTING_4))
    agent = PathAwareAgent('a', Point(0, 0), Point(1, 0))
    agent._commitments['r'] = CommitmentReservation('r', 'a', 'peer', 1, (Point(1, 0),), 'SC')
    assert MovementResolver.resolve_step({'a': agent}, {'a': agent.target_pos}, {}, True, world) == {'a': agent.current_pos}


def test_progress_search_budget_does_not_turn_legal_wait_into_invalidity():
    world = WorldSimulation(SimulationConfig(grid_width=2, grid_height=1, setting=SimulationSetting.SETTING_4))
    a = PathAwareAgent('a', Point(0, 0), Point(1, 0))
    b = PathAwareAgent('b', Point(1, 0), Point(0, 0))
    moves = MovementResolver.resolve_step({'a': a, 'b': b}, {'a': b.current_pos, 'b': a.current_pos}, {}, True, world, max_repair_nodes=0)
    assert moves == {'a': a.current_pos, 'b': b.current_pos}


def test_incomplete_plan_detects_a_permanent_current_state_disconnection():
    from mapf.core.models import Path
    from mapf.engine.pipeline import PipelineContext, PreUpdateStage
    world = WorldSimulation(SimulationConfig(grid_width=3, grid_height=1, setting=SimulationSetting.SETTING_2))
    a = PathAwareAgent('a', Point(0, 0), Point(2, 0))
    parked = PathAwareAgent('parked', Point(1, 0), Point(1, 0))
    a.apply_planned_path(Path(points=[a.current_pos]))
    world.add_agent(a)
    world.add_agent(parked)
    ctx = PipelineContext(world, 8, {'a': a}, False, True)
    PreUpdateStage().execute(ctx)
    assert ctx.is_unsolvable
    assert world._last_replan_failure['static_reachable'] is False
    assert world._last_replan_failure['terminal'] is True
    assert a.current_pos == Point(0, 0)


def test_tiny_waiting_cases_match_independent_progress_oracle():
    import itertools
    import random
    rng = random.Random(20260920)
    cells = [Point(x, y) for x in range(3) for y in range(3)]
    for _ in range(100):
        starts = rng.sample(cells, 4)
        obstacles = set(rng.sample([p for p in cells if p not in starts], rng.randrange(4)))
        free = [p for p in cells if p not in obstacles]
        world = WorldSimulation(SimulationConfig(grid_width=3, grid_height=3,
                                obstacles=obstacles, setting=SimulationSetting.SETTING_4))
        agents = {str(i): PathAwareAgent(str(i), p, next(q for q in free if q != p)) for i, p in enumerate(starts)}
        domains = [[q for q in free if abs(q.x-p.x)+abs(q.y-p.y)<=1] for p in starts]
        desired = {str(i): rng.choice(d) for i, d in enumerate(domains)}
        moves = MovementResolver.resolve_step(agents, desired, {}, True, world)
        points = [moves[str(i)] for i in range(4)]
        def legal(q, initial=tuple(starts)):
            return len(set(q)) == 4 and not any(q[i] == initial[j] and q[j] == initial[i]
                                                for i in range(4) for j in range(i))
        assert legal(points)
        if any(desired[str(i)] != starts[i] for i in range(4)):
            feasible = any(legal(q) and list(q) != starts for q in itertools.product(*domains))
            assert (points != starts) == feasible
