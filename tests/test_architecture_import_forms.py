"""The architectural gate must recognize equivalent absolute and relative imports."""

import pytest

from tests import test_architecture_boundaries as gate


@pytest.mark.parametrize(
    "statement",
    [
        "import mapf.gui",
        "from .. import gui",
        "from .. import application",
        "from ..application import jobs",
    ],
)
def test_relative_aliases_cannot_bypass_the_domain_boundary(
    tmp_path, monkeypatch, statement
):
    source = tmp_path / "src/mapf/core/example.py"
    source.parent.mkdir(parents=True)
    source.write_text(statement + "\n")
    monkeypatch.setattr(gate, "__file__", str(tmp_path / "tests/gate.py"))
    with pytest.raises(AssertionError, match="imports mapf."):
        gate.test_domain_and_application_do_not_import_gui_or_transport()


def test_relative_domain_import_is_allowed(tmp_path, monkeypatch):
    source = tmp_path / "src/mapf/core/example.py"
    source.parent.mkdir(parents=True)
    source.write_text("from . import models\n")
    monkeypatch.setattr(gate, "__file__", str(tmp_path / "tests/gate.py"))
    gate.test_domain_and_application_do_not_import_gui_or_transport()
