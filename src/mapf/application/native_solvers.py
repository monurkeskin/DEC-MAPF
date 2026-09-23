"""Explicit local executable profiles, frozen into ordinary headless run plans.

Profiles are administrator configuration, never an executable path supplied by an
HTTP job request. Loading a profile does not certify its algorithm or its bound.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mapf.solvers.binary_runner import ExternalBinarySolver


class NativeSolverProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    solver_id: str = Field(pattern=r"^Native-[A-Za-z0-9.-]+$")
    display_name: str = Field(min_length=1)
    family: Literal["eecbs", "cbsh2-rtc"]
    setting: Literal["SETTING_1", "SETTING_2", "SETTING_3", "SETTING_4"]
    executable: str
    binary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    coordinate_order: Literal["xy", "row-col"] = "row-col"
    arguments: tuple[str, ...] = ()
    source_revision: str = Field(min_length=1)
    source_patch_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    qualification_scope: str = "Unqualified external executable; no oracle claim"
    qualification_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def valid_invocation(self) -> NativeSolverProfile:
        if not Path(self.executable).is_absolute():
            raise ValueError("Native executable path must be absolute")
        # The adapter owns flags for the instance, output, cutoff and weight.
        self.create(5.0, 1.0)
        return self

    def verify_binary(self) -> None:
        binary = Path(self.executable)
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise ValueError("Native executable is missing or not executable")
        if hashlib.sha256(binary.read_bytes()).hexdigest() != self.binary_sha256:
            raise ValueError("External binary identity changed")

    def create(self, timeout_sec: float, suboptimality: float) -> ExternalBinarySolver:
        return ExternalBinarySolver(
            self.executable,
            solver_name=self.display_name,
            solver_family=self.family,
            supported_settings=frozenset({self.setting}),
            coordinate_order=self.coordinate_order,
            expected_sha256=self.binary_sha256,
            setting_arguments={self.setting: self.arguments},
            time_limit_sec=timeout_sec,
            suboptimality=suboptimality,
        )


class NativeSolverCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["native-solvers-1"]
    profiles: tuple[NativeSolverProfile, ...]


def native_profiles() -> tuple[NativeSolverProfile, ...]:
    path = os.environ.get("MAPF_NATIVE_SOLVER_CATALOG")
    if not path:
        return ()
    source = Path(path)
    if source.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Native solver catalog exceeds 2 MiB")
    profiles = NativeSolverCatalog.model_validate(
        json.loads(source.read_text())
    ).profiles
    ids = [p.solver_id.lower() for p in profiles]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate native solver profile ID")
    return profiles


def native_profile(solver_id: str) -> NativeSolverProfile | None:
    return next(
        (p for p in native_profiles() if p.solver_id.lower() == solver_id.lower()), None
    )
