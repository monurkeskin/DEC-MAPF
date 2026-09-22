"""Human-readable problem assumptions, shared by every effective-input preview."""
from typing import Literal

from pydantic import BaseModel

from mapf.core.models import SimulationSetting
from mapf.metrics.costs import METRIC_VERSION


class ProblemSemantics(BaseModel):
    schema_version: Literal["problem-semantics-1"] = "problem-semantics-1"
    motion: str = "Discrete four-connected grid; one fixed goal per agent."
    coordinates: str = "Zero-based (x, y): column, row."
    time_origin: str = "Initial positions are t=0; one transition consumes one tick."
    wait_before_goal: bool
    goal_policy: Literal["stay", "disappear"]
    goal_timing: str
    forbidden_conflicts: list[str] = ["vertex occupancy", "opposing edge swap"]
    cost: str = "Sum of first-arrival ticks; makespan is their maximum. Incomplete solutions have no delivered cost."
    metric_version: str = METRIC_VERSION
    scope: str = "Grid path validity only. No continuous dynamics, robot footprint or physical safety guarantee."


def problem_semantics(setting: SimulationSetting) -> ProblemSemantics:
    return ProblemSemantics(
        wait_before_goal=setting.allow_wait,
        goal_policy="disappear" if setting.disappear_at_target else "stay",
        goal_timing=("Arrival occupies the goal at that tick; the agent is absent on subsequent ticks."
                     if setting.disappear_at_target else "The agent occupies its goal after arrival."),
    )
