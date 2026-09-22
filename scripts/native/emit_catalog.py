"""Emit application profiles only after matching actual-executable qualification."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    build = json.loads((root / "corrected-catalog.json").read_text())
    raw = (root / "corrected-qualification.json").read_bytes()
    qualification = json.loads(raw)
    if not qualification or any(row["errors"] for row in qualification):
        raise ValueError("Actual-executable qualification did not pass")
    profiles = []
    for item in build:
        checksum = hashlib.sha256(Path(item["executable"]).read_bytes()).hexdigest()
        rows = [r for r in qualification if r["binary_sha256"] == checksum]
        if checksum != item["binary_sha256"] or not rows:
            raise ValueError("Build, executable and qualification identity differ")
        label = "EECBS" if item["family"] == "eecbs" else "CBSH2-RTC"
        setting = item["setting"].replace("SETTING_", "S")
        profiles.append(
            {
                "solver_id": f"Native-{label}-{setting}",
                "display_name": f"{label} native ({setting}, corrected 2021 source)",
                "family": item["family"],
                "setting": item["setting"],
                "executable": item["executable"],
                "binary_sha256": checksum,
                "coordinate_order": "row-col",
                "source_revision": item["revision"],
                "source_patch_sha256": hashlib.sha256(
                    (
                        root / "corrected" / (item["name"] + "-portability.patch")
                    ).read_bytes()
                ).hexdigest(),
                "qualification_receipt_sha256": hashlib.sha256(raw).hexdigest(),
                "qualification_scope": f"{len(rows)} actual-binary synthetic oracle checks passed; "
                "patched historical source under absorbing-first-arrival semantics; "
                "finite regression qualification, not a universal optimality proof or exact historical binary reproduction",
            }
        )
    out = root / "application-catalog.json"
    out.write_text(
        json.dumps(
            {"schema_version": "native-solvers-1", "profiles": profiles}, indent=2
        )
        + "\n"
    )
    print(out)


if __name__ == "__main__":
    main()
