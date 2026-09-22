# CI and distribution qualification

[Documentation index](README.md) · [Contributing](../CONTRIBUTING.md)

The delivery boundary is a tested source archive and installable wheel. The current project is an [alpha](ALPHA-STATUS.md). CI does not publish to PyPI, deploy a hosted GUI, change repository visibility or run the article tournament.

## Required checks

| Gate | Evidence |
| --- | --- |
| Core matrix | Python 3.12/3.13 on Linux/macOS: lint, typing, documentation integrity and complete Python tests |
| Shared contracts | Generated OpenAPI, TypeScript and `interactive-v1` preset are unchanged by regeneration |
| Browser | Actual localhost backend and spawned worker; replay, export/import, assumptions, library pagination, accessibility and recovery checks |
| Distribution | `uv build` produces an sdist and then a wheel from that sdist; packaged Python/UI bytes are compared and documentation links/examples are checked from the extracted archive |
| Installed core | Fresh environment outside the checkout; no FastAPI or psutil; two real tiny trials and completed-study resume |
| Installed resources | Separate headless environment with psutil; real observations and centralized/decentralized admission |
| Installed GUI | Packaged local assets, real worker, independent validation and bundle import without a source checkout |
| Evidence | Nonempty Python/browser acceptance with no failures, skipped tests or flaky retries; receipt hashes and readable counts in job logs/summary |
| Documentation deployment | The `Documentation website` workflow builds from `main`, checks guide/asset integrity and licenses, and publishes that artifact through GitHub Pages |

Workflows cancel superseded CI for the same workflow/ref. They never control local experiment processes. Download caches are keyed by OS, Python, pinned uv version and `uv.lock`; npm uses the frontend lockfile. Virtual environments and scientific workspaces are not cached. Downloadable artifact upload is an optional copy; required evidence and failures remain visible in job logs even when archive publication is unavailable.

Documentation deployments are serialized and use the `github-pages` environment. The deployment job requires a successful site build and is limited to this repository's `main` branch. Generated HTML is delivered as a Pages artifact, with its source receipt, rather than committed to a separate branch. The installed simulation remains local; this workflow publishes only the static documentation.

## Reproduce a distribution check

Use the development environment in [Installation](INSTALLATION.md). Choose a **new** output directory so an old wheel cannot accidentally enter the check:

```bash
npm --prefix frontend run build
uv run --no-sync python scripts/package_gui.py
uv build --out-dir runs/distribution-check
uv run --no-sync python scripts/check_distributions.py runs/distribution-check
```

The source archive includes documentation, examples, frontend source/lock and built UI assets. Qualification compares included files, not just an import from the editable checkout. See the CI workflow for isolated installation commands and the three smoke scripts. This verifies deliverability; it does not claim bit-for-bit build reproducibility across arbitrary build backends or operating systems.

Before a future release, inspect the exact commit's checks, licenses/citations, current documentation and intended export contents. Tag only a concrete qualified release. Public visibility, package publication and any new scientific claims require their own explicit decision; no public release is produced by these workflows.

## Researcher workflow qualification

Qualification includes installed capsule/scaffold/extension checks, strict local documentation builds and guide/reference integrity checks. Run
`python scripts/smoke_adoption_wheel.py` with the **core-only installed-wheel
interpreter from outside the checkout**. It executes 25 bounded teaching trials;
it requires no GUI packages. The ordinary wheel smoke scripts continue to qualify
core/resource/GUI boundaries. Use a clean output directory for each candidate and
retain failed receipts when a qualification reveals a bug.

Next: inspect the [compatibility matrix](COMPATIBILITY.md) and the exact commit's
hosted acceptance results before creating a version tag.

## Clean source export

Create a source snapshot from a reviewed committed revision without copying its Git history, raw benchmark results, local workspaces or untracked files:

```bash
uv run --no-sync python scripts/public_export.py runs/source-export --revision HEAD
```

The destination must not exist. `PUBLICATION-MANIFEST.json` records a content digest and per-file checksums. The command reports the selected source revision separately for a local audit receipt; private development commit identifiers are not embedded in the distributed manifest. The exporter rejects symlinks and known confidential content patterns, and CI checks documentation from the resulting snapshot. This is a bounded automated content check; review the selected files and assets before publication. A clean snapshot must be initialized as a new Git repository if development history is intentionally kept separate. Do not push original historical refs into that destination.

Source archives also exclude raw benchmark tables and local databases. Gallery images, their sanitized provenance, teaching fixtures and supported test/development code remain included. A normal versioned release contains the source archive, wheel, checksums and release notes; native third-party executables require their own distribution terms.
