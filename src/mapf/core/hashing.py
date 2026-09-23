from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mapf.core.models import SimulationSetting
    from mapf.solvers.base import MAPFInstance


def compute_instance_hash(
    instance: MAPFInstance,
    setting: SimulationSetting | str | None = None,
) -> str:
    """Compute a deterministic SHA-256 fingerprint for a MAPF instance.

    Identifies the scenario geometry, start-goal pairs, and setting
    so comparisons can be matched by scenario identity rather than arbitrary indices.
    """
    sorted_obstacles = sorted((p.x, p.y) for p in instance.obstacles)
    sorted_agents = sorted(
        (
            aid,
            (instance.starts[aid].x, instance.starts[aid].y),
            (instance.goals[aid].x, instance.goals[aid].y),
        )
        for aid in instance.starts
    )

    if setting is None:
        setting_str = "UNSPECIFIED"
    elif hasattr(setting, "name"):
        setting_str = str(setting.name)
    else:
        setting_str = str(setting)

    canonical_payload = {
        "width": instance.grid_width,
        "height": instance.grid_height,
        "obstacles": sorted_obstacles,
        "agents": sorted_agents,
        "setting": setting_str,
    }

    serialized = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"inst-{digest[:16]}"


def compute_run_id(
    instance_hash: str,
    solver_name: str,
    config_dict: dict[str, Any] | None = None,
    git_commit: str = "",
) -> str:
    """Compute a deterministic content-based execution ID for a solver run."""
    clean_config = {}
    if config_dict:
        for k, v in config_dict.items():
            if isinstance(v, (int, float, str, bool)):
                clean_config[k] = v
            elif hasattr(v, "name"):
                clean_config[k] = v.name

    canonical_payload = {
        "instance_hash": instance_hash,
        "solver": solver_name,
        "config": clean_config,
        "git_commit": git_commit,
    }

    serialized = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"run-{digest[:16]}"
