"""Request, replay and event models shared by the application and HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from mapf.core.heat import DecisionHeatRecord


class SimulationRequest(BaseModel):
    """Specification for single or comparative simulation runs."""

    grid_width: int = Field(default=16, ge=4, le=64)
    grid_height: int = Field(default=16, ge=4, le=64)
    agent_count: int = Field(default=10, ge=2, le=100)
    solver: str = Field(
        default="PathAware",
        pattern="^(EECBS-1.1|EECBS-1.0|CBS|Prioritized|PathAware|HeatMap|Greedy|Conceder)$",
    )
    compare_solver: str | None = Field(
        default=None,
        pattern="^(EECBS-1.1|EECBS-1.0|CBS|Prioritized|PathAware|HeatMap|Greedy|Conceder)$",
    )
    commitment_type: Literal["SC", "DC", "ZC"] = "SC"
    compare_commitment_type: Literal["SC", "DC", "ZC"] | None = None
    fov_size: int = Field(default=5, ge=3, le=15)
    obstacle_density: float = Field(default=0.0, ge=0.0, le=0.4)
    setting: int = Field(default=4, ge=1, le=4)
    initial_tokens: int = Field(default=5, ge=0, le=50)
    max_steps: int = Field(default=100, ge=10, le=300)
    timeout_sec: float = Field(default=60.0, ge=1.0, le=600.0)
    random_seed: int = Field(default=42)


Coordinate = tuple[StrictInt, StrictInt]


class Point2D(BaseModel):
    x: int
    y: int


class ConflictRecord(BaseModel):
    a: str
    b: str
    time: int
    type: str
    location: list[int] | None = None


class ContractRecord(BaseModel):
    agent_a: str
    agent_b: str
    location: list[int] | None = None
    time: int
    details: dict[str, Any] = Field(default_factory=dict)


class DeliveredMessage(BaseModel):
    event_type: Literal["MESSAGE"] = "MESSAGE"
    sender: str
    recipient: str
    tick: int
    points: list[Coordinate]
    kind: Literal["BROADCAST", "OFFER"]
    session_id: str | None = None
    acknowledgement: int = 0
    payload_bytes: int


class LocalObservation(BaseModel):
    agent_id: str
    tick: int
    position: Coordinate
    obstacles: list[Coordinate]
    messages: list[DeliveredMessage]
    # None means the recording predates obstacle-memory capture, not an empty memory.
    remembered_obstacles: list[Coordinate] | None = None


class FrameSnapshot(BaseModel):
    """Serializable replay state at tick t, starting with the initial state at t=0.

    This transport model is mutable; persisted run artifacts are stored separately.
    """

    tick: int
    active_agents: int
    solved_agents: int
    positions: dict[str, list[int]]
    targets: dict[str, list[int]]
    statuses: dict[
        str,
        Literal["active", "reached", "parked", "disappeared", "deadlocked", "collided"],
    ]
    tokens: dict[str, int]
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    contracts: list[ContractRecord] = Field(default_factory=list)
    heat_grid: dict[str, float] = Field(default_factory=dict)
    phase: Literal["initial", "post_move"] = "initial"
    telemetry_available: bool = False
    heat_provenance: str = "hindsight: executed future occupancy; not agent knowledge"
    planned_paths: dict[str, list[Coordinate]] = Field(default_factory=dict)
    commitments: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    local_observations: dict[str, LocalObservation] | None = None
    local_heat: list[DecisionHeatRecord] = Field(default_factory=list)
    local_heat_omitted: int = Field(default=0, ge=0)
    is_unsolvable: bool = False


class ValidationReceipt(BaseModel):
    version: Literal["trajectory-v2"] = "trajectory-v2"
    status: Literal["valid_solution", "valid_prefix", "invalid", "not_checked"]
    is_valid: bool
    prefix_valid: bool
    errors: list[dict[str, Any]] = Field(default_factory=list)
    first_violation_tick: int | None = None


class SolverRunResult(BaseModel):
    """Complete execution record and replay payload for a single solver branch."""

    solver: str
    solver_key: str
    is_centralized: bool
    status: Literal["solved", "failed", "truncated", "invalid"]
    solver_outcome: Literal["solved", "not_solved"] = "not_solved"
    validation: ValidationReceipt | None = None
    metric_availability: dict[str, bool] = Field(default_factory=dict)
    reported_makespan: int | None = None
    reported_sum_of_costs: int | None = None
    telemetry_events: list[dict[str, Any]] = Field(default_factory=list)
    success: bool
    solved_count: int
    total_agents: int
    makespan: int
    sum_of_costs: int = 0
    runtime_ms: float
    negotiation_count: int = 0
    successful_negotiations: int = 0
    information_sharing_rate: float = 0.0
    norm_path_diff: float = 0.0
    instance_hash: str
    run_id: str
    paths: dict[str, list[Point2D]]
    frames: list[FrameSnapshot]
    measured_metrics: dict[str, Any] = Field(default_factory=dict)


class SimulationResponse(BaseModel):
    """Unified API response for simulation replay and comparison."""

    instance_hash: str
    run_id: str
    random_seed: int
    grid_width: int
    grid_height: int
    setting: int
    disappear_at_target: bool
    obstacles: list[Point2D]
    starts: list[Point2D]
    goals: list[Point2D]
    primary: SolverRunResult
    comparison: SolverRunResult | None = None

    # Top-level convenience mirrors for primary run
    solver: str
    is_centralized: bool
    status: str
    success: bool
    solved_count: int
    total_agents: int
    total_steps: int
    makespan: int
    runtime_ms: float
    negotiation_count: int
    successful_negotiations: int
    information_sharing_rate: float
    norm_path_diff: float
    paths: dict[str, list[Point2D]]
    frames: list[FrameSnapshot]


class BatchBenchmarkRequest(BaseModel):
    suite_name: Literal[
        "quick_test", "appendix_32x32", "commitment_types", "main_matrix"
    ] = "quick_test"


class SSEEventModel(BaseModel):
    """Standardized Server-Sent Event model."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int
    type: Literal["run_completed", "suite_finished", "error", "heartbeat"]
    task_id: str
    data: dict[str, Any] = Field(default_factory=dict)


