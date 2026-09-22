"""Sanitized tests of real native rectangle code and its MDD depth contract.

Link existing build objects while instrumenting the tested rectangle source and
the boundary harness. This is a focused ASan/UBSan check, not whole-solver
sanitization or a proof of MAPF correctness. No production binary is overwritten.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

MODES = (
    "short_first",
    "short_second",
    "empty",
    "null",
    "negative_tick",
    "late_tick",
    "matched",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--setting", choices=("SETTING_1", "SETTING_2", "SETTING_3", "SETTING_4")
    )
    parser.add_argument("--family", choices=("eecbs", "cbsh2-rtc"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    catalog = json.loads(args.catalog.read_text())
    root = args.catalog.resolve().parent
    harness = Path(__file__).with_name("rectangle_contract.cpp")
    records = []
    for profile in catalog:
        if args.setting and profile["setting"] != args.setting:
            continue
        if args.family and profile["family"] != args.family:
            continue
        name = profile["name"] + "-" + profile["setting"]
        tree = root / profile["stage"] / profile["name"]
        source = tree / "src/RectangleReasoning.cpp"
        build = Path(profile["executable"]).parent
        objects = sorted(
            p
            for p in build.rglob("*.cpp.o")
            if p.name not in ("driver.cpp.o", "RectangleReasoning.cpp.o")
        )
        assert objects, build
        setting = int(profile["setting"][-1])
        binary = args.output / name
        command = [
            "c++",
            "-std=c++14",
            "-O1",
            "-g",
            "-DNDEBUG",
            "-fsanitize=address,undefined",
            "-fno-omit-frame-pointer",
            f"-DNO_WAIT={int(setting in (1, 3))}",
            f"-DDISAPPEAR_AT_TARGET={int(setting in (3, 4))}",
            f"-DDEC_MAPF_CBS={int(profile['family'] == 'cbsh2-rtc')}",
            "-I" + str(tree / "inc"),
            "-I" + str(root / "boost-install/include"),
            str(harness),
            str(source),
            *map(str, objects),
            *map(str, sorted((root / "boost-install/lib").glob("*.a"))),
            "-o",
            str(binary),
        ]
        with (args.output / (name + "-build.log")).open("w") as log:
            subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120
            )
        for mode in MODES:
            result = subprocess.run(
                [str(binary), mode],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            (args.output / (name + "-" + mode + ".log")).write_text(
                result.stdout + result.stderr
            )
            records.append(
                {
                    "profile": name,
                    "mode": mode,
                    "exit_code": result.returncode,
                    "passed": result.returncode == 0,
                    "rectangle_source_sha256": hashlib.sha256(
                        source.read_bytes()
                    ).hexdigest(),
                }
            )
            print(name, mode, result.returncode, flush=True)
    assert records, "No selected profiles"
    receipt = {
        "passed": all(r["passed"] for r in records),
        "executions": len(records),
        "failures": sum(not r["passed"] for r in records),
        "records": records,
        "harness_sha256": hashlib.sha256(harness.read_bytes()).hexdigest(),
        "scope": __doc__,
    }
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    raise SystemExit(0 if receipt["passed"] else 1)


if __name__ == "__main__":
    main()
