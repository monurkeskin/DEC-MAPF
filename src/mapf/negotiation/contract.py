from __future__ import annotations

from mapf.core.models import Contract
from mapf.negotiation.conflict import detect_conflicts


def validate_contract(
    contract: Contract,
    current_time: int = 0,
    disappear_at_target: bool = False,
) -> bool:
    """Validate that the agreed paths in a contract are strictly conflict-free."""
    paired_paths = {
        contract.agent_a: contract.path_a,
        contract.agent_b: contract.path_b,
    }
    conflicts = detect_conflicts(
        paths=paired_paths,
        current_time=current_time,
        lookahead_steps=max(contract.path_a.length, contract.path_b.length),
        disappear_at_target=disappear_at_target,
    )
    return len(conflicts) == 0
