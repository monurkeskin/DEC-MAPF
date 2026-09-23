"""Names in trajectory exports are data and cannot terminate the replay script."""

from html.parser import HTMLParser

from mapf.analytics.visualizer import export_trajectory_html
from mapf.core.models import Path, Point
from mapf.solvers.base import MAPFSolution


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        self.scripts += tag == "script"


def test_names_remain_inert_in_standalone_replay(tmp_path):
    name = "</script><script>alert(1)</script>"
    solution = MAPFSolution(
        solver_name=name,
        is_centralized=True,
        success=True,
        paths={name: Path(points=[Point(0, 0), Point(1, 0)])},
        makespan=1,
    )
    output = export_trajectory_html(solution, 2, 1, set(), tmp_path / "replay.html")
    markup = output.read_text()
    tags = Tags()
    tags.feed(markup)
    assert tags.scripts == 1
    assert name not in markup
    assert "&lt;/script&gt;" in markup
    assert r"\u003c/script>" in markup
