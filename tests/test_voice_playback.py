import threading
import numpy as np
from jarvis import voice


def test_generation_continues_while_output_is_playing(monkeypatch):
    produced_next = threading.Event()
    written = []
    def chunks(text, stop):
        yield np.ones(24000, dtype=np.float32)
        produced_next.set()
        yield np.zeros(24000, dtype=np.float32)
    class Output:
        def __init__(self, **kwargs): pass
        def start(self): pass
        def write(self, chunk):
            assert produced_next.wait(.2), 'Audio generation must run during playback'
            written.append(chunk)
        def stop(self): pass
        def close(self): pass
    monkeypatch.setattr(voice, 'audio_chunks', chunks)
    monkeypatch.setattr(voice, 'NativeOutput', Output)
    voice.play_stream('Test', threading.Event())
    assert sum(len(x) for x in written) == 48000
