"""Read-only qualification receipts for historical tables; no inferred identities."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

from mapf.application.runs import RunRepository, atomic_write, encode


def quarantine_text(repository: RunRepository, name: str, content: str) -> dict[str, Any]:
    """Keep unqualified uploaded text outside current run and comparison stores."""
    raw = content.encode()
    sha = hashlib.sha256(raw).hexdigest()
    repository.ensure_space(len(raw) + 1000)
    archive_dir = repository.base_dir / "legacy"
    archive_dir.mkdir(exist_ok=True)
    atomic_write(archive_dir / f"{sha}.txt", raw)
    return {
        "sha256": sha,
        "bytes": len(raw),
        "name": name,
        "status": "quarantined",
        "missing": [
            "verified instance identity", "effective config", "code revision",
            "independent validation",
        ],
    }


def _source_snapshot(source: Path, source_type: str) -> bytes:
    """Read once so parsed rows and archived bytes have the same identity."""
    if source_type not in {"historical-empirical", "digitized-reference", "synthetic-demo", "unknown"}:
        raise ValueError("Declare an explicit historical source type")
    if not source.is_file() or source.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Expected a local table no larger than 50 MiB")
    if source.suffix.lower() not in {".csv", ".parquet", ".xlsx"}:
        raise ValueError("Supported historical tables: CSV, Parquet, XLSX")
    with source.open("rb") as stream:
        data = stream.read(50 * 1024 * 1024 + 1)
    if len(data) > 50 * 1024 * 1024:
        raise ValueError("Expected a local table no larger than 50 MiB")
    return data


def _read_tables(data: bytes, suffix: str) -> dict[str, Any]:
    # Keep optional dataframe dependencies out of the headless execution core.
    import pandas as pd  # type: ignore[import-untyped]
    stream = io.BytesIO(data)
    if suffix == ".xlsx":
        tables = pd.read_excel(stream, sheet_name=None)
    elif suffix == ".parquet":
        tables = {"table": pd.read_parquet(stream)}
    else:
        tables = {"table": pd.read_csv(stream)}
    if sum(len(t) for t in tables.values()) > 500000:
        raise ValueError("Historical import row limit exceeded")
    return dict(tables)


def _existing_receipt(folder: Path, source_type: str, sha: str) -> dict[str, Any]:
    receipt = json.loads((folder / "receipt.json").read_text())
    if receipt["source_type"] != source_type:
        raise ValueError("Source already classified differently; preserve that receipt")
    name = receipt["source_name"]
    if Path(name).name != name:
        raise ValueError("Invalid quarantined source name")
    if hashlib.sha256((folder / name).read_bytes()).hexdigest() != sha:
        raise ValueError("Quarantined source checksum mismatch")
    return dict(receipt)


def _table_receipt(source: Path, source_type: str, data: bytes, tables: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "legacy-quarantine-1", "source_name": source.name,
        "source_sha256": hashlib.sha256(data).hexdigest(), "source_bytes": len(data), "source_type": source_type,
        "status": "quarantined", "eligible_for_current_comparison": False,
        "qualification_required": ["exact map and ordered start/goal records", "effective settings and solver variant",
                                   "source revision and execution identity", "independent trajectory validation",
                                   "metric definitions", "complete planned-trial denominator"],
        "sheets": [{"name": str(name), "rows": len(table), "columns": [str(c) for c in table.columns]}
                   for name, table in tables.items()],
        "scope": "Column names and numerical resemblance cannot establish historical pairing or equivalence",
    }


def quarantine_table(source: Path, destination: Path, source_type: str) -> dict[str, Any]:
    data = _source_snapshot(source, source_type)
    sha = hashlib.sha256(data).hexdigest()
    folder = destination / sha
    if folder.exists():
        return _existing_receipt(folder, source_type, sha)
    tables = _read_tables(data, source.suffix.lower())
    receipt = _table_receipt(source, source_type, data, tables)
    folder.mkdir(parents=True, exist_ok=False)
    atomic_write(folder / source.name, data)
    for index, (name, table) in enumerate(tables.items()):
        # Dataframe JSON encodes missing numerical entries as null, not a fabricated zero.
        rows = json.loads(table.to_json(orient="records", date_format="iso"))
        atomic_write(folder / f"sheet-{index}.json", encode({"name": str(name), "rows": rows}))
    atomic_write(folder / "receipt.json", encode(receipt))
    return receipt
