# Shared domain and physical contracts

`models.py` defines immutable coordinate/path values and explicit configuration. `solution_validator.py` independently checks complete trajectories and prefixes. `space_time_grid.py` implements bounded low-level search with explicit failure reasons; `geometry.py` provides bounded immutable topology/goal caches. `movingai.py` distinguishes imported files from synthetic generators and refuses silent sampling-bound relaxation.

See the [current contract](../../../docs/ALGORITHM.md), the source interfaces and executable tests.
