# Reproducibility and article comparisons

[Researcher documentation](docs/README.md) · [Headless tutorial](docs/HEADLESS.md) · [Experiment reference](docs/EXPERIMENTS.md)

A reproducible execution needs more than a solver name and seed. Preserve the scenario roster, physical semantics, method identity, resource policy, validation and analysis denominator. The repository's software demonstrations establish current behavior on their declared inputs; they do not by themselves reproduce the published study.

## Freeze the study before running

Keep these together:

| Evidence | Why it matters |
| --- | --- |
| Git revision, working diff and Python source hash | A branch name or algorithm label alone does not identify executed code |
| Python/frontend locks and actual environment receipt | Dependency and platform changes can affect execution |
| Original maps/scenario files, source URLs and checksums | Exact geometry and roster membership cannot be reconstructed from density alone |
| Ordered starts/goals, setting and sampling unit | Coordinate order, goal behavior and correlated source rosters affect identity/analysis |
| Effective solver/protocol/search configuration | Defaults and inactive controls must not hide a treatment difference |
| Native binary/source/patch/qualification receipts, when used | A native name is not proof of the same executable or semantics |
| Process, session, step, worker, wall and disk budgets | Different stopping policies create different experiments |
| All planned trials and complete attempt lineage | Failures, cancellations and missing artifacts belong to the denominator |
| Validation, metric version and cohort/analysis receipt | A returned result is not automatically an eligible scientific observation |

The manifest records source/lock and configuration identity. The runner rejects changed Python source bytes. Keep an immutable checkout/environment for a running study; make documentation or implementation changes in a separate worktree. Do not overwrite old artifacts when the method or budget changes.

## A bounded smoke check

```bash
uv sync --locked --python 3.12
mkdir -p runs/smoke
uv run --no-sync mapf batch plan examples/headless-smoke.json --output runs/smoke/manifest.json
uv run --no-sync mapf batch run runs/smoke/manifest.json --workspace runs/smoke/workspace
uv run --no-sync mapf batch status --workspace runs/smoke/workspace
```

This checks sixteen software conditions on two fixtures. The [negotiation tutorial](examples/negotiation-tutorial.json) similarly checks four HeatMap/PathAware conditions. Neither is a representative article sample. Follow [Headless experiments](docs/HEADLESS.md) to export every planned row and analyze a declared comparison.

## Article-derived inputs

Use the **article as the experimental specification** and archived repositories as supporting source evidence. Main-text and appendix designs are distinct:

| Profile | Input contract | Strategy/commitment defaults |
| --- | --- | --- |
| `main-16` | Empty 16×16 maps; complete 20/40/60/80-agent rosters; recomputed shortest paths in 4–24 actions | HeatMap and PathAware, SC; Settings 1–4; FoV 5/7/9 |
| `appendix-32` | Complete 80-agent rosters on 32×32 maps; no main-map 4–24 distance filter | HeatMap, ZC; Settings 1–4; FoV 5/7/9 |

The following templates only prepare specifications. Replace the explicit file paths with verified local originals and predeclare their membership before observing results:

```bash
mkdir -p runs/article-main
uv run --no-sync mapf batch article-rosters --profile main-16 --map /path/to/verified-16x16.map --scenarios /path/to/roster-20.scen /path/to/roster-40.scen --split held-out --workers 2 --wall-seconds 3600 --output runs/article-main/spec.json
uv run --no-sync mapf batch plan runs/article-main/spec.json --output runs/article-main/manifest.json
```

```bash
mkdir -p runs/article-appendix
uv run --no-sync mapf batch article-rosters --profile appendix-32 --map /path/to/verified-32x32.map --scenarios /path/to/complete-80-agent-roster.scen --split held-out --workers 2 --wall-seconds 3600 --output runs/article-appendix/spec.json
uv run --no-sync mapf batch plan runs/article-appendix/spec.json --output runs/article-appendix/manifest.json
```

Inspect every effective input and the full sampling statement before deciding to execute the manifest. The examples' 3,600-second study wall budget is a bounded template, not a published design claim or a promise that a full article batch fits in an hour. `article-rosters` defaults to a 60-second deadline per bilateral negotiation and no total decentralized process cap; explicit step/search/study guards remain. `--timeout-sec` opts into a whole-trial administrative cap. Native centralized comparisons require their own explicit, supported profile and numeric process budget.

The importer accepts archived empty-map `width,height` headers. Stale scenario dimension columns fail by default. Use `--repair-dimensions-from-map` only for a verified metadata mismatch; each correction is recorded and coordinates/source bytes remain preserved. It recomputes four-connected shortest distances, never treating an old distance column as an action-cost oracle. Invalid full rosters fail rather than being silently shortened or replaced.

The older `article-spec` command constructs **fresh filtered main-map prefixes** from explicit MovingAI scenario files. It selects eligible rows, records exclusions and freezes generated rosters. Such a selection can define a new article-configured study, but is not exact import of historical complete rosters. Do not label it `article-rosters`, reuse a main-map filter for the appendix, or infer the paper's entire scenario population from one Java branch.

## Compare under explicit assumptions

The modern implementation includes declared protocol, commitment, scheduling, search and native-source corrections. [TAOP conformance](docs/TAOP-CONFORMANCE.md), [algorithm semantics](docs/ALGORITHM.md) and [native baseline reconstruction](docs/NATIVE-BASELINES.md) document these boundaries. A corrected native comparator is not a byte-identical historical executable. A longer timeout or changed tie behavior is a design difference that must accompany a numerical comparison.

The built-in policies and scheduler are deterministic for fixed inputs. Repeating a seed is not the same as five independently stochastic Java executions. Declare development/held-out file membership and the independent scenario unit. Treat nested roster sizes and treatments from a common scenario as related samples. Report the selection population and limitations of any subsample.

Success uses all planned trials. Costs use common independently valid solved pairs, with their coverage shown. Preserve timeouts and failures when changing budgets; keep a new protocol/configuration under a new experiment identity. Report runtime censoring and environment/load instead of comparing only the fast successful executions. See [Metrics](docs/METRICS.md) and [Scientific interpretation](docs/SCIENCE.md).

Small numerical differences alone neither establish a bug nor certify an acceptable scientific change. Investigate semantic contradictions, illegal trajectories, mismatched metric definitions, unsupported optimality bounds and unaccounted selection first. Claims of improvement, equivalence or significant degradation require the declared matched evidence and uncertainty analysis.

## Archive and share evidence

Stop the workspace's active owner before taking a complete file copy. Preserve `workspace.sqlite3`, its required journal state and the `artifacts/` directory together, plus the external specification/manifest and analysis output. A replay bundle is portable evidence for one run; it is not automatically the entire experiment denominator, database or resumable solver state.

Publish or share only the intended clean evidence package. Keep private raw archives, credentials and unrelated local records out of Git. Use small synthetic fixtures for software tests and the reviewed image provenance for documentation. Empirical dataset publication is separate from the software release.

For supplied CSV/Parquet/XLSX tables, preserve original bytes and missingness. The importer can quarantine a table with an explicit source classification:

```bash
uv run --no-sync mapf batch import-legacy /path/to/historical-results.parquet --source-type historical-empirical --destination runs/legacy-quarantine
```

Importing a table does not recover missing scenario IDs, establish pairing or validate its scientific interpretation. Execute studies through `mapf batch`.

The published reference is [Keskin et al., JAAMAS 38(1), article 10 (2024)](https://doi.org/10.1007/s10458-024-09639-8). Keep published results, current measured runs, historical aggregates and synthetic demonstrations clearly identified. Stable citation keys remain in the [README](README.md#citations) and machine-readable metadata.
