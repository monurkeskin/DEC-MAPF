"""Observed parked cells stay known without exposing another recipient's view."""

import pytest

from mapf.agents.heatmap import HeatMapAgent
from mapf.core.models import (
    CommitmentType,
    Path,
    Point,
    SimulationConfig,
    SimulationSetting,
)
from mapf.engine._perception_stage import PreUpdateStage
from mapf.engine._pipeline_context import PipelineContext
from mapf.engine.world import WorldSimulation


def observed_world(
    setting=SimulationSetting.SETTING_2, commitment=CommitmentType.STANDARD
):
    world = WorldSimulation(
        SimulationConfig(
            grid_width=8,
            grid_height=5,
            fov_size=3,
            setting=setting,
            commitment_type=commitment,
            obstacles={Point(7, 4)},
        )
    )
    for aid, start, goal in [
        ("traveller", Point(1, 1), Point(6, 1)),
        ("parked", Point(2, 1), Point(2, 1)),
        ("distant", Point(6, 3), Point(0, 3)),
    ]:
        world.add_agent(
            HeatMapAgent(aid, start, goal, fov_size=3, commitment_type=commitment)
        )
    world.initialize()
    return world


def leave_view(world):
    traveller = world.agents["traveller"]
    traveller._current_pos = Point(0, 1)
    traveller.apply_planned_path(Path(points=[Point(x, 1) for x in range(7)]))
    world._current_time = 1
    return traveller


@pytest.mark.parametrize(
    "setting", [SimulationSetting.SETTING_1, SimulationSetting.SETTING_2]
)
@pytest.mark.parametrize("commitment", list(CommitmentType))
def test_replan_avoids_a_previously_seen_parked_cell_outside_fov(setting, commitment):
    world = observed_world(setting, commitment)
    traveller = leave_view(world)
    view = world.for_agent("traveller")
    assert Point(2, 1) not in view.get_fov_obstacles(Point(0, 1), 3)
    PreUpdateStage().execute(
        PipelineContext(
            world=world,
            current_time=1,
            active_agents={"traveller": traveller},
            disappear_at_target=setting.disappear_at_target,
            allow_wait=setting.allow_wait,
        )
    )
    assert traveller.planned_path.points[-1] == traveller.target_pos
    assert Point(2, 1) not in traveller.planned_path.points
    assert world.config.obstacles == {Point(7, 4)}


def test_memory_is_recipient_owned_and_visible_obstacles_remain_current():
    world = observed_world()
    before = world.for_agent("traveller")
    leave_view(world)
    after = world.for_agent("traveller")
    assert before.observation.obstacles == frozenset({Point(2, 1)})
    assert after.observation.obstacles == frozenset()
    assert after.observation.remembered_obstacles == frozenset({Point(2, 1)})
    assert after.is_obstacle(Point(2, 1))
    assert not world.for_agent("distant").is_obstacle(Point(2, 1))
    assert not world.for_agent("parked").observation.remembered_obstacles
    assert after.config.obstacles == world.config.obstacles
    assert after.observation.to_dict()["remembered_obstacles"] == [[2, 1]]


@pytest.mark.parametrize(
    "setting", [SimulationSetting.SETTING_3, SimulationSetting.SETTING_4]
)
def test_disappearing_and_moving_agents_are_not_permanent_obstacles(setting):
    world = observed_world(setting)
    leave_view(world)
    view = world.for_agent("traveller")
    assert not view.observation.remembered_obstacles
    assert not view.is_obstacle(Point(2, 1))
    assert not world.for_agent("distant").observation.remembered_obstacles


