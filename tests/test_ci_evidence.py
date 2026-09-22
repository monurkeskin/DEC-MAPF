"""A recoverable CI receipt cannot depend on GitHub artifact storage availability."""

import base64
import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("missing", [False, True])
def test_ci_log_receipts_round_trip_and_missing_evidence_fails(tmp_path, missing):
    path = tmp_path / "results.json"
    raw = b'{"tests":380,"failures":0,"label":"safe synthetic receipt"}\n'
    path.write_bytes(raw)
    paths = [str(path)] + ([str(tmp_path / "missing.xml")] if missing else [])
    process = subprocess.run(
        [sys.executable, str(Path("scripts/ci_evidence.py")), *paths],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GITHUB_SHA": "a" * 40,
            "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        },
        check=False,
    )
    assert process.returncode == int(missing)
    lines = process.stdout.splitlines()
    assert (
        lines[0] == "DEC_MAPF_CI_RECEIPTS_BEGIN"
        and lines[-1] == "DEC_MAPF_CI_RECEIPTS_END"
    )
    receipt = json.loads(lines[1])
    assert receipt["commit"] == "a" * 40 and receipt["complete"] is (not missing)
    recovered = gzip.decompress(base64.b64decode(receipt["files"][0]["gzip_base64"]))
    assert recovered == raw
    assert hashlib.sha256(recovered).hexdigest() == receipt["files"][0]["sha256"]
    assert (
        "Test/check failures remain blocking" in (tmp_path / "summary.md").read_text()
    )
