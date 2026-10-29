import asyncio
import re
import threading
import uuid
import subprocess
import json
from pathlib import Path
from jarvis.paths import RUNTIME

VOICE_MODEL = str(RUNTIME / "whisper-small-mlx") if (RUNTIME / "whisper-small-mlx/weights.npz").exists() else "mlx-community/whisper-small-mlx"
_transcription_lock = threading.Lock()
_speech = None
_generating = False
_speech_epoch = None
_tts_model = None
_tts_lock = threading.Lock()
_mlx_lock = threading.Lock()
NATURAL_VOICE = ("A native French man in his thirties speaking conversational French from France. "
    "Warm, clear mid-low voice, relaxed and friendly. Spontaneous everyday conversation, subtle smile, "
    "natural breathing, small pauses and varied intonation. Fluent and lively without acting or sounding "
    "like a radio announcer. Preserve natural brief hesitations in the text.")


_audio_stream = None
_speech_stop = threading.Event()
VOICE_SPEED = 1.20
VOICE_PITCH = 0.0


class NativeOutput:
    """Core Audio keeps rendering while MLX/Python prepares the next chunk."""
    def __init__(self):
        self.process = subprocess.Popen([str(RUNTIME/'voice-player')],stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)

    def start(self):
        pass

    def write(self, chunk):
        self.process.stdin.write(chunk.astype('<f4',copy=False).tobytes())
        self.process.stdin.flush()

    def stop(self):
        self.process.stdin.close()
        self.process.wait(timeout=90)
        detail = self.process.stderr.read().decode(errors='replace')
        if self.process.returncode:
            raise RuntimeError('Lecture audio native interrompue : '+detail[-300:])
        try:
            from jarvis.paths import STATE
            metrics = next(line.removeprefix('JARVIS_AUDIO ') for line in detail.splitlines() if line.startswith('JARVIS_AUDIO '))
            (STATE/'latest-playback.json').write_text(json.dumps(json.loads(metrics),indent=2))
        except (ValueError,OSError,StopIteration):
            pass

    def abort(self):
        if self.process.poll() is None:
            try: self.process.terminate()
            except ProcessLookupError: pass

    def close(self):
        self.abort()
        try: self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill(); self.process.wait()
        for stream in (self.process.stdin,self.process.stderr):
            if stream and not stream.closed:
                try: stream.close()
                except BrokenPipeError: pass


def audio_chunks(text: str, stop=None):
    if stop is not None and stop.is_set():
        return
    import numpy as np
    from mlx_audio.tts.utils import load_model
    import mlx.core as mx
    global _tts_model
    with _tts_lock, _mlx_lock:
        if stop is not None and stop.is_set():
            return
        natural_model = RUNTIME / "qwen-voice-design"
        use_natural = (natural_model/"model.safetensors").exists()
        if _tts_model is None:
            mx.set_cache_limit(256 * 1024 * 1024)
            _tts_model = load_model(str(natural_model if use_natural else RUNTIME/"qwen-tts"))
        if use_natural:
            mx.random.seed(42)
            output = _tts_model.generate_voice_design(text=text, instruct=NATURAL_VOICE, language="French",
                stream=True, streaming_interval=.48, max_tokens=650, temperature=.65)
        else:
            output = _tts_model.generate_custom_voice(text=text, speaker="Ryan", language="French", stream=True,
                streaming_interval=.32, max_tokens=500, temperature=.5)
        for result in output:
            if stop is not None and stop.is_set():
                return
            audio = np.nan_to_num(np.asarray(result.audio,dtype=np.float32))
            if len(audio):
                yield np.clip(audio,-1,1) * .85


def warmup():
    for _ in audio_chunks("Bonjour."):
        pass


def synthesize(text: str, destination: str | None = None):
    import io
    import wave
    import numpy as np
    chunks = list(audio_chunks(text))
    if not chunks:
        raise RuntimeError("La voix locale n’a produit aucun son")
    audio = np.clip(np.concatenate(chunks), -1, 1)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(24000)
        output.writeframes((audio * 32767).astype("<i2").tobytes())
    payload = buffer.getvalue()
    if destination:
        Path(destination).write_bytes(payload)
    return payload


