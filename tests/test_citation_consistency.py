"""Automated Citation and Metadata Consistency Test Suite (D02).

Asserts that CITATION.cff, reference.bib, codemeta.json, and .zenodo.json
agree on publication identities, DOIs, authors, and software versions.
"""

from __future__ import annotations

import json
from pathlib import Path

EXPECTED_DOI = "10.1007/s10458-024-09639-8"
EXPECTED_SOFTWARE_VERSION = "0.1.0a1"
EXPECTED_AUTHORS = ["Keskin", "Cantürk", "Eran", "Aydoğan"]


def test_citation_cff_consistency() -> None:
    cff_path = Path("CITATION.cff")
    assert cff_path.exists(), "CITATION.cff must exist"
    content = cff_path.read_text(encoding="utf-8")

    assert EXPECTED_DOI in content, f"DOI {EXPECTED_DOI} missing in CITATION.cff"
    assert f'version: "{EXPECTED_SOFTWARE_VERSION}"' in content
    for author in EXPECTED_AUTHORS:
        assert author in content or author.replace("ü", "u").replace("ğ", "g") in content


def test_reference_bib_consistency() -> None:
    bib_path = Path("reference.bib")
    assert bib_path.exists(), "reference.bib must exist"
    content = bib_path.read_text(encoding="utf-8")

    assert EXPECTED_DOI in content, f"DOI {EXPECTED_DOI} missing in reference.bib"
    assert "keskin2024mapf" in content, "Canonical BibTeX key keskin2024mapf missing"
    assert f"version = {{{EXPECTED_SOFTWARE_VERSION}}}" in content


def test_codemeta_consistency() -> None:
    meta_path = Path("codemeta.json")
    assert meta_path.exists(), "codemeta.json must exist"
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["version"] == EXPECTED_SOFTWARE_VERSION
    assert EXPECTED_DOI in meta["referencePublication"]
    family_names = [a["familyName"] for a in meta["authors"]]
    for author in EXPECTED_AUTHORS:
        assert any(author in fn for fn in family_names)


def test_zenodo_consistency() -> None:
    zenodo_path = Path(".zenodo.json")
    if zenodo_path.exists():
        with open(zenodo_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == EXPECTED_SOFTWARE_VERSION
        creators = [c["name"] for c in data.get("creators", [])]
        assert any("Keskin" in name for name in creators)
