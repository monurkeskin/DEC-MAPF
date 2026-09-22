"""Explicit paper profiles and source-bound MovingAI input specifications.

Exact-roster profiles never filter or replace an archived agent. The older
prefix builder describes a fresh main-map population, not historical pairing.
No solver executes while an input specification is constructed.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from mapf.core.geometry import goal_distances
from mapf.core.movingai import parse_movingai_map, parse_movingai_scen


def article_spec(map_file: Path, scenario_files: list[Path], *, agents: list[int],
                 fovs: list[int], workers: int, wall_seconds: float, timeout_sec: float,
                 split: str) -> dict[str, Any]:
    if not scenario_files or len(set(scenario_files)) != len(scenario_files):
        raise ValueError("Provide a nonempty distinct list of scenario files")
    if split not in {"development", "held-out"} or not agents or any(not 1 <= n <= 100 for n in agents):
        raise ValueError("Declare development or held-out split and agent counts in [1,100]")
    if len(set(agents)) != len(agents) or len(set(fovs)) != len(fovs):
        raise ValueError("Duplicate treatment values would create unintended repetitions")
    map_data = map_file.read_bytes()
    width, height, obstacles = parse_movingai_map(map_data.decode())
    if width > 16 or height > 16:
        raise ValueError("The 4..24 prefix filter is a main-map convenience; use the appendix-32 exact-roster profile")
    obs = frozenset((p.x, p.y) for p in obstacles)
    map_sha = hashlib.sha256(map_data).hexdigest()
    sources, scenarios = [], []
    for file in sorted(scenario_files):
        raw = file.read_bytes()
        pairs = parse_movingai_scen(raw.decode())
        rows = [r.split() for r in raw.decode().splitlines()[1:] if r.strip() and not r.startswith('#')]
        if len(rows) != len(pairs) or any(r[1] != map_file.name or (int(r[2]), int(r[3])) != (width, height) for r in rows):
            raise ValueError(f"Scenario references a different map: {file.name}")
        selected, rejected = [], []
        starts, goals = set(), set()
        for index, (start, goal) in enumerate(pairs):
            distance = goal_distances(width, height, obs, (goal.x, goal.y)).get((start.x, start.y))
            reason = None
            if distance is None:
                reason = "unreachable_or_obstacle"
            elif not 4 <= distance <= 24:
                reason = "outside_shortest_4_connected_distance_4_to_24"
            elif start in starts or goal in goals:
                reason = "duplicate_start_or_goal_in_selected_prefix"
            if reason:
                rejected.append({"row": index + 1, "reason": reason})
                continue
            starts.add(start); goals.add(goal)
            selected.append((index + 1, start, goal, distance))
        if len(selected) < max(agents):
            raise ValueError(f"{file.name}: only {len(selected)} eligible distinct pairs; need {max(agents)}")
        scenario_sha = hashlib.sha256(raw).hexdigest()
        unit = hashlib.sha256((map_sha + scenario_sha).encode()).hexdigest()
        selections = {}
        for count in agents:
            subset = selected[:count]
            selections[str(count)] = [{"row": row, "distance": distance} for row, _, _, distance in subset]
            scenarios.append({"name": f"{file.stem}-k{count}", "sampling_unit": unit,
                              "grid_width": width, "grid_height": height,
                              "obstacles": sorted(obs),
                              "starts": {f"agent_{i:03d}": [s.x, s.y] for i, (_, s, _, _) in enumerate(subset)},
                              "goals": {f"agent_{i:03d}": [g.x, g.y] for i, (_, _, g, _) in enumerate(subset)}})
        sources.append({"file": file.name, "sha256": scenario_sha, "sampling_unit": unit,
                        "eligible_rows": len(selected), "selected_prefixes": selections, "rejected_rows": rejected})
    return {
        "name": f"Article-configured {map_file.stem} {split}", "scenarios": scenarios,
        "defaults": {"initial_tokens": 5, "commitment_type": "SC", "max_steps": 300,
                     "timeout_sec": timeout_sec, "recording_level": "metrics-only", "random_seed": 20260920,
                     "negotiation_protocol": "taop-v2",
                     "negotiation_round_limit": 100,
                     "verification_pass_limit": 5, "max_astar_expansions": 10000},
        "matrix": {"solver_id": ["Decentralized-PathAware", "Decentralized-HeatMap"],
                   "setting": [f"SETTING_{i}" for i in range(1, 5)], "fov_size": fovs},
        "budget": {"workers": workers, "wall_seconds": wall_seconds, "max_trials": 100000,
                   "disk_mb": 2048, "threads_per_worker": 1},
        "sampling": {"source_type": "MovingAI-import", "split": split,
                     "population": "Explicit archived MovingAI scenario files after declared geometric eligibility filter",
                     "independent_unit": "scenario source file; nested agent prefixes and treatments stay in one cluster",
                     "map_file": map_file.name, "map_sha256": map_sha, "sources": sources,
                     "selection": "First eligible rows in source order; unique starts/goals; exact 4-connected distance 4..24",
                     "repetitions": "One deterministic policy/scheduler execution per treatment; seed repeats are not independent",
                     "historical_pairing": "Not established: fresh filtered prefixes, not an exact archived roster import",
                     "generalization": "Conditional on this source population and modern variant; no article-score equivalence claim"},
    }


def archived_article_spec(map_file: Path, scenario_files: list[Path], *, profile: str,
                          workers: int, wall_seconds: float, timeout_sec: float | None,
                          split: str, max_steps: int = 10000,
                          repair_dimensions_from_map: bool = False) -> dict[str, Any]:
    """Admit complete ordered rosters under distinct main/appendix protocols.

