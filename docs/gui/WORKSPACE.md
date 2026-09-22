# Developing and reviewing the local workspace

For everyday use, begin with the [illustrated GUI guide](../GUI-GUIDE.md), [gallery](../GALLERY.md) and [documentation index](../README.md). This page describes maintainer architecture and qualification boundaries.

## Architecture

`core/`, `agents/`, `negotiation/`, `engine/` and `solvers/` remain usable without FastAPI or React. `application/` owns scenario validation, plans, process supervision, durable runs, comparison and exports. `gui/api_v1.py` adapts those services to HTTP. `frontend/` presents Configure, Inspect, Compare and Export workflows.

The committed OpenAPI schema supplies generated TypeScript models. A small client adapts auxiliary response views and checks streamed JobEvent values. Run data is immutable after publication, apart from explicit library pin state; imported copies retain lineage under a new run identity.

## Stack decision

The inherited frontend used React/TypeScript/Vite and PixiJS. The current main viewport uses Canvas 2D: the bounded 64×64/100-agent inspection task does not yet justify a scene graph. A local equal-work renderer spike (32×32, 80 agents, 120 frames, with 10 warmup frames excluded in the current harness) measured lower CPU submission cost for Canvas than Pixi. This supports the local choice, not a hardware-independent rendering claim. Pixi remains installed solely for the reproducible spike (`spike.html`).

The UI uses semantic HTML controls and a small CSS token system rather than shadcn/Tailwind. It uses a small explicit request/stream client rather than TanStack Query, and native SVG/table exploration with canonical Matplotlib exports rather than ECharts. These are deliberate v1 scope changes. A larger application may benefit from those libraries once component reuse, charting or cache requirements justify them.

## Workflows

1. **Configure:** select a fixture or edit/import a scenario, choose a solver and setting, inspect the effective preview, submit. MovingAI imports retain source hashes and explicit first-N selection. The grid editor has undo/redo, start/goal/obstacle tools and a coordinate/JSON alternative.
2. **Inspect:** start at t=0; step, scrub, play/pause, adjust speed, select an agent, inspect goals/tokens, jump to a violation, and inspect recorded negotiation events, post-move current plans and signed contract details. Amber dashed overlays show recorded opponent reservations with absolute ticks; choose an agent to restrict the owner. Computation cancellation is a separate action. Select **Recorded local heat** and an agent to inspect actual HeatMap decision weights. Select an individual session/opponent and an aggregate or relative-time slice; the decision tick is distinct from the following post-move frame. Hindsight heat is a separate, mutually exclusive layer.
3. **Compare:** select saved runs, align replay ticks, declare treatment keys, inspect common-solved coverage and deltas, or preview a bounded batch before admission. Named profiles use the same manifest as the CLI. The paired outcome explorer filters/searches/sorts the display and supports keyboard selection. Display filters never alter the statistical summaries or canonical export cohort; unavailable costs remain unavailable.
4. **Export:** save a checked JSON bundle, CSV metrics, LaTeX table, current SVG snapshot or standalone offline HTML replay; load checked bundles and pin library evidence.

## Required UI states

Empty workspace; scenario validation error; preview stale after editing; submitting; queued; running; cancellation requested/terminal; solver failed; invalid result; interrupted job; disconnected stream/poll fallback; missing metric; library empty; import failure; quota exceeded; no common solved pair; duplicate analysis attempt. Display textual labels in addition to color. Dark/light modes, reduced motion, keyboard focus and responsive widths are exercised by browser checks.

## Development

Use `uv sync --locked --python 3.12 --extra gui --extra analysis --extra dev` and `npm --prefix frontend ci`. For hot reload, start the API and `npm --prefix frontend run dev`; Vite proxies API calls. For browser acceptance, build first and run `npm --prefix frontend test`; it creates its own server and temporary database. Tests never need a remote API or paid service. CI uses Chromium; the local macOS configuration uses installed Chrome.

Regenerate schema changes with `.venv/bin/python scripts/export_gui_schema.py` then `npm --prefix frontend run schema`. Keep generation deterministic. Required CI receipts are also persisted losslessly in job logs by `scripts/ci_evidence.py`, independently of the downloadable artifact copy. Missing required receipts fail that step; test/build/schema/browser failures remain blocking. Artifact uploads have seven-day retention and are best-effort because account-wide storage quota can be exhausted. `scripts/package_gui.py` copies only built assets into generated package data. After `uv build --wheel`, install that wheel in a separate environment and run `scripts/smoke_installed_wheel.py` from outside the checkout.

## Qualification boundaries

- Documentation gallery captures are actual checked synthetic runs with [image provenance](../assets/gallery/provenance.json). They are not a substitute for user acceptance of every workflow or a scientific comparison.
- CI definitions and local test receipts do not establish the outcome of a particular remote run; cite its actual commit and job receipt.
- Historical JAAMAS reproduction requires scenario selection, configuration and paper-table provenance for the specific cohort; this architecture page does not qualify a full historical matrix.
- Current events include actual messages, policy decision components, signed transfers and local observations. Full Java strategy equivalence remains unclaimed; see TAOP-CONFORMANCE.md.
- Replay uses checked 32-frame chunks and an 8-chunk/8 MiB serialized LRU; event lists paginate 100 records. The declared long-replay check covers 40 ticks and 20 open/compare cycles, not arbitrary native/GPU memory.
- Actual local heat is recorded only when a strategy computes it before negotiation, in full-trace mode. `heat_recording_limit` defaults to 250,000 sparse values/run; at most 4,096 decision headers are retained. Budget gaps are explicit, and reduced/older recordings do not invent beliefs. Offline HTML supports the same decision and time-slice selection. Recorder counts live in trace metadata, outside scientific metrics.
- Headless/GUI experiments share planned-trial analysis and scenario-block intervals. Multi-user deployment, distributed execution, new scientific strategies and natural-language experiment execution remain outside local scope.

These are visible limitations, not silently successful checks. Read contracts and metric scope before using this interface to make a scientific claim.

## Component examples and exact links

Open `/?components=1` for deterministic interface states using the actual renderer and timeline. Replay links use `?run=RUN_ID&tick=T`. Per-run bookmarks are local browser annotations, not alterations to scientific artifacts. The experiment panel accepts the same JSON matrix as the CLI and exports its exact cohort identity.
