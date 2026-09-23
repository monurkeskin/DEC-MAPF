"""Paired outcome accounting with common-solved cost comparisons."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from mapf.analytics._experiment_cohort import (
    Blocks,
    Trial,
    block_mean,
    interval,
    sampling_unit,
    solved,
)


def _outcome(left: bool, right: bool) -> str:
    return {(True, True): "both_solved", (True, False): "left_only",
            (False, True): "right_only", (False, False): "neither"}[left, right]


def _costs(left: Trial, right: Trial, common: bool) -> dict[str, Any]:
    delta = right["sum_of_costs"] - left["sum_of_costs"] if common else None
    reference = min(left["sum_of_costs"], right["sum_of_costs"]) if common else 0
    return {"delta_right_minus_left": delta,
            "paper_eq2_left": left["sum_of_costs"] / reference - 1 if reference > 0 else None,
            "paper_eq2_right": right["sum_of_costs"] / reference - 1 if reference > 0 else None}


@dataclass
class PairedSamples:
    """One consistent ledger for pair counts, exported rows and clustered deltas."""

    coverage: dict[str, int] = field(default_factory=lambda: {
        "both_solved": 0, "left_only": 0, "right_only": 0, "neither": 0, "unpaired": 0})
    successes: Blocks = field(default_factory=lambda: defaultdict(list))
    costs: Blocks = field(default_factory=lambda: defaultdict(list))
    pairs: list[Trial] = field(default_factory=list)

    @classmethod
    def from_groups(cls, left: dict[str, Trial], right: dict[str, Trial]) -> PairedSamples:
        samples = cls()
        samples.coverage["unpaired"] = len(left.keys() ^ right.keys())
        for key in sorted(left.keys() & right.keys()):
            samples.add(left[key], right[key])
        return samples

    def add(self, left: Trial, right: Trial) -> None:
        unit = sampling_unit(left)
        if unit != sampling_unit(right):
            raise ValueError("Paired trials disagree on independent sampling unit")
        good_left, good_right = solved(left), solved(right)
        self.coverage[_outcome(good_left, good_right)] += 1
        self.successes[unit].append(float(good_right) - float(good_left))
        costs = _costs(left, right, good_left and good_right)
        if costs["delta_right_minus_left"] is not None:
            self.costs[unit].append(float(costs["delta_right_minus_left"]))
        self.pairs.append({"left_trial": left["trial_id"], "right_trial": right["trial_id"],
                           "sampling_unit": unit, "common_solved": good_left and good_right, **costs})

    def summaries(self) -> dict[str, Any]:
        return {"coverage": self.coverage, "pairs": self.pairs,
                "cost": {"mean_delta_right_minus_left": block_mean(self.costs),
                         "interval": interval(self.costs), "independent_units": len(self.costs)},
                "success_difference": {"estimate_right_minus_left": block_mean(self.successes),
                                       "interval": interval(self.successes), "independent_units": len(self.successes)}}
