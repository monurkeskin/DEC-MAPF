"""Persistent summaries must contain only records that were accepted by the logger."""

import datetime
import json
import sys

import polars as pl
import pytest

from mapf.analytics.logger import ExperimentLogger


def record(**changes):
    return {
        "scenario_id": "logger-fixture",
        "setting": 4,
        "agent_type": "PathAware",
        "agent_count": 2,
        "grid_size": 8,
        "fov_size": 5,
        "success": True,
        "total_steps": 8,
        "negotiation_count": 2,
        "successful_negotiations": 2,
        "total_path_length": 16,
        "information_sharing_rate": 0.25,
        "runtime_ms": 12.0,
        **changes,
    }


@pytest.mark.parametrize("failure", ["serialization", "storage"])
def test_failed_stream_write_does_not_count_a_record(tmp_path, failure):
    logger = ExperimentLogger(tmp_path)
    values = record()
    error = TypeError
    if failure == "serialization":
        values["extra_metadata"] = {"unserializable": object()}
    else:
        logger.jsonl_path.mkdir()
        error = OSError
    with pytest.raises(error):
        logger.log_run(**values)
    assert logger.to_polars().is_empty()
    assert logger.summarize_by_strategy().is_empty()


def test_empty_logger_has_no_summary_or_spurious_stream(tmp_path, capsys):
    logger = ExperimentLogger(tmp_path)
    assert logger.to_polars().is_empty()
    assert logger.summarize_by_strategy().is_empty()
    logger.print_summary_table()
    assert "No records logged" in capsys.readouterr().out
    assert not logger.jsonl_path.exists()


@pytest.mark.parametrize("filename", ["records.parquet", "records.csv"])
def test_exports_roundtrip_and_stream_matches_all_in_memory_records(tmp_path, filename):
    logger = ExperimentLogger(tmp_path)
    accepted = [
        logger.log_run(
            **record(seed=seed, success=success, extra_metadata={"tag": "fixture"})
        )
        for seed, success in [(11, True), (12, False)]
    ]
    for value in accepted:
        assert datetime.datetime.fromisoformat(value["timestamp"]).tzinfo is not None
    assert [
        json.loads(line) for line in logger.jsonl_path.read_text().splitlines()
    ] == accepted
    path = logger.save(filename)
    frame = (
        pl.read_parquet(path) if filename.endswith(".parquet") else pl.read_csv(path)
    )
    assert frame.to_dicts() == accepted
    summary = logger.summarize_by_strategy().row(0, named=True)
    assert summary["solution_rate"] == 0.5
    assert summary["avg_makespan"] == 8
    assert summary["avg_is_rate"] == 0.25


@pytest.mark.parametrize("rich_available", [True, False])
def test_memory_only_summary_is_readable_with_or_without_optional_rich(
    tmp_path, capsys, monkeypatch, rich_available
):
    monkeypatch.setenv("COLUMNS", "200")
    if not rich_available:
        monkeypatch.setitem(sys.modules, "rich.console", None)
    logger = ExperimentLogger(tmp_path, stream_jsonl=False)
    logger.log_run(**record())
    with pl.Config(tbl_width_chars=200, tbl_cols=-1):
        logger.print_summary_table()
    output = capsys.readouterr().out
    assert "PathAware" in output
    assert "100.0%" in output if rich_available else "solution_rate" in output
    assert not logger.jsonl_path.exists()
