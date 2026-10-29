import io
import wave
import numpy as np
import pytest
from jarvis.voice import decode_wav


def test_voice_tempo_and_pitch_are_independent(tmp_path):
    import subprocess
    from jarvis.paths import RUNTIME
    samples=(.2*np.sin(2*np.pi*440*np.arange(48000)/24000)).astype(np.float32)
    source=tmp_path/'source.wav';target=tmp_path/'target.wav'
    with wave.open(str(source),'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(24000)
        stream.writeframes((samples*32767).astype('<i2').tobytes())
    subprocess.run([str(RUNTIME/'voice-player'),'--render',str(source),str(target)],check=True)
    with wave.open(str(target),'rb') as stream:
        result=np.frombuffer(stream.readframes(stream.getnframes()),dtype='<i2').astype(np.float32)/32768
    assert abs(len(result)-len(samples)/1.20) < 2
    middle=result[8000:32000]
    frequency=np.argmax(np.abs(np.fft.rfft(middle)))*24000/len(middle)
    assert abs(frequency-440) < 3


def test_cancelled_audio_does_not_emit_a_buffered_tail():
    import threading
    from jarvis.voice import audio_chunks
    stop=threading.Event();stop.set()
    assert list(audio_chunks('Une lecture annulée',stop))==[]


def test_stereo_pcm_is_resampled_for_local_transcription():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(np.full((4800, 2), 16384, dtype='<i2').tobytes())
    result = decode_wav(buffer.getvalue())
    assert result.shape == (1600,)
    assert .45 < float(result.mean()) < .55


def test_invalid_audio_is_rejected():
    with pytest.raises(ValueError):
        decode_wav(b'RIFF broken data')
