import pytest
from jarvis import local_agent


@pytest.mark.asyncio
async def test_explicit_web_request_fetches_real_sources_before_inference(monkeypatch):
    fetched = []
    def search(query):
        fetched.append(query)
        return {'results':[{'url':'https://example.org/verified','title':'Verified'}]}
    class ReachedInference(Exception): pass
    async def emit(event):
        if event['kind']=='tool_result':
            assert event['result']['results'][0]['url']=='https://example.org/verified'
            raise ReachedInference()
    monkeypatch.setattr(local_agent.tools,'search_web',search)
    with pytest.raises(ReachedInference):
        await local_agent.run_agent('Cherche sur le web comment fonctionne une batterie.',[],emit,'test','Assistant',False,None)
    assert fetched == ['comment fonctionne une batterie.']


def test_compact_schema_preserves_validation_fields():
    schema={'type':'object','description':'long','properties':{'query':{'type':'string','description':'long'}},'required':['query'],'additionalProperties':False}
    compact=local_agent.compact_schema(schema)
    assert compact['required']==['query']
    assert compact['additionalProperties'] is False
    assert compact['properties']['query']=={'type':'string'}


@pytest.mark.asyncio
async def test_weather_claim_without_live_tool_is_not_displayed(monkeypatch):
    import json
    from contextlib import asynccontextmanager
    class Response:
        def raise_for_status(self):pass
        async def aiter_lines(self):
            yield json.dumps({'message':{'content':'Demain il fera beau à Paris.'}})
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        @asynccontextmanager
        async def stream(self,*args,**kwargs):yield Response()
    monkeypatch.setattr(local_agent.httpx,'AsyncClient',Client)
    displayed=[]
    async def emit(e):displayed.append(e)
    with pytest.raises(RuntimeError,match='pas été vérifiées'):
        await local_agent.run_agent('Donne la météo détaillée demain à Paris ?',[],emit,'test','Assistant',False,None)
    assert not any(e['kind']=='text' for e in displayed)
