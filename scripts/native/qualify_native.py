"""Actual-executable witnesses with an independent finite joint-state oracle.

Synthetic qualification only: no scientific score or general optimality proof.
Input generators, graph oracle and path checks do not import the MAPF package.
"""

import argparse
import csv
import heapq
import itertools
import json
import random
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def oracle(case, setting):
    goals = tuple(map(tuple, case["goals"]))
    starts = tuple(map(tuple, case["starts"]))
    blocked = set(map(tuple, case.get("obstacles", [])))
    serial = itertools.count()
    queue = [(0, next(serial), starts)]
    best = {starts: 0}
    while queue:
        cost, _, state = heapq.heappop(queue)
        if cost != best[state]:
            continue
        if all(p is None or p == g for p, g in zip(state, goals)):
            return cost
        choices = []
        for p, goal in zip(state, goals):
            if p is None or p == goal:
                choices.append([None if setting >= 3 else p])
            else:
                x, y = p
                candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
                if setting in (2, 4):
                    candidates.append(p)
                choices.append(
                    [
                        q
                        for q in candidates
                        if 0 <= q[0] < case["width"]
                        and 0 <= q[1] < case["height"]
                        and q not in blocked
                    ]
                )
        for nxt in itertools.product(*choices):
            occupied = [p for p in nxt if p is not None]
            if len(occupied) != len(set(occupied)):
                continue
            if any(
                state[i] is not None
                and state[j] is not None
                and nxt[i] == state[j]
                and nxt[j] == state[i]
                for i in range(len(state))
                for j in range(i)
            ):
                continue
            nc = cost + sum(p is not None and p != g for p, g in zip(state, goals))
            if nc < best.get(nxt, float("inf")):
                best[nxt] = nc
                heapq.heappush(queue, (nc, next(serial), nxt))
    return None


def validate(case, paths, setting):
    errors = []
    if set(paths) != set(range(len(case["starts"]))):
        return ["roster"]
    occupied, edges = {}, {}
    horizon = max(map(len, paths.values()))
    for i, path in paths.items():
        start, goal = tuple(case["starts"][i]), tuple(case["goals"][i])
        if not path or path[0] != start or path[-1] != goal:
            errors.append("endpoints")
        for t, p in enumerate(path):
            if (
                not (0 <= p[0] < case["width"] and 0 <= p[1] < case["height"])
                or list(p) in case["obstacles"]
            ):
                errors.append("grid")
            if t:
                d = sum(abs(a - b) for a, b in zip(p, path[t - 1]))
                if d > 1 or (d == 0 and setting in (1, 3) and path[t - 1] != goal):
                    errors.append("move")
                if path[t - 1] == goal and p != goal:
                    errors.append("goal_departure")
        for t in range(horizon):
            p = path[t] if t < len(path) else path[-1] if setting < 3 else None
            if p is None:
                continue
            key = (t, p)
            if key in occupied:
                errors.append("vertex")
            occupied[key] = i
            if t and t < len(path):
                if (t, p, path[t - 1]) in edges:
                    errors.append("edge")
                edges[(t, path[t - 1], p)] = i
    return sorted(set(errors))


