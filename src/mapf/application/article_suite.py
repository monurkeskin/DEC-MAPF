"""Explicit paper profiles and source-bound MovingAI input specifications.

Exact-roster profiles never filter or replace an archived agent. The filtered
prefix builder describes a fresh main-map population, not historical pairing.
No solver executes while an input specification is constructed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mapf.core.geometry import Cell, goal_distances
from mapf.core.models import Point
from mapf.core.movingai import ScenarioRow, parse_movingai_map, parse_movingai_rows


@dataclass(frozen=True)
class _ArticleMap:
    """The physical input shared by roster validation and specification assembly."""

    file: Path
    width: int
    height: int
    obstacles: frozenset[Cell]
    sha256: str
    source_format: str

    @classmethod
    def read(cls, file: Path, *, archive: bool = False) -> _ArticleMap:
        """Keep the raw identity with the topology decoded from those bytes."""
        raw = file.read_bytes()
        text, source_format = (
            _decode_archive_map(raw) if archive else (raw.decode(), "MovingAI-octile")
        )
        width, height, obstacles = parse_movingai_map(text)
        return cls(
            file,
            width,
            height,
            frozenset((p.x, p.y) for p in obstacles),
            hashlib.sha256(raw).hexdigest(),
            source_format,
        )

    def distance(self, start: Point, goal: Point) -> int | None:
        distances = goal_distances(
            self.width, self.height, self.obstacles, (goal.x, goal.y)
        )
        return distances.get((start.x, start.y))

    def contains(self, point: Point) -> bool:
        in_bounds = 0 <= point.x < self.width and 0 <= point.y < self.height
        return in_bounds and (point.x, point.y) not in self.obstacles


def _require_scenario_files(files: list[Path]) -> None:
    if not files or len({file.resolve() for file in files}) != len(files):
        raise ValueError("Provide a nonempty distinct list of scenario files")


def _valid_counts(agents: list[int]) -> bool:
    return bool(agents) and all(1 <= n <= 100 for n in agents)


def _validate_prefix_request(
    scenario_files: list[Path], agents: list[int], fovs: list[int], split: str
) -> None:
    _require_scenario_files(scenario_files)
    if split not in {"development", "held-out"} or not _valid_counts(agents):
        raise ValueError(
            "Declare development or held-out split and agent counts in [1,100]"
        )
    if len(set(agents)) != len(agents) or len(set(fovs)) != len(fovs):
        raise ValueError(
            "Duplicate treatment values would create unintended repetitions"
        )


def _prefix_source(
    file: Path, topology: _ArticleMap, counts: list[int]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = file.read_bytes()
    rows = parse_movingai_rows(raw.decode())
    if not _references_map(rows, topology):
        raise ValueError(f"Scenario references a different map: {file.name}")
    selected, rejected = _eligible_prefix([row.pair for row in rows], topology)
    if len(selected) < max(counts):
        raise ValueError(
            f"{file.name}: only {len(selected)} eligible distinct pairs; need {max(counts)}"
        )
    scenario_sha = hashlib.sha256(raw).hexdigest()
    unit = hashlib.sha256((topology.sha256 + scenario_sha).encode()).hexdigest()
    selections: dict[str, Any] = {}
    scenarios = []
    for count in counts:
        subset = selected[:count]
        selections[str(count)] = [
            {"row": row, "distance": distance} for row, _, _, distance in subset
        ]
        scenarios.append(_prefix_scenario(topology, file, subset, unit))
    source = {
        "file": file.name,
        "sha256": scenario_sha,
        "sampling_unit": unit,
        "eligible_rows": len(selected),
        "selected_prefixes": selections,
        "rejected_rows": rejected,
    }
    return source, scenarios


def _prefix_scenario(
    topology: _ArticleMap,
    file: Path,
    subset: list[tuple[int, Point, Point, int]],
    unit: str,
) -> dict[str, Any]:
    return {
        "name": f"{file.stem}-k{len(subset)}",
        "sampling_unit": unit,
        "grid_width": topology.width,
        "grid_height": topology.height,
        "obstacles": sorted(topology.obstacles),
        "starts": {
            f"agent_{i:03d}": [s.x, s.y] for i, (_, s, _, _) in enumerate(subset)
        },
        "goals": {
            f"agent_{i:03d}": [g.x, g.y] for i, (_, _, g, _) in enumerate(subset)
        },
    }


def article_spec(
    map_file: Path,
    scenario_files: list[Path],
    *,
    agents: list[int],
    fovs: list[int],
    workers: int,
    wall_seconds: float,
    timeout_sec: float,
    split: str,
) -> dict[str, Any]:
    """Build filtered main-map prefixes with explicit clustering and budgets.

    Keyword arguments remain stable for CLI clients. No solver is executed and
    no file is modified; rejected rows are described in the sampling receipt.
    """
    _validate_prefix_request(scenario_files, agents, fovs, split)
    topology = _ArticleMap.read(map_file)
    if topology.width > 16 or topology.height > 16:
        raise ValueError(
            "The 4..24 prefix filter is a main-map convenience; use the appendix-32 exact-roster profile"
        )
    sources, scenarios = [], []
    for file in sorted(scenario_files):
        source, prefixes = _prefix_source(file, topology, agents)
        sources.append(source)
        scenarios.extend(prefixes)
    return {
        "name": f"Article-configured {map_file.stem} {split}",
        "scenarios": scenarios,
        "defaults": _solver_defaults(timeout_sec, 300, "SC"),
        "matrix": _solver_matrix(True, fovs),
        "budget": _execution_budget(workers, wall_seconds, 2048),
        "sampling": {
            "source_type": "MovingAI-import",
            "split": split,
            "population": "Explicit archived MovingAI scenario files after declared geometric eligibility filter",
            "independent_unit": "scenario source file; nested agent prefixes and treatments stay in one cluster",
            "map_file": map_file.name,
            "map_sha256": topology.sha256,
            "sources": sources,
            "selection": "First eligible rows in source order; unique starts/goals; exact 4-connected distance 4..24",
            "repetitions": "One deterministic policy/scheduler execution per treatment; seed repeats are not independent",
            "historical_pairing": "Not established: fresh filtered prefixes, not an exact archived roster import",
            "generalization": "Conditional on this source population and modern variant; no article-score equivalence claim",
        },
    }


def _solver_defaults(
    timeout_sec: float | None, max_steps: int, commitment: str
) -> dict[str, Any]:
    """Shared protocol settings; profile-specific guards remain explicit callers."""
    return {
        "initial_tokens": 5,
        "commitment_type": commitment,
        "max_steps": max_steps,
        "timeout_sec": timeout_sec,
        "recording_level": "metrics-only",
        "random_seed": 20260920,
        "negotiation_protocol": "taop-v2",
        "negotiation_round_limit": 100,
        "verification_pass_limit": 5,
        "max_astar_expansions": 10000,
    }


def _solver_matrix(main: bool, fovs: list[int]) -> dict[str, Any]:
    """Keep the ordered settings shared while admitting the profile's strategies."""
    return {
        "solver_id": ["Decentralized-PathAware", "Decentralized-HeatMap"]
        if main
        else ["Decentralized-HeatMap"],
        "setting": [f"SETTING_{i}" for i in range(1, 5)],
        "fov_size": fovs,
    }


