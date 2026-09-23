"""Hand-calculated reservation and safe replanning counterexamples."""

from mapf.agents.path_aware import PathAwareAgent
from mapf.core.models import CommitmentType, Contract, Path, Point, SimulationConfig
from mapf.core.space_time_grid import ReservationTable
from mapf.engine.world import WorldSimulation


def test_two_opponents_reservations_survive_the_same_tick():
    agent = PathAwareAgent(
        "a", Point(0, 0), Point(2, 0), 5, commitment_type=CommitmentType.STANDARD
    )
    mine = Path(points=[Point(0, 0), Point(1, 0), Point(2, 0)])
    for peer, y in [("b", 1), ("c", 2)]:
        other = Path(points=[Point(0, y), Point(1, y), Point(2, y)])
        agent.on_contract_agreed(
            Contract(
                session_id=peer, agent_a="a", agent_b=peer, path_a=mine, path_b=other
            ),
            7,
        )
    table = ReservationTable()
    agent.reserve_commitments(table, 7)
    assert table.is_vertex_reserved(Point(1, 1), 8)
    assert table.is_vertex_reserved(Point(1, 2), 8)
    assert not table.is_vertex_reserved(Point(1, 0), 8)
    assert table.is_edge_conflict(Point(1, 1), Point(0, 1), 7)


def test_dynamic_commitment_uses_relative_conflict_horizon():
    agent = PathAwareAgent(
        "a", Point(0, 0), Point(2, 0), 5, commitment_type=CommitmentType.DYNAMIC
    )
    agent._last_conflict_step = 1
    agent.on_contract_agreed(
        Contract(
            session_id="x",
            agent_a="a",
            agent_b="b",
            path_a=Path(points=[Point(0, 0), Point(1, 0), Point(2, 0)]),
            path_b=Path(points=[Point(0, 1), Point(1, 1), Point(2, 1)]),
        ),
        10,
    )
    table = ReservationTable()
    agent.reserve_commitments(table, 10)
    assert table.is_vertex_reserved(Point(1, 1), 11)
    assert not table.is_vertex_reserved(Point(2, 1), 12)


def test_failed_force_replan_never_fabricates_teleport():
    agent = PathAwareAgent("a", Point(0, 0), Point(2, 0), 5)
    env = WorldSimulation(
        SimulationConfig(grid_width=3, grid_height=1, obstacles={Point(1, 0)})
    )
    agent.force_move(Point(0, 0), env, 0)
    assert agent.planned_path.points == (Point(0, 0),)


def test_invalid_agreement_rolls_back_the_responder_proposal(monkeypatch):
    from mapf.agents.greedy import GreedyAgent
    from mapf.negotiation.conflict import detect_conflicts
    from mapf.negotiation.session import BilateralNegotiationSession

    env = WorldSimulation(SimulationConfig(grid_width=3, grid_height=2))
    a = GreedyAgent("a", Point(0, 0), Point(2, 0), 5)
    b = GreedyAgent("b", Point(2, 0), Point(0, 0), 5)
    a.plan_initial_path(env)
    b.plan_initial_path(env)
    original = b.planned_path
    conflicting_proposal = Path(
        points=[Point(2, 0), Point(1, 0), Point(1, 1), Point(0, 1), Point(0, 0)]
    )

    def propose(**kwargs):
        b.apply_planned_path(conflicting_proposal)
        return True

    monkeypatch.setattr(b, "evaluate_bid", propose)
    session = BilateralNegotiationSession(max_rounds=1)
    conflict = detect_conflicts({"a": a.planned_path, "b": b.planned_path})[0]
    assert session.negotiate(a, b, conflict, env, 0) is None
    assert b.planned_path == original
    assert (a.tokens, b.tokens) == (5, 5)
    assert not a._commitments and not b._commitments


def test_responder_exception_restores_its_plan(monkeypatch):
    import pytest

    from mapf.agents.greedy import GreedyAgent
    from mapf.negotiation.conflict import detect_conflicts
    from mapf.negotiation.session import BilateralNegotiationSession

    env = WorldSimulation(SimulationConfig(grid_width=3, grid_height=2))
    a = GreedyAgent("a", Point(0, 0), Point(2, 0), 5)
    b = GreedyAgent("b", Point(2, 0), Point(0, 0), 5)
    a.plan_initial_path(env)
    b.plan_initial_path(env)
    original = b.planned_path

    def fail(**kwargs):
        b.apply_planned_path(Path(points=[Point(2, 0), Point(2, 1)]))
        raise RuntimeError("synthetic strategy exception")

    monkeypatch.setattr(b, "evaluate_bid", fail)
    conflict = detect_conflicts({"a": a.planned_path, "b": b.planned_path})[0]
    with pytest.raises(RuntimeError, match="synthetic strategy exception"):
        BilateralNegotiationSession().negotiate(a, b, conflict, env, 0)
    assert b.planned_path == original
    assert (a.tokens, b.tokens) == (5, 5)
