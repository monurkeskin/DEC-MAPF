"""Finite consumer checks, not a proof of solver correctness or completeness."""
from __future__ import annotations

from tempfile import TemporaryDirectory
from typing import Any

from mapf.application.artifacts import import_bundle
from mapf.application.runs import RunRepository
from mapf.core.hashing import compute_instance_hash
from mapf.core.models import SimulationConfig
from mapf.core.solution_validator import validate_solution
from mapf.metrics.costs import trajectory_costs
from mapf.solvers.base import MAPFInstance, MAPFSolution, MAPFSolverProtocol


def check_solver(solver: MAPFSolverProtocol, instance: MAPFInstance, config: SimulationConfig) -> dict[str, Any]:
    """Run ONE caller-supplied tiny fixture synchronously; use the supervisor for untrusted/long solvers.

    Caller inputs are copied, and mutation by the solver is rejected. Successful
    claims, identity, physical paths and canonical costs are checked independently.
    This function does not enforce a process deadline or prove optimality.
    """
    instance, config = instance.model_copy(deep=True), config.model_copy(deep=True)
    before = (instance.model_dump(), config.model_dump())
    result = solver.solve(instance, config)
    if before != (instance.model_dump(), config.model_dump()):
        raise ValueError("Solver mutated its supplied inputs")
    if not isinstance(result, MAPFSolution):
        raise TypeError("Solver must return MAPFSolution")
    if result.solver_name != solver.name or result.is_centralized != solver.is_centralized:
        raise ValueError("Solver/result identity mismatch")
    if result.instance_hash != compute_instance_hash(instance, config.setting):
        raise ValueError("Result instance identity mismatch")
    if not result.success and not result.paths:
        return {"status": "not_checked", "success": False, "solver": solver.name,
                "instance_hash": result.instance_hash, "costs": None,
                "scope": "No candidate paths returned; no physical validity or infeasibility claim"}
    report = validate_solution(instance, result.paths, config.setting)
    if result.success and not report.is_valid:
        raise ValueError("Success is inconsistent with independent path validation")
    if any(error.error_type != "wrong_goal" for error in report.errors):
        raise ValueError("Returned paths contain physical violations")
    costs = trajectory_costs(instance, result.paths)
    if result.success and (result.sum_of_costs != costs["action_sum_of_costs"] or result.makespan != costs["action_makespan"]):
        raise ValueError("Reported cost differs from canonical path costs")
    return {"status": "valid_solution" if result.success else "valid_prefix", "success": result.success,
            "solver": solver.name, "instance_hash": result.instance_hash, "costs": costs,
            "scope": "one finite supplied fixture; no optimality or completeness claim"}


def check_run_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Exercise the actual versioned importer in an isolated disposable workspace."""
    with TemporaryDirectory(prefix="decmapf-conformance-") as directory:
        repository = RunRepository(directory)
        run_id = import_bundle(bundle, repository)
        payload = repository.get_run(run_id)
        if payload is None:
            raise ValueError("Validated import was not readable")
        return {"status": "passed", "format": bundle["format"], "version": bundle["version"],
                "source_run_id": bundle["payload"]["metadata"]["run_id"],
                "validation_status": payload["metadata"]["validation_status"],
                "scope": "integrity and physical replay; checksum is not source authentication"}