def _execution_budget(
    workers: int, wall_seconds: float, disk_mb: int
) -> dict[str, Any]:
    return {
        "workers": workers,
        "wall_seconds": wall_seconds,
        "max_trials": 100000,
        "disk_mb": disk_mb,
        "threads_per_worker": 1,
    }


def _references_map(rows: list[ScenarioRow], topology: _ArticleMap) -> bool:
    expected = (topology.file.name, topology.width, topology.height)
    return all((row.map_name, row.width, row.height) == expected for row in rows)


def _eligible_prefix(
    pairs: list[tuple[Point, Point]], topology: _ArticleMap
) -> tuple[list[tuple[int, Point, Point, int]], list[dict[str, Any]]]:
    selected: list[tuple[int, Point, Point, int]] = []
    rejected: list[dict[str, Any]] = []
    starts: set[Point] = set()
    goals: set[Point] = set()
    for index, (start, goal) in enumerate(pairs):
        distance = topology.distance(start, goal)
        reason = _prefix_rejection(distance, start in starts or goal in goals)
        if reason is not None:
            rejected.append({"row": index + 1, "reason": reason})
            continue
        assert distance is not None
        starts.add(start)
        goals.add(goal)
        selected.append((index + 1, start, goal, distance))
    return selected, rejected


def _prefix_rejection(distance: int | None, duplicate: bool) -> str | None:
    if distance is None:
        return "unreachable_or_obstacle"
    if not 4 <= distance <= 24:
        return "outside_shortest_4_connected_distance_4_to_24"
    if duplicate:
        return "duplicate_start_or_goal_in_selected_prefix"
    return None


