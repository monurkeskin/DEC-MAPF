import os
import subprocess
import sys

_ENV = dict(os.environ, PYTHONPATH=f"src{os.pathsep}{os.environ.get('PYTHONPATH', '')}")


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "mapf", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=_ENV,
    )
    assert result.returncode == 0
    assert "DEC-MAPF" in result.stdout
    assert "solve" in result.stdout
    assert "dashboard" in result.stdout
    assert "verify" in result.stdout


def test_cli_solve_success():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mapf",
            "solve",
            "--solver",
            "HeatMap",
            "--agents",
            "2",
            "--grid",
            "8",
            "--setting",
            "4",
            "--seed",
            "42",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_ENV,
    )
    assert result.returncode == 0
    assert "Success:                  YES" in result.stdout
    assert "Solved Agents:            2 / 2" in result.stdout
