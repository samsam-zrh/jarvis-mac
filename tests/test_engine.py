import asyncio
import os
import signal
import sys

import pytest

from jarvis.engine import interpret_event, terminate_process


def test_goose_events_keep_tool_errors_visible():
    event = {"type": "message", "message": {"role": "assistant", "content": [{"type": "toolRequest", "id": "a", "toolCall": {"status": "success", "value": {"name": "jarvis__create_document", "arguments": {"path": "/tmp/demo.docx"}}}}]}}
    out = interpret_event(event)
    assert out[0]["kind"] == "tool"
    assert "create_document" in out[0]["name"]
    assert interpret_event({"type": "error", "error": "Accès refusé"})[0] == {"kind": "error", "text": "Accès refusé"}


@pytest.mark.asyncio
async def test_cancel_stops_the_process_group():
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(120)", start_new_session=True)
    await terminate_process(process)
    assert process.returncode is not None


@pytest.mark.asyncio
async def test_cancel_stops_child_that_ignores_term():
    import subprocess
    child_code = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready',flush=True); time.sleep(120)"
    parent_code = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "],stdout=subprocess.PIPE,text=True); p.stdout.readline(); print(p.pid,flush=True); time.sleep(120)"
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", parent_code, stdout=asyncio.subprocess.PIPE, start_new_session=True)
    child_pid = int(await process.stdout.readline())
    try:
        await terminate_process(process)
        for _ in range(50):
            state = subprocess.run(["ps", "-p", str(child_pid), "-o", "stat="], capture_output=True, text=True).stdout.strip()
            if not state or state.startswith("Z"):
                break
            await asyncio.sleep(.02)
        assert not state or state.startswith("Z")
    finally:
        try:
            os.kill(child_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


@pytest.mark.asyncio
async def test_failed_shortcut_recovers_remaining_actions_with_agent(monkeypatch):
    from jarvis import engine, local_agent
    runner = engine.Engine()
    completed = []
    async def fast(action, emit):
        if action['kind'] == 'spotify':raise ValueError('Playlist non trouvée')
        completed.append(action)
        return 'Spotify ouverte'
    async def agent(text, history, emit, model, system, desktop, command, **kwargs):
        assert 'Playlist non trouvée' in text
        assert 'gdm' in text
        assert 'déjà' in text
        assert kwargs['eager_desktop'] is True
        return 'Lecture vérifiée'
    async def emit(event):pass
    monkeypatch.setattr(runner,'run_fast_action',fast)
    monkeypatch.setattr(local_agent,'run_agent',agent)
    assert await runner.run('ouvre Spotify et lance la playlist GDM','main',[],emit) == 'Lecture vérifiée'
    assert len(completed) == 1
