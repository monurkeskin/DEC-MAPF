"""Historical in-process suite definitions; public admission uses explicit manifests."""

from itertools import product
from typing import Any

from mapf.core.models import CommitmentType, SimulationSetting

_SEEDS = (42, 101, 137, 256)
_SETTINGS = tuple(SimulationSetting)
_BASE = {"map_name": "empty-16-16", "grid_size": 16, "obstacle_density": 0.0,
         "k": 80, "setting": SimulationSetting.SETTING_4, "commitment": CommitmentType.ZERO,
         "strategy": "HeatMap", "fov": 5}
_AXES: dict[str, dict[str, tuple[Any, ...]]] = {
    "quick_test": {"seed": (42, 101), "strategy": ("HeatMap", "PathAware")},
    "appendix_32x32": {
        "map": (("empty-32-32", 0.0), ("random-32-32-10", 0.10), ("random-32-32-20", 0.20)),
        "setting": _SETTINGS, "fov": (5, 7, 9), "seed": _SEEDS},
    "commitment_types": {
        "setting": (SimulationSetting.SETTING_3, SimulationSetting.SETTING_4),
        "commitment": (CommitmentType.STANDARD, CommitmentType.DYNAMIC, CommitmentType.ZERO),
        "fov": (5, 7, 9), "seed": _SEEDS},
    "main_matrix": {"strategy": ("HeatMap", "PathAware"), "setting": _SETTINGS,
                    "k": (20, 40, 60, 80), "seed": _SEEDS},
}


def suite_runs(name: str) -> list[dict[str, Any]]:
    axes = _AXES.get(name, _AXES["main_matrix"])
    defaults = dict(_BASE)
    if name == "quick_test":
        defaults["k"] = 20
    if name == "appendix_32x32":
        defaults["grid_size"] = 32
    return [_definition(defaults, dict(zip(axes, values, strict=True))) for values in product(*axes.values())]


def _definition(defaults: dict[str, Any], selected: dict[str, Any]) -> dict[str, Any]:
    result = {**defaults, **selected}
    if "map" in result:
        result["map_name"], result["obstacle_density"] = result.pop("map")
    return result
