"""Branch constraints and solve-local state shared by the Python CT searches."""

from __future__ import annotations

from dataclasses import dataclass, field

from mapf.core.models import Conflict, ConflictType, Point, SimulationConfig
from mapf.solvers.base import MAPFInstance

VertexConstraints = dict[str, set[tuple[Point, int]]]
EdgeConstraints = dict[str, set[tuple[Point, Point, int]]]


@dataclass
class SearchContext:
    instance: MAPFInstance
    config: SimulationConfig
    seen: set[object] = field(default_factory=set)

    def admit(self, vertices: VertexConstraints, edges: EdgeConstraints) -> bool:
        signature = tuple(
            (agent, frozenset(vertices[agent]), frozenset(edges[agent]))
            for agent in sorted(vertices)
        )
        if signature in self.seen:
            return False
        self.seen.add(signature)
        return True


def branch_constraints(
    vertices: VertexConstraints, edges: EdgeConstraints, conflict: Conflict, agent: str
) -> tuple[VertexConstraints, EdgeConstraints]:
    """Copy the parent; forbid only this branch's conflicting move or occupancy."""
    child_vertices = {key: set(values) for key, values in vertices.items()}
    child_edges = {key: set(values) for key, values in edges.items()}
    if conflict.conflict_type == ConflictType.VERTEX:
        child_vertices[agent].add((conflict.location_a, conflict.time))
    else:
        start = conflict.location_a
        end = conflict.location_b or conflict.location_a
        if agent != conflict.agent_a:
            start, end = end, start
        child_edges[agent].add((start, end, conflict.time))
    return child_vertices, child_edges


def termination_reason(timed_out: bool, open_nodes: bool, incomplete: bool) -> str:
    if timed_out:
        return "timeout"
    if open_nodes:
        return "iteration_limit"
    return "low_level_limit" if incomplete else "search_exhausted"
