import asyncio
import threading
import pytest
from jarvis.cancellation import current_stop
from jarvis.spotify import _call


@pytest.mark.asyncio
async def test_cancelled_thread_cannot_dispatch_another_desktop_action():
    stop=threading.Event()
    token=current_stop.set(stop)
    try:
        stop.set()
        with pytest.raises(RuntimeError,match='Tâche arrêtée'):
            await asyncio.to_thread(_call,'click',{'pid':-1})
    finally:
        current_stop.reset(token)
