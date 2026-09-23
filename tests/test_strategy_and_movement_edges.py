"""Small exact grids exercise strategy adapters and movement admission boundaries."""

from types import SimpleNamespace

import pytest

from mapf.agents.greedy import ConcederAgent
from mapf.core.models import Bid, Path, Point, SimulationConfig, SimulationSetting
from mapf.engine._movement_resolution import MoveAuthorization, MoveCandidates
from mapf.engine._perception_stage import ConflictDetectionStage, PreUpdateStage
from mapf.engine.movement import MovementResolver
from mapf.engine.pipeline import PipelineContext
from mapf.engine.world import WorldSimulation
from mapf.solvers._conflict_tree import SearchContext
from mapf.solvers.base import MAPFInstance
from mapf.solvers.decentralized import DecentralizedNegotiationSolver


@pytest.mark.parametrize("strategy", ["Greedy", "Conceder"])
def test_baseline_strategy_adapter_obeys_instance_geometry(strategy):
    instance = MAPFInstance(
        starts={"a": Point(0, 0)},
        goals={"a": Point(2, 0)},
        grid_width=3,
        grid_height=2,
        obstacles={Point(1, 0)},
    )
    result = DecentralizedNegotiationSolver(strategy).solve(
        instance, SimulationConfig(max_steps=10)
    )
    assert result.success and result.sum_of_costs == 4
    assert Point(1, 0) not in result.paths["a"].points


def test_conceder_keeps_its_plan_when_opponent_leaves_no_route():
    world = WorldSimulation(
        SimulationConfig(
            grid_width=3,
            grid_height=1,
            setting=SimulationSetting.SETTING_3,
            max_steps=3,
        )
    )
    agent = ConcederAgent("a", Point(0, 0), Point(2, 0))
    original = Path(points=[Point(0, 0), Point(1, 0), Point(2, 0)])
    agent.apply_planned_path(original)
    offered = agent.make_bid("b", None, world, 0, 1)
    assert offered.token_offered == 1 and offered.proposed_path == original
    bid = Bid(
        bidder_id="b",
        proposed_path=Path(points=[Point(2, 0), Point(1, 0), Point(0, 0)]),
    )
    assert not agent.evaluate_bid(bid, world, 0)
    assert agent.planned_path == original


def test_movement_rejects_negative_search_budget_before_work():
    with pytest.raises(ValueError, match="nonnegative"):
        MovementResolver.resolve_step({}, {}, {}, True, None, max_repair_nodes=-1)
    assert MovementResolver.resolve_step({}, {}, {}, True, None) == {}


@pytest.mark.parametrize("stage", [PreUpdateStage, ConflictDetectionStage])
@pytest.mark.parametrize("unsolvable", [False, True])
def test_perception_does_not_read_world_after_stop_or_with_no_agents(stage, unsolvable):
    ctx = PipelineContext(None, 0, {}, True, True)
    ctx.is_unsolvable = unsolvable
    stage().execute(ctx)
    assert ctx.conflicts == []


def test_invalid_desired_move_cannot_enter_an_obstacle():
    world = WorldSimulation(
        SimulationConfig(grid_width=3, grid_height=2, obstacles={Point(1, 0)})
    )
    agent = ConcederAgent("a", Point(0, 0), Point(2, 0))
    candidates = MoveCandidates({"a": agent}, {}, world).preferred(
        "a", Point(1, 0), True
    )
    assert candidates == [Point(0, 0)]


def test_future_commitments_distinguish_own_and_other_occupancy():
    agent = SimpleNamespace(current_pos=Point(0, 0), target_pos=Point(1, 0))
    env = SimpleNamespace(config=SimpleNamespace(setting=SimulationSetting.SETTING_2))
    authorization = MoveAuthorization({"a": agent}, True, env, 3)
    table = authorization.tables["a"]
    table.reserve_vertex("b", Point(2, 0), 8)
    table.reserve_vertex("b", Point(1, 0), 2)
    table.reserve_vertex("a", Point(1, 0), 8)
    assert authorization.allowed("a", Point(1, 0))
    table.reserve_vertex("b", Point(1, 0), 4)
    assert not authorization.allowed("a", Point(1, 0))


def test_constraint_search_deduplicates_equivalent_unordered_sets():
    instance = MAPFInstance(
        starts={"a": Point(0, 0)}, goals={"a": Point(1, 0)}, grid_width=2, grid_height=1
    )
    search = SearchContext(instance, SimulationConfig())
    assert search.admit({"a": {(Point(0, 0), 1), (Point(1, 0), 2)}}, {"a": set()})
    assert not search.admit({"a": {(Point(1, 0), 2), (Point(0, 0), 1)}}, {"a": set()})
    assert search.admit({"a": {(Point(0, 0), 1)}}, {"a": set()})
