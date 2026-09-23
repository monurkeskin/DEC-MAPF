"""Incremental results must equal the independently retained full scans."""

import random

import pytest

from mapf.agents.heatmap import HeatMapAgent
from mapf.core.models import Path, Point, SimulationConfig, SimulationSetting
from mapf.engine.world import WorldSimulation
from mapf.negotiation.conflict import detect_conflicts
from mapf.negotiation.index import ConflictIndex


def mutate_plan(paths, goals, aid, rng):
    if rng.random() < 0.15:
        paths.pop(aid, None)
        goals.pop(aid, None)
    else:
        points = [
            Point(rng.randrange(3), rng.randrange(3))
            for _ in range(rng.randrange(1, 9))
        ]
        paths[aid] = Path(points=points)
        goals[aid] = points[-1] if rng.random() < 0.5 else Point(8, 8)


@pytest.mark.parametrize("roster_size", [8, 48])
def test_incremental_conflicts_match_full_scan_during_mutations(roster_size):
    rng = random.Random(93271)
    paths, goals = {}, {}
    index = ConflictIndex()
    for iteration in range(500):
        aid = str(rng.randrange(roster_size))
        mutate_plan(paths, goals, aid, rng)
        kwargs = {
            "current_time": iteration // 7,
            "lookahead_steps": (iteration // 51) % 7,
            "disappear_at_target": bool(iteration // 31 % 2),
            "goals": goals,
        }
        expected = detect_conflicts(paths, **kwargs)
        assert index.detect(paths, **kwargs) == expected
        assert (
            index.detect(paths, **kwargs) == expected
        )  # reuse cannot mutate the returned value

    if roster_size > 16:
        assert index.stats["incremental_queries"] > 0
    assert index.stats["result_hits"] >= 500


def test_conflict_index_reuses_unchanged_plans_and_keeps_same_cell_ordering():
    paths = {aid: Path(points=[Point(0, 0), Point(1, 0)]) for aid in ["c", "a", "b"]}
    index = ConflictIndex()
    assert index.detect(paths) == detect_conflicts(paths)
    rebuilt = index.stats["path_updates"]
    for tick in range(30):
        assert index.detect(paths, current_time=tick) == detect_conflicts(
            paths, current_time=tick
        )
    assert index.stats["path_updates"] == rebuilt
    paths["a"] = Path(points=[Point(2, 0), Point(1, 0)])
    assert index.detect(paths) == detect_conflicts(paths)
    assert index.stats["path_updates"] == rebuilt + 1


def make_world():
    world = WorldSimulation(
        SimulationConfig(
            grid_width=12,
            grid_height=12,
            fov_size=5,
            obstacles={Point(1, 1)},
            setting=SimulationSetting.SETTING_2,
        )
    )
    for aid, pos in [("a", Point(2, 2)), ("b", Point(3, 2)), ("c", Point(10, 10))]:
        world.add_agent(HeatMapAgent(aid, pos, Point(pos.x, 8), fov_size=5))
    world.initialize()
    return world


def within_square(point, center, radius):
    return abs(point.x - center.x) <= radius and abs(point.y - center.y) <= radius


def peer_evidence(world, aid, other_id):
    from mapf.core.observations import Message

    agent, other = world.agents[aid], world.agents[other_id]
    if not within_square(
        other.current_pos, agent.current_pos, world.config.fov_size // 2
    ):
        return None, None
    reached = other.get_state().reached_goal
    disappears = world.config.setting.disappear_at_target
    obstacle = other.target_pos if reached and not disappears else None
    if other_id == aid or (reached and disappears):
        return obstacle, None
    horizon = world.config.broadcast_horizon or world.config.fov_size
    message = Message(
        other_id,
        aid,
        world.current_time,
        tuple((p.x, p.y) for p in other.planned_path.points[:horizon]),
    )
    return obstacle, message


def legacy_observation(world, aid):
    # Full scan retained independently from the production index and geometry helpers.
    from mapf.core.observations import Observation

    agent = world.agents[aid]
    radius = world.config.fov_size // 2
    obstacles = {
        p for p in world.config.obstacles if within_square(p, agent.current_pos, radius)
    }
    messages = []
    for other_id in world.agents:
        obstacle, message = peer_evidence(world, aid, other_id)
        if obstacle is not None:
            obstacles.add(obstacle)
        if message is not None:
            messages.append(message)
    return Observation(
        aid,
        world.current_time,
        agent.current_pos,
        frozenset(obstacles),
        tuple(messages),
    )


def test_recipient_cache_tracks_path_position_roster_tick_and_topology_changes():
    world = make_world()
    first = world.for_agent("a")
    repeated = world.for_agent("a")
    assert (
        first is not repeated
    )  # owned mutable config/search cache must remain isolated
    assert first.observation is repeated.observation
    assert first.observation == legacy_observation(world, "a")
    # Another recipient's plan changes without a plugin-managed revision counter.
    world.agents["b"].apply_planned_path(Path(points=[Point(3, 2), Point(4, 2)]))
    assert world.for_agent("a").observation == legacy_observation(world, "a")
    assert world.for_agent("a").observation is not first.observation
    world.agents.pop("b")
    assert world.for_agent("a").observation == legacy_observation(world, "a")
    world._current_time = 4
    assert world.for_agent("a").observation == legacy_observation(world, "a")
    world.config.obstacles.add(Point(2, 3))
    assert world.for_agent("a").observation == legacy_observation(world, "a")


def test_far_away_plan_does_not_invalidate_recipient_but_fov_entry_does():
    world = make_world()
    first = world.for_agent("a").observation
    c = world.agents["c"]
    c.apply_planned_path(Path(points=[Point(10, 10), Point(9, 10)]))
    assert world.for_agent("a").observation is first
    c._current_pos = Point(2, 3)
    c.apply_planned_path(Path(points=[Point(2, 3), Point(3, 3)]))
    assert world.for_agent("a").observation == legacy_observation(world, "a")
    assert world.for_agent("a").observation is not first


def test_observations_follow_arrival_goal_horizon_and_query_overrides(monkeypatch):
    world = make_world()
    b = world.agents["b"]
    first = world.for_agent("a").observation
    b._target_pos = b.current_pos
    b._reached_goal = True
    parked = world.for_agent("a").observation
    assert parked is not first and b.target_pos in parked.obstacles
    world.config.setting = SimulationSetting.SETTING_4
    vanished = world.for_agent("a").observation
    assert b.target_pos not in vanished.obstacles
    assert not any(m.sender == "b" for m in vanished.messages)
    b._reached_goal = False
    world.config.broadcast_horizon = 1
    assert all(len(m.points) == 1 for m in world.for_agent("a").observation.messages)
    monkeypatch.setattr(world, "get_fov_obstacles", lambda center, size: {Point(0, 0)})
    assert world.for_agent("a").observation.obstacles == frozenset({Point(0, 0)})
    monkeypatch.setattr(world, "get_fov_broadcasts", lambda *args, **kwargs: {})
    assert world.for_agent("a").observation.messages == ()
