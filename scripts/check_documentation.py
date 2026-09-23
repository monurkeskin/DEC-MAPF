"""Check local guide links, Python snippet syntax and gallery image integrity.

This is a documentation integrity check, not execution or scientific validation.
Run the documented examples separately before claiming their workflows work.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
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


def documents_to_check():
    """Check the source-export boundary, including nested contributor guides.

    Use filesystem discovery so this works in a clean export without Git.
    Prune local environments and generated outputs before descending into them.
    """
    export = runpy.run_path(str(Path(__file__).with_name("public_export.py")))
    documents = []
    for directory, children, filenames in os.walk(ROOT):
        children[:] = [name for name in children if name not in export["FORBIDDEN_PARTS"]]
        for name in filenames:
            path = Path(directory) / name
            relative = path.relative_to(ROOT).as_posix()
            if path.suffix == ".md" and export["exportable"](relative):
                documents.append(path)
    return sorted(documents)


def check_publication(documents, errors):
    publication_patterns = runpy.run_path(str(ROOT / "scripts/public_export.py"))[
        "PATTERNS"
    ]
    public_pages = documents + [
        p for p in (ROOT / "docs").rglob("*") if p.suffix in {".json", ".html", ".csv"}
    ]
    for path in public_pages:
        if any(pattern.search(path.read_bytes()) for pattern in publication_patterns):
            errors.append(
                f"{path.relative_to(ROOT)}: content is outside the initial public baseline"
            )
    if any((ROOT / "docs/releases").glob("*")):
        errors.append(
            "Internal release-history pages are outside the initial public baseline"
        )


def missing_heading(local, fragment):
    if not fragment or local.suffix != ".md":
        return False
    return unquote(fragment) not in anchors(local.read_text())


def check_link(path, target, errors):
    parsed = urlsplit(target.strip("<>"))
    if parsed.scheme or parsed.netloc:
        return 0
    local = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
    if not local.exists():
        errors.append(f"{path.relative_to(ROOT)}: missing {target}")
    elif missing_heading(local, parsed.fragment):
        errors.append(f"{path.relative_to(ROOT)}: missing heading {target}")
    return 1


def check_document(path, errors):
    snippet_count = 0
    text = path.read_text()
    for snippet in re.findall(
        r"^```python\s*\n(.*?)^```", text, re.MULTILINE | re.DOTALL
    ):
        snippet_count += 1
        try:
            ast.parse(snippet)
        except SyntaxError as error:
            errors.append(f"{path.relative_to(ROOT)}: Python snippet: {error}")
    prose = re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
    targets = re.findall(r"\[[^\]]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)", prose)
    targets += re.findall(r'(?:href|src)="([^"]+)"', prose)
    link_count = sum(check_link(path, target, errors) for target in targets)
    return link_count, snippet_count


def check_shot_alignment(shot, errors):
    shown_tick = re.search(r"t\s*=\s*(\d+)", shot["tick_label"])
    if (
        not shown_tick
        or shot.get("rendered_frame_label") != f"Agents · t={shown_tick[1]}"
    ):
        errors.append(
            f"Gallery timeline does not match the loaded replay frame: {shot['file']}"
        )


def check_shot_source(shot, trials, errors):
    trial = trials.get(shot["run_id"], {})
    if shot["source_sha256"] != trial.get("source_sha256") or shot[
        "original_run_id"
    ] != trial.get("original_run_id"):
        errors.append(
            f"Gallery screenshot does not match its recorded source: {shot['file']}"
        )


def check_shot(shot, trials, gallery, errors):
    check_shot_alignment(shot, errors)
    payload = (gallery / shot["file"]).read_bytes()
    if (
        hashlib.sha256(payload).hexdigest() != shot["sha256"]
        or len(payload) != shot["bytes"]
    ):
        errors.append(f"Gallery image checksum/size differs: {shot['file']}")
    if shot["validation"] != "valid_solution":
        errors.append(f"Gallery screenshot has an unqualified result: {shot['file']}")
    check_shot_source(shot, trials, errors)
    cells = shot["grid"][0] * shot["grid"][1]
    if not math.isclose(
        shot["obstacle_fraction"], shot["obstacles"] / cells
    ) or not math.isclose(
        shot["initial_agent_fraction_of_free_cells"],
        shot["agents"] / (cells - shot["obstacles"]),
    ):
        errors.append(f"Gallery density definitions differ: {shot['file']}")
    return (tuple(shot["grid"]), shot["agents"], shot["obstacles"], shot["commitment"])


def check_gallery_manifest(receipt, errors):
    if receipt.get("schema_version") != "article-regime-gallery-1":
        errors.append("Unexpected gallery provenance schema")
    if len(receipt["screenshots"]) != 6 or len(receipt["all_trials"]) != 2:
        errors.append("Expected six article-regime images of two diagnostic recordings")


def check_trial_sources(trials, errors):
    for trial in trials.values():
        if trial.get("paths_and_scientific_metrics_identical") is not True or trial.get(
            "source_sha256"
        ) != trial.get("original_source_sha256"):
            errors.append(
                f"Gallery recording lacks original-source/path/metric parity: {trial['run_id']}"
            )


def check_gallery(errors):
    gallery = ROOT / "docs/assets/gallery"
    receipt = json.loads((gallery / "provenance.json").read_text())
    check_gallery_manifest(receipt, errors)
    trials = {trial["run_id"]: trial for trial in receipt["all_trials"]}
    check_trial_sources(trials, errors)
    regimes = {
        check_shot(shot, trials, gallery, errors) for shot in receipt["screenshots"]
    }
    if regimes != {((16, 16), 80, 0, "SC"), ((32, 32), 80, 205, "ZC")}:
        errors.append("Gallery does not cover the two declared article regimes")
    if any(
        trial["validation_status"] != "valid_solution"
        for trial in receipt["all_trials"]
    ):
        errors.append("Gallery receipt contains a non-solved demonstration")
    return receipt


def check_gif(asset, payload, errors):
    if payload[:6] not in {b"GIF87a", b"GIF89a"} or asset["duration_ms"] != 30600:
        errors.append(f"Animation format or timing differs: {asset['file']}")
    if (
        int.from_bytes(payload[6:8], "little") != asset["width"]
        or int.from_bytes(payload[8:10], "little") != asset["height"]
    ):
        errors.append(f"Animation dimensions differ: {asset['file']}")


def check_animation(gallery, errors):
    animation = json.loads((gallery / "animation-provenance.json").read_text())
    if (
        animation.get("ticks") != list(range(51))
        or animation.get("validation") != "valid_solution"
    ):
        errors.append("Animation must retain the complete checked replay")
    for asset in animation["assets"]:
        payload = (gallery / asset["file"]).read_bytes()
        if (
            hashlib.sha256(payload).hexdigest() != asset["sha256"]
            or len(payload) != asset["bytes"]
        ):
            errors.append(f"Animation asset checksum/size differs: {asset['file']}")
        if asset["file"].endswith(".gif"):
            check_gif(asset, payload, errors)
    return animation


def check_narrative(errors):
    narrative = ROOT / "docs/assets/narrative"
    narrative_receipt = json.loads((narrative / "provenance.json").read_text())
    for name, checksum in narrative_receipt["assets"].items():
        if hashlib.sha256((narrative / name).read_bytes()).hexdigest() != checksum:
            errors.append(f"Narrative asset checksum differs: {name}")


def main() -> None:
    documents = documents_to_check()
    errors = []
    check_publication(documents, errors)
    counts = [check_document(path, errors) for path in documents]
    link_count = sum(pair[0] for pair in counts)
    snippet_count = sum(pair[1] for pair in counts)
    receipt = check_gallery(errors)
    animation = check_animation(ROOT / "docs/assets/gallery", errors)
    check_narrative(errors)
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        json.dumps(
            {
                "documents": len(documents),
                "local_links": link_count,
                "python_snippets_parsed": snippet_count,
                "image_checksums": len(receipt["screenshots"]),
                "animation_asset_checksums": len(animation["assets"]),
                "status": "passed",
            }
        )
    )


if __name__ == "__main__":
    main()
