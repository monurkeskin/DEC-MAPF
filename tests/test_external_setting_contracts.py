"""External invocation/parser tests; these fixtures do not qualify a real binary."""

import pytest

from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.solvers.base import MAPFInstance
from mapf.solvers.binary_runner import ExternalBinarySolver


def executable(tmp_path, text, reject_suboptimality=False):
    source = tmp_path / "fixture.sh"
    source.write_text("#!/bin/sh\n" + ("for arg in \"$@\"; do [ \"$arg\" = --suboptimality ] && exit 2; done\n"
                     if reject_suboptimality else "") +
        'for arg in "$@"; do\nif [ "$prev" = --outputPaths ]; then out="$arg"; fi\nprev="$arg"\ndone\n' +
        "cat <<'PATHS' > \"$out\"\n" + text + "\nPATHS\n")
    source.chmod(0o755)
    return source


def single():
    return MAPFInstance(grid_width=3, grid_height=2,
        starts={"a": Point(0, 0)}, goals={"a": Point(2, 0)})


def test_cbsh2_does_not_receive_an_unsupported_suboptimality_option(tmp_path):
    binary = executable(tmp_path, "Agent 0: (0,0)->(1,0)->(2,0)", True)
    solver = ExternalBinarySolver(binary, solver_name="CBSH2-RTC",
        supported_settings=frozenset({"SETTING_2"}))
    assert solver.solve(single(), SimulationConfig(setting=SimulationSetting.SETTING_2)).success


def test_external_row_major_linear_paths_are_decoded_on_rectangular_grid(tmp_path):
    binary = executable(tmp_path, "Agent 0: 0->1->2->")
    solver = ExternalBinarySolver(binary, supported_settings=frozenset({"SETTING_2"}))
    result = solver.solve(single(), SimulationConfig(setting=SimulationSetting.SETTING_2))
    assert result.success
    assert result.sum_of_costs == 2


@pytest.mark.parametrize("setting", list(SimulationSetting))
def test_declared_setting_does_not_waive_independent_wait_validation(tmp_path, setting):
    binary = executable(tmp_path, "Agent 0: (0,0)->(0,0)->(1,0)->(2,0)")
    solver = ExternalBinarySolver(binary, supported_settings=frozenset({setting.name}))
    result = solver.solve(single(), SimulationConfig(setting=setting))
    assert result.success == setting.allow_wait
    assert result.metrics["solver_reported_success"] is True
    assert result.metrics["independent_validation"]["is_valid"] == setting.allow_wait


def test_multiple_physical_settings_require_explicit_invocation_mapping(tmp_path):
    binary = executable(tmp_path, "Agent 0: (0,0)->(1,0)->(2,0)")
    with pytest.raises(ValueError, match="setting_arguments"):
        ExternalBinarySolver(binary, supported_settings=frozenset({"SETTING_1", "SETTING_2"}))


def test_paper_cbsh2_profile_does_not_claim_disappear_support(tmp_path):
    binary = executable(tmp_path, "Agent 0: (0,0)->(1,0)->(2,0)")
    with pytest.raises(ValueError, match="SETTING_1.*SETTING_2"):
        ExternalBinarySolver(binary, solver_name="CBSH2-RTC", supported_settings=frozenset({"SETTING_4"}))


def test_setting_arguments_are_forwarded_and_explicit_timeout_overrides_constructor(tmp_path):
    binary = executable(tmp_path, "Agent 0: 0->1->2")
    source = binary.read_text().replace('for arg in "$@"; do\n',
        'printf "%s\\n" "$@" > "' + str(tmp_path / 'argv.txt') + '"\nfor arg in "$@"; do\n', 1)
    binary.write_text(source)
    solver = ExternalBinarySolver(binary, time_limit_sec=2.5,
        supported_settings=frozenset({"SETTING_1", "SETTING_2"}),
        setting_arguments={"SETTING_1": ("--fixture-wait", "false"),
                           "SETTING_2": ("--fixture-wait", "true")})
    for config, cutoff in ((SimulationConfig(setting=SimulationSetting.SETTING_1), 2.5),
        (SimulationConfig(setting=SimulationSetting.SETTING_2, centralized_timeout_sec=3.75), 3.75)):
        result = solver.solve(single(), config)
        assert result.success
        argv = (tmp_path / 'argv.txt').read_text().splitlines()
        assert argv[argv.index('--cutoffTime')+1] == str(cutoff)
        assert argv[argv.index('--fixture-wait')+1] == str(config.setting.allow_wait).lower()
        assert result.metrics['cutoff_seconds'] == cutoff


def test_setting_arguments_cannot_silently_change_the_frozen_solver_weight(tmp_path):
    binary = executable(tmp_path, "Agent 0: 0->1->2")
    with pytest.raises(ValueError, match="cannot override"):
        ExternalBinarySolver(binary, supported_settings=frozenset({"SETTING_2"}),
            setting_arguments={"SETTING_2": ("--suboptimality=4",)})


def test_native_reported_cost_survives_independent_canonical_cost(tmp_path):
    binary = executable(tmp_path, "Agent 0: 0->1->2")
    binary.write_text(binary.read_text()+'''\nfor arg in "$@"; do
if [ "$prev" = --output ]; then stats="$arg"; fi
prev="$arg"
done
printf 'solution cost,min f value\\n999,2\\n' > "$stats"
''')
    result = ExternalBinarySolver(binary, supported_settings=frozenset({"SETTING_2"})).solve(
        single(), SimulationConfig(setting=SimulationSetting.SETTING_2))
    assert result.success and result.sum_of_costs == 2
    assert result.metrics["solver_reported_sum_of_costs"] == 999
    assert result.metrics["solver_diagnostics"]["reported_cost_matches_paths"] is False


def test_native_search_limit_is_distinct_from_infrastructure_failure(tmp_path):
    binary = executable(tmp_path, "Agent 0: 0->1->2")
    binary.write_text(binary.read_text()+'''\nrm "$out"
for arg in "$@"; do
if [ "$prev" = --output ]; then stats="$arg"; fi
prev="$arg"
done
printf 'solution cost\\n-1\\n' > "$stats"
''')
    result = ExternalBinarySolver(binary, supported_settings=frozenset({"SETTING_2"})).solve(
        single(), SimulationConfig(setting=SimulationSetting.SETTING_2))
    assert not result.success
    assert result.metrics["termination_reason"] == "native_reported_limit"
    assert result.metrics["solver_diagnostics"]["statistics"]["solution cost"] == "-1"