SettingName = Literal["SETTING_1", "SETTING_2", "SETTING_3", "SETTING_4"]
ExecutionState = Literal[
    "pending", "running", "completed", "failed", "cancelled", "timed_out", "interrupted"
]


class ScenarioValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grid_width: int = Field(default=8, ge=1, le=64)
    grid_height: int = Field(default=8, ge=1, le=64)
    obstacles: list[Coordinate] = Field(default_factory=list, max_length=4096)
    starts: dict[str, Coordinate] = Field(default_factory=dict, max_length=100)
    goals: dict[str, Coordinate] = Field(default_factory=dict, max_length=100)
    setting: SettingName = "SETTING_1"
    name: str = Field(default="Custom scenario", max_length=160)


class JobSubmissionRequest(ScenarioValidateRequest):
    solver_id: str = "Decentralized-HeatMap"
    scenario_id: str | None = Field(default=None, max_length=100)
    max_steps: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Explicit simulation step guard; interactive form caps at 500, research batches permit 10000",
    )
    timeout_sec: float | None = Field(
        default=5.0,
        ge=0.1,
        le=600.0,
        description="Optional whole-process safety budget; null removes this cap for decentralized jobs only",
    )
    negotiation_deadline_sec: float = Field(
        default=60.0,
        ge=0.01,
        le=600.0,
        description="Wall seconds for each bilateral negotiation; resets per session, not per offer",
    )
    fov_size: int = Field(default=3, ge=3, le=15)
    broadcast_horizon: int | None = Field(default=None, ge=1, le=100)
    negotiation_horizon: int | None = Field(default=None, ge=1, le=100)
    negotiation_protocol: Literal["taop-v2", "taop-v1", "legacy-alternating-v1"] = (
        "taop-v2"
    )
    negotiation_round_limit: int = Field(default=30, ge=1, le=500)
    verification_pass_limit: int = Field(default=5, ge=1, le=20)
    max_astar_expansions: int = Field(default=1500, ge=100, le=100000)
    initial_tokens: int = Field(default=10, ge=0, le=100)
    commitment_type: Literal["SC", "DC", "ZC"] = "SC"
    random_seed: int = Field(default=42, ge=0, le=2**32 - 1)
    recording_level: Literal["metrics-only", "events", "full-trace"] = "full-trace"
    heat_recording_limit: int = Field(default=250000, ge=0, le=2000000)
    suboptimality: float = Field(default=1.1, ge=1.0, le=3.0)

    @field_validator("fov_size")
    @classmethod
    def odd_width(cls, value: int) -> int:
        if value % 2 == 0:
            raise ValueError("FoV is an odd square width in cells (3, 5, ..., 15)")
        return value


class JobStatusResponse(BaseModel):
    job_id: str
    run_id: str
    attempt_id: str
    definition_digest: str
    solver_id: str
    state: ExecutionState
    created_at: float
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None
    timeout_scope: Literal["process", "negotiation"] | None = None
    timeout_session_id: str | None = None
    timeout_diagnostics: dict[str, Any] | None = None
    solver_diagnostics: dict[str, Any] | None = None
    result: SolverRunResult | None = None
    effective_config: dict[str, Any]
    worker_pid: int | None = None
    parent_job_id: str | None = None
    experiment_id: str | None = None
    trial_id: str | None = None
    attempt_index: int = 0


class ScenarioValidateResponse(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)


class JobEvent(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    sequence: int = Field(ge=1)
    job_id: str
    run_id: str
    attempt_id: str
    type: Literal["status", "done", "diagnostic"]
    timestamp: float
    state: ExecutionState
    message: str | None = None


class MovingAIImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="MovingAI import", max_length=160)
    map_text: str = Field(max_length=100000)
    scenario_text: str = Field(max_length=100000)
    agent_count: int = Field(default=4, ge=1, le=100)
    setting: SettingName = "SETTING_4"


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jobs: list[JobSubmissionRequest] = Field(min_length=1, max_length=32)


class PlanAdmission(PlanRequest):
    plan_digest: str


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: list[str] = Field(min_length=1, max_length=100)
    right: list[str] = Field(min_length=1, max_length=100)
    treatment_keys: list[
        Literal[
            "solver_id",
            "commitment_type",
            "fov_size",
            "initial_tokens",
            "suboptimality",
            "recording_level",
        ]
    ] = Field(default=["solver_id"])
