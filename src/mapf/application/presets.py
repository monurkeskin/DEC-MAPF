"""Named, versioned starting configurations, distinct from article protocols."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from mapf.application.contracts import JobSubmissionRequest


class PresetDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset_id: str
    name: str
    description: str
    inputs: JobSubmissionRequest


def get_preset(preset_id: str) -> PresetDescriptor:
    """Return fresh values; interactive-v1 preserves the original GUI starter."""
    if preset_id != "interactive-v1":
        raise ValueError(f"Unknown preset: {preset_id}")
    return PresetDescriptor(preset_id=preset_id, name="Interactive starter v1",
        description="Small interactive checks: 10-second process guard, 3 negotiation passes per tick. Not an article configuration.",
        inputs=JobSubmissionRequest(grid_width=8, grid_height=8, name="Draft",
            solver_id="Decentralized-HeatMap", setting="SETTING_4", fov_size=3,
            initial_tokens=10, commitment_type="SC", max_steps=100, timeout_sec=10,
            negotiation_deadline_sec=60, random_seed=42, recording_level="full-trace",
            heat_recording_limit=250000, suboptimality=1.1, negotiation_protocol="taop-v2",
            negotiation_round_limit=30, verification_pass_limit=3, max_astar_expansions=1500))


def preset_request(preset_id: str, **overrides: Any) -> JobSubmissionRequest:
    """Apply explicitly declared overrides using the same validated input schema."""
    return JobSubmissionRequest.model_validate({**get_preset(preset_id).inputs.model_dump(), **overrides})
