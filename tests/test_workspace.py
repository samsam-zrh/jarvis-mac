import json
from urllib.parse import urlsplit, parse_qs
import pytest
from jarvis import workspace
from jarvis.fast_actions import match_action


@pytest.mark.parametrize('phrase',['Ouvre mes mails','Ouvre ma messagerie sur Safari','Ouvre Gmail dans Safari'])
def test_mail_commands_use_gmail_in_safari(monkeypatch,phrase):
    action = match_action(phrase)
    assert action['kind'] == 'service'
    called=[]
    monkeypatch.setattr(workspace,'open_item',lambda *a,**k: called.append(a) or {'verified_launch_request':True})
    workspace.open_service(action['service'])
    assert called == [('https://mail.google.com/mail/u/0/#inbox','Safari')]


def test_draft_keeps_unicode_and_is_never_sent(monkeypatch,tmp_path):
    monkeypatch.setattr(workspace,'STATE',tmp_path)
    opened=[]
    monkeypatch.setattr(workspace,'open_item',lambda *a,**k: opened.append(a) or {'verified_launch_request':True})
    text='Salut ! J’arrive à 18 h. Ne clique pas sur « envoyer ». & à bientôt'
    result=workspace.draft_message('emma@example.com',text,subject='Rendez-vous')
    assert result['sent'] is False
    assert result['recipient_resolved'] is True
    params=parse_qs(urlsplit(opened[0][0]).query)
    assert params['body']==[text]
    assert params['to']==['emma@example.com']
    assert json.loads(next((tmp_path/'drafts').glob('*.json')).read_text())['body']==text


def test_name_is_not_changed_into_an_invented_address(monkeypatch,tmp_path):
    monkeypatch.setattr(workspace,'STATE',tmp_path)
    opened=[]
    monkeypatch.setattr(workspace,'open_item',lambda *a,**k: opened.append(a) or {})
    result=workspace.draft_message('Emma','Je serai en retard.')
    assert result['recipient_resolved'] is False
    assert 'to=' in opened[0][0]
    assert 'Emma' not in opened[0][0]


def test_browser_failure_returns_instruction_to_use_existing_interface(monkeypatch):
    class Result:
        returncode=1;stderr='Apple Events permission denied'
    monkeypatch.setattr(workspace.subprocess,'run',lambda *a,**k: Result())
    with pytest.raises(RuntimeError,match='use_desktop'):
        workspace.browser_tabs()
