"""Discrete replay frames: agent lifecycle, recorded decisions and hindsight heat."""

from dataclasses import dataclass, field
from typing import Any, Literal

from mapf.application._replay_assessment import SolutionAssessment
from mapf.application.contracts import (
    ConflictRecord,
    ContractRecord,
    FrameSnapshot,
    Point2D,
)
from mapf.core.models import SimulationSetting
from mapf.solvers.base import MAPFInstance, MAPFSolution

AgentStatus = Literal["active", "reached", "parked", "disappeared", "deadlocked", "collided"]


@dataclass(frozen=True)
class TimelineSettings:
    setting: SimulationSetting
    fov_size: int
    initial_tokens: int
    include_frames: bool


@dataclass
class _Population:
    positions: dict[str, list[int]] = field(default_factory=dict)
    targets: dict[str, list[int]] = field(default_factory=dict)
    statuses: dict[str, AgentStatus] = field(default_factory=dict)
    active: int = 0
    solved: int = 0


def _recorded_frames(solution: MAPFSolution) -> dict[int, dict[str, Any]]:
    frames: dict[int, dict[str, Any]] = {}
    initial = solution.metrics.get("initial_snapshot", {})
    if initial:
        frames[0] = initial
    for raw in solution.metrics.get("frames", []):
        frame = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw)
        frames[frame.get("tick", 0) + 1] = frame
    return frames


@dataclass
class ReplayTimeline:
    """Construct t=0-based views from trajectories and available recorded frames.

    Executed-path hindsight is derived; local observations, commitments and
    decision heat are copied only when recorded. This is not solver resumption.
    """

    instance: MAPFInstance
    solution: MAPFSolution
    assessment: SolutionAssessment
    settings: TimelineSettings
    paths: dict[str, list[Point2D]] = field(init=False)
    raw_frames: dict[int, dict[str, Any]] = field(init=False)

    def __post_init__(self) -> None:
        self.paths = {aid: [Point2D(x=p.x, y=p.y) for p in path.points]
                      for aid, path in self.solution.paths.items()}
        self.raw_frames = _recorded_frames(self.solution)

    @property
    def total_ticks(self) -> int:
        return max((path.length for path in self.solution.paths.values()), default=0)

    def build(self) -> list[FrameSnapshot]:
        if not self.settings.include_frames:
            return []
        return [self.frame(tick) for tick in range(self.total_ticks + 1)]

    def _status(self, aid: str, tick: int) -> AgentStatus:
        arrival = self.assessment.arrival_ticks.get(aid)
        if arrival is None or tick < arrival:
            return "active"
        if not self.settings.setting.disappear_at_target:
            return "parked"
        return "reached" if tick == arrival else "disappeared"

    def _collided_agents(self, tick: int) -> set[str | None]:
        return {aid for error in self.assessment.physical_errors
                if error.error_type in ("vertex_collision", "edge_collision")
                and error.time_step == tick for aid in (error.agent_a, error.agent_b)}

    def _population(self, tick: int) -> _Population:
        population = _Population()
        collided = self._collided_agents(tick)
        for aid, start in self.instance.starts.items():
            goal = self.instance.goals[aid]
            population.targets[aid] = [goal.x, goal.y]
            path = self.solution.paths.get(aid)
            point = path.points[min(tick, len(path.points) - 1)] if path and path.points else start
            population.positions[aid] = [point.x, point.y]
            status = self._status(aid, tick)
            population.active += status == "active"
            population.solved += status != "active"
            # Arrival counts describe progress; collision labels describe this tick's violation.
            population.statuses[aid] = "collided" if aid in collided else status
        return population

    def _tokens(self, tick: int, raw: dict[str, Any]) -> dict[str, int]:
        if tick == 0 and not self.solution.is_centralized:
            return dict.fromkeys(self.instance.starts, self.settings.initial_tokens)
        tokens = raw.get("tokens", {})
        return {aid: tokens[aid] for aid in self.instance.starts if aid in tokens}

    def _heat(self, tick: int, population: _Population) -> dict[str, float]:
        heat: dict[str, float] = {}
        for aid, points in self.paths.items():
            if population.statuses.get(aid) in ("disappeared", "parked"):
                continue
            for point in points[tick:tick + self.settings.fov_size]:
                key = f"{point.x}-{point.y}"
                heat[key] = heat.get(key, 0.0) + 1.0
        return heat

    def frame(self, tick: int) -> FrameSnapshot:
        population = self._population(tick)
        raw = self.raw_frames.get(tick) or {}
        return FrameSnapshot(
            tick=tick, active_agents=population.active, solved_agents=population.solved,
            positions=population.positions, targets=population.targets, statuses=population.statuses,
            tokens=self._tokens(tick, raw), heat_grid=self._heat(tick, population),
            conflicts=_conflicts(raw, tick), contracts=_contracts(raw, tick),
            is_unsolvable=raw.get("is_unsolvable", False), phase="initial" if tick == 0 else "post_move",
            telemetry_available=tick in self.raw_frames,
            planned_paths=raw.get("planned_paths", {}), commitments=raw.get("commitments", {}),
            local_observations=raw.get("local_observations"), local_heat=raw.get("local_heat", []),
            local_heat_omitted=raw.get("local_heat_omitted", 0),
        )


def _conflicts(raw: dict[str, Any], tick: int) -> list[ConflictRecord]:
    return [ConflictRecord(a=c.get("a", ""), b=c.get("b", ""), time=c.get("time", tick),
                           type=c.get("type", "vertex"), location=c.get("location"))
            for c in raw.get("conflicts", [])]


def _contracts(raw: dict[str, Any], tick: int) -> list[ContractRecord]:
    return [ContractRecord(agent_a=c.get("agent_a", ""), agent_b=c.get("agent_b", ""),
                           time=c.get("time", tick), location=c.get("location"), details=c.get("details", {}))
            for c in raw.get("contracts", [])]
