"""Small named profiles. Historical paper selection is never inferred or fabricated."""

from __future__ import annotations

from typing import Any

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.plans import preview_batch


def list_profiles() -> list[dict[str, Any]]:
    return [
        {
            "id": "smoke-v1",
            "name": "Local smoke: crossing and four-agent grid",
            "enabled": True,
            "scope": "4 deterministic modern-code checks; no JAAMAS population inference",
        },
        {
            "id": "settings-smoke-v1",
            "name": "All four lifecycle settings",
            "enabled": True,
            "scope": "4 tiny crossing cases; regression witnesses, not a random sample",
        },
        {
            "id": "historical-jaamas-subsample",
            "name": "Historical JAAMAS subsample",
            "enabled": False,
            "scope": "Requires the exact archived scenario/seed/config selection and provenance mapping; no inferred rerun",
        },
    ]


def profile_jobs(profile_id: str) -> list[JobSubmissionRequest]:
    if profile_id == "smoke-v1":
        return [
            JobSubmissionRequest(
                scenario_id=s,
                solver_id=solver,
                setting="SETTING_4",
                max_steps=50,
                timeout_sec=10,
            )
            for s in ("crossing-2a", "grid-8x8-4a")
            for solver in ("Decentralized-HeatMap", "Prioritized")
        ]
    if profile_id == "settings-smoke-v1":
        return [
            JobSubmissionRequest(
                scenario_id="crossing-2a",
                solver_id="CBS",
                setting=setting,
                max_steps=30,
                timeout_sec=5,
            )
            for setting in ("SETTING_1", "SETTING_2", "SETTING_3", "SETTING_4")
        ]
    raise ValueError(
        "Profile is unavailable; historical selection must be provided explicitly"
    )


def preview_profile(profile_id: str) -> dict[str, Any]:
    jobs = profile_jobs(profile_id)
    return dict(
        preview_batch(jobs),
        profile_id=profile_id,
        jobs=[j.model_dump(mode="json") for j in jobs],
    )
