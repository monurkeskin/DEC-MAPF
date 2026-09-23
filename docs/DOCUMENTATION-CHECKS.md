# Documentation verification

[Documentation index](README.md) · [Gallery provenance](assets/gallery/provenance.json) · [Alpha status](ALPHA-STATUS.md)

The current gallery qualifies six actual GUI captures of two selected solved examples from the article settings. Both were recorded from the frozen scientific source with the original inputs and ordered rosters, changing only `metrics-only` recording to `full-trace`. Per-agent paths and canonical scientific metrics matched the preserved original outcomes exactly. Both results passed independent trajectory validation, and the captures produced no browser page errors.

The 16×16 example has 80 agents and no obstacles; the 32×32 example has 80 agents and 205 blocked cells. Captions distinguish initial occupancy from obstacle density, decision time from frame time, local knowledge from hindsight, and original execution identity from the alpha viewer. Original records were not overwritten or added again to the article population.

## Recheck the guides

```bash
uv run --no-sync python scripts/documentation_reference.py --check
uv run --no-sync python scripts/check_documentation.py
uv run --no-sync python scripts/build_docs.py
```

The reference check detects drift from request models. Documentation integrity covers Markdown inside the source-export boundary, including module, frontend and benchmark READMEs, examples and contribution templates. It checks local links/headings, Python snippet syntax, image hashes and the gallery's provenance relationships. The strict site build checks the staged documentation and generates a per-file build receipt. These checks do not themselves execute a simulation or establish scientific reproduction.

To recapture from the selected recorded workspace, follow [the gallery instructions](GALLERY.md#recreate-the-gallery). Raw workspaces remain outside Git. The image receipt records the capture recipe and viewer hashes; captured pixels are not expected to match across browser versions or runtimes.

## Software and scientific evidence

The core and GUI workflows qualify the headless/visual paths, generated contracts, installed distributions and browser behavior. Read their results for the exact commit; a workflow definition is not evidence that it passed. [Distribution checks](RELEASE-CHECKS.md) describe the installable-package boundary and [compatibility](COMPATIBILITY.md) separates software from artifact versions.

Export checks reject internal development chronology and private commit literals. Content hashes identify the distributed files.

Selected solved illustrations cannot establish general success rates, SOTA scaling, historical numerical equivalence, complete accessibility or cross-platform behavior. The [experiment guide](EXPERIMENTS.md) and [metric definitions](METRICS.md) describe how to collect and interpret a study's outcomes.
