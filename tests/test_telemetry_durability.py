import json
import time

import polars as pl
import pytest

from mapf.analytics.post_simulation import (
    compute_concession_curves,
    compute_token_inequality_gini,
    load_events_as_polars,
)
from mapf.telemetry.events import AgentMoveEvent
from mapf.telemetry.logger import AsyncExperimentLogger


def test_checked_prefix_survives_writer_failure_and_failures_are_not_silent(tmp_path, monkeypatch):
    logger = AsyncExperimentLogger(tmp_path, run_id="fault", buffer_flush_interval=1, queue_capacity=2)
    logger.start()
    logger.hook.on_move(AgentMoveEvent(0, "a", 1, 0, False, 0))
    until = time.monotonic() + 3
    while logger._total_events_written < 1 and time.monotonic() < until:
        time.sleep(.01)
    assert logger._total_events_written == 1
    def fail(_batch):
        raise OSError("injected disk failure")
    monkeypatch.setattr(logger, "_flush_batch", fail)
    logger.hook.on_move(AgentMoveEvent(1, "a", 1, 0, True, 0))
    until = time.monotonic() + 3
    while logger._error is None and time.monotonic() < until:
        time.sleep(.01)
    with pytest.raises(RuntimeError, match="disk failure"):
        logger.stop()
    assert not logger.events_file_path.exists()
    index = json.loads((logger.chunks_dir / "index.json").read_text())
    assert not index["complete"]
    prefix = load_events_as_polars(logger.chunks_dir)
    assert prefix["tick"].to_list() == [1]  # post-move time, shared by disk and GUI
    assert prefix["schema_version"].to_list() == ["telemetry-2"]
    with pytest.raises(FileExistsError):
        AsyncExperimentLogger(tmp_path, run_id="fault").start()
    (logger.chunks_dir / index["chunks"][0]["file"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        load_events_as_polars(logger.chunks_dir)


def test_late_heterogeneous_fields_and_missing_utilities_stay_missing(tmp_path):
    path = tmp_path / "mixed.jsonl"
    records = [{"event_type": "MOVE", "agent_id": "a", "tick": i} for i in range(200)]
    records.append({"event_type": "BID", "round_idx": 1, "offered_utility": None,
                    "utility_components": {"reason": "unavailable"}})
    path.write_text("\n".join(json.dumps(row) for row in records))
    frame = load_events_as_polars(path)
    assert "utility_components" in frame.columns
    assert compute_concession_curves(frame)["mean_utility"] == []
    old = pl.DataFrame([{"event_type": "NEGO_SESSION", "outcome": "AGREED", "tokens_transferred": 3}])
    assert compute_token_inequality_gini(old)["available"] is False


def test_balances_are_not_clamped_or_inferred_from_session_role():
    bad = pl.DataFrame([{"event_type": "TOKEN_TRANSFER", "balances_before": {"a": 5, "b": 5},
                         "balances_after": {"a": -1, "b": 11}}])
    with pytest.raises(ValueError, match="overdraft"):
        compute_token_inequality_gini(bad, agent_ids=["a", "b"])
