"""Narration must not invent transfers, observations or obligations."""
import pytest

from mapf.application.narratives import negotiation_story


def payload(amount=0):
    return {'metadata':{'run_id':'teaching-run'}, 'result':{'telemetry_events':[
        {'event_type':'MESSAGE','kind':'OFFER','session_id':'s','sequence':1,'tick':0,'sender':'a','recipient':'b','acknowledgement':0},
        {'event_type':'BID','session_id':'s','sequence':2,'tick':0,'decision':'ACCEPT','agent_id':'a'},
        {'event_type':'TOKEN_TRANSFER','session_id':'s','sequence':3,'tick':0,'amount':amount,'payer':'a','payee':'b'},
        {'event_type':'NEGO_SESSION','session_id':'s','sequence':4,'tick':0,'outcome':'AGREED','initiator_id':'a','opponent_id':'b','conflict_x':1,'conflict_y':1},
        {'event_type':'MOVE','sequence':5,'tick':1,'agent_id':'b','x':1,'y':0}]},
        'frames':[{'tick':0,'commitments':{}},{'tick':1,'commitments':{'b':[{'contract_id':'s','owner_id':'b','start_tick':0,'end_tick':2}]}}]}


def test_zero_settlement_is_not_described_as_payment_and_ticks_are_distinct():
    story=negotiation_story(payload())
    assert story['amount']==0 and story['session_id']=='s'
    settlement=next(s for s in story['steps'] if s['kind']=='settlement')
    assert 'zero' in settlement['text'].lower()
    assert settlement['event_sequence']==3 and settlement['tick']==0
    obligation=next(s for s in story['steps'] if s['kind']=='commitment')
    assert obligation['tick']==1 and obligation['reference']=='frames[1].commitments'
    assert story['steps'][-1]['kind']=='move' and story['steps'][-1]['tick']==1


def test_positive_transfer_and_missing_evidence_are_explicit():
    story=negotiation_story(payload(2))
    assert '2 token' in next(s for s in story['steps'] if s['kind']=='settlement')['text']
    p=payload();p['frames'][1]['commitments']={}
    assert 'unavailable' in next(s for s in negotiation_story(p)['steps'] if s['kind']=='commitment')['text'].lower()
    p['result']['telemetry_events']=[]
    with pytest.raises(ValueError,match='agreed'):negotiation_story(p)
