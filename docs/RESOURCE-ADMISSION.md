# Resource-aware local batches

[Headless guide](HEADLESS.md) · [Parameters](PARAMETERS.md) · [Architecture](ARCHITECTURE.md)

Ordinary batches keep their fixed worker limit by default. An explicit
`budget.resources` object enables CPU/RAM admission through the same supervisor,
journal, cancellation and resume machinery. This helps mixed workloads when a
large centralized search would otherwise occupy the available memory. It does
not change a solver's search, process or bilateral-session deadline.

## Run the small example

```bash
uv sync --locked --python 3.12 --extra resources
mkdir -p runs/resource-demo
uv run --no-sync mapf batch plan examples/resource-aware-study.json --output runs/resource-demo/manifest.json
uv run --no-sync mapf batch run runs/resource-demo/manifest.json --workspace runs/resource-demo/workspace
uv run --no-sync mapf batch status --workspace runs/resource-demo/workspace
```

The example has four tiny teaching trials and two worker slots. It is not a
performance benchmark. Keep other extras in your `uv sync` command if you use them.
Fixed-worker core execution does not require psutil; only resource admission does.

For a larger explicitly planned local study, `workers: 6` allows at most six
processes. The default resource policy permits at most two centralized and four
decentralized jobs at once. These are ceilings, not promises that six jobs will
fit. All policy values are recorded in the immutable experiment manifest.

## What is measured and enforced

The probe samples host available RAM, host CPU utilization and each owned
worker's process-tree RSS. Conservative configurable reservations account for
future growth: by default 10 GiB for optimal centralized search, 2 GiB for
bounded/incomplete centralized search and 256 MiB for decentralized work.
Actual RSS above a reservation is also accounted for. These estimates are not
memory allocations, OS-enforced limits or claims about a solver's worst case.

Admission checks the free-memory floor, total owned-memory reservation ceiling,
CPU threshold, family slots and total worker slots. It can skip a waiting heavy
job to start an eligible light job. A bounded mixed-family queue prevents the
first family from hiding all work of the other family. Sampling or process-access
failure blocks new admissions instead of treating missing measurements as zero.
Resource policy never kills an already running solver.

`resource-status.json` in the workspace records the latest sample, policy,
admitted IDs and blocked reasons. It is a bounded latest-status file, not an
unlimited resource trace. Every started job retains its admission receipt in its
journal and completed bundle metadata. `/api/v1/health` also exposes the current
workspace policy and sample. All configured solver deadlines remain visible in
the usual effective inputs.

If no job is running and no waiting job can start for `idle_timeout_sec`, the
experiment stops as **resource_blocked**. Pending work becomes interrupted
administrative work, not a solver timeout or infeasibility result. The CLI exits
with code 2. Inspect the blocked reasons and resume with the same policy once
resources are available. Changing the policy requires a new manifest; it never
rewrites old terminal outcomes. Ordinary wall/disk budgets still apply.

## Use the same policy in the GUI

```bash
uv sync --locked --python 3.12 --extra resources --extra gui --extra analysis
npm --prefix frontend ci
npm --prefix frontend run build
MAPF_WORKSPACE_DIR=runs/resource-gui/workspace uv run --no-sync mapf dashboard --workers 2 --resource-policy examples/resource-policy.json
```

The example study's `budget.resources` matches that JSON policy file. A GUI-owned
experiment must match its supervisor's policy and fit its worker/disk limits;
mismatches are rejected before the experiment starts. CLI and GUI must still use
separate active workspace directories. Increase `--workers` only when your
declared policy and machine headroom justify it. Local POSIX execution remains the
qualified platform scope; a Windows process supervisor is not claimed.

Freeze the resource policy and source for a study. A changed policy requires a
new plan; do not retrofit its settings into an active execution or relabel
existing results.
