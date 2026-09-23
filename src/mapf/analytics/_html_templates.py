"""Render packaged standalone report templates without optional GUI dependencies."""

from collections.abc import Mapping
from importlib.resources import files
from string import Template


def render_template(name: str, values: Mapping[str, object]) -> str:
    """Substitute values already encoded for their HTML or JavaScript context."""
    source = (
        files("mapf.analytics").joinpath("templates", name).read_text(encoding="utf-8")
    )
    return Template(source).substitute(values)
