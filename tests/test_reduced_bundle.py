"""Reduced recordings keep truthful availability and still round-trip physical paths."""
import time
from copy import deepcopy

import pytest

from mapf.application.artifacts import export_bundle, import_bundle, standalone_html
from mapf.application.contracts import JobSubmissionRequest
from mapf.application.jobs import completed_payload
from mapf.application.plans import preview, provenance
from mapf.application.runs import RunRepository, new_id
from mapf.application.worker import solve_plan


def small_payload(level):
    plan=preview(JobSubmissionRequest(scenario_id='crossing-2a',solver_id='CBS',recording_level=level))
    plan['provenance']=provenance()
    job={'job_id':new_id('job'),'run_id':new_id('run'),'attempt_id':new_id('attempt'),
         'definition_digest':plan['definition_digest'],'plan':plan,'effective_config':plan['effective_config'],
         'created_at':time.time(),'started_at':time.time()}
    return completed_payload(job,solve_plan(plan))


def test_metrics_only_bundle_roundtrip_does_not_invent_replay(tmp_path):
    payload=small_payload('metrics-only')
    assert payload['frames']==[] and payload['result']['success']
    original=deepcopy(payload)
    repo=RunRepository(tmp_path)
    imported=repo.get_run(import_bundle(export_bundle(payload),repo))
    assert imported['result']['paths']==payload['result']['paths']
    assert imported['frames']==[] and imported['metadata']['frame_count']==0
    assert imported['result']['validation']['status']=='valid_solution'
    assert payload==original
    assert 'No recorded replay frames' in standalone_html(imported)


@pytest.mark.parametrize('fault',['missing','short','declared_count'])
def test_truncated_full_recording_cannot_masquerade_as_reduced(tmp_path,fault):
    payload=small_payload('full-trace')
    if fault=='declared_count':payload['metadata']['frame_count']=0
    else:
        frames=[] if fault=='missing' else payload['frames'][:-1]
        payload['frames']=frames;payload['result']['frames']=frames
    with pytest.raises(ValueError,match='(replay|frame)'):
        import_bundle(export_bundle(payload),RunRepository(tmp_path))
