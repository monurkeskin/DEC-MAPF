"""Read-only qualification receipts for historical tables; no inferred identities."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from mapf.application.runs import atomic_write, encode


def quarantine_table(source: Path, destination: Path, source_type: str) -> dict[str, Any]:
    if source_type not in {"historical-empirical", "digitized-reference", "synthetic-demo", "unknown"}:
        raise ValueError("Declare an explicit historical source type")
    if not source.is_file() or source.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Expected a local table no larger than 50 MiB")
    if source.suffix.lower() not in {".csv", ".parquet", ".xlsx"}:
        raise ValueError("Supported historical tables: CSV, Parquet, XLSX")
    # Keep optional dataframe dependencies out of the headless execution core.
    import pandas as pd  # type: ignore[import-untyped]
    if source.suffix.lower() == ".xlsx":
        tables = pd.read_excel(source, sheet_name=None)
    elif source.suffix.lower() == ".parquet":
        tables = {"table": pd.read_parquet(source)}
    else:
        tables = {"table": pd.read_csv(source)}
    if sum(len(t) for t in tables.values()) > 500000:
        raise ValueError("Historical import row limit exceeded")
    data = source.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    folder = destination / sha
    if folder.exists():
        receipt = json.loads((folder / "receipt.json").read_text())
        if receipt["source_type"] != source_type:
            raise ValueError("Source already classified differently; preserve that receipt")
        if hashlib.sha256((folder / source.name).read_bytes()).hexdigest() != sha:
            raise ValueError("Quarantined source checksum mismatch")
        return receipt  # type: ignore[no-any-return]
    receipt = {
        "schema_version": "legacy-quarantine-1", "source_name": source.name,
        "source_sha256": sha, "source_bytes": len(data), "source_type": source_type,
        "status": "quarantined", "eligible_for_current_comparison": False,
        "qualification_required": ["exact map and ordered start/goal records", "effective settings and solver variant",
                                   "source revision and execution identity", "independent trajectory validation",
                                   "metric definitions", "complete planned-trial denominator"],
        "sheets": [{"name": str(name), "rows": len(table), "columns": [str(c) for c in table.columns]}
                   for name, table in tables.items()],
        "scope": "Column names and numerical resemblance cannot establish historical pairing or equivalence",
    }
    folder.mkdir(parents=True, exist_ok=False)
    atomic_write(folder / source.name, data)
    for index, (name, table) in enumerate(tables.items()):
        # Dataframe JSON encodes missing numerical entries as null, not a fabricated zero.
        rows = json.loads(table.to_json(orient="records", date_format="iso"))
        atomic_write(folder / f"sheet-{index}.json", encode({"name": str(name), "rows": rows}))
    atomic_write(folder / "receipt.json", encode(receipt))
    return receipt
