"""Library execution must not reseed or consume a caller's random stream."""

import argparse
import random

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.plans import preview
from mapf.application.worker import solve_plan
from mapf.cli import solve_command


def test_headless_replay_is_deterministic_without_reseeding_callers():
    saved = random.getstate()
    try:
        plan = preview(
            JobSubmissionRequest(
                scenario_id="crossing-2a",
                solver_id="Decentralized-HeatMap",
                setting="SETTING_4",
                max_steps=30,
                negotiation_deadline_sec=60,
                timeout_sec=None,
            )
        )
        before = random.getstate()
        first = solve_plan(plan)["result"]
        assert random.getstate() == before
        for _ in range(29):
            random.random()
        before = random.getstate()
        second = solve_plan(plan)["result"]
        assert random.getstate() == before
        for key in ("paths", "success", "measured_metrics", "negotiation_count"):
            assert first[key] == second[key]
    finally:
        random.setstate(saved)


def test_cli_generation_does_not_touch_global_rng(capsys):
    saved = random.getstate()
    try:
        args = argparse.Namespace(
            solver="CBS",
            agents=2,
            grid=8,
            setting=4,
            commitment="SC",
            fov=5,
            density=0,
            seed=517,
            max_steps=30,
            timeout=5,
        )
        before = random.getstate()
        assert solve_command(args) == 0
        assert random.getstate() == before
    finally:
        random.setstate(saved)
