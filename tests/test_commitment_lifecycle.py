"""Article section 4.1 and archived Java lifecycle witnesses.

Expected occupied cells and ticks are handwritten, independent of production
reservation construction. An allocation's horizon and its release event differ.
"""

import pytest

from mapf.agents.greedy import ConcederAgent, GreedyAgent
from mapf.core.models import (
    CommitmentType,
    Conflict,
    ConflictType,
    Contract,
    Path,
    Point,
    SimulationConfig,
    SimulationSetting,
)
from mapf.core.space_time_grid import ReservationTable
from mapf.engine.movement import MovementResolver
from mapf.engine.pipeline import NegotiationStage, PipelineContext
from mapf.engine.world import WorldSimulation
from mapf.negotiation.ledger import settle_contract
from mapf.negotiation.session import BilateralNegotiationSession


def route(*cells):
    return Path(points=[Point(*cell) for cell in cells])


def agreement(policy, tick=7):
    offered = route((1, 0), (1, 1), (2, 1), (3, 1))
    response = route((0, 1), (0, 2), (0, 3))
    proposer = GreedyAgent("b", offered.points[0], offered.points[-1], 5, policy)
    acceptor = GreedyAgent("a", response.points[0], response.points[-1], 5, policy)
    contract = Contract(session_id="first", agent_a="b", agent_b="a",
        path_a=offered, path_b=response, accepted_by="a", allocated_path=offered,
        conflict_tick=tick + 2, timestamp=tick, token_transfer=1,
        protocol_version="taop-v1")
    settle_contract(proposer, acceptor, contract, tick)
    return proposer, acceptor


@pytest.mark.parametrize("policy", list(CommitmentType))
def test_full_allocation_is_binding_during_agreement_tick(policy):
    proposer, acceptor = agreement(policy)
    table = ReservationTable()
    acceptor.reserve_commitments(table, 7)
    assert table.is_vertex_reserved(Point(1, 1), 8)
    assert table.is_edge_conflict(Point(1, 1), Point(1, 0), 7)
    assert table.is_vertex_reserved(Point(2, 1), 9)
    assert table.is_vertex_reserved(Point(3, 1), 10) == (policy != CommitmentType.DYNAMIC)
    assert not proposer._commitments  # An earlier acceptor obligation is not a proposer duty.


@pytest.mark.parametrize("forced", [False, True])
@pytest.mark.parametrize("policy", list(CommitmentType))
def test_release_occurs_after_movement_and_uses_absolute_ticks(policy, forced):
    _, agent = agreement(policy)
    env = WorldSimulation(SimulationConfig(grid_width=4, grid_height=4))
    if forced:
        agent.force_move(Point(0, 2), env, 7)
    else:
        agent.step(7)
    table = ReservationTable()
    agent.reserve_commitments(table, 8)
    assert table.is_vertex_reserved(Point(2, 1), 9) == (policy != CommitmentType.ZERO)
    assert table.is_vertex_reserved(Point(3, 1), 10) == (policy == CommitmentType.STANDARD)
    assert bool(agent._commitments) == (policy != CommitmentType.ZERO)


def test_zero_commitment_blocks_current_tick_override_even_if_proposer_replans():
    proposer, acceptor = agreement(CommitmentType.ZERO)
    env = WorldSimulation(SimulationConfig(grid_width=4, grid_height=4))
    # The physical cell is now free, but the acceptor promised to avoid it in this tick.
    proposer.apply_planned_path(route((1, 0), (2, 0), (3, 0), (3, 1)))
    moves = MovementResolver.resolve_step({"a": acceptor, "b": proposer},
        {"a": Point(1, 1), "b": Point(2, 0)}, {}, True, env, current_time=7)
    assert moves["a"] != Point(1, 1)


