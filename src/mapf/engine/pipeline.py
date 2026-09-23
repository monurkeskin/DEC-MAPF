"""Ordered five-stage MAPF ticks with explicit perception, negotiation and movement."""

from __future__ import annotations

from mapf.engine._movement_stage import MovementStage
from mapf.engine._negotiation_stage import NegotiationStage
from mapf.engine._perception_stage import ConflictDetectionStage, PreUpdateStage
from mapf.engine._pipeline_context import PipelineContext, SimulationStage
from mapf.engine._post_update_stage import PostUpdateStage

# Keep the established stage import paths available to clients and custom pipelines.
__all__ = [
    "ConflictDetectionStage",
    "MovementStage",
    "NegotiationStage",
    "PipelineContext",
    "PostUpdateStage",
    "PreUpdateStage",
    "SimulationPipeline",
    "SimulationStage",
]


class SimulationPipeline:
    """Orchestrates ordered execution of discrete tick pipeline stages."""

    def __init__(self, stages: list[SimulationStage] | None = None) -> None:
        self.stages = stages or [
            PreUpdateStage(),
            ConflictDetectionStage(),
            NegotiationStage(),
            MovementStage(),
            PostUpdateStage(),
        ]

    def step(self, ctx: PipelineContext) -> bool:
        """Run stages in order, stopping when a stage ends the simulation."""
        for stage in self.stages:
            stage.execute(ctx)
            if ctx.is_unsolvable:
                return False
        return ctx.all_done
