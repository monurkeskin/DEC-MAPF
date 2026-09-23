"""Replay must distinguish solver claims, physical evidence and missing telemetry."""

import pytest

from mapf.application.replay import build_solver_run_result
from mapf.core.models import Path, Point, SimulationSetting
from mapf.solvers.base import MAPFInstance, MAPFSolution


def replay(paths, *, central=False, success=False, **options):
    instance = MAPFInstance(grid_width=3, grid_height=2, starts={"a": Point(0, 0), "b": Point(2, 0)},
                            goals={"a": Point(1, 0), "b": Point(2, 1)})
    solution = MAPFSolution(solver_name="actual", is_centralized=central, success=success,
                            paths={aid: Path([Point(*p) for p in points]) for aid, points in paths.items()},
                            **options.pop("solution_fields", {}))
    return build_solver_run_result("label", "fixture", instance, solution, SimulationSetting.SETTING_4, 3,
                                   **options)


@pytest.mark.parametrize("central", [True, False])
def test_missing_candidate_is_not_a_valid_prefix_for_central_search(central):
    result = replay({}, central=central)
    assert result.validation.status == ("not_checked" if central else "invalid")
    assert not result.success and not result.validation.prefix_valid
    assert [e["error_type"] for e in result.validation.errors] == ["missing_path", "missing_path"]
    assert result.frames[0].positions == {"a": [0, 0], "b": [2, 0]}
    assert result.frames[0].tokens == ({} if central else {"a": 5, "b": 5})


def test_solver_reported_success_cannot_hide_a_missing_path():
    result = replay({"a": [(0, 0), (1, 0)]}, central=True,
                    solution_fields={"metrics": {"solver_reported_success": True}})
    assert result.solver_outcome == "solved"
    assert result.status == "invalid" and not result.success


def test_recorded_decisions_align_after_movement_and_absence_remains_explicit():
    class Recorded:
        def to_dict(self):
            return {"tick": 0, "tokens": {"a": 2, "b": 8}, "conflicts": [{}], "contracts": [{}],
                    "planned_paths": {"b": [[2, 0], [2, 1]]}, "local_heat_omitted": 3}

    result = replay({"a": [(0, 0), (1, 0)], "b": [(2, 0), (2, 0), (2, 1)]}, success=True,
                    solution_fields={"metrics": {"frames": [Recorded()], "initial_snapshot": {"tokens": {"a": 99}}}})
    assert result.solver == "actual"
    assert [frame.telemetry_available for frame in result.frames] == [True, True, False]
    assert result.frames[0].tokens == {"a": 5, "b": 5}
    assert result.frames[1].tokens == {"a": 2, "b": 8}
    assert result.frames[1].conflicts[0].time == result.frames[1].contracts[0].time == 1
    assert result.frames[1].local_heat_omitted == 3
    assert result.frames[2].tokens == {}


def test_arrival_progress_does_not_erase_a_collision_at_the_goal():
    result = replay({"a": [(0, 0), (1, 0)], "b": [(2, 0), (1, 0)]})
    assert result.frames[1].statuses == {"a": "collided", "b": "collided"}
    assert result.frames[1].solved_agents == 1
    assert result.frames[1].active_agents == 1
    assert result.validation.first_violation_tick == 1


def test_reduced_recording_preserves_validation_and_measured_metrics():
    fields = {"metrics": {"nego_by_step": {0: 1}, "negotiation_count": 1, "successful_negotiations": 1,
                           "termination_reason": "goals_reached", "solver_diagnostics": {"expanded": 4}}}
    paths = {"a": [(0, 0), (1, 0)], "b": [(2, 0), (2, 1)]}
    full = replay(paths, success=True, solution_fields=fields)
    reduced = replay(paths, success=True, include_frames=False, solution_fields=fields)
    assert reduced.frames == []
    assert reduced.model_dump(exclude={"frames"}) == full.model_dump(exclude={"frames"})
    assert reduced.measured_metrics["negotiations_by_tick"] == {"0": 1}
    assert reduced.measured_metrics["solver_diagnostics"] == {"expanded": 4}
