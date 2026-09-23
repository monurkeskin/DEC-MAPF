"""Read-only compatibility access to explicitly present local historical tables."""

from pathlib import Path
from typing import Any

import polars as pl
from fastapi import APIRouter, HTTPException

api = APIRouter()

@api.get("/api/results/{suite_name}")
async def get_archived_results(suite_name: str) -> dict[str, Any]:
    root = Path(__file__).resolve().parent.parent.parent.parent
    res_dir = root / "benchmarks" / "results"
    file_map = {
        "appendix_32x32": res_dir / "appendix_32x32_results.parquet",
        "commitment_types": res_dir / "commitment_types_results.parquet",
        "main_matrix": res_dir / "precise_statistical_audit.parquet",
        "regression_core": res_dir
        / "regression"
        / "regression_core_results.parquet",
    }
    target_file = file_map.get(suite_name)
    if not target_file or not target_file.exists():
        raise HTTPException(
            status_code=404, detail=f"Archived dataset {suite_name} not found"
        )

    df = pl.read_parquet(target_file)
    return {
        "suite_name": suite_name,
        "total_rows": len(df),
        "records": df.to_dicts(),
    }

def _table(caption: str, columns: str, header: str, rows: list[str]) -> str:
    return "\n".join([
        r"\begin{table}[t]", r"\centering", r"\caption{" + caption + "}",
        r"\begin{tabular}{" + columns + "}", r"\toprule", header, r"\midrule",
        *rows, r"\bottomrule", r"\end{tabular}", r"\end{table}",
    ])


def _appendix_table(df: pl.DataFrame) -> str:
    keys = ["map_name", "setting_name", "fov"]
    summary = df.group_by(keys).agg(pl.col("success").mean()).sort(keys)
    rows = [_appendix_row(row) for row in summary.iter_rows(named=True)]
    return _table(r"JAAMAS 2024 Appendix A: $32 \times 32$ Map Success Rates ($k=80$)",
                  "lllr", r"Map & Setting & FoV & Solution Rate (\%) \\", rows)


def _appendix_row(row: dict[str, Any]) -> str:
    name = str(row["map_name"]).replace("_", r"\_")
    setting = str(row["setting_name"]).replace("_", r"\_")
    return f"{name} & {setting} & {row['fov']} & {row['success'] * 100:.1f}\\% \\\\"


def _commitment_table(df: pl.DataFrame) -> str:
    keys = ["setting_name", "commitment", "fov"]
    summary = df.group_by(keys).agg([pl.col("success").mean(), pl.col("norm_path_diff").mean(),
                                     pl.col("negotiations").mean()]).sort(keys)
    rows = [_commitment_row(row) for row in summary.iter_rows(named=True)]
    return _table(r"Section 5.4 Commitment Protocol Comparison ($k=80$)", "lllrrr",
                  r"Setting & Protocol & FoV & Success (\%) & Path Diff (\%) & Negotiations \\", rows)


def _commitment_row(row: dict[str, Any]) -> str:
    setting = str(row["setting_name"]).replace("_", r"\_")
    commitment = str(row["commitment"]).replace("_", r"\_")
    return (f"{setting} & {commitment} & {row['fov']} & {row['success'] * 100:.1f}\\% & "
            f"{row['norm_path_diff']:.2f}\\% & {row['negotiations']:.1f} \\\\")


@api.get("/api/export/latex/{suite_name}")
async def export_latex_table(suite_name: str) -> dict[str, str]:
    root = Path(__file__).resolve().parents[3] / "benchmarks" / "results"
    templates = {"appendix_32x32": _appendix_table, "commitment_types": _commitment_table}
    render = templates.get(suite_name)
    if render is None:
        return {"latex": "% No LaTeX template available for this suite"}
    path = root / f"{suite_name}_results.parquet"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Dataset not ready")
    return {"latex": render(pl.read_parquet(path))}
