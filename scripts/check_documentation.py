"""Check local guide links, Python snippet syntax and gallery image integrity.

This is a documentation integrity check, not execution or scientific validation.
Run the documented examples separately before claiming their workflows work.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import runpy
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def anchors(text: str) -> set[str]:
    used: dict[str, int] = {}
    result = set(re.findall(r'<(?:a|h[1-6])[^>]+id="([^"]+)"', text))
    for title in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.MULTILINE):
        title = re.sub(r"<[^>]+>", "", title).replace("`", "")
        slug = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        duplicate = used.get(slug, 0)
        result.add(slug if duplicate == 0 else f"{slug}-{duplicate}")
        used[slug] = duplicate + 1
    return result


def main() -> None:
    documents = [ROOT / name for name in ("README.md", "CONTRIBUTING.md", "REPRODUCIBILITY.md", "CHANGELOG.md", "examples/README.md")]
    documents += sorted((ROOT / "docs").rglob("*.md"))
    documents += sorted((ROOT / "examples/capsules").rglob("*.md"))
    documents += sorted((ROOT / "src/mapf").glob("*/README.md"))
    errors, link_count, snippet_count = [], 0, 0
    publication_patterns = runpy.run_path(str(ROOT / "scripts/public_export.py"))["PATTERNS"]
    public_pages = documents + [p for p in (ROOT / "docs").rglob("*")
                                if p.suffix in {".json", ".html", ".csv"}]
    for path in public_pages:
        if any(pattern.search(path.read_bytes()) for pattern in publication_patterns):
            errors.append(f"{path.relative_to(ROOT)}: content is outside the initial public baseline")
    if any((ROOT / "docs/releases").glob("*")):
        errors.append("Internal release-history pages are outside the initial public baseline")
    for path in documents:
        text = path.read_text()
        for snippet in re.findall(r"^```python\s*\n(.*?)^```", text, re.MULTILINE | re.DOTALL):
            snippet_count += 1
            try:
                ast.parse(snippet)
            except SyntaxError as error:
                errors.append(f"{path.relative_to(ROOT)}: Python snippet: {error}")
        prose = re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
        targets = re.findall(r"\[[^\]]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)", prose)
        targets += re.findall(r'(?:href|src)="([^"]+)"', prose)
        for target in targets:
            parsed = urlsplit(target.strip("<>"))
            if parsed.scheme or parsed.netloc:
                continue
            link_count += 1
            local = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if not local.exists():
                errors.append(f"{path.relative_to(ROOT)}: missing {target}")
            elif parsed.fragment and local.suffix == ".md" and unquote(parsed.fragment) not in anchors(local.read_text()):
                errors.append(f"{path.relative_to(ROOT)}: missing heading {target}")
    gallery = ROOT / "docs/assets/gallery"
    receipt = json.loads((gallery / "provenance.json").read_text())
    if receipt.get("schema_version") != "article-regime-gallery-1":
        errors.append("Unexpected gallery provenance schema")
    if len(receipt["screenshots"]) != 6 or len(receipt["all_trials"]) != 2:
        errors.append("Expected six article-regime images of two diagnostic recordings")
    trials = {trial["run_id"]: trial for trial in receipt["all_trials"]}
    for trial in trials.values():
        if (trial.get("paths_and_scientific_metrics_identical") is not True
                or trial.get("source_sha256") != trial.get("original_source_sha256")):
            errors.append(f"Gallery recording lacks original-source/path/metric parity: {trial['run_id']}")
    regimes = set()
    for shot in receipt["screenshots"]:
        shown_tick = re.search(r"t\s*=\s*(\d+)", shot["tick_label"])
        if not shown_tick or shot.get("rendered_frame_label") != f"Agents · t={shown_tick[1]}":
            errors.append(f"Gallery timeline does not match the loaded replay frame: {shot['file']}")
        payload = (gallery / shot["file"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != shot["sha256"] or len(payload) != shot["bytes"]:
            errors.append(f"Gallery image checksum/size differs: {shot['file']}")
        if shot["validation"] != "valid_solution":
            errors.append(f"Gallery screenshot has an unqualified result: {shot['file']}")
        trial = trials.get(shot["run_id"], {})
        if (shot["source_sha256"] != trial.get("source_sha256")
                or shot["original_run_id"] != trial.get("original_run_id")):
            errors.append(f"Gallery screenshot does not match its recorded source: {shot['file']}")
        cells = shot["grid"][0] * shot["grid"][1]
        if (not math.isclose(shot["obstacle_fraction"], shot["obstacles"] / cells)
                or not math.isclose(shot["initial_agent_fraction_of_free_cells"], shot["agents"] / (cells - shot["obstacles"]))):
            errors.append(f"Gallery density definitions differ: {shot['file']}")
        regimes.add((tuple(shot["grid"]), shot["agents"], shot["obstacles"], shot["commitment"]))
    if regimes != {((16, 16), 80, 0, "SC"), ((32, 32), 80, 205, "ZC")}:
        errors.append("Gallery does not cover the two declared article regimes")
    if any(trial["validation_status"] != "valid_solution" for trial in receipt["all_trials"]):
        errors.append("Gallery receipt contains a non-solved demonstration")
    animation = json.loads((gallery / "animation-provenance.json").read_text())
    if animation.get("ticks") != list(range(51)) or animation.get("validation") != "valid_solution":
        errors.append("Animation must retain the complete checked replay")
    for asset in animation["assets"]:
        payload = (gallery / asset["file"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != asset["sha256"] or len(payload) != asset["bytes"]:
            errors.append(f"Animation asset checksum/size differs: {asset['file']}")
        if asset["file"].endswith(".gif"):
            if payload[:6] not in {b"GIF87a", b"GIF89a"} or asset["duration_ms"] != 30600:
                errors.append(f"Animation format or timing differs: {asset['file']}")
            if int.from_bytes(payload[6:8], "little") != asset["width"] or int.from_bytes(payload[8:10], "little") != asset["height"]:
                errors.append(f"Animation dimensions differ: {asset['file']}")
    narrative = ROOT / "docs/assets/narrative"
    narrative_receipt = json.loads((narrative / "provenance.json").read_text())
    for name, checksum in narrative_receipt["assets"].items():
        if hashlib.sha256((narrative / name).read_bytes()).hexdigest() != checksum:
            errors.append(f"Narrative asset checksum differs: {name}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(json.dumps({"documents": len(documents), "local_links": link_count,
                      "python_snippets_parsed": snippet_count,
                      "image_checksums": len(receipt["screenshots"]),
                      "animation_asset_checksums": len(animation["assets"]), "status": "passed"}))


if __name__ == "__main__":
    main()