def _validate_archive_request(
    profile: str, split: str, scenario_files: list[Path], max_steps: int
) -> None:
    if profile not in {"main-16", "appendix-32"}:
        raise ValueError("Choose main-16 or appendix-32 explicitly")
    if split not in {"development", "held-out"}:
        raise ValueError("Declare development or held-out split")
    _require_scenario_files([path.resolve() for path in scenario_files])
    if not 1 <= max_steps <= 10000:
        raise ValueError("Explicit step guard must be in [1, 10000]")


def _decode_archive_map(raw: bytes) -> tuple[str, str]:
    text = raw.decode()
    lines = text.splitlines()
    if not lines or not re.fullmatch(r"\d+,\d+", lines[0]):
        return text, "MovingAI-octile"
    width, height = (int(v) for v in lines[0].split(","))
    body = "\n".join(lines[1:])
    text = f"type octile\nheight {height}\nwidth {width}\nmap\n{body}\n"
    return text, "archived-width-height-grid"


def _require_profile_map(topology: _ArticleMap, profile: str) -> None:
    main = profile == "main-16"
    expected = 16 if main else 32
    size_valid = (topology.width, topology.height) == (expected, expected)
    terrain_valid = not main or not topology.obstacles
    if not size_valid or not terrain_valid:
        raise ValueError(
            f"{profile} requires a {expected}x{expected} map"
            + (" without obstacles" if main else "")
        )


def _archive_pairs(
    file: Path, raw: bytes, topology: _ArticleMap, repair: bool
) -> tuple[list[tuple[Point, Point]], list[dict[str, Any]]]:
    # Coordinates use the actual map. A stale declaration must still be
    # explicitly admitted and recorded below; the source bytes stay untouched.
    rows = parse_movingai_rows(
        raw.decode(), coordinate_bounds=(topology.width, topology.height)
    )
    if any(row.map_name != topology.file.name for row in rows):
        raise ValueError(f"Scenario references a different map: {file.name}")
    corrections = _dimension_corrections(rows, topology, file, repair)
    return [row.pair for row in rows], corrections


def _dimension_corrections(
    rows: list[ScenarioRow], topology: _ArticleMap, file: Path, repair: bool
) -> list[dict[str, Any]]:
    corrections = [
        {
            "row": index,
            "declared": list(row.dimensions),
            "map": [topology.width, topology.height],
        }
        for index, row in enumerate(rows, 1)
        if row.dimensions != (topology.width, topology.height)
    ]
    if corrections and not repair:
        raise ValueError(
            f"{file.name}: dimensions disagree with map; explicit repair_dimensions_from_map required"
        )
    return corrections


@dataclass(frozen=True)
class _RosterValidator:
    """Admit an entire source roster atomically; never replace rejected agents."""

    file: Path
    topology: _ArticleMap
    profile: str

    def validate(self, pairs: list[tuple[Point, Point]]) -> list[dict[str, int]]:
        allowed_counts = {20, 40, 60, 80} if self.profile == "main-16" else {80}
        if len(pairs) not in allowed_counts:
            raise ValueError(
                f"{self.file.name}: full roster size is not admitted by {self.profile}"
            )
        starts: set[Point] = set()
        goals: set[Point] = set()
        ordered_rows = []
        for row, (start, goal) in enumerate(pairs, 1):
            if start in starts or goal in goals:
                raise ValueError(
                    f"{self.file.name}: duplicate start or goal at row {row}; roster unchanged"
                )
            distance = self._distance(start, goal, row)
            starts.add(start)
            goals.add(goal)
            ordered_rows.append({"row": row, "distance": distance})
        return ordered_rows

    def _distance(self, start: Point, goal: Point, row: int) -> int:
        if not all(self.topology.contains(p) for p in (start, goal)):
            raise ValueError(f"{self.file.name}: invalid coordinate at row {row}")
        distance = self.topology.distance(start, goal)
        if not _profile_distance_valid(distance, self.profile == "main-16"):
            raise ValueError(
                f"{self.file.name}: row {row} violates {self.profile} reachability/distance requirements; roster unchanged"
            )
        assert distance is not None
        return distance


