"""Keep scientific execution independent of transport and optional GUI libraries."""

import ast
from pathlib import Path


def imported_modules(node, package):
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    if not node.level:
        return [node.module] if node.module else []
    parent = package[: len(package) - node.level + 1]
    if node.module:
        return [".".join(parent + node.module.split("."))]
    return [".".join(parent + [alias.name]) for alias in node.names]


def boundary_violations(source, root, layer):
    forbidden = ("mapf.gui", "fastapi", "uvicorn")
    if layer != "application":
        forbidden += ("mapf.application",)
    package = ["mapf", *source.relative_to(root).parts[:-1]]
    violations = []
    for node in ast.walk(ast.parse(source.read_text())):
        for module in imported_modules(node, package):
            if any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in forbidden
            ):
                violations.append(
                    f"{source.relative_to(root)}:{node.lineno} imports {module}"
                )
    return violations


def test_domain_and_application_do_not_import_gui_or_transport():
    root = Path(__file__).resolve().parents[1] / "src/mapf"
    violations = []
    for layer in [
        "core",
        "engine",
        "agents",
        "negotiation",
        "telemetry",
        "application",
    ]:
        for source in (root / layer).rglob("*.py"):
            violations.extend(boundary_violations(source, root, layer))
    assert not violations, "\n".join(violations)


def test_core_import_does_not_initialize_workspace_persistence():
    import subprocess
    import sys
    import sysconfig

    # Coverage imports SQLite itself. Disable startup hooks while retaining the
    # declared dependencies, so the probe observes only the application's imports.
    import_paths = list(
        dict.fromkeys(
            [
                str(Path(__file__).resolve().parents[1] / "src"),
                sysconfig.get_path("purelib"),
                sysconfig.get_path("platlib"),
            ]
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            (
                f"import sys; sys.path[:0] = {import_paths!r}; "
                "import mapf; import mapf.telemetry; "
                'assert "mapf.application.runs" not in sys.modules; '
                'assert "sqlite3" not in sys.modules'
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
