"""Validated experiment specifications and deterministic manifest expansion."""
from __future__ import annotations

import itertools
import math
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.plans import preview, provenance
from mapf.application.presets import get_preset
from mapf.application.resources import ResourcePolicy
from mapf.application.runs import RunRepository, digest


class ExperimentBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workers: int = Field(default=2, ge=1, le=6)
    wall_seconds: float = Field(default=900, ge=1, le=86400)
    max_trials: int = Field(default=10000, ge=1, le=100000)
    disk_mb: int = Field(default=2048, ge=64, le=65536)
    threads_per_worker: int = Field(default=1, ge=1, le=1)
    resources: ResourcePolicy | None = None

    @model_validator(mode="after")
    def check_worker_policy(self) -> ExperimentBudget:
        if self.resources is None and self.workers > 4:
            raise ValueError("More than four workers requires explicit resource admission")
        return self


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    scenarios: list[dict[str, Any]] = Field(min_length=1)
    defaults: dict[str, Any] = Field(default_factory=dict)
    preset_id: str | None = None
    matrix: dict[str, list[Any]] = Field(default_factory=dict)
    exclude: list[dict[str, Any]] = Field(default_factory=list)
    budget: ExperimentBudget = Field(default_factory=ExperimentBudget)
    sampling: dict[str, Any] = Field(default_factory=lambda: {
        "population": "declared fixtures only", "independent_unit": "instance_hash",
    })


def _validate_axes(spec: ExperimentSpec) -> list[str]:
    declared = set(spec.matrix).union(*spec.exclude)
    if declared - JobSubmissionRequest.model_fields.keys():
        raise ValueError("Unknown matrix/exclusion parameter")
    lengths = [len(values) for values in spec.matrix.values()]
    if 0 in lengths:
        raise ValueError("Each matrix axis needs at least one value")
    count = len(spec.scenarios) * math.prod(lengths)
    if count > spec.budget.max_trials:
        raise ValueError("Cartesian expansion exceeds max_trials (before exclusions)")
    return sorted(spec.matrix)


def _combinations(spec: ExperimentSpec, keys: list[str]) -> Iterator[tuple[int, dict[str, Any]]]:
    preset = get_preset(spec.preset_id).inputs.model_dump() if spec.preset_id else {}
    for index, scenario in enumerate(spec.scenarios):
        for values in itertools.product(*(spec.matrix[key] for key in keys)):
            yield index, {**preset, **spec.defaults, **scenario, **dict(zip(keys, values, strict=True))}


class _TrialExpansion:
    """Assign stable trial ordinals while retaining every declared exclusion."""

    def __init__(self, source: dict[str, Any], repository: RunRepository | None) -> None:
        self.source, self.repository = source, repository
        self.trials: list[dict[str, Any]] = []
        self.excluded: list[dict[str, Any]] = []

    def consider(self, index: int, effective: dict[str, Any], rules: list[dict[str, Any]]) -> None:
        sampling_unit = effective.pop("sampling_unit", None)
        matches = [i for i, rule in enumerate(rules) if all(effective.get(key) == value for key, value in rule.items())]
        if matches:
            self.excluded.append({"scenario_index": index, "inputs": effective, "rule_indices": matches})
            return
        trial = self._trial(index, effective)
        trial["sampling_unit"] = sampling_unit or digest({key: trial["plan"]["scenario"][key] for key in
            ("grid_width", "grid_height", "starts", "goals", "obstacles")})
        self.trials.append(trial)

    def _trial(self, index: int, effective: dict[str, Any]) -> dict[str, Any]:
        plan = preview(JobSubmissionRequest.model_validate(effective), self.repository)
        plan["provenance"] = {key: value for key, value in self.source.items() if key != "source_files"}
        identity = digest({"definition": plan["definition_digest"], "source": self.source["source_sha256"]})
        return {"trial_id": digest({"identity": identity, "ordinal": len(self.trials)}),
                "definition_identity": identity, "scenario_index": index, "plan": plan}


def _manifest_body(spec: ExperimentSpec, expansion: _TrialExpansion) -> dict[str, Any]:
    if not expansion.trials:
        raise ValueError("All experiment trials were excluded")
    limits = [trial["plan"]["effective_config"]["timeout_sec"] for trial in expansion.trials]
    body = {"schema_version": "experiment-1", "name": spec.name, "sampling": spec.sampling,
            "budget": spec.budget.model_dump(), "trials": expansion.trials, "excluded": expansion.excluded,
            "source_sha256": expansion.source["source_sha256"], "provenance": expansion.source,
            "maximum_process_seconds": None if any(limit is None for limit in limits) else sum(limits)}
    if spec.preset_id:
        body["preset_id"] = spec.preset_id
    return body


def compile_experiment(raw: dict[str, Any], repository: RunRepository | None = None) -> dict[str, Any]:
    spec = ExperimentSpec.model_validate(raw)
    keys = _validate_axes(spec)
    expansion = _TrialExpansion(provenance(), repository)
    for index, effective in _combinations(spec, keys):
        expansion.consider(index, effective, spec.exclude)
    body = _manifest_body(spec, expansion)
    checksum = digest(body)
    return {**body, "manifest_digest": checksum, "experiment_id": "experiment-" + checksum[:24]}


def verify_manifest(manifest: dict[str, Any], *, check_source: bool = True) -> None:
    body = manifest.copy()
    declared_digest = body.pop("manifest_digest", None)
    declared_id = body.pop("experiment_id", None)
    checksum = digest(body)
    if checksum != declared_digest:
        raise ValueError("Experiment manifest digest mismatch")
    if declared_id != "experiment-" + checksum[:24]:
        raise ValueError("Experiment identity does not match its digest")
    ExperimentBudget.model_validate(manifest["budget"])
    if check_source:
        _verify_source(manifest["source_sha256"])


def _verify_source(expected: str) -> None:
    if provenance()["source_sha256"] != expected:
        raise ValueError("Source changed since planning; freeze a new experiment manifest")

