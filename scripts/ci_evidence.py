"""Preserve small acceptance receipts in job logs independently of artifact quota."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path


def result_summary(path: Path, raw: bytes) -> dict:
    """Readable counts supplement the lossless receipt; they never change a check result."""
    try:
        if path.suffix == ".xml":
            cases = list(ET.fromstring(raw).iter("testcase"))
            return {"cases": len(cases), **{name: sum(case.find(name) is not None for case in cases)
                                           for name in ("failure", "error", "skipped")}}
        if path.suffix == ".json":
            value = json.loads(raw)
            if "stats" in value:
                return {key: value["stats"].get(key, 0) for key in ("expected", "unexpected", "skipped", "flaky")}
            if "status" in value:
                return {"status": value["status"]}
    except (ET.ParseError, ValueError, TypeError, KeyError):
        return {"summary": "unavailable; inspect receipt"}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    files = []
    failed = False
    for path in args.paths:
        if not path.is_file():
            files.append({"path": str(path), "error": "Required evidence file missing"})
            failed = True
            continue
        raw = path.read_bytes()
        if len(raw) > 4 * 1024 * 1024:
            files.append(
                {"path": str(path), "error": "Receipt exceeds 4 MiB log limit"}
            )
            failed = True
            continue
        files.append(
            {
                "path": str(path),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "result": result_summary(path, raw),
                "gzip_base64": base64.b64encode(gzip.compress(raw, mtime=0)).decode(
                    "ascii"
                ),
            }
        )
    receipt = {
        "schema": "ci-receipts-v1",
        "commit": os.getenv("GITHUB_SHA", "unavailable"),
        "job": os.getenv("GITHUB_JOB", "local"),
        "run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "complete": not failed,
        "files": files,
    }
    print("DEC_MAPF_CI_RECEIPTS_BEGIN", flush=True)
    print(json.dumps(receipt, separators=(",", ":")), flush=True)
    print("DEC_MAPF_CI_RECEIPTS_END", flush=True)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a") as stream:
            stream.write(
                "## Acceptance evidence\n\nMachine-readable receipts are retained in this job's log, with SHA-256 and lossless gzip/base64. Test/check failures remain blocking. Artifact download publication is a separate, best-effort copy.\n\n"
            )
            stream.write(f"Commit: `{receipt['commit']}`\n\n| Receipt | Result | SHA-256 |\n| --- | --- | --- |\n")
            stream.writelines(f"| `{file['path']}` | {json.dumps(file.get('result', file.get('error', {})))} | `{file.get('sha256', 'missing')}` |\n" for file in files)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
