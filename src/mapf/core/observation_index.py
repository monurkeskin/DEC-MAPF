"""Recipient-scoped observation reuse with spatial invalidation and immutable plans."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from mapf.agents.base import goal_reached
from mapf.core.models import Path, Point, SimulationConfig
from mapf.core.observations import Message, Observation
from mapf.core.protocols import AgentProtocol


@dataclass(frozen=True, slots=True)
class _FieldOfView:
    center: Point
    radius: int

    def contains(self, point: Point) -> bool:
        return (
            abs(point.x - self.center.x) <= self.radius
            and abs(point.y - self.center.y) <= self.radius
        )


@dataclass(frozen=True)
class Actor:
    position: Point
    goal: Point
    path: Path
    reached: bool

    def matches(self, position: Point, goal: Point, path: Path, reached: bool) -> bool:
        if self.path is not path:
            return False
        return (self.position, self.goal, self.reached) == (position, goal, reached)

    def affects(self, area: _FieldOfView) -> bool:
        return area.contains(self.position) or (
            self.reached and area.contains(self.goal)
        )


@dataclass(frozen=True, slots=True)
class _ActorChange:
    aid: str
    before: Actor | None
    after: Actor | None

    def affects(self, view: Observation, radius: int) -> bool:
        if view.agent_id == self.aid:
            return True
        area = _FieldOfView(view.position, radius)
        return any(
            state is not None and state.affects(area)
            for state in (self.before, self.after)
        )


@dataclass(frozen=True, slots=True)
class _ObservationSettings:
    obstacles: frozenset[Point]
    fov_size: int
    horizon: int
    disappear_at_target: bool

    @classmethod
    def from_config(cls, config: SimulationConfig) -> _ObservationSettings:
        return cls(
            frozenset(config.obstacles),
            config.fov_size,
            config.broadcast_horizon or config.fov_size,
            config.setting.disappear_at_target,
        )


class ObservationIndex:
    """Cache recipient-local views within one world's ordered tick context.

    Changes to tick, roster order or settings invalidate views; actor changes
    invalidate affected recipients. Message order follows the original roster.
    The world owns this index; strategies receive only the resulting view.
    """

    def __init__(self) -> None:
        self.stats: Counter[str] = Counter()
        self._actors: dict[str, Actor] = {}
        self._cells: dict[Point, set[str]] = {}
        self._parked: Counter[Point] = Counter()
        self._views: dict[str, Observation] = {}
        self._payloads: dict[str, tuple[tuple[int, int], ...]] = {}
        self._tick: int | None = None
        self._config: _ObservationSettings | None = None
        self._order: tuple[str, ...] = ()

    def observe(
        self,
        agents: dict[str, AgentProtocol],
        config: SimulationConfig,
        tick: int,
        recipient: str,
    ) -> Observation:
        settings = _ObservationSettings.from_config(config)
        self._sync_context(settings, tick, tuple(agents))
        for change in self._changes(agents):
            self._invalidate_views(change, config.fov_size // 2)
            self._apply_change(change)
        if recipient in self._views:
            self.stats["view_hits"] += 1
            return self._views[recipient]
        view = self._build_view(recipient, settings, tick)
        self._views[recipient] = view
        self.stats["view_builds"] += 1
        return view

    def _sync_context(
        self, settings: _ObservationSettings, tick: int, order: tuple[str, ...]
    ) -> None:
        if (self._tick, self._config, self._order) != (tick, settings, order):
            self._views.clear()
        if self._config != settings:
            self._payloads.clear()
        self._tick, self._config, self._order = tick, settings, order

    def _changes(self, agents: dict[str, AgentProtocol]) -> list[_ActorChange]:
        changes = [
            _ActorChange(aid, self._actors[aid], None)
            for aid in self._actors.keys() - agents.keys()
        ]
        for aid, agent in agents.items():
            position, goal, path = (
                agent.current_pos,
                agent.target_pos,
                agent.planned_path,
            )
            reached = goal_reached(agent)
            old = self._actors.get(aid)
            if old is None or not old.matches(position, goal, path, reached):
                changes.append(
                    _ActorChange(aid, old, Actor(position, goal, path, reached))
                )
        return changes

    def _invalidate_views(self, change: _ActorChange, radius: int) -> None:
        for rid, view in list(self._views.items()):
            if change.affects(view, radius):
                self._views.pop(rid)

    def _apply_change(self, change: _ActorChange) -> None:
        aid, old, new = change.aid, change.before, change.after
        if old is not None:
            self._remove_actor(aid, old)
        self._payloads.pop(aid, None)
        if new is None:
            self._actors.pop(aid)
        else:
            self._actors[aid] = new
            self._cells.setdefault(new.position, set()).add(aid)
            if new.reached:
                self._parked[new.goal] += 1
        self.stats["actor_updates"] += 1

    def _remove_actor(self, aid: str, actor: Actor) -> None:
        self._cells[actor.position].discard(aid)
        if not self._cells[actor.position]:
            self._cells.pop(actor.position)
        if actor.reached:
            self._parked[actor.goal] -= 1
            if not self._parked[actor.goal]:
                self._parked.pop(actor.goal)

    def _build_view(
        self, recipient: str, settings: _ObservationSettings, tick: int
    ) -> Observation:
        center = self._actors[recipient].position
        area = _FieldOfView(center, settings.fov_size // 2)
        nearby = self._nearby_agents(area)
        obstacles = {p for p in settings.obstacles if area.contains(p)}
        if not settings.disappear_at_target:
            obstacles.update(p for p in self._parked if area.contains(p))
        messages = self._messages(recipient, nearby, settings, tick)
        return Observation(
            recipient, tick, center, frozenset(obstacles), tuple(messages)
        )

    def _nearby_agents(self, area: _FieldOfView) -> set[str]:
        nearby: set[str] = set()
        # Sparse worlds need not manufacture a Point for each empty FoV cell.
        if len(self._cells) < (2 * area.radius + 1) ** 2:
            for point, ids in self._cells.items():
                if area.contains(point):
                    nearby.update(ids)
        else:
            for x in range(
                area.center.x - area.radius, area.center.x + area.radius + 1
            ):
                for y in range(
                    area.center.y - area.radius, area.center.y + area.radius + 1
                ):
                    nearby.update(self._cells.get(Point(x, y), ()))
        return nearby

    def _messages(
        self,
        recipient: str,
        nearby: set[str],
        settings: _ObservationSettings,
        tick: int,
    ) -> list[Message]:
        messages = []
        for aid in self._order:
            if aid not in nearby or aid == recipient:
                continue
            actor = self._actors[aid]
            if actor.reached and settings.disappear_at_target:
                continue
            if aid not in self._payloads:
                self._payloads[aid] = tuple(
                    (p.x, p.y) for p in actor.path.points[: settings.horizon]
                )
            messages.append(Message(aid, recipient, tick, self._payloads[aid]))
        return messages
