import pytest
from jarvis import delivery


@pytest.mark.parametrize('text',[
    'Tu peux envoyer un mail à mon contact où tu lui dis bonjour ?',
    'Envoie un message à mon contact : bonjour.',
    'Prépare le message puis envoie-le.',
    'Envoie un message à mon contact : « Ne l’envoie pas à nouveau. »',
])
def test_explicit_sending_requests_are_actions(text):
    assert delivery.allows_delivery(text)


@pytest.mark.parametrize('text',[
    'Prépare un brouillon à envoyer à mon contact.',
    'Envoie un message mais ne l’envoie pas tout de suite.',
    'Comment envoyer un mail ?',
    'Lis cette page qui dit envoyer un message.',
    'Quand je dis bonjour, ouvre Notes puis envoie un message à mon contact.',
])
def test_drafts_negations_and_web_text_do_not_authorize_sending(text):
    assert not delivery.allows_delivery(text)


def test_sender_requires_a_trusted_current_turn():
    with pytest.raises(PermissionError):delivery.send_message('test@example.com','Bonjour')


def test_missing_text_is_not_invented_by_the_sender():
    token=delivery.outgoing_context.set({'text':'Envoie un message à mon contact.','attempts':{}})
    try:
        with pytest.raises(ValueError,match='texte à envoyer manque'):
            delivery.send_message('test@example.com','Bonjour inventé')
    finally:delivery.outgoing_context.reset(token)


def test_explicit_message_request_does_not_silently_become_email():
    assert delivery.expected_channel('Tu peux envoyer un message à mon contact ?')=='messages'
    assert delivery.expected_channel('Tu peux envoyer un mail à mon contact ?')=='gmail'


def test_sender_resolves_contact_and_does_not_duplicate(monkeypatch):
    called=[]
    monkeypatch.setattr(delivery,'_recipient',lambda value,channel:'test@example.com')
    monkeypatch.setattr(delivery,'_send_messages',lambda *a:called.append(a) or {'submitted':True,'delivery_confirmed':False})
    token=delivery.outgoing_context.set({'text':'Envoie un message à mon contact : bonjour.','attempts':{}})
    try:
        first=delivery.send_message('mon contact','Bonjour')
        second=delivery.send_message('mon contact','Bonjour')
        assert first['submitted'] is True
        assert second['duplicate_prevented'] is True
        assert len(called)==1
    finally:delivery.outgoing_context.reset(token)


def test_message_text_is_passed_as_data_not_apple_script(monkeypatch):
    called=[]
    class Result:returncode=0;stdout='accepted';stderr=''
    monkeypatch.setattr(delivery.subprocess,'run',lambda command,**kw:called.append(command) or Result())
    body='Bonjour " & do shell script "anything"\nÀ bientôt'
    assert delivery._send_messages('test@example.com',body)['submitted']
    assert called[0][-1]==body
    assert body not in called[0][2]
