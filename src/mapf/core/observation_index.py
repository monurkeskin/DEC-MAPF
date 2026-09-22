"""Recipient-scoped observation reuse with spatial invalidation and immutable plans."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from mapf.agents.base import goal_reached
from mapf.core.models import Path, Point, SimulationConfig
from mapf.core.observations import Message, Observation
from mapf.core.protocols import AgentProtocol


@dataclass(frozen=True)
class Actor:
    position: Point
    goal: Point
    path: Path
    reached: bool


class ObservationIndex:
    def __init__(self) -> None:
        self.stats: Counter[str] = Counter()
        self._actors: dict[str, Actor] = {}
        self._cells: dict[Point, set[str]] = {}
        self._parked: Counter[Point] = Counter()
        self._views: dict[str, Observation] = {}
        self._payloads: dict[str, tuple[tuple[int, int], ...]] = {}
        self._tick: int | None = None
        self._config: tuple[frozenset[Point], int, int, bool] | None = None
        self._order: tuple[str, ...] = ()

    def observe(
        self,
        agents: dict[str, AgentProtocol],
        config: SimulationConfig,
        tick: int,
        recipient: str,
    ) -> Observation:
        horizon = config.broadcast_horizon or config.fov_size
        context = (
            frozenset(config.obstacles),
            config.fov_size,
            horizon,
            config.setting.disappear_at_target,
        )
        order = tuple(agents)
        if self._tick != tick or self._config != context or self._order != order:
            self._views.clear()
        if self._config != context:
            self._payloads.clear()
        self._tick, self._config, self._order = tick, context, order
        changes: list[tuple[str, Actor | None, Actor | None]] = []
        for aid in self._actors.keys() - agents.keys():
            changes.append((aid, self._actors[aid], None))
        for aid, agent in agents.items():
            position, goal, path = (
                agent.current_pos,
                agent.target_pos,
                agent.planned_path,
            )
            reached = goal_reached(agent)
            old = self._actors.get(aid)
            if old is None or not (
                old.path is path
                and old.position == position
                and old.goal == goal
                and old.reached == reached
            ):
                changes.append((aid, old, Actor(position, goal, path, reached)))
        radius = config.fov_size // 2

        def near(point: Point, center: Point) -> bool:
            return (
                abs(point.x - center.x) <= radius and abs(point.y - center.y) <= radius
            )

        for aid, old, updated_actor in changes:
            for rid, view in list(self._views.items()):
                if rid == aid or any(
                    state is not None
                    and (
                        near(state.position, view.position)
                        or (state.reached and near(state.goal, view.position))
                    )
                    for state in (old, updated_actor)
                ):
                    self._views.pop(rid)
            if old is not None:
                self._cells[old.position].discard(aid)
                if not self._cells[old.position]:
                    self._cells.pop(old.position)
                if old.reached:
                    self._parked[old.goal] -= 1
                    if not self._parked[old.goal]:
                        self._parked.pop(old.goal)
            self._payloads.pop(aid, None)
            if updated_actor is None:
                self._actors.pop(aid)
            else:
                self._actors[aid] = updated_actor
                self._cells.setdefault(updated_actor.position, set()).add(aid)
                if updated_actor.reached:
                    self._parked[updated_actor.goal] += 1
            self.stats["actor_updates"] += 1
        if recipient in self._views:
            self.stats["view_hits"] += 1
            return self._views[recipient]
        center = self._actors[recipient].position
        nearby: set[str] = set()
        obstacles: set[Point] = set()
        # Sparse worlds have fewer occupied cells than cells in a FoV square.
        # Avoid manufacturing Point objects for every empty cell in that case.
        area = (2 * radius + 1) ** 2
        if len(self._cells) < area:
            for point, ids in self._cells.items():
                if near(point, center):
                    nearby.update(ids)
        else:
            for x in range(center.x - radius, center.x + radius + 1):
                for y in range(center.y - radius, center.y + radius + 1):
                    nearby.update(self._cells.get(Point(x, y), ()))
        obstacles.update(point for point in context[0] if near(point, center))
        if not context[3]:
            obstacles.update(point for point in self._parked if near(point, center))
        messages: list[Message] = []
        for aid in order:
            if aid not in nearby or aid == recipient:
                continue
            actor = self._actors[aid]
            if actor.reached and context[3]:
                continue
            if aid not in self._payloads:
                self._payloads[aid] = tuple(
                    (p.x, p.y) for p in actor.path.points[:horizon]
                )
            messages.append(Message(aid, recipient, tick, self._payloads[aid]))
        view = Observation(
            recipient, tick, center, frozenset(obstacles), tuple(messages)
        )
        self._views[recipient] = view
        self.stats["view_builds"] += 1
        return view
