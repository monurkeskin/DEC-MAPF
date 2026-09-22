"""Resource and recording-invariance check on the current corrected core."""
import json
import subprocess
import sys
from pathlib import Path


def test_profiling_suite_execution(tmp_path) -> None:
    output = tmp_path / "qualification.json"
    process = subprocess.run([sys.executable, "scripts/qualify_performance.py", "--output", str(output)],
                             capture_output=True, text=True, timeout=60, check=False)
    assert process.returncode == 0, process.stderr
    result = json.loads(output.read_text())
    assert len(result["results"]) == 24
    assert {row["negotiation_protocol"] for row in result["results"]} == {"taop-v1"}
    assert {row["fixture"] for row in result["results"]} == {"sparse", "dense", "obstacles", "corridor"}
    for fixture in {row["fixture"] for row in result["results"]}:
        assert len({row["signature"] for row in result["results"] if row["fixture"] == fixture}) == 1
    assert all(row["traced_peak_bytes"] < 256 * 1024**2 for row in result["results"])
    assert all(row["events_dropped"] == 0 for row in result["results"])
    # The old writer must never overwrite its historical aggregate paths.
    legacy = subprocess.run([sys.executable, str(Path("benchmarks/run_profiling_suite.py"))],
                            capture_output=True, text=True, check=False)
    assert legacy.returncode != 0 and "Archived unqualified runner" in legacy.stderr
