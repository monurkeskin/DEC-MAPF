# Read and search the docs locally

Build the existing Markdown into a navigable, searchable site. This requires no public hosting, online analytics or separate handwritten copy of the guides.

```bash
uv sync --locked --extra docs
uv run --no-sync python scripts/build_docs.py --serve
```

Open `http://127.0.0.1:8002`. Omit `--serve` for a strict build into `.docs-build/site/`. JavaScript, fonts and search assets are local; search needs the local HTTP server because browsers restrict some `file://` requests.

The navigation separates tutorials, task guides, reference and explanation. The homepage comes from the repository README. The staging script copies approved documentation/source assets, refuses symlink inputs, and excludes run workspaces, raw research data, environments and Git metadata. It generates a source/version receipt with per-file hashes. This command builds the site locally. The GitHub Pages workflow uses the same build process for the hosted documentation.

[Build script](../scripts/build_docs.py), [MkDocs documentation](https://www.mkdocs.org/user-guide/configuration/) and [Material search configuration](https://squidfunk.github.io/mkdocs-material/setup/setting-up-site-search/) describe the build boundary. The optional `docs` dependencies are pinned by `uv.lock`; headless users do not need them.

Next: choose [your first workflow](README.md), or return to the [repository homepage](../README.md).
