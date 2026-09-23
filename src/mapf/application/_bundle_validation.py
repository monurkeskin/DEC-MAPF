"""Check imported evidence independently before publishing it to a workspace."""

import json
from dataclasses import dataclass
from typing import Any

from mapf.application._replay_assessment import SolutionAssessment, assess_solution
from mapf.application._replay_frames import ReplayTimeline, TimelineSettings
from mapf.application.contracts import SolverRunResult
from mapf.application.plans import instance_from_snapshot
from mapf.application.runs import digest
from mapf.application.scenarios import ScenarioService
from mapf.core.hashing import compute_instance_hash
from mapf.core.models import Path, Point, SimulationSetting
from mapf.metrics.costs import trajectory_costs
from mapf.solvers.base import MAPFInstance, MAPFSolution


def _copy_checked_envelope(bundle: dict[str, Any]) -> dict[str, Any]:
    if bundle.get("format") != "decmapf-run" or bundle.get("version") != "1.0":
        raise ValueError("Unsupported bundle format/version; legacy archives require the quarantine importer")
    payload = bundle.get("payload")
    if not isinstance(payload, dict) or digest(payload) != bundle.get("sha256"):
        raise ValueError("Bundle checksum mismatch")
    return dict(json.loads(json.dumps(payload)))


@dataclass
class _BundleEvidence:
    payload: dict[str, Any]
    result: SolverRunResult
    instance: MAPFInstance
    setting: SimulationSetting

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self.payload["metadata"])

    def solution(self) -> MAPFSolution:
        return MAPFSolution(
            solver_name=self.result.solver, is_centralized=self.result.is_centralized,
            success=self.result.success, makespan=self.result.makespan,
            paths={aid: Path(points=[Point(p.x, p.y) for p in points])
                   for aid, points in self.result.paths.items()},
            metrics={"solver_reported_success": self.result.solver_outcome == "solved"},
        )

    def verify(self) -> None:
        errors = ScenarioService.validate_instance(self.instance, self.setting)
        if errors:
            raise ValueError("Invalid bundle scenario: " + "; ".join(errors))
        solution = self.solution()
        assessment = assess_solution(self.instance, solution, self.setting,
                                     self.metadata["effective_config"]["max_steps"])
        self._candidate(assessment)
        self._timeline(solution, assessment)
        self._costs(solution)
        self._identity()
        self._metadata(assessment)
        self._definition()

    def _candidate(self, assessment: SolutionAssessment) -> None:
        self._receipt(assessment)
        self._outcome(assessment)
        if self.result.solved_count != assessment.solved_count:
            raise ValueError("Bundle goal-arrival count disagrees with its paths")
        if self.result.total_agents != len(self.instance.starts):
            raise ValueError("Bundle agent count disagrees with its scenario")

    def _receipt(self, assessment: SolutionAssessment) -> None:
        receipt = self.result.validation
        if receipt is None or receipt.is_valid != assessment.receipt.is_valid:
            raise ValueError("Bundle independent-validation receipt does not match its paths")
        if digest(receipt.model_dump(mode="json")) != digest(assessment.receipt.model_dump(mode="json")):
            raise ValueError("Bundle validation receipt does not match independently recomputed evidence")

    def _outcome(self, assessment: SolutionAssessment) -> None:
        if self.result.success != (self.result.status == "solved"):
            raise ValueError("Bundle success and solution status disagree")
        if self.result.success and not assessment.success:
            raise ValueError("Invalid paths cannot be a successful run")
        if (self.result.status == "invalid") != (assessment.status == "invalid"):
            raise ValueError("Bundle invalidity status disagrees with its paths")

    def _replay_length(self) -> None:
        frames, paths = self.result.frames, self.result.paths
        if len(frames) > 501 or len(paths) > 100:
            raise ValueError("Bundle exceeds supported replay limits")
        if self.metadata.get("frame_count") != len(frames):
            raise ValueError("Bundle declared frame count disagrees with recorded replay")
        self._recording_length()

    def _recording_length(self) -> None:
        frames, paths = self.result.frames, self.result.paths
        reduced = self.metadata["effective_config"].get("recording_level") == "metrics-only"
        if reduced:
            if frames:
                raise ValueError("Metrics-only bundle unexpectedly contains replay frames")
            return
        expected = max((len(p) - 1 for p in paths.values()), default=0) + 1
        if len(frames) != expected:
            raise ValueError("Bundle replay length does not match its recorded paths")

    def _timeline(self, solution: MAPFSolution, assessment: SolutionAssessment) -> None:
        if self.payload.get("frames") != self.payload["result"]["frames"]:
            raise ValueError("Bundle frame representations disagree")
        self._replay_length()
        settings = TimelineSettings(self.setting, self.metadata["effective_config"]["fov_size"], 0, True)
        timeline = ReplayTimeline(self.instance, solution, assessment, settings)
        trajectory_fields = {"tick", "positions", "targets", "statuses", "active_agents",
                             "solved_agents", "phase", "heat_grid"}
        for tick, frame in enumerate(self.result.frames):
            expected = timeline.frame(tick).model_dump(mode="json", include=trajectory_fields)
            actual = frame.model_dump(mode="json", include=trajectory_fields)
            if actual != expected:
                raise ValueError("Bundle replay timeline, lifecycle or hindsight heat disagrees with its paths")

    def _costs(self, solution: MAPFSolution) -> None:
        costs = trajectory_costs(self.instance, solution.paths)
        expected_soc = costs["recorded_action_count"]
        expected_makespan = max((len(p) - 1 for p in self.result.paths.values()), default=0)
        if self.result.success:
            expected_soc = costs["action_sum_of_costs"]
            expected_makespan = costs["action_makespan"]
        if self.result.makespan != expected_makespan or self.result.sum_of_costs != expected_soc:
            raise ValueError("Bundle canonical costs do not match its paths")

    def _identity(self) -> None:
        expected_hash = compute_instance_hash(self.instance, self.setting)
        if self.metadata["instance_hash"] != expected_hash or self.result.instance_hash != expected_hash:
            raise ValueError("Bundle scenario identity mismatch")
        if self.result.run_id != self.metadata["run_id"]:
            raise ValueError("Bundle run identity mismatch")
        if self.result.solver != self.metadata["solver_name"]:
            raise ValueError("Bundle solver identity mismatch")

    def _metadata(self, assessment: SolutionAssessment) -> None:
        for key in ("success", "makespan", "sum_of_costs", "runtime_ms"):
            if self.metadata[key] != getattr(self.result, key):
                raise ValueError(f"Bundle metadata disagrees with result: {key}")
        receipt = assessment.receipt
        if self.metadata["is_valid"] != receipt.is_valid or self.metadata["validation_status"] != receipt.status:
            raise ValueError("Bundle metadata misrepresents validation")

    def _definition(self) -> None:
        meta = self.metadata
        if meta["effective_config"]["setting"] != meta["setting"] or meta["instance"]["setting"] != meta["setting"]:
            raise ValueError("Bundle effective setting mismatch")
        definition = {"instance_hash": meta["instance_hash"], "effective_config": meta["effective_config"],
                      "algorithm_version": meta["provenance"]["algorithm_version"]}
        if meta["definition_digest"] != digest(definition):
            raise ValueError("Bundle effective-input digest mismatch")


def checked_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return an isolated verified copy; malformed external data never mutates storage."""
    payload = _copy_checked_envelope(bundle)
    try:
        evidence = _BundleEvidence(payload, SolverRunResult.model_validate(payload["result"]),
                                   instance_from_snapshot(payload["metadata"]["instance"]),
                                   SimulationSetting[payload["metadata"]["setting"]])
        evidence.verify()
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f"Malformed bundle structure: {exc}") from exc
    return payload
