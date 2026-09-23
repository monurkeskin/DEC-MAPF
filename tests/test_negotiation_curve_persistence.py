"""Per-tick paper metrics survive a metrics-only adapter without inventing data."""
import pytest

from mapf.application.replay import build_solver_run_result
from mapf.core.models import Path, Point, SimulationSetting
from mapf.solvers.base import MAPFInstance, MAPFSolution


@pytest.mark.parametrize('instrumented', [True, False])
def test_negotiation_curve_retention_and_unavailable_state(instrumented):
    instance = MAPFInstance(starts={'a': Point(0, 0)}, goals={'a': Point(1, 0)}, grid_width=2, grid_height=1)
    solution = MAPFSolution(solver_name='fixture', is_centralized=not instrumented, success=True,
                           paths={'a': Path(points=[Point(0, 0), Point(1, 0)])},
                           metrics={'nego_by_step': {0: 2, 1: 1}, 'negotiation_count': 3,
                                    'successful_negotiations': 2} if instrumented else {})
    result = build_solver_run_result('fixture', 'fixture', instance, solution,
                                    SimulationSetting.SETTING_4, 5, 5, 20, include_frames=False)
    assert result.frames == []
    if instrumented:
        assert result.measured_metrics['negotiations_by_tick'] == {'0': 2, '1': 1}
        assert result.measured_metrics['negotiation_count'] == 3
        assert result.measured_metrics['successful_negotiations'] == 2
    else:
        assert 'negotiations_by_tick' not in result.measured_metrics
