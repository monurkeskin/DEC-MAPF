# Start a study you can inspect and resume

Create a small, runnable project before replacing its fixtures with your own scientific population. The GUI is optional throughout.

```bash
mapf study init my-study --name "My first study"
python my-study/run.py
python my-study/analyze.py
```

The first command creates a new directory containing `study.json`, `maps/`, `run.py`, `analyze.py`, a README and output exclusions. Existing directories and symlinks are rejected. It does not execute any solver. The starter is four teaching trials, one worker, 120 batch seconds and a 256 MiB workspace allowance. Inspect the explicit per-process deadline before changing it; these are not article defaults.

`run.py` creates `outputs/manifest.json`, executes through the ordinary process supervisor, and writes a summary. A second invocation refuses existing outputs. `analyze.py` opens the workspace read-only and exports all planned rows and `experiment-card.json`. A card records real configuration/source/metric identities and the complete denominator. Pending trials, timeouts and unsolved valid prefixes are not converted into successful solutions. Unmeasured peak memory remains unavailable.

To export a card from any existing experiment:

```bash
mapf study card EXPERIMENT_ID --workspace runs/my-workspace --output experiment-card.json
```

Use the actual ID printed by planning/status. For interrupted work, use `mapf batch resume EXPERIMENT_ID --workspace my-study/outputs/workspace`; it creates explicit attempts and preserves prior evidence. Inspect the recorded state before deciding whether a failed trial should be retried.

Next: [replace the fixtures with your maps](SCENARIOS.md), declare the sampling unit, then follow [the headless workflow](HEADLESS.md).
