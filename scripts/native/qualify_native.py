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


def traversable(case, point):
    inside = 0 <= point[0] < case["width"] and 0 <= point[1] < case["height"]
    return inside and list(point) not in case["obstacles"]


def choices(case, setting, point, goal):
    if point is None or point == goal:
        return [None if setting >= 3 else point]
    x, y = point
    candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    if setting in (2, 4):
        candidates.append(point)
    return [p for p in candidates if traversable(case, p)]


def joint_step_allowed(state, nxt):
    occupied = [p for p in nxt if p is not None]
    if len(occupied) != len(set(occupied)):
        return False
    for i, j in itertools.combinations(range(len(state)), 2):
        if state[i] is None or state[j] is None:
            continue
        if nxt[i] == state[j] and nxt[j] == state[i]:
            return False
    return True


def oracle(case, setting):
    case = {**case, "obstacles": [list(p) for p in case.get("obstacles", [])]}
    goals = tuple(map(tuple, case["goals"]))
    starts = tuple(map(tuple, case["starts"]))
    serial = itertools.count()
    queue = [(0, next(serial), starts)]
    best = {starts: 0}
    while queue:
        cost, _, state = heapq.heappop(queue)
        if cost != best[state]:
            continue
        unfinished = sum(p is not None and p != g for p, g in zip(state, goals))
        if not unfinished:
            return cost
        domains = [choices(case, setting, p, g) for p, g in zip(state, goals)]
        for nxt in itertools.product(*domains):
            nc = cost + unfinished
            if joint_step_allowed(state, nxt) and nc < best.get(nxt, float("inf")):
                best[nxt] = nc
                heapq.heappush(queue, (nc, next(serial), nxt))
    return None


def motion_errors(previous, current, goal, setting):
    errors = []
    distance = sum(abs(a - b) for a, b in zip(current, previous))
    forbidden_hold = distance == 0 and setting in (1, 3) and previous != goal
    if distance > 1 or forbidden_hold:
        errors.append("move")
    if previous == goal and current != goal:
        errors.append("goal_departure")
    return errors


def path_errors(case, path, agent, setting):
    if not path:
        return ["endpoints"]
    start, goal = tuple(case["starts"][agent]), tuple(case["goals"][agent])
    errors = []
    if path[0] != start or path[-1] != goal:
        errors.append("endpoints")
    for tick, point in enumerate(path):
        if not traversable(case, point):
            errors.append("grid")
        if tick:
            errors.extend(motion_errors(path[tick - 1], point, goal, setting))
    return errors


class TrajectoryConflicts:
    """Independent occupancy witnesses; no production solver or validator imports."""

    def __init__(self, setting, horizon):
        self.setting = setting
        self.horizon = horizon
        self.occupied = set()
        self.edges = set()

    def position(self, path, tick):
        if tick < len(path):
            return path[tick]
        return path[-1] if self.setting < 3 else None

    def scan(self, path):
        errors = []
        if not path:
            return errors  # The caller records the missing endpoints.
        for tick in range(self.horizon):
            point = self.position(path, tick)
            if point is None:
                continue
            key = (tick, point)
            if key in self.occupied:
                errors.append("vertex")
            self.occupied.add(key)
            if tick and tick < len(path):
                errors.extend(self.check_edge(tick, path[tick - 1], point))
        return errors

    def check_edge(self, tick, previous, current):
        swapped = (tick, current, previous) in self.edges
        self.edges.add((tick, previous, current))
        return ["edge"] if swapped else []


def validate(case, paths, setting):
    if set(paths) != set(range(len(case["starts"]))):
        return ["roster"]
    errors = []
    conflicts = TrajectoryConflicts(setting, max(map(len, paths.values())))
    for agent, path in paths.items():
        errors.extend(path_errors(case, path, agent, setting))
        errors.extend(conflicts.scan(path))
    return sorted(set(errors))


def write_case(case, d):
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


