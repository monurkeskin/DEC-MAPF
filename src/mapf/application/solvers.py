"""UI descriptors and construction share the authoritative solver registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.native_solvers import (
    NativeSolverProfile,
    native_profile,
    native_profiles,
)
from mapf.solvers.base import MAPFSolverProtocol
from mapf.solvers.registry import create_from_inputs, list_solvers, solver_metadata

ALGORITHM_VERSION = "dec-mapf-token-concession"

def process_timeout_limit(is_centralized: bool) -> float:
    """Local per-attempt bounds, independent of the batch wall budget."""
    return 600.0


@dataclass(frozen=True)
class ParameterDescriptor:
    name: str
    display_name: str
    param_type: str
    default: Any
    description: str
    options: list[str] | None = None
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None


_PARAMETER_LABELS = {
    "fov_size": ("FoV square width (cells)", "Odd spatial width; temporal horizons are separate.", 2),
    "initial_tokens": ("Initial tokens per agent", "Nonnegative integer endowment", 1),
    "commitment_type": ("Commitment policy", "SC: Standard; DC: Dynamic; ZC: Zero", None),
    "timeout_sec": ("Timeout (seconds)", "Whole process wall budget including startup; nullable only for decentralized jobs.", 0.1),
    "max_astar_expansions": ("Search expansion limit", "Per low-level search; exhaustion does not prove infeasibility.", 100),
    "negotiation_deadline_sec": ("Negotiation deadline (seconds)", "One wall-clock budget per bilateral session; never renewed by an offer.", 0.1),
    "heat_recording_limit": ("Local heat value budget", "Sparse values per full-trace run; exhaustion is explicitly recorded.", 1),
    "broadcast_horizon": ("Broadcast horizon (states)", "Blank follows FoV width; includes current position.", 1),
    "negotiation_horizon": ("Negotiation horizon (states)", "Blank follows FoV width; includes current position.", 1),
    "negotiation_round_limit": ("Negotiation round limit", "Diagnostic checkpoint in taop-v2; hard offer cap in the alternative protocol modes.", 1),
    "verification_pass_limit": ("Negotiation passes per tick", "Bounded repeated conflict verification.", 1),
    "negotiation_protocol": ("Negotiation protocol", "Explicit protocol identity; legacy modes are separate methods.", None),
    "suboptimality": ("Focal weight", "Simplified focal CBS weight; not a verified EECBS bound.", 0.1),
}


def parameter_descriptor(name: str) -> ParameterDescriptor:
    """Defaults, bounds and choices come from the same schema used to validate jobs."""
    raw = JobSubmissionRequest.model_json_schema()["properties"][name]
    schema = next((item for item in raw.get("anyOf", []) if item.get("type") != "null"), raw)
    label, description, step = _PARAMETER_LABELS[name]
    kind = "select" if "enum" in schema else {"integer": "int", "number": "float"}.get(schema.get("type"), "str")
    return ParameterDescriptor(name, label, kind, raw.get("default"), description,
        options=schema.get("enum"), min_value=schema.get("minimum"),
        max_value=schema.get("maximum"), step=step)


@dataclass(frozen=True)
class SolverCapability:
    solver_id: str
    display_name: str
    category: str
    is_centralized: bool
    supports_fov: bool
    supports_commitments: bool
    supports_tokens: bool
    supports_time_limit: bool
    supports_suboptimality: bool
    description: str
    parameters: list[ParameterDescriptor] = field(default_factory=list)
    algorithm_version: str = ALGORITHM_VERSION
    scientific_scope: str = (
        "Modern implementation; no historical numerical-equivalence claim"
    )


class SolverRegistry:
    @staticmethod
    def canonical_id(solver_id: str) -> str:
        profile = native_profile(solver_id)
        if profile is not None:
            return profile.solver_id
        name = solver_id.removeprefix("Decentralized-")
        for registered in list_solvers():
            if name.lower() == registered.lower():
                return registered
        raise ValueError(f"Unsupported solver: {solver_id}")

    @staticmethod
    def list_capabilities() -> list[SolverCapability]:
        result = []
        for name, meta in list_solvers().items():
            central = meta["is_centralized"]
            solver_id = name if central else f"Decentralized-{name}"
            metadata = solver_metadata(name)
            names = ["timeout_sec", "max_astar_expansions"]
            if not central:
                names = ["fov_size", "initial_tokens", "commitment_type"] + names + [
                    "negotiation_deadline_sec", "heat_recording_limit", "broadcast_horizon",
                    "negotiation_horizon", "negotiation_round_limit", "verification_pass_limit",
                    "negotiation_protocol",
                ]
            if metadata.supports_suboptimality:
                names.append("suboptimality")
            params = [parameter_descriptor(key) for key in names]
            display = metadata.display_name or name
            result.append(
                SolverCapability(
                    solver_id,
                    display,
                    "centralized" if central else "decentralized",
                    central,
                    not central,
                    not central,
                    not central,
                    True,
                    metadata.supports_suboptimality,
                    metadata.description,
                    params,
                )
            )
        for profile in native_profiles():
            result.append(SolverCapability(profile.solver_id, profile.display_name,
                "centralized", True, False, False, False, True, profile.family == "eecbs",
                f"Pinned native {profile.family} executable; {profile.setting}",
                scientific_scope=profile.qualification_scope))
        return result

    @staticmethod
    def get_capability(solver_id: str) -> SolverCapability | None:
        try:
            name = SolverRegistry.canonical_id(solver_id)
        except ValueError:
            return None
        return next(
            c
            for c in SolverRegistry.list_capabilities()
            if c.solver_id.removeprefix("Decentralized-") == name
        )

    @staticmethod
    def create_solver(
        solver_id: str, timeout_sec: float = 5.0, suboptimality: float = 1.1,
        *, frozen_native_profile: dict[str, Any] | None = None,
    ) -> MAPFSolverProtocol:
        if frozen_native_profile is not None:
            profile = NativeSolverProfile.model_validate(frozen_native_profile)
            if profile.solver_id != solver_id:
                raise ValueError("Frozen profile does not match the requested solver")
            profile.verify_binary()
            return profile.create(timeout_sec, suboptimality)
        if solver_id.startswith("Native-"):
            raise ValueError("Native solver execution requires a frozen profile in the run plan")
        name = SolverRegistry.canonical_id(solver_id)
        return create_from_inputs(name, {"timeout_sec": timeout_sec, "suboptimality": suboptimality})
