import base64
import pytest
from fastapi.testclient import TestClient
from jarvis import server


@pytest.mark.parametrize('text,expected,source',[
    ('ouvre-moi l’application Notes','ouvre-moi l’application Notes','apple'),
    ('crée un document sur lia','Crée un document sur l’intelligence artificielle.','whisper'),
])
def test_voice_request_uses_fast_transcript_or_local_verification(monkeypatch,tmp_path,text,expected,source):
    async def start(body):
        assert body.text == expected
        return {'id':'test'}
    def transcribe(audio):
        assert source == 'whisper'
        assert audio == b'audio'
        return {'text':'Jarvis. Crée un document sur l’intelligence artificielle.'}
    monkeypatch.setattr(server,'STATE',tmp_path)
    monkeypatch.setattr(server,'start_chat',start)
    monkeypatch.setattr(server.voice,'transcribe_audio',transcribe)
    result=TestClient(server.app).post('/api/voice-command',json={'text':text,'audio':base64.b64encode(b'audio').decode()},headers={'Authorization':'Bearer '+server.TOKEN})
    assert result.status_code == 200
    assert result.json()['source'] == source
    assert result.json()['transcript'] == expected


def test_voice_interruption_endpoint_stops_audio(monkeypatch):
    called=[]
    async def stop():called.append(True)
    monkeypatch.setattr(server.voice,'stop_speech',stop)
    result=TestClient(server.app).post('/api/voice/stop',headers={'Authorization':'Bearer '+server.TOKEN})
    assert result.status_code == 200
    assert called == [True]


def test_long_apple_transcript_is_not_replaced_by_whisper_fragment(monkeypatch,tmp_path):
    text='Écris un message à Emma pour lui dire que je serai là à dix-huit heures et ouvre mes mails dans Safari ensuite.'
    async def start(body):
        assert body.text == text
        return {'id':'long'}
    monkeypatch.setattr(server,'STATE',tmp_path)
    monkeypatch.setattr(server,'start_chat',start)
    monkeypatch.setattr(server.voice,'transcribe_audio',lambda audio: {'text':'Ouvre mes mails.'})
    result=TestClient(server.app).post('/api/voice-command',json={'text':text,'audio':base64.b64encode(b'audio').decode()},headers={'Authorization':'Bearer '+server.TOKEN})
    assert result.status_code == 200
    assert result.json()['source'] == 'apple-complete'


def test_turn_detection_rejects_invalid_audio():
    result=TestClient(server.app).post('/api/voice/turn',json={'audio':'bad*base64'},headers={'Authorization':'Bearer '+server.TOKEN})
    assert result.status_code == 422
