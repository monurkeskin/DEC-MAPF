"""Response contracts used by OpenAPI and the generated TypeScript client."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mapf.application.contracts import (
    FrameSnapshot,
    ScenarioValidateRequest,
    SettingName,
    SolverRunResult,
)
from mapf.application.semantics import ProblemSemantics


class ExtensibleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

class ScenarioSummary(ExtensibleResponse):
    scenario_id: str
    name: str
    agent_count: int
    grid_width: int
    grid_height: int
    description: str

class ScenarioDetail(ScenarioValidateRequest):
    model_config = ConfigDict(extra="allow")
    instance_hash: str
    agent_order: list[str]
    scenario_id: str | None = None
    description: str | None = None

class RunSummary(ExtensibleResponse):
    run_id: str
    instance_hash: str
    solver_name: str
    setting: str
    agent_count: int
    grid_width: int
    grid_height: int
    success: bool
    is_valid: bool
    validation_status: str
    makespan: int
    sum_of_costs: int
    runtime_ms: float
    frame_count: int
    timestamp: float
    pinned: bool = False

class RunPage(BaseModel):
    items: list[RunSummary]
    total: int
    next_cursor: str | None
    solver_names: list[str]
    validation_statuses: list[str]


class EffectiveConfig(ExtensibleResponse):
    solver_id: str
    setting: SettingName
    max_steps: int
    timeout_sec: float | None
    negotiation_deadline_sec: float | None = None
    fov_size: int
    initial_tokens: int
    commitment_type: Literal["SC", "DC", "ZC"]
    random_seed: int
    recording_level: Literal["metrics-only", "events", "full-trace"]
    heat_recording_limit: int = 250000
    suboptimality: float
    agent_order: list[str]
    negotiation_round_limit: int
    verification_pass_limit: int
    max_astar_expansions: int
    broadcast_horizon: int | None = None
    negotiation_horizon: int | None = None
    negotiation_protocol: Literal["taop-v2", "taop-v1", "legacy-alternating-v1"] = "legacy-alternating-v1"

class RunMetadata(RunSummary):
    instance: ScenarioDetail
    effective_config: EffectiveConfig
    provenance: dict[str, Any]
    trace: dict[str, Any]
    attempt_id: str
    definition_digest: str
    timings: dict[str, float]
    execution_status: str
    solver_outcome: str

class RunDetail(ExtensibleResponse):
    schema_version: str
    metadata: RunMetadata
    result: SolverRunResult
    frames: list[FrameSnapshot]

class FrameSlice(BaseModel):
    run_id: str
    offset: int
    total: int
    frames: list[FrameSnapshot]

class PlanEntry(ExtensibleResponse):
    scenario: ScenarioDetail
    effective_config: EffectiveConfig
    inactive_parameters: list[str]
    definition_digest: str
    warnings: list[str]
    semantics: ProblemSemantics | None = None

class PlanResponse(ExtensibleResponse):
    plans: list[PlanEntry]
    count: int
    plan_digest: str
    maximum_process_seconds: float | None
    inference_scope: str

class ExperimentStart(BaseModel):
    manifest: dict[str, Any]
    resume: bool = False
    retry_failed: bool = False

class AnalysisRequest(BaseModel):
    expected_cohort_sha256: str | None = None
    left: str
    right: str
    filters: dict[str, list[Any]] = Field(default_factory=dict)

class MethodSummary(BaseModel):
    planned: int
    solved: int
    success_rate: float | None
    scenario_weighted_success_rate: float | None
    interval: list[float] | None
    independent_units: int
    outcomes: dict[str, int]
    solved_runtime_ms: list[float]

class AnalysisPair(BaseModel):
    left_trial: str
    right_trial: str
    sampling_unit: str
    common_solved: bool
    delta_right_minus_left: float | None
    paper_eq2_left: float | None
    paper_eq2_right: float | None


class AnalysisResponse(ExtensibleResponse):
    schema_version: str
    left_solver: str
    right_solver: str
    left: MethodSummary
    right: MethodSummary
    coverage: dict[str, int]
    cost: dict[str, Any]
    success_difference: dict[str, Any]
    filters: dict[str, list[Any]]
    included_trial_ids: list[str]
    cohort_sha256: str
    pairs: list[AnalysisPair]
    method: str
    scope: str
    runtime_policy: str
    paper_eq2_reference: str