def native_command(profile, inputs, weight, timeout):
    d, agent_count = inputs
    cmd = [
        profile["executable"],
        "-m",
        str(d / "grid.map"),
        "-a",
        str(d / "case.scen"),
        "-k",
        str(agent_count),
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
    return cmd


def decode_path(raw, width):
    pairs = re.findall(r"\((\d+),(\d+)\)", raw)
    if pairs:
        return [(int(col), int(row)) for row, col in pairs]
    return [
        (int(n) % width, int(n) // width) for n in raw.strip().split("->") if n.strip()
    ]


def read_paths(path, width):
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text().splitlines():
        header, raw = line.split(":", 1)
        idx = int(re.search(r"\d+", header)[0])
        result[idx] = decode_path(raw, width)
    return result


def read_stats(path):
    if not path.exists():
        return {}
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    return rows[-1] if rows else {}


def execute(profile, case, weight, timeout=2):
    with tempfile.TemporaryDirectory() as folder:
        d = Path(folder)
        write_case(case, d)
        cmd = native_command(profile, (d, len(case["starts"])), weight, timeout)
        try:
            process = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout + 1, check=False
            )
        except subprocess.TimeoutExpired:
            return {"exit": "timeout", "paths": {}, "stdout": "", "stats": {}}
        return {
            "exit": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "paths": read_paths(d / "paths.txt", case["width"]),
            "stats": read_stats(d / "out.csv"),
        }


def free_cells(width, height, obstacles):
    return [
        (x, y) for y in range(height) for x in range(width) if [x, y] not in obstacles
    ]


def regime_cases(rng, regime):
    width, height, agents, obstacles = regime
    cells = free_cells(width, height, obstacles)
    return [
        {
            "width": width,
            "height": height,
            "starts": rng.sample(cells, agents),
            "goals": rng.sample(cells, agents),
            "obstacles": obstacles,
        }
        for _ in range(30)
    ]


def cases():
    rng = random.Random(901123)
    result = []
    for regime in [
        (2, 2, 2, []),
        (3, 2, 2, []),
        (3, 3, 3, []),
        (4, 3, 3, [[1, 1]]),
        (3, 3, 2, [[0, 0], [2, 2]]),
    ]:
        result.extend(regime_cases(rng, regime))
    return result


def qualification_row(profile, item, weight):
    case_id, case = item
    setting = int(profile["setting"][-1])
    optimum = oracle(case, setting)
    if optimum is None:
        return None  # Search exhaustion is not an infeasibility certificate.
    execution = execute(profile, case, weight)
    paths = execution["paths"]
    errors = validate(case, paths, setting) if paths else ["no_solution"]
    cost = sum(len(p) - 1 for p in paths.values())
    if paths:
        errors.extend(cost_errors(execution, (optimum, weight), cost))
    return {
        "case_id": case_id,
        "case": case,
        "setting": setting,
        "weight": weight,
        "binary_sha256": profile["binary_sha256"],
        "family": profile["family"],
        "optimum": optimum,
        "cost": cost,
        "errors": errors,
        "execution": execution,
    }


def cost_errors(execution, bounds, cost):
    optimum, weight = bounds
    errors = []
    if not optimum <= cost <= weight * optimum + 1e-8:
        errors.append("cost_bound")
    if int(execution["stats"].get("solution cost", -99)) != cost:
        errors.append("reported_cost_mismatch")
    return errors


def profile_rows(profile, fixtures, weight):
    rows = []
    for item in enumerate(fixtures):
        row = qualification_row(profile, item, weight)
        if row is not None:
            rows.append(row)
    return rows


def failure_count(rows):
    return sum(bool(row["errors"]) for row in rows)


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
        weights = [1.0, 1.1] if profile["family"] == "eecbs" else [1.0]
        for weight in weights:
            current = profile_rows(profile, fixtures, weight)
            rows.extend(current)
            print(
                profile["name"],
                int(profile["setting"][-1]),
                weight,
                len(current),
                "failed",
                failure_count(current),
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
