import pytest
from jarvis import routines
from jarvis.fast_actions import match_plan


def test_named_routine_expands_without_model_in_request_order(monkeypatch,tmp_path):
    monkeypatch.setattr(routines,'STATE',tmp_path)
    routines.save_routine('Mode travail',['Ouvre Notes','Mets le volume à 40 %','Ouvre Safari'])
    plan=match_plan('Mode travail')
    assert [a['kind'] for a in plan]==['open','audio','open']
    assert plan[1]['volume']==40
    assert len(match_plan('Lance mode travail puis ouvre Pages'))==4


def test_message_sending_cannot_be_hidden_in_a_direct_routine(monkeypatch,tmp_path):
    monkeypatch.setattr(routines,'STATE',tmp_path)
    with pytest.raises(ValueError,match='non directe'):
        routines.save_routine('Mon raccourci',['Envoie un message à mon contact : bonjour'])
