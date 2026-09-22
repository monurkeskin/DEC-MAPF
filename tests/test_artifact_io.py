"""Shared artifact writes preserve the last committed bytes on publication failure."""
import pytest

from mapf import artifact_io
from mapf.application import runs


def test_replace_failure_keeps_previous_artifact_and_removes_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / 'artifact.json'
    target.write_bytes(b'previous checked artifact')

    def fail_replace(source, destination):
        raise OSError('injected replacement failure')

    monkeypatch.setattr(artifact_io.os, 'replace', fail_replace)
    with pytest.raises(OSError, match='replacement failure'):
        artifact_io.atomic_write(target, b'new bytes')
    assert target.read_bytes() == b'previous checked artifact'
    assert list(tmp_path.iterdir()) == [target]


def test_shared_encoder_keeps_the_existing_canonical_bytes_and_import_contract():
    assert runs.atomic_write is artifact_io.atomic_write
    assert runs.encode is artifact_io.encode
    assert artifact_io.encode({'z': 1.0, 'a': ['é', True]}) == '{"a":["é",true],"z":1}'.encode()
    with pytest.raises(ValueError):
        artifact_io.encode({'invalid': float('nan')})
