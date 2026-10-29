import pytest
from fastapi.testclient import TestClient

from jarvis.server import app, TOKEN


@pytest.fixture
def client():
    return TestClient(app)


def test_api_requires_token(client):
    assert client.get("/api/status").status_code == 401
    assert client.post("/api/chat", json={"text": "Bonjour"}).status_code == 401


def test_foreign_origin_rejected_even_with_token(client):
    response = client.post("/api/chat", json={"text": "Bonjour"}, headers={"Authorization": f"Bearer {TOKEN}", "Origin": "https://evil.example"})
    assert response.status_code == 403


def test_bad_host_rejected(client):
    response = client.get("/api/history", headers={"Authorization": f"Bearer {TOKEN}", "Host": "evil.example:8766"})
    assert response.status_code == 403


def test_history_authenticated(client):
    response = client.get("/api/history", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200
    assert isinstance(response.json()["messages"], list)


def test_invalid_profile_rejected(client):
    response = client.post("/api/settings", json={"profile": "remote"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_simultaneous_requests_cannot_start_two_agents(monkeypatch):
    import asyncio
    import httpx
    from jarvis import server
    entered = asyncio.Event()
    release = asyncio.Event()
    async def slow_status():
        entered.set()
        await release.wait()
        return {"ready": True}
    async def fake_run(*args):
        await asyncio.sleep(60)
    monkeypatch.setattr(server, 'status', slow_status)
    monkeypatch.setattr(server.engine, 'run', fake_run)
    monkeypatch.setattr(server.storage, 'add_message', lambda *args: None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver', headers={'Authorization': f'Bearer {TOKEN}'}) as c:
        first = asyncio.create_task(c.post('/api/chat', json={'text': 'Test un'}))
        await entered.wait()
        second = asyncio.create_task(c.post('/api/chat', json={'text': 'Test deux'}))
        release.set()
        responses = await asyncio.gather(first, second)
        assert sorted(r.status_code for r in responses) == [200, 409]
        await c.post('/api/cancel')


@pytest.mark.asyncio
async def test_cancel_releases_task_and_accepts_next_request(monkeypatch):
    import asyncio
    import httpx
    from jarvis import server
    entered=asyncio.Event()
    async def status():return {'ready':True}
    async def run(*args):
        entered.set()
        await asyncio.sleep(60)
    monkeypatch.setattr(server,'status',status)
    monkeypatch.setattr(server.engine,'run',run)
    monkeypatch.setattr(server.storage,'add_message',lambda *args:None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',headers={'Authorization':f'Bearer {TOKEN}'}) as c:
        first=(await c.post('/api/chat',json={'text':'First task'})).json()['id']
        await entered.wait()
        assert (await c.post('/api/cancel')).status_code==200
        assert server.tasks[first]['status']=='cancelled'
        assert server.tasks[first]['stop'].is_set()
        assert server.active is None
        assert (await c.post('/api/chat',json={'text':'Next task'})).status_code==200
        await c.post('/api/cancel')
