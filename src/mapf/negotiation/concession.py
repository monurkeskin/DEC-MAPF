"""Legal concession construction using only the recipient's local information."""
from mapf.agents.base import BaseAgent
from mapf.core.models import Bid, BidDecision, Path
from mapf.core.protocols import AgentProtocol, EnvironmentProtocol
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar
from mapf.negotiation.ledger import OfferLedger


def planning_context(agent: AgentProtocol, env: EnvironmentProtocol, tick: int) -> tuple[SpaceTimeAStar, ReservationTable]:
    planner = SpaceTimeAStar(env.config.grid_width, env.config.grid_height,
        obstacles=env.config.obstacles | env.get_fov_obstacles(agent.current_pos, env.config.fov_size),
        candidate_cache=getattr(env, "candidate_cache", None))
    table = ReservationTable()
    if isinstance(agent, BaseAgent):
        agent.reserve_commitments(table, tick)
    return planner, table


def feasible_concession(agent: AgentProtocol, bid: Bid, env: EnvironmentProtocol, tick: int) -> BidDecision:
    """Accept only when a complete legal response exists; never clear obligations."""
    planner, table = planning_context(agent, env, tick)
    table.reserve_path(bid.bidder_id, bid.proposed_path, tick)
    path = planner.search(start=agent.current_pos, goal=agent.target_pos, start_time=tick,
        reservation_table=table, allow_wait=env.config.setting.allow_wait,
        max_expansions=env.config.max_astar_expansions,
        max_time_steps=max(0, env.config.max_steps - tick),
        permanent_at_goal=not env.config.setting.disappear_at_target)
    reason = "FORCED_FEASIBLE_CONCESSION" if path is not None else "NO_FEASIBLE_CONCESSION_FOUND"
    return BidDecision(accepted=path is not None, proposed_path=path or agent.planned_path,
        reason=reason, components={"reason": reason, "search_status": planner.last_search_status,
                                   "expansions": planner.last_expansions})


def novel_offer(agent: AgentProtocol, ledger: OfferLedger, env: EnvironmentProtocol, tick: int) -> Path | None:
    """Finite candidate proposal, not proof that the entire bid space is empty."""
    planner, table = planning_context(agent, env, tick)
    horizon = env.config.negotiation_horizon or env.config.fov_size
    paths = planner.find_bounded_candidate_paths(start=agent.current_pos, goal=agent.target_pos,
        start_time=tick, reservation_table=table, allow_wait=env.config.setting.allow_wait,
        max_candidates=8, max_extra_steps=max(2, horizon), max_expansions=env.config.max_astar_expansions,
        max_time_steps=max(0, env.config.max_steps - tick),
        permanent_at_goal=not env.config.setting.disappear_at_target)
    previous = ledger.offers.get(agent.agent_id, set())
    return next((path for path in paths
                 if tuple((p.x, p.y) for p in path.points[:horizon]) not in previous), None)
