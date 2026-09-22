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
            rss = {}
            for job_id, pid in processes.items():
                total = 0
                try:
                    parent = psutil.Process(pid)
                    tree = [parent, *parent.children(recursive=True)]
                except psutil.NoSuchProcess:
                    tree = []
                for process in tree:
                    try:
                        total += process.memory_info().rss
                    except psutil.NoSuchProcess:
                        continue
                rss[job_id] = total
            # A short explicit interval avoids psutil's meaningless first
            # nonblocking value when this probe is called by a new thread.
            return ResourceSnapshot(psutil.virtual_memory().available, psutil.cpu_percent(interval=0.05), rss)
        except (psutil.Error, OSError) as exc:
            return ResourceSnapshot(None, None, error=f"{type(exc).__name__}: {exc}")


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
        return int(getattr(self.policy, f"{kind}_reserve_mb")) * MIB

    def choose(self, waiting: list[dict[str, Any]], running: list[dict[str, Any]],
               processes: dict[str, int], slots: int, *, now: float | None = None) -> list[dict[str, Any]]:
        now = time.monotonic() if now is None else now
        if now - self._sampled_at >= 1:
            self._snapshot = self.probe.sample(processes)
            self._sampled_at = now
            self._sampled_utc = time.time()
        snapshot, policy = self._snapshot, self.policy
        counts = Counter("decentralized" if resource_kind(j) == "decentralized" else "centralized" for j in running)
        experiments = Counter(j.get("experiment_id") for j in running if j.get("experiment_id"))
        rss = snapshot.rss_bytes
        reserved = sum(max(self.reserve(resource_kind(j)), rss.get(j["job_id"], 0)) for j in running)
        growth = sum(max(0, self.reserve(resource_kind(j)) - rss.get(j["job_id"], 0)) for j in running)
        selected: list[dict[str, Any]] = []
        blocked: dict[str, str] = {}
        for job in waiting:
            kind = resource_kind(job)
            family = "decentralized" if kind == "decentralized" else "centralized"
            need = self.reserve(kind)
            if len(selected) >= slots:
                reason = "worker_slots"
            elif job.get("experiment_id") and experiments[job["experiment_id"]] >= job.get("experiment_worker_limit", 6):
                reason = "experiment_worker_limit"
            elif snapshot.error or snapshot.available_bytes is None or snapshot.cpu_percent is None:
                reason = "resource_telemetry_unavailable"
            elif counts[family] >= getattr(policy, f"{family}_slots"):
                reason = f"{family}_slots"
            elif snapshot.cpu_percent >= policy.max_cpu_percent:
                reason = "cpu_pressure"
            elif snapshot.available_bytes - growth - need < policy.free_memory_mb * MIB:
                reason = "free_memory"
            elif reserved + need > policy.max_owned_memory_mb * MIB:
                reason = "owned_memory_reservation"
            else:
                selected.append(job)
                counts[family] += 1
                if job.get("experiment_id"):
                    experiments[job["experiment_id"]] += 1
                reserved += need
                growth += need
                continue
            blocked[job["job_id"]] = reason
        if waiting and not running and not selected:
            self.blocked_since = now if self.blocked_since is None else self.blocked_since
        else:
            self.blocked_since = None
        self.latest = {"sampled_at": self._sampled_utc, "policy": policy.model_dump(),
                       "observation": asdict(snapshot), "admitted": [j["job_id"] for j in selected],
                       "blocked": blocked, "scope": "admission estimates; not an OS memory limit or runtime prediction"}
        return selected

    def idle_exhausted(self) -> bool:
        return self.blocked_since is not None and time.monotonic() - self.blocked_since >= self.policy.idle_timeout_sec
