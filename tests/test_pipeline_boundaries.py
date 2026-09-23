"""All agents must act on a coherent tick; failed joint moves must remain atomic."""

import pytest

from mapf.agents.path_aware import PathAwareAgent
from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.engine.movement import JointMoveFailure, MovementResolver
from mapf.engine.pipeline import MovementStage, PipelineContext
from mapf.engine.world import WorldSimulation


class ObservedAgent(PathAwareAgent):
    def force_move(self, position, env, current_time):
        self.events.append(("move", self.agent_id))
        self.received_view = env.observation
        return super().force_move(position, env, current_time)

    def step(self, current_time):
        self.events.append(("move", self.agent_id))
        return super().step(current_time)


def movement_world():
    world = WorldSimulation(
        SimulationConfig(
            grid_width=3,
            grid_height=3,
            setting=SimulationSetting.SETTING_4,
        )
    )
    events = []
    for aid, start, goal in [
        ("a", Point(0, 0), Point(2, 0)),
        ("b", Point(2, 1), Point(0, 1)),
    ]:
        agent = ObservedAgent(aid, start, goal)
        agent.events = events
        world.add_agent(agent)
    world.initialize()
    return world, events


@pytest.mark.parametrize(
    "force_first", [False, True], ids=["planned-first", "forced-first"]
)
def test_fallback_observes_every_peer_before_any_agent_moves(monkeypatch, force_first):
    world, events = movement_world()
    original_view = world.for_agent

    def capture_view(aid):
        events.append(("view", aid))
        return original_view(aid)

    moves = {"a": Point(0, 1) if force_first else Point(1, 0), "b": Point(2, 2)}
    monkeypatch.setattr(world, "for_agent", capture_view)
    monkeypatch.setattr(MovementResolver, "resolve_step", lambda **kwargs: moves)
    ctx = PipelineContext(world, 0, world.agents, True, True)
    MovementStage().execute(ctx)

    assert events == [("view", "a"), ("view", "b"), ("move", "a"), ("move", "b")]
    seen_by_b = world.agents["b"].received_view
    assert seen_by_b.tick == 0 and seen_by_b.position == Point(2, 1)
    assert [(m.sender, m.points[0]) for m in seen_by_b.messages] == [("a", (0, 0))]
    assert {aid: a.current_pos for aid, a in world.agents.items()} == moves


def test_failed_joint_resolution_never_moves_or_advances_time(monkeypatch):
    world, events = movement_world()
    before = {aid: a.current_pos for aid, a in world.agents.items()}

    def fail_resolution(**kwargs):
        raise JointMoveFailure("joint_repair_budget", {"nodes": 3, "budget": 3})

    monkeypatch.setattr(MovementResolver, "resolve_step", fail_resolution)
    ctx = PipelineContext(world, 0, world.agents, True, True)
    MovementStage().execute(ctx)

    assert ctx.is_unsolvable and ctx.resolved_moves == {}
    assert events == []
    assert {aid: a.current_pos for aid, a in world.agents.items()} == before
    assert world.current_time == 0 and world.frames == []
