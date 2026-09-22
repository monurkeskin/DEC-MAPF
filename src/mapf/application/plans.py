"""One explicit effective-input planner used by HTTP, batch admission, and CLI."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from mapf.application.contracts import JobSubmissionRequest, ScenarioValidateRequest
from mapf.application.native_solvers import native_profile
from mapf.application.runs import RunRepository, digest
from mapf.application.scenarios import ScenarioService
from mapf.application.semantics import problem_semantics
from mapf.application.solvers import (
    ALGORITHM_VERSION,
    SolverRegistry,
    process_timeout_limit,
)
from mapf.core.models import Point, SimulationSetting
from mapf.solvers.base import MAPFInstance


def instance_from_snapshot(data: dict[str, Any]) -> MAPFInstance:
    order = data.get("agent_order", list(data["starts"]))
    if set(order) != set(data["starts"]) or len(order) != len(set(order)):
        raise ValueError("Agent order must contain each roster ID exactly once")
    return MAPFInstance(
        grid_width=data["grid_width"],
        grid_height=data["grid_height"],
        starts={a: Point(*data["starts"][a]) for a in order},
        goals={a: Point(*p) for a, p in data["goals"].items()},
        obstacles={Point(*p) for p in data["obstacles"]},
    )


def scenario_snapshot(request: ScenarioValidateRequest) -> dict[str, Any]:
    data = request.model_dump(mode="json")
    instance = instance_from_snapshot(data)
    setting = SimulationSetting[request.setting]
    errors = ScenarioService.validate_instance(instance, setting)
    if errors:
        raise ValueError("; ".join(errors))
    return ScenarioService.snapshot_instance(instance, setting, name=request.name)


def builtins() -> dict[str, dict[str, Any]]:
    result = {}
    for sid, name, description, instance, setting in [
        ScenarioService.create_crossing_scenario(),
        ScenarioService.create_bottleneck_scenario(),
        ScenarioService.create_narrow_corridor_scenario(),
        ScenarioService.create_dense_grid_scenario(4),
        ScenarioService.create_dense_grid_scenario(8),
    ]:
        result[sid] = dict(
            ScenarioService.snapshot_instance(instance, setting, name=name),
            scenario_id=sid,
            description=description,
        )
    return result


def provenance() -> dict[str, Any]:
    source = Path(__file__).resolve().parents[1]
    root = source.parents[1]
    source_tree = (root / "src/mapf").resolve() == source and (root / "pyproject.toml").is_file()
    own_repository = source_tree and (root / ".git").exists()

    def git(*args: str) -> str:
        if not own_repository:
            return "unavailable"
        try:
            proc = subprocess.run(
                ["git", "--no-optional-locks", *args],
                cwd=root,
                text=True,
                capture_output=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "unavailable"
        return proc.stdout.strip() if proc.returncode == 0 else "unavailable"

    files = {
        str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(source.rglob("*.py"))
    }
    versions = {}
    for pkg in ("dec-mapf", "pydantic", "fastapi", "numpy", "polars", "psutil"):
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = "not-installed"
    git_status = git("status", "--porcelain")
    return {
        "git_commit": git("rev-parse", "HEAD"),
        "working_tree_dirty": None if git_status == "unavailable" else bool(git_status),
        "source_origin": "source-tree" if source_tree else "installed-package",
        "source_sha256": digest(files),
        "source_files": files,
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "logical_cpu_count": os.cpu_count(),
        "thread_limits": {key: os.environ.get(key, "unset") for key in (
            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"
        )},
        "lock_sha256": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest()
        if source_tree and (root / "uv.lock").exists() else "not-in-wheel",
        "dependencies": versions,
        "algorithm_version": ALGORITHM_VERSION,
        "metric_version": "delivered-metrics-v2",
        "validation_version": "trajectory-v2",
    }


def preview(
    request: JobSubmissionRequest, repository: RunRepository | None = None
) -> dict[str, Any]:
    cap = SolverRegistry.get_capability(request.solver_id)
    if cap is None:
        raise ValueError(f"Unsupported solver: {request.solver_id}")
    timeout_limit = process_timeout_limit(cap.is_centralized)
    if cap.is_centralized and request.timeout_sec is None:
        raise ValueError("A centralized solver requires an explicit process timeout")
    if request.timeout_sec is not None and request.timeout_sec > timeout_limit:
        raise ValueError(f"{cap.display_name} process timeout must not exceed {timeout_limit:g} seconds")
    if request.scenario_id:
        snap = builtins().get(request.scenario_id)
        if snap is None and repository:
            snap = repository.get_scenario(request.scenario_id)
        if snap is None:
            raise KeyError(request.scenario_id)
        snap = dict(snap)
        # The selected setting is an explicit treatment; never take the template default silently.
        inst = instance_from_snapshot(snap)
        setting = SimulationSetting[request.setting]
        errors = ScenarioService.validate_instance(inst, setting)
        if errors:
            raise ValueError("; ".join(errors))
        snap = ScenarioService.snapshot_instance(inst, setting, name=snap["name"])
    else:
        snap = scenario_snapshot(request)
    config = request.model_dump(
        mode="json",
        exclude={
            "scenario_id",
            "starts",
            "goals",
            "obstacles",
            "name",
            "grid_width",
            "grid_height",
        },
    )
    config["solver_id"] = cap.solver_id
    config["agent_order"] = snap["agent_order"]
    config["broadcast_horizon"] = request.broadcast_horizon or request.fov_size
    config["negotiation_horizon"] = request.negotiation_horizon or request.fov_size
    profile = native_profile(cap.solver_id)
    if profile is not None:
        if profile.setting != request.setting:
            raise ValueError(f"{profile.solver_id} requires {profile.setting}")
        profile.verify_binary()
        config["native_profile"] = profile.model_dump(mode="json")
    inactive = (
        ["fov_size", "initial_tokens", "commitment_type", "negotiation_deadline_sec",
         "negotiation_protocol", "negotiation_round_limit",
         "verification_pass_limit", "broadcast_horizon", "negotiation_horizon", "heat_recording_limit"] if cap.is_centralized else []
    )
    if not cap.supports_suboptimality:
        inactive.append("suboptimality")
    definition = {
        "instance_hash": snap["instance_hash"],
        "effective_config": config,
        "algorithm_version": cap.algorithm_version,
    }
    return {
        "scenario": snap,
        "effective_config": config,
        "definition_digest": digest(definition),
        "inactive_parameters": inactive,
        "scientific_scope": cap.scientific_scope,
        "semantics": problem_semantics(SimulationSetting[request.setting]).model_dump(mode="json"),
        "warnings": (
            ["Legacy EECBS ID denotes simplified focal CBS; no certified EECBS bound"]
            if request.solver_id.startswith("EECBS")
            else []
        ),
        "budget": {
            "max_steps": request.max_steps,
            "process_timeout_sec": request.timeout_sec,
            "negotiation_deadline_sec": request.negotiation_deadline_sec if not cap.is_centralized else None,
            "negotiation_round_limit": request.negotiation_round_limit if not cap.is_centralized else None,
            "verification_pass_limit": request.verification_pass_limit if not cap.is_centralized else None,
            "max_astar_expansions": request.max_astar_expansions,
            "agents": len(snap["starts"]),
        },
    }


def preview_batch(
    jobs: list[JobSubmissionRequest], repository: RunRepository | None = None
) -> dict[str, Any]:
    expanded = [preview(r, repository) for r in jobs]
    return {
        "plans": expanded,
        "count": len(expanded),
        "exclusions": [],
        "plan_digest": digest(expanded),
        "maximum_process_seconds": None if any(r.timeout_sec is None for r in jobs)
        else sum(r.timeout_sec for r in jobs if r.timeout_sec is not None),
        "max_concurrency": 2,
        "inference_scope": "Declared local cases only; not a full historical experiment",
    }
