"""Historical imports must bind normalized rows to one immutable byte snapshot."""

import hashlib
import json

import pandas as pd
import pytest

from mapf.application.legacy import quarantine_table


def test_source_replacement_during_parse_cannot_change_archived_evidence(tmp_path, monkeypatch):
    source = tmp_path / "source.csv"
    original = b"cost\n7\n"
    source.write_bytes(original)
    read_csv = pd.read_csv

    def replace_after_read(*args, **kwargs):
        frame = read_csv(*args, **kwargs)
        source.write_bytes(b"cost\n999\n")
        return frame

    monkeypatch.setattr(pd, "read_csv", replace_after_read)
    receipt = quarantine_table(source, tmp_path / "archive", "historical-empirical")
    folder = tmp_path / "archive" / receipt["source_sha256"]
    assert receipt["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert (folder / "source.csv").read_bytes() == original
    assert json.loads((folder / "sheet-0.json").read_text())["rows"] == [{"cost": 7}]


def test_content_addressed_reimport_accepts_a_renamed_source(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("cost\n7\n")
    destination = tmp_path / "archive"
    receipt = quarantine_table(source, destination, "unknown")
    renamed = tmp_path / "renamed.csv"
    source.rename(renamed)
    assert quarantine_table(renamed, destination, "unknown") == receipt
    assert not (destination / receipt["source_sha256"] / renamed.name).exists()


@pytest.mark.parametrize(("name", "kind", "message"), [
    ("data.csv", "inferred", "explicit historical"),
    ("missing.csv", "unknown", "local table"),
    ("data.txt", "unknown", "Supported historical"),
])
def test_invalid_import_is_rejected_without_creating_archive(tmp_path, name, kind, message):
    for filename in ("data.csv", "data.txt"):
        (tmp_path / filename).write_text("cost\n7\n")
    with pytest.raises(ValueError, match=message):
        quarantine_table(tmp_path / name, tmp_path / "archive", kind)
    assert not (tmp_path / "archive").exists()


def test_row_limit_rejects_import_before_persistence(tmp_path, monkeypatch):
    source = tmp_path / "source.csv"
    source.write_text("cost\n7\n")
    monkeypatch.setattr(pd, "read_csv", lambda *args, **kwargs: pd.DataFrame(index=range(500001)))
    with pytest.raises(ValueError, match="row limit"):
        quarantine_table(source, tmp_path / "archive", "unknown")
    assert not (tmp_path / "archive").exists()


def test_reimport_detects_corruption_of_original_bytes(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("cost\n7\n")
    destination = tmp_path / "archive"
    receipt = quarantine_table(source, destination, "unknown")
    (destination / receipt["source_sha256"] / source.name).write_text("cost\n999\n")
    with pytest.raises(ValueError, match="checksum"):
        quarantine_table(source, destination, "unknown")


def test_source_growing_after_metadata_check_is_still_size_bounded(tmp_path, monkeypatch):
    source = tmp_path / "source.csv"
    source.write_text("cost\n7\n")
    original_open = type(source).open

    def grow_before_read(path, mode="r", *args, **kwargs):
        if path == source and mode == "rb":
            with original_open(source, "r+b") as stream:
                stream.truncate(50 * 1024 * 1024 + 1)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(type(source), "open", grow_before_read)
    with pytest.raises(ValueError, match="50 MiB"):
        quarantine_table(source, tmp_path / "archive", "unknown")
    assert not (tmp_path / "archive").exists()


def test_changed_receipt_cannot_redirect_source_verification_outside_archive(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("cost\n7\n")
    destination = tmp_path / "archive"
    receipt = quarantine_table(source, destination, "unknown")
    receipt["source_name"] = "../../source.csv"
    (destination / receipt["source_sha256"] / "receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Invalid quarantined source name"):
        quarantine_table(source, destination, "unknown")
