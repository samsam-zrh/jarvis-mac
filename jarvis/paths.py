import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = Path(os.environ.get("JARVIS_STATE", str(ROOT / ".state")))
STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
RUNTIME = ROOT / ".runtime"
OLLAMA_URL = "http://127.0.0.1:11436"
PORT = 8766
DEFAULT_MODELS = {"fast": "qwen3.5:4b-q4_K_M", "precise": "qwen3.5:9b-mtp-nvfp4"}


def settings():
    import json
    path = STATE / "settings.json"
    defaults = {"profile": "fast", "speak": True, "desktop": True, "models": DEFAULT_MODELS}
    if path.exists():
        defaults.update(json.loads(path.read_text()))
    return defaults


def save_settings(values):
    import json
    current = settings()
    current.update({k: v for k, v in values.items() if k in ("profile", "speak", "desktop")})
    if current["profile"] not in DEFAULT_MODELS:
        raise ValueError("Profil inconnu")
    temporary = STATE / "settings.tmp"
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2))
    temporary.replace(STATE / "settings.json")
    return current
