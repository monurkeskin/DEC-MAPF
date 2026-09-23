"""Independent admission and atomic settlement for deadline-bounded TAOP v2."""
from typing import Any

from mapf.agents.base import BaseAgent
from mapf.core.models import Bid, Conflict, Contract, Path
from mapf.core.protocols import AgentProtocol, EnvironmentProtocol
from mapf.core.solution_validator import validate_solution
from mapf.negotiation.ledger import OfferLedger, settle_contract
from mapf.solvers.base import MAPFInstance


def admit_agreement(session: Any, a: AgentProtocol, b: AgentProtocol, proposer: AgentProtocol,
                    acceptor: AgentProtocol, offered: Bid, response: Path, conflict: Conflict,
                    env: EnvironmentProtocol, tick: int, ledger: OfferLedger) -> Contract | None:
    allocation = Path(points=offered.proposed_path.points[:env.config.negotiation_horizon or env.config.fov_size])
    paths = {proposer.agent_id: offered.proposed_path, acceptor.agent_id: response}
    instance = MAPFInstance(starts={x.agent_id: x.current_pos for x in (a, b)},
        goals={x.agent_id: x.target_pos for x in (a, b)}, grid_width=env.config.grid_width,
        grid_height=env.config.grid_height, obstacles=env.config.obstacles)
    validation = validate_solution(instance, paths, env.config.setting)
    errors = [e for e in validation.errors if not (
        e.error_type in ("vertex_collision", "edge_collision") and e.time_step is not None
        and e.time_step >= len(allocation.points) - (e.error_type == "edge_collision"))]
    broken = any(isinstance(x, BaseAgent) and not x.respects_commitments(
        paths[x.agent_id], tick, stay_at_goal=not env.config.setting.disappear_at_target) for x in (a, b))
    if errors or broken:
        session.last_session_reason = "CONTRACT_VALIDATION_FAILED"
        return None
    transfer = ledger.payment(proposer.agent_id, acceptor.agent_id)
    contract = Contract(session_id=session.last_session_id, agent_a=a.agent_id, agent_b=b.agent_id,
        path_a=paths[a.agent_id], path_b=paths[b.agent_id], timestamp=tick,
        token_transfer=transfer if proposer is a else -transfer,
        accepted_by=acceptor.agent_id, allocated_path=allocation, conflict_tick=conflict.end_time,
        token_usage=dict(ledger.usage), protocol_version=session.protocol)
    session.check_deadline()
    session.last_settlement = settle_contract(a, b, contract, tick)
    session.check_deadline()
    if hasattr(env, "record_settlement"):
        env.record_settlement(session.last_settlement)
    session.last_session_reason = "AGREED"
    return contract
