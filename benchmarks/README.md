# Benchmark inputs and software regressions

Use the [headless experiment workflow](../docs/EXPERIMENTS.md) to define and run a study. It freezes inputs and source identity, bounds local processes and resources, preserves attempts, validates trajectories and includes every planned outcome in analysis.

## Included software checks

`suites/regression_core.json` contains 32 synthetic regression instances with checked instance hashes. These are software fixtures, not empirical article results. Run the regression tests with:

```bash
uv run --no-sync pytest tests/test_frozen_regression_suite.py
```

`scripts/qualify_performance.py` exercises a fixed bounded protocol profile for software resource/recording comparisons; `scripts/profile_engineering.py` exercises the default protocol. Neither profile establishes article reproduction. The retired `run_profiling_suite.py` entry point refuses execution and directs callers to supported checks. `scripts/render_modern_assets.py` also refuses to plot its obsolete aggregate schema, which lacks qualified denominators and paired cohorts. Use the saved-workspace export and analysis commands in the [headless guide](../docs/HEADLESS.md).

## Empirical studies

Supply original maps, rosters and a declared sampling population separately. The article's main design uses 100 scenarios at each of 20/40/60/80 agents, four settings, FoV widths 5/7/9, standard commitment, five tokens and five randomized repetitions. The appendix has a distinct 32×32 obstacle-density design. Consult [reproducibility](../REPRODUCIBILITY.md) before constructing a comparison.

The implementation's method choices are documented in [algorithm semantics](../docs/ALGORITHM.md) and [protocol conformance](../docs/TAOP-CONFORMANCE.md). Preserve unsuccessful and time-limited outcomes. A selected subset, synthetic fixture or passing software suite is not the complete published experiment.
