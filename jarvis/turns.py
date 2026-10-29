"""Local acoustic end-of-turn detection; no network or language-model request."""
import threading
import time

from jarvis.paths import RUNTIME

_lock = threading.Lock()
_session = None
_extractor = None


def predict_turn(audio: bytes) -> dict:
    import numpy as np
    import onnxruntime as ort
    from transformers import WhisperFeatureExtractor
    from jarvis.voice import decode_wav
    global _session, _extractor
    started = time.monotonic()
    samples = decode_wav(audio)[-128000:]
    # Smart Turn expects left padding, with the latest speech at the end.
    samples = np.pad(samples, (max(0, 128000 - len(samples)), 0))
    with _lock:
        if _session is None:
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            _session = ort.InferenceSession(str(RUNTIME / 'smart-turn/model.onnx'),
                sess_options=options, providers=['CPUExecutionProvider'])
            _extractor = WhisperFeatureExtractor(chunk_length=8)
        features = _extractor(samples, sampling_rate=16000, return_tensors='np',
            padding='max_length', max_length=128000, truncation=True, do_normalize=True).input_features
        probability = float(np.asarray(_session.run(None, {'input_features': features.astype(np.float32)})[0]).ravel()[0])
    return {'complete': probability >= .65, 'probability': round(probability, 4),
            'local': True, 'elapsed_ms': round((time.monotonic() - started) * 1000, 1)}


def warmup():
    import io
    import wave
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)
        output.writeframes(b'\0' * 32000)
    return predict_turn(stream.getvalue())