@pytest.mark.parametrize(
    "entry",
    [
        "force_move",
        "heatmap_offer",
        "path_aware_offer",
        "path_aware_response",
        "conceder",
        "protocol_concession",
        "protocol_offer",
    ],
)
def test_strategy_and_protocol_replanning_use_the_same_memory(entry):
    from mapf.agents.greedy import ConcederAgent
    from mapf.agents.path_aware import PathAwareAgent
    from mapf.core.models import Bid, Conflict, ConflictType
    from mapf.negotiation.concession import feasible_concession, novel_offer
    from mapf.negotiation.ledger import OfferLedger

    world = observed_world()
    leave_view(world)
    view = world.for_agent("traveller")
    cls = (
        PathAwareAgent
        if entry.startswith("path_aware")
        else ConcederAgent
        if entry == "conceder"
        else HeatMapAgent
    )
    agent = cls("traveller", Point(0, 1), Point(6, 1), initial_tokens=0)
    agent.plan_initial_path(view)
    offered = Bid(
        bidder_id="peer",
        proposed_path=Path(points=[Point(6, 4)]),
        token_offered=0,
        round_num=1,
    )
    if entry == "force_move":
        agent.force_move(Point(0, 1), view, 1)
        path = agent.planned_path
    elif entry in {"conceder", "path_aware_response"}:
        assert agent.evaluate_bid(offered, view, 1)
        path = agent.planned_path
    elif entry == "path_aware_offer":
        conflict = Conflict(
            agent_a="traveller",
            agent_b="peer",
            conflict_type=ConflictType.VERTEX,
            time=3,
            location_a=Point(2, 1),
            location_b=Point(2, 1),
        )
        agent.on_pre_negotiation("peer", conflict, view, 1)
        path = agent.make_bid("peer", offered, view, 1, 1).proposed_path
    elif entry == "heatmap_offer":
        path = agent.make_bid("peer", offered, view, 1, 1).proposed_path
    elif entry == "protocol_concession":
        decision = feasible_concession(agent, offered, view, 1)
        assert decision.accepted
        path = decision.proposed_path
    else:
        path = novel_offer(agent, OfferLedger(), view, 1)
    assert path is not None and path.points[-1] == Point(6, 1)
    assert Point(2, 1) not in path.points


def test_trace_distinguishes_unrecorded_memory_from_recorded_empty_memory():
    from mapf.application.contracts import LocalObservation

    raw = {
        "agent_id": "a",
        "tick": 0,
        "position": [0, 0],
        "obstacles": [],
        "messages": [],
    }
    assert LocalObservation.model_validate(raw).remembered_obstacles is None
    raw["remembered_obstacles"] = []
    assert LocalObservation.model_validate(raw).remembered_obstacles == []


@pytest.mark.parametrize("commitment", list(CommitmentType))
def test_remembered_obstacle_detour_keeps_live_agreement_constraints(commitment):
    from mapf.core.models import Contract

    world = observed_world(commitment=commitment)
    traveller = leave_view(world)
    allocated = Path(points=[Point(1, 0), Point(0, 0), Point(0, 1)])
    traveller.on_contract_agreed(
        Contract(
            session_id="earlier",
            agent_a="traveller",
            agent_b="peer",
            path_a=traveller.planned_path,
            path_b=allocated,
            accepted_by="traveller",
            allocated_path=allocated,
            conflict_tick=3,
        ),
        1,
    )
    PreUpdateStage().execute(
        PipelineContext(world, 1, {"traveller": traveller}, False, True)
    )
    points = traveller.planned_path.points
    assert points[-1] == traveller.target_pos and Point(2, 1) not in points
    for offset, reserved in enumerate(allocated.points):
        assert points[offset] != reserved
        if offset + 1 < len(allocated.points):
            assert (points[offset], points[offset + 1]) != (
                allocated.points[offset + 1],
                reserved,
            )
    assert traveller.get_state().metadata["commitments"][0]["contract_id"] == "earlier"


def test_a_visible_moving_agent_is_not_remembered_as_a_parked_obstacle():
    world = observed_world()
    moving = HeatMapAgent("moving", Point(1, 2), Point(7, 2), fov_size=3)
    world.add_agent(moving)
    view = world.for_agent("traveller")
    assert "moving" in view.get_fov_broadcasts(Point(1, 1), 3, "traveller")
    assert Point(1, 2) not in view.remembered_obstacles
