"""Stage approved repository documentation and build a fully local searchable site."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / ".docs-build"


def site_path(relative: Path) -> Path:
    if str(relative) == "README.md":
        return Path("index.md")
    if str(relative) == ".zenodo.json":
        return Path("zenodo-metadata.json")
    if relative.parts[0] == ".github":
        return Path("contribution-templates", *relative.parts[1:])
    return relative


def rendered_html_links(text: str, source: Path, target: Path, content: Path) -> str:
    """Resolve raw HTML anchors, which MkDocs leaves outside Markdown rewriting.

    Keep the repository's .md links intact; change only the staged site copy.
    External URLs and links to non-Markdown assets retain their original bytes.
    """
    def replace(match: re.Match[str]) -> str:
        parsed = urlsplit(match[3])
        if parsed.scheme or parsed.netloc or not parsed.path:
            return match[0]
        resolved = (source.parent / unquote(parsed.path)).resolve()
        if resolved.suffix != ".md" or not resolved.is_relative_to(ROOT):
            return match[0]
        rendered = content / site_path(resolved.relative_to(ROOT)).with_suffix(".html")
        destination = urlunsplit(parsed._replace(path=os.path.relpath(rendered, target.parent)))
        return match[1] + match[2] + destination + match[2]

    return re.sub(r'''(<a\b[^>]*\bhref\s*=\s*)(["'])(.*?)\2''', replace, text)


def stage() -> None:
    content = STAGING / "content"
    if content.exists():
        shutil.rmtree(content)
    content.mkdir(parents=True)
    sources: dict[str, str] = {}
    allowed = {".txt", ".md", ".json", ".csv", ".png", ".gif", ".webp", ".svg", ".html", ".py", ".mjs", ".map", ".scen", ".yml"}
    paths = [ROOT / n for n in ("README.md", "CONTRIBUTING.md", "REPRODUCIBILITY.md", "CHANGELOG.md", "CITATION.cff", "reference.bib", "LICENSE", "THIRD_PARTY_NOTICES.md", "pyproject.toml", "uv.lock", "codemeta.json", ".zenodo.json", "frontend/package-lock.json", "mkdocs.yml")]
    for folder in ("docs", "examples", "scripts", "tests"):
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix in allowed and "__pycache__" not in p.parts)
    paths.extend(p for p in (ROOT / "src/mapf").rglob("*") if p.is_file() and p.suffix in {".py", ".md"})
    paths += [ROOT / "benchmarks/README.md"]
    paths += list((ROOT / ".github").rglob("*.md")) + list((ROOT / ".github").rglob("*.yml"))
    for source in paths:
        if source.is_symlink() or not source.resolve().is_relative_to(ROOT):
            raise ValueError(f"Documentation source must be a repository-owned regular file: {source}")
        relative = source.relative_to(ROOT)
        target = content / site_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = source.read_bytes()
        if source.suffix == ".md":
            # Keep root README as the sole homepage source; adjust only references to it.
            text = data.decode()
            def link(match: re.Match[str], source: Path = source, target: Path = target) -> str:
                destination = match[1]
                bare, separator, fragment = destination.partition("#")
                resolved = (source.parent / bare).resolve()
                if bare and "://" not in bare and resolved.is_relative_to(ROOT):
                    new_path = content / site_path(resolved.relative_to(ROOT))
                    destination = os.path.relpath(new_path, target.parent) + (separator + fragment if separator else "")
                return "](" + destination + ")"
            text = re.sub(r"\]\(([^)]+)\)", link, text)
            text = rendered_html_links(text, source, target, content)
            data = text.encode()
        target.write_bytes(data)
        sources[str(relative)] = hashlib.sha256(source.read_bytes()).hexdigest()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    content_sha256 = hashlib.sha256(json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    receipt = {"package_version": version, "content_sha256": content_sha256,
               "sources": sources, "scope": "Documentation build identity, not experiment qualification"}
    (content / "documentation-source.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (content / "docs/SITE-VERSION.md").write_text(f"# Documentation build\n\nDEC-MAPF · Alpha **{version}**.\n\nContent checksum: `{content_sha256}`. [Source file hashes](../documentation-source.json) identify the files used to render these pages. This is not a benchmark completion receipt.\n\nNext: [choose a workflow](README.md).\n")


def finalize_site(site: Path) -> None:
    """Ship only the configured English search assets; fail closed on new languages."""
    index = json.loads((site / "search/search_index.json").read_text())
    if index["config"]["lang"] != ["en"]:
        raise ValueError("Review additional search-language licenses before distributing them")
    unused = site / "assets/javascripts/lunr"
    if unused.exists():
        shutil.rmtree(unused)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help="Serve the built site on loopback port 8002")
    args = parser.parse_args()
    runpy.run_path(str(ROOT / "scripts/check_licenses.py"))["check"](ROOT, docs=True)
    stage()
    subprocess.run([sys.executable, "-m", "mkdocs", "build", "--strict", "--config-file", str(ROOT / "mkdocs.yml")], cwd=ROOT, check=True)
    finalize_site(STAGING / "site")
    if args.serve:
        subprocess.run([sys.executable, "-m", "http.server", "8002", "--bind", "127.0.0.1", "--directory", str(STAGING / "site")], check=True)


if __name__ == "__main__":
    main()
