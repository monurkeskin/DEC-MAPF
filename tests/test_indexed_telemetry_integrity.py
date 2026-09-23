"""Indexed event streams must reject inconsistent references and sequence gaps."""

import gzip
import hashlib
import json

import polars as pl
import pytest

from mapf.analytics.post_simulation import (
    compute_spatial_hotspots,
    compute_token_inequality_gini,
    load_events_as_polars,
)


@pytest.mark.parametrize(("change", "message"), [
    ("path", "Unsafe"), ("count", "count mismatch"),
    ("total", "sequence is incomplete"), ("sequence", "sequence is incomplete"),
])
def test_valid_checksum_does_not_hide_invalid_index(tmp_path, change, message):
    sequence = 2 if change == "sequence" else 1
    raw = gzip.compress(json.dumps({"sequence": sequence, "event_type": "MOVE"}).encode())
    (tmp_path / "part.jsonl.gz").write_bytes(raw)
    chunk = {"file": "part.jsonl.gz", "sha256": hashlib.sha256(raw).hexdigest(), "count": 1}
    if change == "path":
        chunk["file"] = "../part.jsonl.gz"
    if change == "count":
        chunk["count"] = 2
    index = {"events": 2 if change == "total" else 1, "chunks": [chunk]}
    (tmp_path / "index.json").write_text(json.dumps(index))
    with pytest.raises(ValueError, match=message):
        load_events_as_polars(tmp_path)


@pytest.mark.parametrize("receipt", [
    {"balances_before": {"a": 4, "b": 6}, "balances_after": {"a": 3, "b": 7}},
    {"balances_before": {"a": 5, "b": 5}, "balances_after": {"a": 4, "b": 7}},
])
def test_token_reconstruction_refuses_inconsistent_receipts(receipt):
    frame = pl.DataFrame([dict(receipt, event_type="TOKEN_TRANSFER")])
    with pytest.raises(ValueError):
        compute_token_inequality_gini(frame, agent_ids=["a", "b"])


def test_zero_token_roster_has_zero_inequality_without_fabricated_transfers():
    result = compute_token_inequality_gini(pl.DataFrame(), initial_tokens=0, agent_ids=["a", "b"])
    assert result["balances"] == {"a": 0, "b": 0} and result["gini_coefficient"] == 0


def test_out_of_bounds_conflicts_do_not_wrap_into_density_grid():
    frame = pl.DataFrame([{"event_type": "NEGO_SESSION", "conflict_x": x, "conflict_y": 0}
                          for x in (-1, 1, 4)])
    result = compute_spatial_hotspots(frame, 4, 2)
    assert result["total_conflicts"] == 3
    assert result["top_chokepoints"] == [{"x": 1, "y": 0, "conflicts": 1}]
