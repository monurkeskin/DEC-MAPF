"""Malformed worker notifications cannot partially acquire or renew a deadline."""

import pytest

from mapf.application.deadlines import NegotiationWatch


@pytest.mark.parametrize("diagnostics", [None, "phase", [1]], ids=["null", "string", "list"])
def test_bad_start_diagnostics_leave_watch_available(diagnostics):
    watch = NegotiationWatch()
    with pytest.raises(ValueError, match="diagnostics"):
        watch.receive({"type": "negotiation_started", "session_id": "bad", "deadline": 60,
                       "diagnostics": diagnostics})
    assert watch.session_id is None and watch.deadline is None
    watch.receive({"type": "negotiation_started", "session_id": "good", "deadline": 70})
    assert watch.expired(70)


@pytest.mark.parametrize("session_id", [None, "", 1])
def test_missing_start_identity_does_not_acquire_deadline(session_id):
    watch = NegotiationWatch()
    with pytest.raises(ValueError, match="identity"):
        watch.receive({"type": "negotiation_started", "session_id": session_id, "deadline": 60})
    assert watch.session_id is None and not watch.expired(100)


def test_boolean_is_not_a_monotonic_deadline():
    with pytest.raises(ValueError, match="deadline"):
        NegotiationWatch().receive({"type": "negotiation_started", "session_id": "a", "deadline": True})


@pytest.mark.parametrize("event", [
    {"type": "negotiation_progress", "session_id": "a", "diagnostics": []},
    {"type": "not-a-deadline", "session_id": "a"},
])
def test_bad_event_preserves_last_valid_progress(event):
    watch = NegotiationWatch()
    watch.receive({"type": "negotiation_started", "session_id": "a", "deadline": 60,
                   "diagnostics": {"phase": "proposal", "observed_monotonic": 20}})
    with pytest.raises(ValueError):
        watch.receive(event)
    assert watch.timeout_diagnostics(61)["seconds_since_progress"] == 41
    assert watch.deadline == 60 and watch.diagnostics["phase"] == "proposal"
