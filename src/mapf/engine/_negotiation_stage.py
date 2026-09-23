"""Ordered local matchmaking, contract recording, and negotiation diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mapf.core.models import Conflict, Contract
from mapf.engine._pipeline_context import PipelineContext, active_conflicts
from mapf.telemetry.events import NegotiationSessionEvent


@dataclass(frozen=True, slots=True)
class _SessionReceipt:
    reason: str
    session_id: str
    rounds: int


class NegotiationStage:
    """Run disjoint pairs per snapshot, then verify their revised plans."""

    name = "Negotiation"

    def execute(self, ctx: PipelineContext) -> None:
        if ctx.is_unsolvable or not ctx.active_agents:
            return
        radius = ctx.world.config.fov_size // 2
        for pass_idx in range(ctx.world.config.verification_pass_limit):
            conflicts = self._active_conflicts(ctx, radius)
            if not conflicts:
                break
            # Modern deterministic order; published repetitions randomized partners.
            conflicts.sort(
                key=lambda c: (
                    c.time,
                    min(c.agent_a, c.agent_b),
                    max(c.agent_a, c.agent_b),
                )
            )
            agreed = self._run_pass(ctx, conflicts, pass_idx + 1)
            if ctx.is_unsolvable or not agreed:
                break

    def _run_pass(
        self, ctx: PipelineContext, conflicts: list[Conflict], pass_number: int
    ) -> bool:
        busy: set[str] = set()
        agreed = False
        for conflict in conflicts:
            if conflict.agent_a in busy or conflict.agent_b in busy:
                continue
            contract = ctx.world.negotiator.negotiate(
                agent_a=ctx.world.agents[conflict.agent_a],
                agent_b=ctx.world.agents[conflict.agent_b],
                conflict=conflict,
                env=ctx.world,
                current_time=ctx.current_time,
            )
            # Skip stale pairings involving a plan changed in this snapshot.
            busy.update((conflict.agent_a, conflict.agent_b))
            if contract is not None:
                agreed = True
                self._record_contract(ctx, conflict, contract)
            receipt = self._record_session(ctx, conflict, contract)
            if receipt.reason == "NEGOTIATION_DEADLINE":
                self._stop(
                    ctx,
                    "negotiation_deadline",
                    {
                        "session_id": receipt.session_id,
                        "rounds": receipt.rounds,
                        "pass": pass_number,
                        "diagnostics": getattr(
                            ctx.world.negotiator, "last_diagnostics", {}
                        ),
                    },
                )
                break
        return agreed

    @staticmethod
    def _record_contract(
        ctx: PipelineContext, conflict: Conflict, contract: Contract
    ) -> None:
        ctx.signed_contracts.append(
            {
                "time": ctx.current_time,
                "agent_a": conflict.agent_a,
                "agent_b": conflict.agent_b,
                "location": [conflict.location_a.x, conflict.location_a.y],
                "details": _contract_details(ctx, conflict, contract),
            }
        )

    @staticmethod
    def _record_session(
        ctx: PipelineContext,
        conflict: Conflict,
        contract: Contract | None,
    ) -> _SessionReceipt:
        negotiator = ctx.world.negotiator
        ctx.world.record_negotiation(
            {
                "time": ctx.current_time,
                "agent_a": conflict.agent_a,
                "agent_b": conflict.agent_b,
                "success": contract is not None,
                "location": conflict.location_a,
                "wall_seconds": getattr(negotiator, "last_session_duration_sec", None),
                "deadline_seconds": ctx.world.config.negotiation_deadline_sec,
            }
        )
        reason = getattr(negotiator, "last_session_reason", "NONE")
        ctx.world.record_negotiation_outcome(reason)
        session_id = getattr(negotiator, "last_session_id", "") or (
            contract.session_id
            if contract is not None
            else f"nego-{ctx.current_time}-{conflict.agent_a}-{conflict.agent_b}"
        )
        receipt = _SessionReceipt(
            reason, session_id, getattr(negotiator, "last_session_rounds", 1)
        )
        _emit_session(ctx, conflict, contract, receipt)
        return receipt

    @staticmethod
    def _stop(ctx: PipelineContext, reason: str, detail: dict[str, Any]) -> None:
        ctx.is_unsolvable = True
        ctx.world.stop_negotiation(reason, detail)

    @staticmethod
    def _active_conflicts(ctx: PipelineContext, radius: int) -> list[Conflict]:
        return active_conflicts(ctx, radius)


def _contract_details(
    ctx: PipelineContext, conflict: Conflict, contract: Contract
) -> dict[str, Any]:
    allocated = contract.allocated_path
    return {
        "session_id": contract.session_id,
        "token_transfer_a_to_b": contract.token_transfer,
        "accepted_by": contract.accepted_by,
        "protocol_version": contract.protocol_version,
        "allocated_path": [[p.x, p.y] for p in allocated.points]
        if allocated is not None
        else None,
        "conflict_end_tick": contract.conflict_tick,
        "token_usage": contract.token_usage,
        "settlement": getattr(ctx.world.negotiator, "last_settlement", None),
        "path_a": [[p.x, p.y] for p in contract.path_a.points],
        "path_b": [[p.x, p.y] for p in contract.path_b.points],
        "absolute_start_tick": ctx.current_time,
        "reservations_a": ctx.world.agents[conflict.agent_a]
        .get_state()
        .metadata.get("commitments", []),
        "reservations_b": ctx.world.agents[conflict.agent_b]
        .get_state()
        .metadata.get("commitments", []),
    }


def _emit_session(
    ctx: PipelineContext,
    conflict: Conflict,
    contract: Contract | None,
    receipt: _SessionReceipt,
) -> None:
    ctx.world.telemetry_hook.on_negotiation_end(
        NegotiationSessionEvent(
            session_id=receipt.session_id,
            tick=ctx.current_time,
            initiator_id=conflict.agent_a,
            opponent_id=conflict.agent_b,
            conflict_x=conflict.location_a.x,
            conflict_y=conflict.location_a.y,
            total_rounds=receipt.rounds,
            outcome="AGREED" if contract is not None else "FAILED",
            tokens_transferred=abs(contract.token_transfer)
            if contract is not None
            else 0,
            reject_reason=receipt.reason,
        )
    )
