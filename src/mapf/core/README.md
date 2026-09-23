# Shared domain and physical contracts

`models.py` defines immutable coordinate/path values and explicit configuration. `solution_validator.py` independently checks complete trajectories and prefixes. `space_time_grid.py` is the low-level search boundary; `_space_time_search.py` owns one search's frontier, reservations and stopping receipt. `geometry.py` provides bounded immutable topology/goal caches.

`movingai.py` owns strict map/scenario parsing and typed source rows. `sampling.py` owns seeded synthetic generation without relaxing sampling bounds; its generators remain importable from `movingai.py` for compatibility. See [input conventions](../../../docs/SCENARIOS.md#movingai-import) and the [code reading guide](../../../docs/CODE-GUIDE.md).

See [search and physical semantics](../../../docs/ALGORITHM.md).
