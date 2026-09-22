"""Keep scientific execution independent of transport and optional GUI libraries."""
import ast
from pathlib import Path


def test_domain_and_application_do_not_import_gui_or_transport():
    root = Path(__file__).resolve().parents[1] / 'src/mapf'
    violations = []
    for layer in ['core', 'engine', 'agents', 'negotiation', 'telemetry', 'application']:
        for source in (root / layer).rglob('*.py'):
            tree = ast.parse(source.read_text())
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.level:
                        package = ['mapf', *source.relative_to(root).parts[:-1]]
                        modules = ['.'.join(package[:len(package) - node.level + 1] + node.module.split('.'))]
                    else:
                        modules = [node.module]
                forbidden = ('mapf.gui', 'fastapi', 'uvicorn')
                if layer != 'application':
                    forbidden += ('mapf.application',)
                for module in modules:
                    if any(module == prefix or module.startswith(prefix + '.') for prefix in forbidden):
                        violations.append(f'{source.relative_to(root)}:{node.lineno} imports {module}')
    assert not violations, '\n'.join(violations)


def test_core_import_does_not_initialize_workspace_persistence():
    import subprocess
    import sys

    result = subprocess.run([sys.executable, '-c',
        ('import sys; import mapf; import mapf.telemetry; '
        'assert "mapf.application.runs" not in sys.modules; '
        'assert "sqlite3" not in sys.modules')], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
