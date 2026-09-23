import datetime
import json
from pathlib import Path
from typing import Any

import polars as pl


class ExperimentLogger:
    """Append descriptive run records to JSONL and export them through Polars.

    Caller-supplied values are retained without independent qualification.
    Use the experiment service for planned denominators and paired analysis."""

    def __init__(self, log_dir: str | Path = "runs", stream_jsonl: bool = True) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.stream_jsonl = stream_jsonl
        self.jsonl_path = self.log_dir / "experiment_runs.jsonl"
        self._records: list[dict[str, Any]] = []

    def log_run(
        self,
        scenario_id: str,
        setting: int,
        agent_type: str,
        agent_count: int,
        grid_size: int,
        fov_size: int,
        success: bool,
        total_steps: int,
        negotiation_count: int,
        successful_negotiations: int,
        total_path_length: int,
        information_sharing_rate: float,
        seed: int = 42,
        runtime_ms: float = 0.0,
        normalized_path_diff: float = 0.0,
        extra_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "scenario_id": scenario_id,
            "setting": setting,
            "agent_type": agent_type,
            "agent_count": agent_count,
            "grid_size": grid_size,
            "fov_size": fov_size,
            "seed": seed,
            "success": success,
            "total_steps": total_steps,
            "negotiation_count": negotiation_count,
            "successful_negotiations": successful_negotiations,
            "total_path_length": total_path_length,
            "information_sharing_rate": information_sharing_rate,
            "normalized_path_diff": normalized_path_diff,
            "runtime_ms": runtime_ms,
        }
        if extra_metadata:
            record.update(extra_metadata)

        if self.stream_jsonl:
            serialized = json.dumps(record) + "\n"
            with open(self.jsonl_path, "a", encoding="utf-8") as f:
                f.write(serialized)

        self._records.append(record)
        return record

    def to_polars(self) -> pl.DataFrame:
        if not self._records:
            return pl.DataFrame()
        return pl.DataFrame(self._records)

    def save(self, filename: str = "experiment_results.parquet") -> Path:
        df = self.to_polars()
        output_path = self.log_dir / filename
        if filename.endswith(".parquet"):
            df.write_parquet(output_path)
        else:
            df.write_csv(output_path)
        return output_path

    def summarize_by_strategy(self) -> pl.DataFrame:
        df = self.to_polars()
        if df.is_empty():
            return pl.DataFrame()

        return (
            df.group_by(["setting", "agent_type", "agent_count", "fov_size"])
            .agg(
                [
                    pl.col("success").mean().alias("solution_rate"),
                    pl.col("total_steps").mean().alias("avg_makespan"),
                    pl.col("negotiation_count").mean().alias("avg_negotiations"),
                    pl.col("information_sharing_rate").mean().alias("avg_is_rate"),
                    pl.col("normalized_path_diff").mean().alias("avg_norm_diff"),
                    pl.col("runtime_ms").mean().alias("avg_runtime_ms"),
                ]
            )
            .sort(["setting", "agent_type", "agent_count"])
        )

    def print_summary_table(self) -> None:
        """Print grouped descriptive means using Rich when available."""
        summary = self.summarize_by_strategy()
        if summary.is_empty():
            print("[ExperimentLogger] No records logged yet.")
            return

        try:
            from rich.console import Console
            from rich.table import Table

            console = Console()
            table = Table(title="DEC-MAPF Benchmark Summary", header_style="bold cyan")
            table.add_column("Setting", justify="center")
            table.add_column("Strategy", justify="left")
            table.add_column("Agents (k)", justify="right")
            table.add_column("FoV", justify="right")
            table.add_column("Success Rate", justify="right")
            table.add_column("Makespan", justify="right")
            table.add_column("Negotiations", justify="right")
            table.add_column("IS Rate", justify="right")
            table.add_column("Norm Diff", justify="right")
            table.add_column("Time (ms)", justify="right")

            for row in summary.iter_rows(named=True):
                table.add_row(
                    str(row["setting"]),
                    str(row["agent_type"]),
                    str(row["agent_count"]),
                    str(row["fov_size"]),
                    f"{row['solution_rate']*100:.1f}%",
                    f"{row['avg_makespan']:.1f}",
                    f"{row['avg_negotiations']:.1f}",
                    f"{row['avg_is_rate']*100:.1f}%",
                    f"{row['avg_norm_diff']*100:.2f}%",
                    f"{row['avg_runtime_ms']:.1f}",
                )
            console.print(table)
        except ImportError:
            print(summary)
