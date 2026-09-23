"""Opt-in local resource admission. Never changes solver deadlines or kills a job."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from mapf.solvers.registry import solver_metadata

MIB = 1024 * 1024


class ResourcePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    centralized_slots: int = Field(default=2, ge=1, le=6)
    decentralized_slots: int = Field(default=4, ge=1, le=6)
    max_cpu_percent: float = Field(default=90, gt=0, le=100)
    free_memory_mb: int = Field(default=1024, ge=0)
    max_owned_memory_mb: int = Field(default=18432, ge=1)
    optimal_reserve_mb: int = Field(default=10240, ge=1)
    bounded_reserve_mb: int = Field(default=2048, ge=1)
    decentralized_reserve_mb: int = Field(default=256, ge=1)
    idle_timeout_sec: float = Field(default=300, ge=0.1, le=86400)


@dataclass(frozen=True)
class ResourceSnapshot:
    available_bytes: int | None
    cpu_percent: float | None
    rss_bytes: dict[str, int] = field(default_factory=dict)
    error: str | None = None


class ResourceProbe(Protocol):
    def sample(self, processes: dict[str, int]) -> ResourceSnapshot: ...


class SystemResourceProbe:
    """Optional psutil adapter; inaccessible trees are unknown, never zero RAM."""

    def __init__(self) -> None:
        try:
            import psutil  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ValueError("Resource admission requires the resources extra: uv sync --extra resources") from exc
        self.psutil = psutil

    def sample(self, processes: dict[str, int]) -> ResourceSnapshot:
        psutil = self.psutil
        try:
            rss = {job_id: self._tree_rss(pid) for job_id, pid in processes.items()}
            # A short explicit interval avoids psutil's meaningless first
            # nonblocking value when this probe is called by a new thread.
            return ResourceSnapshot(psutil.virtual_memory().available, psutil.cpu_percent(interval=0.05), rss)
        except (psutil.Error, OSError) as exc:
            return ResourceSnapshot(None, None, error=f"{type(exc).__name__}: {exc}")

    def _tree_rss(self, pid: int) -> int:
        try:
            parent = self.psutil.Process(pid)
            tree = [parent, *parent.children(recursive=True)]
        except self.psutil.NoSuchProcess:
            tree = []
        return sum(self._process_rss(process) for process in tree)

    def _process_rss(self, process: Any) -> int:
        try:
            return int(process.memory_info().rss)
        except self.psutil.NoSuchProcess:
            return 0


def resource_kind(job: dict[str, Any]) -> str:
    cfg = job["effective_config"]
    profile = cfg.get("native_profile")
    if profile is not None:
        central = True
        weighted = profile["family"] == "eecbs" and cfg["suboptimality"] > 1
    else:
        meta = solver_metadata(cfg["solver_id"].removeprefix("Decentralized-"))
        central = meta.is_centralized
        weighted = meta.resource_class == "bounded" or (
            meta.supports_suboptimality and cfg["suboptimality"] > 1)
    return "decentralized" if not central else "bounded" if weighted else "optimal"


def _reserve(policy: ResourcePolicy, kind: str) -> int:
    return int(getattr(policy, f"{kind}_reserve_mb")) * MIB


def _family(kind: str) -> str:
    return "decentralized" if kind == "decentralized" else "centralized"


class _AdmissionWindow:
    """Account for running reservations and each selection in one sampled window."""

    def __init__(self, policy: ResourcePolicy, snapshot: ResourceSnapshot,
                 running: list[dict[str, Any]], slots: int) -> None:
        self.policy, self.snapshot, self.slots = policy, snapshot, slots
        self.counts = Counter(_family(resource_kind(job)) for job in running)
        self.experiments = Counter(job.get("experiment_id") for job in running if job.get("experiment_id"))
        rss = snapshot.rss_bytes
        self.reserved = sum(max(_reserve(policy, resource_kind(job)), rss.get(job["job_id"], 0)) for job in running)
        self.growth = sum(max(0, _reserve(policy, resource_kind(job)) - rss.get(job["job_id"], 0)) for job in running)
        self.selected: list[dict[str, Any]] = []
        self.blocked: dict[str, str] = {}

    def consider(self, job: dict[str, Any]) -> None:
        kind = resource_kind(job)
        need = _reserve(self.policy, kind)
        reason = self._reason(job, kind, need)
        if reason is not None:
            self.blocked[job["job_id"]] = reason
            return
        self.selected.append(job)
        self.counts[_family(kind)] += 1
        if job.get("experiment_id"):
            self.experiments[job["experiment_id"]] += 1
        self.reserved += need
        self.growth += need

    def _reason(self, job: dict[str, Any], kind: str, need: int) -> str | None:
        if len(self.selected) >= self.slots:
            return "worker_slots"
        if job.get("experiment_id") and self.experiments[job["experiment_id"]] >= job.get("experiment_worker_limit", 6):
            return "experiment_worker_limit"
        return self._resource_reason(kind, need)

    def _resource_reason(self, kind: str, need: int) -> str | None:
        snapshot = self.snapshot
        if snapshot.error or snapshot.available_bytes is None or snapshot.cpu_percent is None:
            return "resource_telemetry_unavailable"
        family = _family(kind)
        if self.counts[family] >= getattr(self.policy, f"{family}_slots"):
            return f"{family}_slots"
        if snapshot.cpu_percent >= self.policy.max_cpu_percent:
            return "cpu_pressure"
        return self._memory_reason(snapshot.available_bytes, need)

    def _memory_reason(self, available: int, need: int) -> str | None:
        if available - self.growth - need < self.policy.free_memory_mb * MIB:
            return "free_memory"
        if self.reserved + need > self.policy.max_owned_memory_mb * MIB:
            return "owned_memory_reservation"
        return None


class ResourceAdmission:
    """Pure admission decisions over one sampled snapshot; cheap to test independently."""

    def __init__(self, policy: ResourcePolicy, probe: ResourceProbe | None = None) -> None:
        self.policy = policy
        self.probe = probe if probe is not None else SystemResourceProbe()
        self.latest: dict[str, Any] = {}
        self.blocked_since: float | None = None
        self._sampled_at = float("-inf")
        self._sampled_utc: float | None = None
        self._snapshot = ResourceSnapshot(None, None, error="not sampled")

    def reserve(self, kind: str) -> int:
        return _reserve(self.policy, kind)

    def choose(self, waiting: list[dict[str, Any]], running: list[dict[str, Any]],
               processes: dict[str, int], slots: int, *, now: float | None = None) -> list[dict[str, Any]]:
        now = time.monotonic() if now is None else now
        if now - self._sampled_at >= 1:
            self._snapshot = self.probe.sample(processes)
            self._sampled_at = now
            self._sampled_utc = time.time()
        window = _AdmissionWindow(self.policy, self._snapshot, running, slots)
        for job in waiting:
            window.consider(job)
        selected = window.selected
        if waiting and not running and not selected:
            self.blocked_since = now if self.blocked_since is None else self.blocked_since
        else:
            self.blocked_since = None
        self.latest = {"sampled_at": self._sampled_utc, "policy": self.policy.model_dump(),
                       "observation": asdict(self._snapshot), "admitted": [j["job_id"] for j in selected],
                       "blocked": window.blocked, "scope": "admission estimates; not an OS memory limit or runtime prediction"}
        return selected

    def idle_exhausted(self) -> bool:
        return self.blocked_since is not None and time.monotonic() - self.blocked_since >= self.policy.idle_timeout_sec