@pytest.mark.parametrize("policy", list(CommitmentType))
def test_new_agreement_cannot_override_an_earlier_acceptor_obligation(policy, monkeypatch):
    _, acceptor = agreement(policy)
    third = GreedyAgent("c", Point(3, 3), Point(1, 3), 5, policy)
    third.apply_planned_path(route((3, 3), (2, 3), (1, 3)))
    # This path is physically compatible with C but breaks A's promise to B at t=8.
    acceptor.apply_planned_path(route((0, 1), (1, 1), (1, 2), (0, 2), (0, 3)))
    monkeypatch.setattr(third, "evaluate_bid", lambda *args, **kwargs: True)
    env = WorldSimulation(SimulationConfig(grid_width=4, grid_height=4, fov_size=5))
    env.add_agent(acceptor)
    env.add_agent(third)
    env._current_time = 7
    session = BilateralNegotiationSession(max_rounds=1, protocol="taop-v1")
    conflict = Conflict(agent_a="a", agent_b="c", time=8,
        conflict_type=ConflictType.VERTEX, location_a=Point(1, 1))
    assert session.negotiate(acceptor, third, conflict, env, 7) is None
    assert (acceptor.tokens, third.tokens) == (6, 5)
    assert len(acceptor._commitments) == 1


def test_dynamic_swap_obligation_includes_both_ends_of_the_conflicting_edge():
    env = WorldSimulation(SimulationConfig(grid_width=4, grid_height=3, fov_size=5))
    a = GreedyAgent("a", Point(1, 1), Point(2, 1), 5, CommitmentType.DYNAMIC)
    b = ConcederAgent("b", Point(2, 1), Point(0, 1), 5, CommitmentType.DYNAMIC)
    a.plan_initial_path(env)
    b.plan_initial_path(env)
    env.add_agent(a)
    env.add_agent(b)
    env._current_time = 7
    conflict = Conflict(agent_a="a", agent_b="b", time=7,
        conflict_type=ConflictType.EDGE, location_a=Point(2, 1), location_b=Point(1, 1))
    contract = BilateralNegotiationSession(protocol="taop-v1").negotiate(a, b, conflict, env, 7)
    assert contract is not None
    table = ReservationTable()
    b.reserve_commitments(table, 7)
    assert table.is_vertex_reserved(Point(2, 1), 8)
    assert table.is_edge_conflict(Point(2, 1), Point(1, 1), 7)
    assert not table.is_vertex_reserved(Point(2, 1), 9)


def test_finished_session_releases_agent_for_next_verification_pass(monkeypatch):
    world = WorldSimulation(SimulationConfig(grid_width=5, grid_height=5,
        fov_size=5, setting=SimulationSetting.SETTING_4, verification_pass_limit=3))
    initial = {
        "a": route((0, 1), (1, 1), (2, 1)),
        "b": route((1, 0), (1, 1), (1, 2)),
        "c": route((2, 3), (1, 3), (0, 3)),
    }
    for aid, path in initial.items():
        agent = GreedyAgent(aid, path.points[0], path.points[-1])
        world.add_agent(agent)
        agent.apply_planned_path(path)
    calls = []

    def negotiate(agent_a, agent_b, conflict, env, current_time):
        calls.append((agent_a.agent_id, agent_b.agent_id))
        if len(calls) == 1:
            # A/B resolve their vertex conflict, exposing a future A/C conflict.
            agent_a.apply_planned_path(route((0, 1), (0, 2), (0, 3), (1, 3), (2, 3), (2, 2), (2, 1)))
        else:
            agent_a.apply_planned_path(route((0, 1), (0, 2), (0, 1), (1, 1), (2, 1)))
        return Contract(session_id=f"fixture-{len(calls)}", agent_a=agent_a.agent_id,
            agent_b=agent_b.agent_id, path_a=agent_a.planned_path, path_b=agent_b.planned_path)

    monkeypatch.setattr(world.negotiator, "negotiate", negotiate)
    ctx = PipelineContext(world, 0, world.agents, True, True)
    NegotiationStage().execute(ctx)
    assert calls == [("a", "b"), ("a", "c")]
    assert world.current_time == 0  # Both sessions precede the first movement.
