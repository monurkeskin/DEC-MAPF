"""Export paired analysis together with the complete planned-trial evidence."""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

from mapf.application.experiments import ExperimentService
from mapf.application.responses import AnalysisRequest
from mapf.application.runs import encode


def experiment_archive(
    service: ExperimentService, experiment_id: str, request: AnalysisRequest
) -> bytes:
    from mapf.analytics.experiment import analyze_experiment, export_analysis

    rows = service.rows(experiment_id)
    result = analyze_experiment(
        rows, request.left, request.right, filters=request.filters
    )
    if (
        request.expected_cohort_sha256
        and request.expected_cohort_sha256 != result["cohort_sha256"]
    ):
        raise ValueError("Experiment outcomes changed; analyze again before exporting")
    buffer = io.BytesIO()
    with tempfile.TemporaryDirectory(prefix="mapf-analysis-") as directory:
        folder = Path(directory)
        (folder / "experiment-manifest.json").write_bytes(
            encode(service.get_manifest(experiment_id))
        )
        (folder / "all-planned-trials.json").write_bytes(encode(rows))
        export_analysis(result, folder)
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(folder.iterdir()):
                archive.write(file, file.name)
    return buffer.getvalue()