The scenario's distance column is deliberately ignored: archived files may
contain Euclidean distances. Four-connected distances are measured from the map.
Historical authorship/experiment identity still requires an external receipt.
"""
    if profile not in {"main-16", "appendix-32"}:
        raise ValueError("Choose main-16 or appendix-32 explicitly")
    if split not in {"development", "held-out"}:
        raise ValueError("Declare development or held-out split")
    if not scenario_files or len({p.resolve() for p in scenario_files}) != len(scenario_files):
        raise ValueError("Provide a nonempty distinct list of scenario files")
    if not 1 <= max_steps <= 10000:
        raise ValueError("Explicit step guard must be in [1, 10000]")
    raw_map = map_file.read_bytes()
    map_text = raw_map.decode()
    map_format = "MovingAI-octile"
    lines = map_text.splitlines()
    if lines and re.fullmatch(r"\d+,\d+", lines[0]):
        # Historical empty maps use a width,height header; preserve raw bytes
        # and apply the same rectangular-body/terrain validator after decoding.
        w, h = (int(v) for v in lines[0].split(','))
        map_text = f"type octile\nheight {h}\nwidth {w}\nmap\n" + '\n'.join(lines[1:]) + '\n'
        map_format = "archived-width-height-grid"
    width, height, obstacles = parse_movingai_map(map_text)
    main = profile == "main-16"
    expected = 16 if main else 32
    if (width, height) != (expected, expected) or (main and obstacles):
        raise ValueError(f"{profile} requires a {expected}x{expected} map" + (" without obstacles" if main else ""))
    obs = frozenset((p.x, p.y) for p in obstacles)
    map_sha = hashlib.sha256(raw_map).hexdigest()
    sources: list[dict[str, Any]] = []
    scenarios: list[dict[str, Any]] = []
    for file in sorted(scenario_files):
        raw = file.read_bytes()
        rows = [r.split() for r in raw.decode().splitlines()[1:] if r.strip() and not r.lstrip().startswith('#')]
        if any(len(r) != 9 for r in rows):
            raise ValueError(f"{file.name}: scenario rows require nine columns")
        if any(r[1] != map_file.name for r in rows):
            raise ValueError(f"Scenario references a different map: {file.name}")
        corrections = []
        for index, row in enumerate(rows):
            declared = (int(row[2]), int(row[3]))
            if declared != (width, height):
                if not repair_dimensions_from_map:
                    raise ValueError(f"{file.name}: dimensions disagree with map; explicit repair_dimensions_from_map required")
                corrections.append({"row": index + 1, "declared": list(declared), "map": [width, height]})
                row[2:4] = [str(width), str(height)]
        header = raw.decode().splitlines()[0] if raw else ''
        pairs = parse_movingai_scen(header + '\n' + '\n'.join('\t'.join(row) for row in rows))
        if len(pairs) not in ({20, 40, 60, 80} if main else {80}):
            raise ValueError(f"{file.name}: full roster size is not admitted by {profile}")
        starts, goals = set(), set()
        ordered_rows = []
        for index, (start, goal) in enumerate(pairs):
            if start in starts or goal in goals:
                raise ValueError(f"{file.name}: duplicate start or goal at row {index + 1}; roster unchanged")
            if any(not (0 <= p.x < width and 0 <= p.y < height) or (p.x, p.y) in obs for p in (start, goal)):
                raise ValueError(f"{file.name}: invalid coordinate at row {index + 1}")
            distance = goal_distances(width, height, obs, (goal.x, goal.y)).get((start.x, start.y))
            if distance is None or (main and not 4 <= distance <= 24):
                raise ValueError(f"{file.name}: row {index + 1} violates {profile} reachability/distance requirements; roster unchanged")
            starts.add(start)
            goals.add(goal)
            ordered_rows.append({"row": index + 1, "distance": distance})
        sha = hashlib.sha256(raw).hexdigest()
        unit = hashlib.sha256((map_sha + sha).encode()).hexdigest()
        scenarios.append({"name": file.stem, "sampling_unit": unit,
                          "grid_width": width, "grid_height": height, "obstacles": sorted(obs),
                          "starts": {f"agent_{i:03d}": [s.x, s.y] for i, (s, _) in enumerate(pairs)},
                          "goals": {f"agent_{i:03d}": [g.x, g.y] for i, (_, g) in enumerate(pairs)}})
        sources.append({"file": file.name, "sha256": sha, "sampling_unit": unit,
                        "agent_count": len(pairs), "ordered_rows": ordered_rows, "rejected_rows": [],
                        "dimension_corrections": corrections})
    return {
        "name": f"Paper {profile}: exact ordered rosters; {split}", "scenarios": scenarios,
        "defaults": {"initial_tokens": 5, "commitment_type": "SC" if main else "ZC",
                     "max_steps": max_steps, "timeout_sec": timeout_sec,
                     "negotiation_deadline_sec": 60.0,
                     "recording_level": "metrics-only", "random_seed": 20260920,
                     "negotiation_protocol": "taop-v2",
                     "negotiation_round_limit": 100,
                     "verification_pass_limit": 5, "max_astar_expansions": 10000},
        "matrix": {"solver_id": ["Decentralized-PathAware", "Decentralized-HeatMap"] if main else ["Decentralized-HeatMap"],
                   "setting": [f"SETTING_{i}" for i in range(1, 5)], "fov_size": [5, 7, 9]},
        "budget": {"workers": workers, "wall_seconds": wall_seconds, "max_trials": 100000,
                   "disk_mb": 8192, "threads_per_worker": 1},
        "sampling": {"source_type": "exact-MovingAI-roster", "profile": profile, "split": split,
                     "population": "Explicit complete scenario files; no row filtering or prefix expansion",
                     "independent_unit": "ordered scenario roster; all repeated treatments remain paired",
                     "map_file": map_file.name, "map_sha256": map_sha,
                     "map_format": map_format,
                     "obstacle_count": len(obs), "obstacle_fraction": len(obs) / (width * height),
                     "sources": sources, "selection": "All rows in original order; invalid files reject atomically",
                     "distance_rule": "4..24 exact four-connected actions" if main else "Reachability only; no 16x16 distance filter",
                     "distance_column": "Not used; independently recomputed on the four-connected map",
                     "repair_dimensions_from_map": repair_dimensions_from_map,
                     "repetitions": "One deterministic modern execution per treatment; not five stochastic Java repeats",
                     "historical_pairing": "Exact archive roster identity requires a separately recorded archive commit and blob receipt",
                     "limits": {"process_seconds": timeout_sec, "step_guard": max_steps,
                                "negotiation_seconds": 60.0,
                                "scope": "Modern compute guards; step guard is not a published article parameter"}},
    }
