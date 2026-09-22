from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Any

from mapf.agents.base import goal_reached
from mapf.core.components import SimFrame
from mapf.core.heat import HeatRecorder
from mapf.core.models import (
    Conflict,
    Path,
    Point,
    RecordingLevel,
    SimulationConfig,
)
from mapf.core.observation_index import ObservationIndex
from mapf.core.observations import LocalEnvironment, Message, Observation
from mapf.core.protocols import AgentProtocol, EnvironmentProtocol
from mapf.core.reachability import StaticConnectivity
from mapf.engine.pipeline import PipelineContext, SimulationPipeline
from mapf.metrics.communication import CommunicationLedger
from mapf.negotiation.index import ConflictIndex
from mapf.negotiation.session import BilateralNegotiationSession
from mapf.telemetry.events import DiagnosticEvent, ManifestEvent
from mapf.telemetry.hook import NullTelemetryHook, TelemetryHook

logger = logging.getLogger("mapf.world")


class WorldSimulation(EnvironmentProtocol):
    """Discrete-time multi-agent MAPF world simulation engine."""

    def __init__(self, config: SimulationConfig) -> None:
        self._config = config
        self._agents: dict[str, AgentProtocol] = {}
        self._current_time: int = 0
        self._negotiation_history: list[dict[str, Any]] = []
        self._path_history: dict[str, list[Point]] = {}
        self._broadcast_history: list[dict[str, Path]] = []
        self._negotiator = BilateralNegotiationSession(
            max_rounds=config.negotiation_round_limit, protocol=config.negotiation_protocol,
            deadline_sec=config.negotiation_deadline_sec,
            lifecycle_hook=config.negotiation_lifecycle_hook,
        )
        self._collision_count: int = 0
        self._frames: list[SimFrame] = []
        self._pipeline = SimulationPipeline()
        self._is_unsolvable: bool = False
        self._stop_reason: str | None = None
        self._last_negotiation_failure: dict[str, Any] | None = None
        self._communication = CommunicationLedger()
        self._delivered_this_tick: set[Message] = set()
        self._observations: dict[str, Observation] = {}
        self._observation_index = ObservationIndex()
        self._conflict_index = ConflictIndex()
        self._heat_recorder = HeatRecorder(config.recording_level == RecordingLevel.FULL_TRACE,
                                           config.heat_recording_limit)
        self._initial_snapshot: dict[str, Any] = {}
        self._safety_interventions = 0
        self._movement_diagnostics: Counter[str] = Counter()
        self._replan_diagnostics: Counter[str] = Counter()
        self._last_replan_failure: dict[str, Any] | None = None
        self._last_movement_failure: dict[str, Any] | None = None
        self._connectivity = StaticConnectivity(config.grid_width, config.grid_height)
        self._last_reachability_failure: dict[str, Any] | None = None
        self._negotiation_outcomes: Counter[str] = Counter()
        self._no_motion_streak = 0
        self._longest_no_motion_streak = 0
        if config.enable_telemetry and config.telemetry_hook is not None:
            self._telemetry_hook: TelemetryHook = config.telemetry_hook
        else:
            self._telemetry_hook = NullTelemetryHook()

    @property
    def telemetry_hook(self) -> TelemetryHook:
        return self._telemetry_hook

    @property
    def frames(self) -> list[SimFrame]:
        return self._frames

    @property
    def negotiator(self) -> BilateralNegotiationSession:
        return self._negotiator

    @property
    def config(self) -> SimulationConfig:
        return self._config

    @property
    def current_time(self) -> int:
        return self._current_time

    @property
    def agents(self) -> dict[str, AgentProtocol]:
        return self._agents

    def detect_conflicts(self, *, paths: dict[str, Path], goals: dict[str, Point],
                         current_time: int, lookahead_steps: int,
                         disappear_at_target: bool) -> list[Conflict]:
        return self._conflict_index.detect(paths=paths, goals=goals, current_time=current_time,
            lookahead_steps=lookahead_steps, disappear_at_target=disappear_at_target)

    def record_replan(self, status: str, receipt: dict[str, Any] | None = None) -> None:
        self._replan_diagnostics[status] += 1
        if receipt is not None:
            self._last_replan_failure = {"tick": self.current_time, **receipt}

    def mark_unsolvable(self) -> None:
        self._is_unsolvable = True

    def record_negotiation(self, entry: dict[str, Any]) -> None:
        self._negotiation_history.append(entry)

    def record_negotiation_outcome(self, reason: str) -> None:
        self._negotiation_outcomes[reason] += 1

    def stop_negotiation(self, reason: str, detail: dict[str, Any]) -> None:
        self._is_unsolvable = True
        self._stop_reason = reason
        self._last_negotiation_failure = {
            "tick": self.current_time, "reason": reason,
            "scope": "execution_stopped; no initial-instance infeasibility proof", **detail,
        }
        self.telemetry_hook.on_diagnostic(DiagnosticEvent(
            "NEGOTIATION_STOP", self.current_time, self._last_negotiation_failure))

    def stop_movement(self, reason: str, receipt: dict[str, Any]) -> None:
        self._is_unsolvable = True
        self._stop_reason = reason
        self._last_movement_failure = {"tick": self.current_time, **receipt}
        self._movement_diagnostics["blocked_ticks"] += 1

    def record_movement_repair(self, repair: dict[str, Any]) -> None:
        self._movement_diagnostics["attempted_ticks"] += 1
        if repair.get("cause") == "progress":
            self._movement_diagnostics["progress_recovery_ticks"] += 1
        self._movement_diagnostics["search_nodes"] += repair["search_nodes"]
        self._movement_diagnostics["remaining_agent_holds"] += len(repair["remaining_holds"])
        self._movement_diagnostics["remaining_blocked_agents"] += len(repair["remaining_blocked_agents"])
        for component in repair["components"]:
            self._movement_diagnostics[component["status"]] += 1
        self.telemetry_hook.on_diagnostic(DiagnosticEvent("MOVEMENT_REPAIR", self.current_time, repair))

    def record_motion(self, *, stationary: bool) -> None:
        self._no_motion_streak = self._no_motion_streak + 1 if stationary else 0
        self._longest_no_motion_streak = max(self._longest_no_motion_streak, self._no_motion_streak)

    def record_safety_intervention(self) -> None:
        self._safety_interventions += 1

    def record_position(self, agent_id: str, position: Point) -> None:
        self._path_history[agent_id].append(position)

    def drain_decision_heat(self) -> tuple[list[dict[str, Any]], int]:
        return self._heat_recorder.drain()

    def finish_tick(self, frame: SimFrame) -> None:
        if self.config.recording_level != RecordingLevel.METRICS_ONLY:
            self._frames.append(frame)
        self._current_time += 1

    def add_agent(self, agent: AgentProtocol) -> None:
        self._agents[agent.agent_id] = agent
        self._path_history[agent.agent_id] = [agent.current_pos]

    def is_obstacle(self, p: Point) -> bool:
        if p in self._config.obstacles:
            return True
        if not self._config.setting.disappear_at_target:
            for a in self._agents.values():
                if goal_reached(a) and a.target_pos == p:
                    return True
        return False

    def is_within_bounds(self, p: Point) -> bool:
        return 0 <= p.x < self._config.grid_width and 0 <= p.y < self._config.grid_height

    def get_fov_obstacles(self, center: Point, fov_size: int) -> set[Point]:
        radius = fov_size // 2
        obs = {
            o
            for o in self._config.obstacles
            if abs(o.x - center.x) <= radius and abs(o.y - center.y) <= radius
        }
        if not self._config.setting.disappear_at_target:
            for a in self._agents.values():
                if goal_reached(a):
                    pt = a.target_pos
                    if abs(pt.x - center.x) <= radius and abs(pt.y - center.y) <= radius:
                        obs.add(pt)
        return obs

    def get_fov_broadcasts(
        self, center: Point, fov_size: int, requesting_agent_id: str
    ) -> dict[str, Path]:
        radius = fov_size // 2
        visible: dict[str, Path] = {}
        for a_id, agent in self._agents.items():
            if a_id == requesting_agent_id:
                continue
            if (
                abs(agent.current_pos.x - center.x) <= radius
                and abs(agent.current_pos.y - center.y) <= radius
            ):
                if goal_reached(agent) and self.config.setting.disappear_at_target:
                    continue
                horizon = self.config.broadcast_horizon or self.config.fov_size
                visible[a_id] = Path(points=agent.planned_path.points[:horizon])
        return visible

    def deliver_message(self, sender: str, recipient: str, path: Path, kind: Any = "BROADCAST",
                        *, session_id: str | None = None, acknowledgement: int = 0) -> Message:
        message = Message(sender, recipient, self.current_time,
                          tuple((p.x, p.y) for p in path.points), kind, session_id, acknowledgement)
        return self._deliver(message)

    def _deliver(self, message: Message) -> Message:
        # Re-reading an unchanged observation is not another protocol delivery.
        if message.kind == "OFFER" or message not in self._delivered_this_tick:
            self._communication.deliver(message)
            self._telemetry_hook.on_diagnostic(message)
            self._delivered_this_tick.add(message)
        return message

    def for_agent(self, agent_id: str) -> LocalEnvironment:
        # Keep subclass/instance query overrides observable rather than caching
        # results behind an untracked plugin implementation.
        standard_queries = all(getattr(getattr(self, name), '__func__', None) is getattr(WorldSimulation, name)
                               for name in ('get_fov_obstacles', 'get_fov_broadcasts'))
        if standard_queries:
            observation = self._observation_index.observe(self._agents, self.config, self.current_time, agent_id)
            for message in observation.messages:
                self._deliver(message)
            self._observations[agent_id] = observation
            return LocalEnvironment(self.config, observation)
        agent = self._agents[agent_id]
        messages = tuple(self.deliver_message(sender, agent_id, path) for sender, path in
                         self.get_fov_broadcasts(agent.current_pos, self.config.fov_size, agent_id).items())
        observation = Observation(agent_id, self.current_time, agent.current_pos,
                                  frozenset(self.get_fov_obstacles(agent.current_pos, self.config.fov_size)), messages)
        self._observations[agent_id] = observation
        return LocalEnvironment(self.config, observation)

    def record_settlement(self, receipt: dict[str, Any]) -> None:
        self._communication.transfer(receipt["amount"])
        self._telemetry_hook.on_diagnostic(DiagnosticEvent("TOKEN_TRANSFER", self.current_time, receipt))

    def record_decision_heat(self, agent: AgentProtocol, tick: int, session_id: str) -> None:
        record = self._heat_recorder.capture(agent, tick, session_id)
        if record is not None:
            self._telemetry_hook.on_diagnostic(DiagnosticEvent('DECISION_HEAT', tick, record))

    def observation_snapshot(self) -> dict[str, Any]:
        return {aid: observation.to_dict() for aid, observation in self._observations.items()}

    def initialize(self) -> None:
        """Plan initial paths for all registered agents and record provenance manifest."""
        self._telemetry_hook.on_manifest(
            ManifestEvent(
                git_commit="unavailable; use execution manifest",
                random_seed=self._config.random_seed,
                grid_width=self._config.grid_width,
                grid_height=self._config.grid_height,
                agent_count=len(self._agents),
                setting=self._config.setting.name,
                commitment=self._config.commitment_type.value,
                fov_size=self._config.fov_size,
                obstacles_count=len(self._config.obstacles),
                timestamp=time.time(),
            )
        )
        for agent in self._agents.values():
            # Initial planning has static map knowledge and no prematurely generated
            # peer trajectory. Initial observations are captured after all plans exist.
            empty = Observation(agent.agent_id, 0, agent.current_pos, frozenset(self.config.obstacles), ())
            agent.plan_initial_path(LocalEnvironment(self.config, empty))
        for aid in self._agents:
            self.for_agent(aid)
        self._initial_snapshot = {
            "planned_paths": {aid: [[p.x, p.y] for p in a.planned_path.points] for aid, a in self._agents.items()},
            "local_observations": self.observation_snapshot(),
        }

    def step(self) -> bool:
        """Execute one simulation step across all agents using the 5-stage pipeline."""
        if self._current_time > 0:
            self._delivered_this_tick.clear()
            self._observations.clear()
        active_agents = {
            a_id: a
            for a_id, a in self._agents.items()
            if not goal_reached(a)
        }

        if not active_agents:
            return True

        # This is an execution stopping condition, not information delivered to
        # agents. Absorbing arrived agents cannot vacate their cells. If one
        # remaining goal is disconnected even ignoring all movable agents and
        # commitments, no continuation from this reached state can finish.
        # Disappearing agents and finite reservations must never enter this test.
        if not self._config.setting.disappear_at_target:
            parked = frozenset(a.target_pos for a in self._agents.values() if goal_reached(a))
            if parked:
                disconnected = self._connectivity.disconnected(
                    {aid: a.current_pos for aid, a in active_agents.items()},
                    {aid: a.target_pos for aid, a in active_agents.items()},
                    frozenset(self._config.obstacles) | parked,
                )
                if disconnected:
                    self._stop_reason = "permanent_goal_disconnection"
                    self._is_unsolvable = True
                    self._last_reachability_failure = {
                        "tick": self._current_time,
                        "scope": "reached_state_only",
                        "disconnected_agents": disconnected,
                        "parked_cells": [[p.x, p.y] for p in sorted(parked, key=lambda p: (p.x, p.y))],
                        "component_builds": self._connectivity.builds,
                    }
                    self._telemetry_hook.on_diagnostic(DiagnosticEvent(
                        "REACHED_STATE", self._current_time, self._last_reachability_failure,
                    ))
                    return False

        ctx = PipelineContext(
            world=self,
            current_time=self._current_time,
            active_agents=active_agents,
            disappear_at_target=self._config.setting.disappear_at_target,
            allow_wait=self._config.setting.allow_wait,
        )
        return self._pipeline.step(ctx)

    def run(self) -> dict[str, Any]:
        """Run full simulation until all agents finish or max_steps reached."""
        self.initialize()

        while self._current_time < self._config.max_steps:
            all_done = self.step()
            if all_done:
                break
            if getattr(self, "_is_unsolvable", False):
                break

        # Independent physical solution validation
        from mapf.core.solution_validator import validate_solution
        from mapf.solvers.base import MAPFInstance

        inst = MAPFInstance(
            starts={aid: a.start_pos for aid, a in self._agents.items()},
            goals={aid: a.target_pos for aid, a in self._agents.items()},
            grid_width=self._config.grid_width,
            grid_height=self._config.grid_height,
            obstacles=self._config.obstacles,
        )
        executed_paths = {aid: Path(points=hist) for aid, hist in self._path_history.items()}
        val_result = validate_solution(inst, executed_paths, self._config.setting)

        # Collision count derived directly from independent physical validation
        self._collision_count = sum(
            1 for e in val_result.errors if e.error_type in ("vertex_collision", "edge_collision")
        )

        # Compute summary
        solved_count = sum(1 for a in self._agents.values() if goal_reached(a))
        total_count = len(self._agents)
        success = (solved_count == total_count) and val_result.is_valid and (self._collision_count == 0)

        total_path_length = sum(max(0, len(hist) - 1) for hist in self._path_history.values())
        initial_path_length = sum(a.get_state().initial_path_length for a in self._agents.values())

        # Group negotiations by time step
        nego_by_step: dict[int, int] = {}
        unique_contacts: dict[str, set[str]] = {a_id: set() for a_id in self._agents}
        for n in self._negotiation_history:
            t = n["time"]
            nego_by_step[t] = nego_by_step.get(t, 0) + 1
            unique_contacts[n["agent_a"]].add(n["agent_b"])
            unique_contacts[n["agent_b"]].add(n["agent_a"])

        avg_contacts = sum(len(c) for c in unique_contacts.values()) / float(max(1, total_count))
        broadcast_ratio = avg_contacts / float(max(1, total_count - 1)) if total_count > 1 else 0.0

        norm_path_diff = (
            float(total_path_length - initial_path_length) / float(initial_path_length)
            if initial_path_length > 0
            else 0.0
        )

        measured = self._communication.metrics(self._path_history, {aid: a.tokens for aid, a in self._agents.items()})
        return {
            "success": success,
            "solved_count": solved_count,
            "total_agents": total_count,
            "total_steps": self._current_time,
            "collision_count": self._collision_count,
            "negotiation_count": len(self._negotiation_history),
            "successful_negotiations": sum(1 for n in self._negotiation_history if n["success"]),
            "path_history": self._path_history,
            "total_path_length": total_path_length,
            "initial_path_length": initial_path_length,
            "norm_path_diff": max(0.0, norm_path_diff),
            "legacy_partner_ratio": broadcast_ratio,
            **measured,
            "safety_interventions": self._safety_interventions,
            "heat_recording": {"enabled": self._heat_recorder.enabled,
                    "entry_limit": self._heat_recorder.entry_limit, "entries": self._heat_recorder.entries,
                    "record_limit": self._heat_recorder.record_limit, "records": self._heat_recorder.total,
                    "omitted": self._heat_recorder.omitted},
            "solver_diagnostics": {
                "version": "failure-diagnostics-v2",
                "movement_repair": dict(self._movement_diagnostics),
                "preupdate_search": dict(self._replan_diagnostics),
                "last_replan_failure": self._last_replan_failure,
                "last_movement_failure": self._last_movement_failure,
                "last_reachability_failure": self._last_reachability_failure,
                "negotiation_outcomes": dict(self._negotiation_outcomes),
                "last_negotiation_failure": self._last_negotiation_failure,
                "longest_no_motion_streak": self._longest_no_motion_streak,
                "final_no_motion_streak": self._no_motion_streak,
            },
            # Physical arrival can stop an invalid trajectory too. Keep the
            # stopping condition separate from independent solution validity.
            "termination_reason": "all_arrived" if solved_count == total_count else self._stop_reason or ("bounded_replan_failed" if self._is_unsolvable else "step_limit"),
            "initial_snapshot": self._initial_snapshot if self.config.recording_level == RecordingLevel.FULL_TRACE else {},
            "nego_by_step": nego_by_step,
            "frames": [f.to_dict() for f in self._frames] if self._config.recording_level != RecordingLevel.METRICS_ONLY else [],
        }
