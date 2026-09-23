"""Archive admission validates declared populations without replacing source rows."""

import hashlib

import pytest

from mapf.application.article_suite import archived_article_spec, article_spec
from tests.test_article_rosters import fixture


def prefix_spec(map_file, scenario_files, **changes):
    options = {
        "agents": [1],
        "fovs": [5],
        "workers": 1,
        "wall_seconds": 60,
        "timeout_sec": 10,
        "split": "held-out",
        **changes,
    }
    return article_spec(map_file, scenario_files, **options)


def test_indented_scenario_comment_is_not_an_agent_row(tmp_path):
    map_file, scenario = fixture(tmp_path, 16, 20, 7)
    original = prefix_spec(map_file, [scenario])
    raw = scenario.read_text().replace("version 1\n", "version 1\n   # roster note\n\n")
    scenario.write_text(raw)
    annotated = prefix_spec(map_file, [scenario])
    source = annotated["sampling"]["sources"][0]
    assert source["eligible_rows"] == 20
    assert source["selected_prefixes"] == {"1": [{"row": 1, "distance": 7}]}
    assert source["sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert annotated["scenarios"][0]["starts"] == original["scenarios"][0]["starts"]
    assert scenario.read_text() == raw


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"agents": []}, "agent counts"),
        ({"agents": [101]}, "agent counts"),
        ({"agents": [1, 1]}, "Duplicate treatment"),
        ({"fovs": [5, 5]}, "Duplicate treatment"),
        ({"split": "unlabelled"}, "split"),
        ({"agents": [80]}, "eligible distinct pairs"),
    ],
)
def test_prefix_population_constraints_remain_explicit(tmp_path, options, message):
    map_file, scenario = fixture(tmp_path, 16, 20, 7)
    before = scenario.read_bytes()
    with pytest.raises(ValueError, match=message):
        prefix_spec(map_file, [scenario], **options)
    assert scenario.read_bytes() == before


@pytest.mark.parametrize("repeat", [0, 2])
def test_empty_or_repeated_source_lists_are_rejected(tmp_path, repeat):
    map_file, scenario = fixture(tmp_path, 16, 20, 7)
    with pytest.raises(ValueError, match="nonempty distinct"):
        prefix_spec(map_file, [scenario] * repeat)
    with pytest.raises(ValueError, match="nonempty distinct"):
        archived_article_spec(
            map_file,
            [scenario] * repeat,
            profile="main-16",
            workers=1,
            wall_seconds=60,
            timeout_sec=10,
            split="held-out",
        )


def test_symlink_alias_cannot_count_as_a_second_source_population(tmp_path):
    map_file, scenario = fixture(tmp_path, 16, 20, 7)
    alias = tmp_path / "alias.scen"
    alias.symlink_to(scenario)
    with pytest.raises(ValueError, match="nonempty distinct"):
        prefix_spec(map_file, [scenario, alias])


@pytest.mark.parametrize("builder", ["prefix", "archive"])
def test_standard_version_and_leading_whitespace_preserve_roster(tmp_path, builder):
    map_file, scenario = fixture(tmp_path, 16, 20, 7)
    raw = "\n" + scenario.read_text().replace("version 1", "version 1.0")
    scenario.write_text(raw)
    if builder == "prefix":
        result = prefix_spec(map_file, [scenario])
    else:
        result = archived_article_spec(
            map_file,
            [scenario],
            profile="main-16",
            workers=1,
            wall_seconds=60,
            timeout_sec=10,
            split="held-out",
        )
    assert result["scenarios"][0]["starts"]["agent_000"] == [0, 0]
    assert (
        result["sampling"]["sources"][0]["sha256"]
        == hashlib.sha256(raw.encode()).hexdigest()
    )
    assert scenario.read_text() == raw


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"profile": "unknown"}, "main-16 or appendix-32"),
        ({"split": "unlabelled"}, "split"),
        ({"max_steps": 0}, "step guard"),
        ({"max_steps": 10001}, "step guard"),
    ],
)
def test_archive_protocol_constraints_remain_explicit(tmp_path, options, message):
    map_file, scenario = fixture(tmp_path, 16, 20, 7)
    kwargs = {
        "profile": "main-16",
        "workers": 1,
        "wall_seconds": 60,
        "timeout_sec": 10,
        "split": "held-out",
        **options,
    }
    with pytest.raises(ValueError, match=message):
        archived_article_spec(map_file, [scenario], **kwargs)
