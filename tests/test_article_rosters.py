"""Paper profiles preserve archived rosters instead of resampling their rows."""
from pathlib import Path

import pytest

from mapf.application.article_suite import archived_article_spec, article_spec
from mapf.application.contracts import JobSubmissionRequest
from mapf.application.experiments import compile_experiment
from mapf.core.models import Point
from mapf.core.movingai import format_movingai_map, format_movingai_scen


def fixture(tmp_path: Path, width: int, count: int, distance: int) -> tuple[Path, Path]:
    map_file = tmp_path / f"empty-{width}-{width}.map"
    map_file.write_text(format_movingai_map(width, width, set()))
    pairs = [(Point(i % 3, i // 3), Point(i % 3 + distance, i // 3)) for i in range(count)]
    scenario = tmp_path / "ordered.scen"
    scenario.write_text(format_movingai_scen(pairs, map_file.name, width, width))
    return map_file, scenario


def spec(map_file, scenario, profile):
    return archived_article_spec(map_file, [scenario], profile=profile, workers=1,
                                 wall_seconds=60, timeout_sec=10, split="held-out")


def test_appendix_preserves_all_80_rows_including_distances_over_24(tmp_path):
    map_file, scenario = fixture(tmp_path, 32, 80, 29)
    # This historical field is not a four-connected shortest-path certificate.
    lines = scenario.read_text().splitlines()
    scenario.write_text(lines[0] + "\n" + "\n".join("\t".join(line.split()[:-1] + ["0.1"]) for line in lines[1:]) + "\n")
    result = spec(map_file, scenario, "appendix-32")
    assert result["defaults"]["commitment_type"] == "ZC"
    assert result["matrix"]["solver_id"] == ["Decentralized-HeatMap"]
    assert len(result["scenarios"]) == 1
    assert len(result["scenarios"][0]["starts"]) == 80
    assert result["scenarios"][0]["goals"]["agent_079"] == [30, 26]
    source = result["sampling"]["sources"][0]
    assert [r["distance"] for r in source["ordered_rows"]] == [29] * 80
    assert source["rejected_rows"] == []
    assert len(compile_experiment(result)["trials"]) == 12


def test_main_profile_uses_sc_and_both_methods_and_preserves_order(tmp_path):
    map_file, scenario = fixture(tmp_path, 16, 20, 7)
    result = spec(map_file, scenario, "main-16")
    assert result["defaults"]["commitment_type"] == "SC"
    assert len(result["matrix"]["solver_id"]) == 2
    assert result["scenarios"][0]["starts"]["agent_019"] == [1, 6]
    assert len(compile_experiment(result)["trials"]) == 24


def test_archived_empty_map_header_decodes_without_changing_source(tmp_path):
    map_file, scenario = fixture(tmp_path, 32, 80, 29)
    original = map_file.read_text()
    map_file.write_text("32,32\n" + "\n".join(original.splitlines()[4:]) + "\n")
    raw = map_file.read_bytes()
    result = spec(map_file, scenario, "appendix-32")
    assert result["scenarios"][0]["obstacles"] == []
    assert result["sampling"]["map_format"] == "archived-width-height-grid"
    assert map_file.read_bytes() == raw
    map_file.write_bytes(raw[:-10])
    with pytest.raises(ValueError, match="dimensions"):
        spec(map_file, scenario, "appendix-32")


def test_stale_archive_dimensions_require_explicit_recorded_repair(tmp_path):
    map_file, scenario = fixture(tmp_path, 32, 80, 29)
    scenario.write_text(scenario.read_text().replace("\t32\t32\t", "\t16\t16\t"))
    before = scenario.read_bytes()
    with pytest.raises(ValueError, match="explicit repair"):
        spec(map_file, scenario, "appendix-32")
    result = archived_article_spec(map_file, [scenario], profile="appendix-32", workers=1,
                                  wall_seconds=60, timeout_sec=10, split="held-out",
                                  repair_dimensions_from_map=True)
    changes = result["sampling"]["sources"][0]["dimension_corrections"]
    assert changes == [{"row": i, "declared": [16, 16], "map": [32, 32]} for i in range(1, 81)]
    assert scenario.read_bytes() == before
    assert result["scenarios"][0]["goals"]["agent_079"] == [30, 26]


@pytest.mark.parametrize("bad", ["distance", "duplicate", "map", "count"])
def test_bad_exact_roster_fails_without_filtering_or_replacement(tmp_path, bad):
    map_file, scenario = fixture(tmp_path, 16, 20, 7)
    lines = scenario.read_text().splitlines()
    row = lines[1].split()
    if bad == "distance":
        row[6] = "1"
    elif bad == "duplicate":
        row = lines[2].split()
    elif bad == "map":
        row[1] = "different.map"
    elif bad == "count":
        lines.pop()
    lines[1] = "\t".join(row)
    scenario.write_text("\n".join(lines) + "\n")
    before = scenario.read_bytes()
    with pytest.raises(ValueError):
        spec(map_file, scenario, "main-16")
    assert scenario.read_bytes() == before


def test_profile_and_generous_step_guard_are_explicit(tmp_path):
    map_file, scenario = fixture(tmp_path, 32, 80, 29)
    with pytest.raises(ValueError, match="16"):
        spec(map_file, scenario, "main-16")
    result = spec(map_file, scenario, "appendix-32")
    assert result["defaults"]["max_steps"] == 10000
    assert JobSubmissionRequest(max_steps=10000).max_steps == 10000
    with pytest.raises(ValueError):
        JobSubmissionRequest(max_steps=10001)
    with pytest.raises(ValueError, match="prefix filter"):
        article_spec(map_file, [scenario], agents=[80], fovs=[5], workers=1,
                     wall_seconds=60, timeout_sec=10, split="held-out")
