"""A bounded logger must surface pressure and still allow owned-writer cleanup."""

import gzip
import json
import threading
import time

import pytest

from mapf.telemetry.events import AgentMoveEvent
from mapf.telemetry.logger import AsyncExperimentLogger


def move(tick):
    return AgentMoveEvent(tick, "a", tick, 0, False, 3)


@pytest.mark.parametrize("identifier", ["../escape", "has space", "a" * 101])
def test_run_identifier_cannot_escape_its_output_namespace(tmp_path, identifier):
    with pytest.raises(ValueError, match="plain identifier"):
        AsyncExperimentLogger(tmp_path, run_id=identifier)


@pytest.mark.parametrize("options", [
    {"queue_capacity": 0}, {"queue_capacity": 10001},
    {"buffer_flush_interval": 0}, {"buffer_flush_interval": 10001},
])
def test_logger_bounds_are_checked_before_start(tmp_path, options):
    with pytest.raises(ValueError, match="bounds"):
        AsyncExperimentLogger(tmp_path, **options)


def test_empty_context_publishes_a_valid_empty_stream_and_cannot_be_restarted(tmp_path):
    with AsyncExperimentLogger(tmp_path, run_id="empty") as logger:
        logger.start()  # Starting the same active owner is idempotent.
    logger.stop()
    assert gzip.decompress(logger.events_file_path.read_bytes()) == b""
    index = json.loads((logger.chunks_dir / "index.json").read_text())
    assert index["complete"] and index["events"] == 0
    with pytest.raises(ValueError, match="immutable"):
        logger.start()
    with pytest.raises(ValueError, match="immutable"):
        AsyncExperimentLogger(tmp_path, run_id="empty").start()


def test_logger_rejects_producers_before_start_and_after_stop(tmp_path):
    logger = AsyncExperimentLogger(tmp_path)
    logger.stop()
    with pytest.raises(RuntimeError, match="not accepting"):
        logger.hook.on_move(move(0))
    logger.start()
    logger.stop()
    with pytest.raises(RuntimeError, match="not accepting"):
        logger.hook.on_move(move(1))


def test_failed_initial_index_cannot_accept_events_without_a_writer(tmp_path, monkeypatch):
    logger = AsyncExperimentLogger(tmp_path)

    def disk_failure(complete):
        raise OSError("index disk failure")

    monkeypatch.setattr(logger, "_index", disk_failure)
    with pytest.raises(OSError, match="index disk"):
        logger.start()
    with pytest.raises(RuntimeError, match="writer failed"):
        logger.hook.on_move(move(0))
    assert not logger.events_file_path.exists()


def test_idle_flush_publishes_checked_prefix_before_stop(tmp_path):
    with AsyncExperimentLogger(tmp_path, buffer_flush_interval=100) as logger:
        logger.hook.on_move(move(0))
        deadline = time.monotonic() + 3
        while True:
            index = json.loads((logger.chunks_dir / "index.json").read_text())
            if index["events"] == 1:
                break
            assert time.monotonic() < deadline
            time.sleep(.01)
        assert not index["complete"] and index["events"] == 1
        assert not logger.events_file_path.exists()
    records = [json.loads(line) for line in gzip.decompress(logger.events_file_path.read_bytes()).splitlines()]
    assert [(event["sequence"], event["tick"]) for event in records] == [(1, 1)]


@pytest.fixture
def stalled_writer(tmp_path, monkeypatch, request):
    logger = AsyncExperimentLogger(tmp_path, buffer_flush_interval=1, queue_capacity=getattr(request, "param", 1))
    entered, release = threading.Event(), threading.Event()
    flush = logger._flush_batch

    def slow_flush(batch):
        entered.set()
        assert release.wait(timeout=8), "Test must release its owned writer"
        flush(batch)

    monkeypatch.setattr(logger, "_flush_batch", slow_flush)
    logger.start()
    logger.hook.on_move(move(0))
    assert entered.wait(timeout=3)
    logger.hook.on_move(move(1))
    try:
        yield logger, release
    finally:
        release.set()
        logger.stop()
        logger._worker_thread.join(timeout=3)


def expire_full_queue_budget(logger, monkeypatch):
    """Expire the blocking queue boundary while keeping the real stalled writer."""
    put = logger._queue.put

    def expired_put(item, block=True, timeout=None):
        assert block and timeout == 2  # The production wait budget stays unchanged.
        monkeypatch.setattr(logger._queue, "put", put)
        return put(item, block=False)  # A genuinely full Queue still raises Full.

    monkeypatch.setattr(logger._queue, "put", expired_put)


def test_backpressure_is_visible_and_never_increments_accepted_sequence(stalled_writer, monkeypatch):
    logger, release = stalled_writer
    expire_full_queue_budget(logger, monkeypatch)
    with pytest.raises(RuntimeError, match="backpressure"):
        logger.hook.on_move(move(2))
    release.set()
    logger.stop()
    records = [json.loads(line) for line in gzip.decompress(logger.events_file_path.read_bytes()).splitlines()]
    assert [event["sequence"] for event in records] == [1, 2]
    assert [event["tick"] for event in records] == [1, 2]


def test_shutdown_can_be_retried_after_queue_pressure_without_leaking_writer(stalled_writer, monkeypatch):
    logger, release = stalled_writer
    expire_full_queue_budget(logger, monkeypatch)
    with pytest.raises(RuntimeError, match="shutdown budget"):
        logger.stop()
    release.set()
    logger.stop()
    assert not logger._worker_thread.is_alive()
    assert json.loads((logger.chunks_dir / "index.json").read_text())["complete"]


@pytest.mark.parametrize("stalled_writer", [2], indirect=True, ids=["two-queue-slots"])
def test_shutdown_deadline_can_be_retried_without_sending_a_second_sentinel(stalled_writer, monkeypatch):
    logger, release = stalled_writer
    join = logger._worker_thread.join
    with monkeypatch.context() as patch:
        patch.setattr(logger._worker_thread, "join", lambda timeout: join(timeout=.01))
        with pytest.raises(RuntimeError, match="shutdown deadline"):
            logger.stop()
    release.set()
    logger.stop()
    assert not logger._worker_thread.is_alive()
    assert json.loads((logger.chunks_dir / "index.json").read_text())["events"] == 2