def play_stream(text, stop):
    import queue
    global _audio_stream
    pending = queue.Queue()
    finished = object()
    def produce():
        try:
            for chunk in audio_chunks(text, stop):
                if stop.is_set():
                    break
                pending.put(chunk)
        except Exception as error:
            pending.put(error)
        finally:
            pending.put(finished)
    producer = threading.Thread(target=produce, name="jarvis-audio-producer", daemon=True)
    producer.start()
    stream = None
    buffered = []
    samples = 0
    complete = False
    def take():
        while not stop.is_set():
            try:
                item = pending.get(timeout=.05)
                if isinstance(item, Exception):
                    raise item
                return item
            except queue.Empty:
                pass
        return finished
    try:
        # Produce independently of the blocking speaker writes. A short reserve
        # absorbs GPU jitter without inserting silence between generated chunks.
        while samples < 24000 * 1.5 and not complete and not stop.is_set():
            item = take()
            complete = item is finished
            if not complete:
                buffered.append(item)
                samples += len(item)
        if stop.is_set() or not buffered:
            return
        stream = NativeOutput()
        _audio_stream = stream
        stream.start()
        for chunk in buffered:
            if stop.is_set():
                break
            stream.write(chunk)
        while not complete and not stop.is_set():
            item = take()
            complete = item is finished
            if not complete and not stop.is_set():
                stream.write(item)
        if not stop.is_set():
            stream.stop()
    except (BrokenPipeError, OSError, RuntimeError):
        if not stop.is_set():
            raise
    finally:
        stop.set()
        if stream is not None:
            stream.close()
        if _audio_stream is stream:
            _audio_stream = None


def is_speaking():
    return _generating or bool(_speech and _speech.returncode is None)


def decode_wav(audio: bytes):
    import io
    import math
    import wave
    import numpy as np
    from scipy.signal import resample_poly
    if len(audio) > 20_000_000:
        raise ValueError("Enregistrement trop volumineux")
    try:
        with wave.open(io.BytesIO(audio), "rb") as stream:
            channels, width, rate = stream.getnchannels(), stream.getsampwidth(), stream.getframerate()
            if channels not in (1, 2) or width not in (2, 4) or not 8000 <= rate <= 192000:
                raise ValueError("Audio PCM 16 ou 32 bits, mono ou stéréo requis")
            samples = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2" if width == 2 else "<i4").astype(np.float32)
    except (wave.Error, EOFError, ZeroDivisionError) as error:
        raise ValueError("Enregistrement WAV invalide") from error
    samples /= float(2 ** (8 * width - 1))
    if channels == 2:
        samples = samples.reshape(-1, 2).mean(axis=1)
    if rate != 16000:
        factor = math.gcd(rate, 16000)
        samples = resample_poly(samples, 16000 // factor, rate // factor)
    if not len(samples):
        raise ValueError("Enregistrement vide")
    return samples.astype(np.float32)


def transcribe_audio(audio: bytes):
    import mlx_whisper
    samples = decode_wav(audio)
    with _transcription_lock, _mlx_lock:
        result = mlx_whisper.transcribe(samples, path_or_hf_repo=VOICE_MODEL, language="fr", fp16=True, verbose=False,
                                       condition_on_previous_text=False, initial_prompt="Conversation en français avec Jarvis. Applications, documents, messagerie, musique et recherches sur Internet. L’IA signifie l’intelligence artificielle.")
        return {"text": result["text"].strip(), "language": "fr", "local": True}


def warm_transcription():
    import numpy as np
    import mlx_whisper
    with _transcription_lock, _mlx_lock:
        mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo=VOICE_MODEL, language="fr", fp16=True, verbose=False, condition_on_previous_text=False)


async def stop_speech():
    global _speech, _speech_epoch, _generating
    _speech_epoch = uuid.uuid4()
    _generating = False
    _speech_stop.set()
    stream = _audio_stream
    if stream is not None:
        try:
            await asyncio.to_thread(stream.abort)
        except Exception:
            pass
    if _speech and _speech.returncode is None:
        _speech.terminate()
        await _speech.wait()
    _speech = None


async def speak(text: str):
    global _speech_epoch, _generating, _speech_stop
    await stop_speech()
    text = re.sub(r"(?im)^\s*(?:sources?|références?)\s*:.*$", "", text)
    text = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\bJarvis\b", "l’assistant", text, flags=re.I)
    text = re.sub(r"[*#`]|\[([^\]]+)\]\([^)]*\)", lambda m: m.group(1) or "", text)
    text = text[:700].strip()
    if not text:
        return
    epoch = uuid.uuid4()
    _speech_epoch = epoch
    stop = threading.Event()
    _speech_stop = stop
    _generating = True
    try:
        await asyncio.to_thread(play_stream, text, stop)
    finally:
        if _speech_epoch == epoch:
            _generating = False
