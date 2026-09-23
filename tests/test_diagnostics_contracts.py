"""Missing telemetry is not a measured zero or successful negotiation."""
import argparse
import json
from html.parser import HTMLParser

import polars as pl
import pytest

from mapf.analytics.diagnostics_report import generate_html_report
from mapf.analytics.post_simulation import (
    analyze_rejection_reasons,
    compute_agent_wait_dynamics,
    compute_token_inequality_gini,
)
from mapf.cli import diagnostics_command


@pytest.mark.parametrize('analyze,metric', [
    (analyze_rejection_reasons, 'success_rate'),
    (compute_agent_wait_dynamics, 'mean_wait_ratio'),
    (compute_token_inequality_gini, 'gini_coefficient'),
])
def test_unobserved_population_has_no_numeric_estimate(analyze, metric):
    result = analyze(pl.DataFrame())
    assert result['available'] is False
    assert result[metric] is None


def test_observed_no_waits_and_no_transfers_are_valid_zeros():
    events = pl.DataFrame([{'event_type': 'MOVE', 'agent_id': 'a', 'is_waiting': False}])
    assert compute_agent_wait_dynamics(events)['mean_wait_ratio'] == 0
    assert compute_token_inequality_gini(events, agent_ids=['a', 'b'])['gini_coefficient'] == 0


def test_legacy_session_diagnostics_report_unavailable_balances_without_crashing(tmp_path, capsys):
    events = tmp_path / 'legacy.jsonl'
    events.write_text(json.dumps({'event_type': 'NEGO_SESSION', 'outcome': 'AGREED',
                                  'conflict_x': 0, 'conflict_y': 0}) + '\n')
    output = tmp_path / 'diagnostics.html'
    args = argparse.Namespace(events=str(events), output=str(output), grid=2)
    assert diagnostics_command(args) == 0
    assert 'Unavailable' in capsys.readouterr().out
    assert output.is_file()
    assert '100.0%' in output.read_text()  # One actually observed agreement.


def test_empty_diagnostics_do_not_invent_rates_or_token_balances(tmp_path):
    output = tmp_path / 'empty.html'
    generate_html_report('empty', {}, {'density_matrix': [[0]]}, {}, {}, {}, {}, [], 1, 1, output)
    text = output.read_text()
    assert '100.0%' not in text
    assert 'Min Tokens: <strong>5</strong>' not in text
    assert 'No negotiation sessions recorded' in text


def test_report_renders_identifiers_and_rejection_reasons_as_text(tmp_path):
    attack = '<script>window.untrusted = true</script>'
    output = tmp_path / 'escaped.html'
    generate_html_report(attack, {'git_commit': attack, 'setting': attack},
                         {'density_matrix': [[0]]}, {}, {}, {},
                         {'total_sessions': 1, 'success_rate': 0, 'breakdown': {attack: 1}},
                         [], 1, 1, output)
    tags = []

    class Tags(HTMLParser):
        def handle_starttag(self, tag, attrs):
            tags.append(tag)

    Tags().feed(output.read_text())
    assert 'script' not in tags
    assert '&lt;script&gt;' in output.read_text()
