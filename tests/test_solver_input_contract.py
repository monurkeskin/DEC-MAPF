"""Reject inconsistent solver inputs before launching any search."""

import pytest

from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.solvers.base import MAPFInstance
from mapf.solvers.cbs import CentralizedCBSSolver


def instance(**changes):
    values = {"grid_width": 3, "grid_height": 2, "starts": {"a": Point(0, 0), "b": Point(0, 1)},
              "goals": {"a": Point(2, 0), "b": Point(2, 1)}}
    return MAPFInstance(**(values | changes))


@pytest.mark.parametrize(("changes", "message"), [
    ({"starts": {}, "goals": {}}, "matching start/goal"),
    ({"goals": {"a": Point(2, 0)}}, "matching start/goal"),
    ({"starts": {"a": Point(0, 0), "b": Point(0, 0)}}, "unique"),
    ({"starts": {"a": Point(-1, 0), "b": Point(0, 1)}}, "traversable"),
    ({"goals": {"a": Point(3, 0), "b": Point(2, 1)}}, "traversable"),
    ({"obstacles": {Point(2, 0)}}, "traversable"),
], ids=["empty", "roster", "duplicate", "start-bounds", "goal-bounds", "blocked"])
def test_invalid_geometry_or_roster_cannot_enter_solver(changes, message):
    with pytest.raises(ValueError, match=message):
        CentralizedCBSSolver().solve(instance(**changes), SimulationConfig())


@pytest.mark.parametrize("setting", list(SimulationSetting))
def test_shared_goal_is_allowed_only_when_agents_disappear(setting):
    problem = instance(goals={"a": Point(2, 0), "b": Point(2, 0)})
    config = SimulationConfig(setting=setting, max_steps=20)
    if not setting.disappear_at_target:
        with pytest.raises(ValueError, match="Shared goals"):
            CentralizedCBSSolver().solve(problem, config)
    else:
        result = CentralizedCBSSolver().solve(problem, config)
        assert result.success and result.metrics["independent_validation"]["is_valid"]


@pytest.mark.parametrize(("field", "value"), [
    ("grid_width", 4), ("grid_height", 3), ("obstacles", {Point(1, 1)}),
])
def test_explicit_config_geometry_cannot_override_instance(field, value):
    with pytest.raises(ValueError, match=f"geometry mismatch: {field}"):
        CentralizedCBSSolver().solve(instance(), SimulationConfig(**{field: value}))