def execute(profile, case, weight, timeout=2):
    with tempfile.TemporaryDirectory() as folder:
        d = Path(folder)
        blocked = list(map(tuple, case["obstacles"]))
        (d / "grid.map").write_text(
            f"type octile\nheight {case['height']}\nwidth {case['width']}\nmap\n"
            + "\n".join(
                "".join("@" if (x, y) in blocked else "." for x in range(case["width"]))
                for y in range(case["height"])
            )
            + "\n"
        )
        (d / "case.scen").write_text(
            "version 1\n"
            + "\n".join(
                f"0\tgrid.map\t{case['width']}\t{case['height']}\t{s[0]}\t{s[1]}\t{g[0]}\t{g[1]}\t0"
                for s, g in zip(case["starts"], case["goals"])
            )
            + "\n"
        )
        cmd = [
            profile["executable"],
            "-m",
            str(d / "grid.map"),
            "-a",
            str(d / "case.scen"),
            "-k",
            str(len(case["starts"])),
            "-t",
            str(timeout),
            "-o",
            str(d / "out.csv"),
            "--outputPaths",
            str(d / "paths.txt"),
        ]
        if profile["family"] == "eecbs":
            cmd += ["--suboptimality", str(weight)]
        cmd += profile.get("arguments", [])
        try:
            p = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout + 1, check=False
            )
        except subprocess.TimeoutExpired:
            return {"exit": "timeout", "paths": {}, "stdout": "", "stats": {}}
        paths = {}
        if (d / "paths.txt").exists():
            for line in (d / "paths.txt").read_text().splitlines():
                header, raw = line.split(":", 1)
                idx = int(re.search(r"\d+", header)[0])
                pairs = re.findall(r"\((\d+),(\d+)\)", raw)
                if pairs:
                    paths[idx] = [(int(col), int(row)) for row, col in pairs]
                else:
                    paths[idx] = [
                        (int(n) % case["width"], int(n) // case["width"])
                        for n in raw.strip().split("->")
                        if n.strip()
                    ]
        stats = (
            list(csv.DictReader((d / "out.csv").open()))[-1]
            if (d / "out.csv").exists()
            else {}
        )
        return {
            "exit": p.returncode,
            "paths": paths,
            "stdout": p.stdout,
            "stderr": p.stderr,
            "stats": stats,
        }


def cases():
    rng = random.Random(901123)
    result = []
    for width, height, agents, obstacles in [
        (2, 2, 2, []),
        (3, 2, 2, []),
        (3, 3, 3, []),
        (4, 3, 3, [[1, 1]]),
        (3, 3, 2, [[0, 0], [2, 2]]),
    ]:
        cells = [
            (x, y)
            for y in range(height)
            for x in range(width)
            if [x, y] not in obstacles
        ]
        for _ in range(30):
            result.append(
                {
                    "width": width,
                    "height": height,
                    "starts": rng.sample(cells, agents),
                    "goals": rng.sample(cells, agents),
                    "obstacles": obstacles,
                }
            )
    return result


def main():
    global ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", default="historical")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    ROOT = args.root.resolve()
    catalog = json.loads((ROOT / f"{args.stage}-catalog.json").read_text())
    fixtures = cases()
    (ROOT / "qualification-fixtures.json").write_text(
        json.dumps(fixtures, indent=2) + "\n"
    )
    rows = []
    for profile in catalog:
        setting = int(profile["setting"][-1])
        for weight in [1.0, 1.1] if profile["family"] == "eecbs" else [1.0]:
            current = []
            for i, case in enumerate(fixtures):
                opt = oracle(case, setting)
                if opt is None:
                    continue  # Search exhaustion is not an infeasibility certificate.
                run = execute(profile, case, weight)
                errors = (
                    validate(case, run["paths"], setting)
                    if run["paths"]
                    else ["no_solution"]
                )
                cost = sum(len(p) - 1 for p in run["paths"].values())
                if run["paths"] and not (opt <= cost <= weight * opt + 1e-8):
                    errors.append("cost_bound")
                if run["paths"] and int(run["stats"].get("solution cost", -99)) != cost:
                    errors.append("reported_cost_mismatch")
                row = {
                    "case_id": i,
                    "case": case,
                    "setting": setting,
                    "weight": weight,
                    "binary_sha256": profile["binary_sha256"],
                    "family": profile["family"],
                    "optimum": opt,
                    "cost": cost,
                    "errors": errors,
                    "execution": run,
                }
                rows.append(row)
                current.append(row)
            print(
                profile["name"],
                setting,
                weight,
                len(current),
                "failed",
                sum(bool(r["errors"]) for r in current),
                flush=True,
            )
            (ROOT / f"{args.stage}-qualification.json").write_text(
                json.dumps(rows, indent=2) + "\n"
            )
    print("TOTAL", len(rows), "FAILURES", sum(bool(r["errors"]) for r in rows))
    if any(r["errors"] for r in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
