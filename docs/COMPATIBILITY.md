# Know which artifacts can be used together

Keep software version, problem semantics and evidence format separate when reopening a study. A package upgrade does not make an old run a new scientific execution.

This is [DEC-MAPF, alpha research software](ALPHA-STATUS.md), with Python package version `0.1.0a2`. The finite compatibility checks below describe current behavior, not a stable-release guarantee.

| Boundary | Current contract | Compatibility and rejection |
| --- | --- | --- |
| Package | `dec-mapf`; Python 3.12/3.13 qualified | `mapf` is the import and CLI name |
| Public Python API | `mapf.api.API_VERSION == "1"` | Additive changes within API 1; documented migrations for breaking changes |
| HTTP API | `/api/v1`; checked OpenAPI schema | Unknown request fields rejected; generated client checked in CI |
| Experiment plan | `experiment-1` | Digest binds effective inputs and source; source drift rejects run/resume |
| Workspace | SQLite workspace schema 1; legacy schema 0 reader | Read-only opening never creates or migrates a store; unsupported newer schemas rejected |
| Portable run | `decmapf-run`, version `1.0`, RFC8785 digest | Production importer independently rechecks paths, frames, costs and identities; unknown versions rejected; metrics-only bundles retain paths with no replay frames |
| Telemetry | `telemetry-2` | Missing or reduced-recording layers are unavailable, never reconstructed as agent knowledge |
| Trajectory validation | `trajectory-v2` | Complete solutions and physical but unfinished prefixes are distinct |
| Communication metrics | `delivered-metrics-v2` | Actual received messages; historical/unqualified estimates cannot be silently pooled |
| Study card / narrative | `experiment-card-1` / `negotiation-story-1` | Derived descriptions retain source identities; neither is a reproducibility certificate |
| Scientific method | Recorded `algorithm_version`, protocol and setting | Never infer method equivalence from a package number or a solver label |

## Reopen a saved study

1. Keep an original copy of the workspace/bundle and its manifest.
2. Use `mapf batch status --workspace PATH` or the read-only `RunRepository.open_existing(PATH, read_only=True)` boundary.
3. Import a bundle only through the checked importer. For legacy CSV/JSON without the required provenance, use [quarantine import](EXPERIMENTS.md); do not invent missing fields.
4. If source identity changed, plan a new experiment. Resume does not silently overwrite the original code identity.

CI covers old schema reads, future-schema rejection, bundle tampering, installed package provenance and source/wheel byte identity. Finite compatibility fixtures do not guarantee every historical file can be recovered.

A software citation names the exact alpha version and commit. The [2024 article](https://doi.org/10.1007/s10458-024-09639-8) is a separate publication; its DOI is not a DOI for this software. No software DOI or public package availability is claimed.

Next: [qualify a release](RELEASE-CHECKS.md) and retain the exact tested distributions and their hashes.
