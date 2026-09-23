"""Historical compatibility presets; the versioned API supplies current scenarios."""

from typing import Any

from fastapi import APIRouter

api = APIRouter()

@api.get("/api/presets")
async def get_presets() -> list[dict[str, Any]]:
    """Synthetic presets using article-sized grids; original rosters are not loaded."""
    return [
        {
            "id": "preset_empty_32_s2_fov5",
            "name": "Appendix A: empty-32-32 Setting 2 (FoV 5, k=80) [historical configuration; results unqualified]",
            "grid_width": 32,
            "grid_height": 32,
            "agent_count": 80,
            "solver": "HeatMap",
            "compare_solver": "PathAware",
            "commitment_type": "ZC",
            "compare_commitment_type": "ZC",
            "fov_size": 5,
            "obstacle_density": 0.0,
            "setting": 2,
            "random_seed": 42,
        },
        {
            "id": "preset_random_32_10_s4_fov7",
            "name": "Appendix A: random-32-32-10 Setting 4 (FoV 7, k=80) [historical configuration; results unqualified]",
            "grid_width": 32,
            "grid_height": 32,
            "agent_count": 80,
            "solver": "HeatMap",
            "compare_solver": "PathAware",
            "commitment_type": "ZC",
            "compare_commitment_type": "ZC",
            "fov_size": 7,
            "obstacle_density": 0.10,
            "setting": 4,
            "random_seed": 101,
        },
        {
            "id": "preset_commitment_s4_sc_vs_zc",
            "name": "Section 5.4: SC vs. ZC Commitment Comparison (Setting 4, k=80)",
            "grid_width": 16,
            "grid_height": 16,
            "agent_count": 80,
            "solver": "HeatMap",
            "compare_solver": "HeatMap",
            "commitment_type": "SC",
            "compare_commitment_type": "ZC",
            "fov_size": 5,
            "obstacle_density": 0.0,
            "setting": 4,
            "random_seed": 42,
        },
        {
            "id": "preset_dense_scaling_k80",
            "name": "Main Benchmark: 16x16 Setting 4 High Density (k=80, FoV 5)",
            "grid_width": 16,
            "grid_height": 16,
            "agent_count": 80,
            "solver": "HeatMap",
            "compare_solver": "PathAware",
            "commitment_type": "SC",
            "compare_commitment_type": "SC",
            "fov_size": 5,
            "obstacle_density": 0.0,
            "setting": 4,
            "random_seed": 137,
        },
    ]
