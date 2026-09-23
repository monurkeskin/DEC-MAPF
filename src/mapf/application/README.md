# Application services shared by Python, CLI and HTTP

Start at `ExperimentService` in `experiments.py` for a complete study.
`experiment_manifest.py` freezes requests and budgets; `ExperimentExecutor`
admits trials through the owning `JobSupervisor`; `ExperimentStore` supplies
persistence without putting SQL into execution policy. `RunRepository` owns the
journal, checked artifacts and explicit attempt lineage.

For a single job, follow `plans.py` → `jobs.py` → `worker.py`. For replay, follow
`replay.py` → `_replay_assessment.py` → `_replay_frames.py`: physical validation
and recorded decisions remain separate from derived visual information.
`movingai.py` applies workspace policy to parsed source rows; `article_suite.py`
distinguishes filtered prefixes from complete ordered rosters. Neither runs a
solver while building inputs.

These services do not import FastAPI or depend on a browser. Use the
[code reading guide](../../../docs/CODE-GUIDE.md), [public boundary](../../../docs/PUBLIC-API.md)
and [experiment workflow](../../../docs/EXPERIMENTS.md) before extending them.
