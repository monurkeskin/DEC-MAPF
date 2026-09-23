"""Independent occupancy checks for unfinished paths and permanent reservations."""

from mapf.agents.greedy import GreedyAgent
from mapf.core.models import Path, Point, SimulationConfig, SimulationSetting
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar
from mapf.engine.pipeline import NegotiationStage, PipelineContext
from mapf.engine.world import WorldSimulation


def test_incomplete_plan_does_not_imply_disappearance_during_conflict_detection(
    monkeypatch,
):
    world = WorldSimulation(
        SimulationConfig(
            grid_width=3, grid_height=2, setting=SimulationSetting.SETTING_4
        )
    )
    a = GreedyAgent("a", Point(0, 0), Point(2, 0))
    b = GreedyAgent("b", Point(1, 0), Point(0, 0))
    world.add_agent(a)
    world.add_agent(b)
    a.apply_planned_path(
        Path([Point(0, 0)])
    )  # Bounded recovery left an unfinished plan.
    b.apply_planned_path(Path([Point(1, 0), Point(0, 0)]))
    found = []

    def negotiate(**kwargs):
        found.append(kwargs["conflict"])

    monkeypatch.setattr(world.negotiator, "negotiate", negotiate)
    NegotiationStage().execute(PipelineContext(world, 7, world.agents, True, True))
    assert len(found) == 1
    assert found[0].time == 8
    assert found[0].location_a == Point(0, 0)


def test_search_rejects_an_already_permanently_occupied_start():
    table = ReservationTable()
    table.reserve_path("parked", Path([Point(0, 0)]), start_time=3, permanent=True)
    planner = SpaceTimeAStar(3, 2)
    # Occupancy began before this search: the finite vertex entry is at t=3,
    # while the permanent reservation also forbids starting here at t=7.
    assert (
        planner.search(Point(0, 0), Point(2, 0), start_time=7, reservation_table=table)
        is None
    )
    assert planner.last_search_status == "start_reserved"
    assert (
        planner.search(
            Point(0, 0),
            Point(2, 0),
            start_time=7,
            reservation_table=table,
            ignore_agent_id="parked",
        )
        is not None
    )