def _profile_distance_valid(distance: int | None, main: bool) -> bool:
    if distance is None:
        return False
    return not main or 4 <= distance <= 24


def _archive_source(
    file: Path, topology: _ArticleMap, profile: str, repair: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read once; pair raw-byte provenance with the complete admitted roster."""
    raw = file.read_bytes()
    pairs, corrections = _archive_pairs(file, raw, topology, repair)
    ordered_rows = _RosterValidator(file, topology, profile).validate(pairs)
    sha = hashlib.sha256(raw).hexdigest()
    unit = hashlib.sha256((topology.sha256 + sha).encode()).hexdigest()
    scenario = {
        "name": file.stem,
        "sampling_unit": unit,
        "grid_width": topology.width,
        "grid_height": topology.height,
        "obstacles": sorted(topology.obstacles),
        "starts": {f"agent_{i:03d}": [s.x, s.y] for i, (s, _) in enumerate(pairs)},
        "goals": {f"agent_{i:03d}": [g.x, g.y] for i, (_, g) in enumerate(pairs)},
    }
    source = {
        "file": file.name,
        "sha256": sha,
        "sampling_unit": unit,
        "agent_count": len(pairs),
        "ordered_rows": ordered_rows,
        "rejected_rows": [],
        "dimension_corrections": corrections,
    }
    return source, scenario


def archived_article_spec(
    map_file: Path,
    scenario_files: list[Path],
    *,
    profile: str,
    workers: int,
    wall_seconds: float,
    timeout_sec: float | None,
    split: str,
    max_steps: int = 10000,
    repair_dimensions_from_map: bool = False,
) -> dict[str, Any]:
    """Admit complete ordered rosters under distinct main/appendix protocols.

    The scenario's distance column is deliberately ignored: archived files may
    contain Euclidean distances. Four-connected distances are measured from the
    map. Historical experiment identity still requires an external receipt.
    """
    _validate_archive_request(profile, split, scenario_files, max_steps)
    topology = _ArticleMap.read(map_file, archive=True)
    _require_profile_map(topology, profile)
    main = profile == "main-16"
    defaults = _solver_defaults(timeout_sec, max_steps, "SC" if main else "ZC")
    defaults["negotiation_deadline_sec"] = 60.0
    sources: list[dict[str, Any]] = []
    scenarios: list[dict[str, Any]] = []
    for file in sorted(scenario_files):
        source, scenario = _archive_source(
            file, topology, profile, repair_dimensions_from_map
        )
        sources.append(source)
        scenarios.append(scenario)
    return {
        "name": f"Paper {profile}: exact ordered rosters; {split}",
        "scenarios": scenarios,
        "defaults": defaults,
        "matrix": _solver_matrix(main, [5, 7, 9]),
        "budget": _execution_budget(workers, wall_seconds, 8192),
        "sampling": {
            "source_type": "exact-MovingAI-roster",
            "profile": profile,
            "split": split,
            "population": "Explicit complete scenario files; no row filtering or prefix expansion",
            "independent_unit": "ordered scenario roster; all repeated treatments remain paired",
            "map_file": map_file.name,
            "map_sha256": topology.sha256,
            "map_format": topology.source_format,
            "obstacle_count": len(topology.obstacles),
            "obstacle_fraction": len(topology.obstacles)
            / (topology.width * topology.height),
            "sources": sources,
            "selection": "All rows in original order; invalid files reject atomically",
            "distance_rule": "4..24 exact four-connected actions"
            if main
            else "Reachability only; no 16x16 distance filter",
            "distance_column": "Not used; independently recomputed on the four-connected map",
            "repair_dimensions_from_map": repair_dimensions_from_map,
            "repetitions": "One deterministic modern execution per treatment; not five stochastic Java repeats",
            "historical_pairing": "Exact archive roster identity requires a separately recorded archive commit and blob receipt",
            "limits": {
                "process_seconds": timeout_sec,
                "step_guard": max_steps,
                "negotiation_seconds": 60.0,
                "scope": "Modern compute guards; step guard is not a published article parameter",
            },
        },
    }
