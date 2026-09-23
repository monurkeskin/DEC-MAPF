"""The fixed participants and environment of one bilateral session."""

from dataclasses import dataclass
from typing import Any

from mapf.core.models import Conflict, Path
from mapf.core.protocols import AgentProtocol, EnvironmentProtocol


@dataclass(frozen=True)
class NegotiationContext:
    session: Any
    a: AgentProtocol
    b: AgentProtocol
    conflict: Conflict
    env: EnvironmentProtocol
    tick: int

    @property
    def participants(self) -> tuple[AgentProtocol, AgentProtocol]:
        return self.a, self.b

    def local_views(self) -> dict[str, EnvironmentProtocol]:
        return {agent.agent_id: self.env.for_agent(agent.agent_id) if hasattr(self.env, "for_agent") else self.env
                for agent in self.participants}

    def allocation(self, path: Path) -> Path:
        horizon = self.env.config.negotiation_horizon or self.env.config.fov_size
        return Path(points=path.points[:horizon])

    def record_heat(self, agent: AgentProtocol) -> None:
        if hasattr(self.env, "record_decision_heat"):
            self.env.record_decision_heat(agent, self.tick, self.session.last_session_id)
