#!/usr/bin/env python3
"""Démarrage privé des services ; aucune configuration système modifiée."""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from jarvis.paths import PORT, ROOT, RUNTIME, STATE, OLLAMA_URL


def reachable(url):
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status < 400
    except Exception:
        return False


def main():
    if not reachable(OLLAMA_URL + "/api/version"):
        logfile = (STATE / "ollama.log").open("ab")
        env = {**os.environ, "OLLAMA_HOST": "127.0.0.1:11436", "OLLAMA_MODELS": str(RUNTIME / "models"),
               "OLLAMA_NO_CLOUD": "1", "OLLAMA_CONTEXT_LENGTH": "8192", "OLLAMA_NUM_PARALLEL": "1",
               "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_KEEP_ALIVE": "30m"}
        subprocess.Popen([str(RUNTIME / "ollama/ollama"), "serve"], cwd=ROOT, env=env, stdout=logfile, stderr=logfile, start_new_session=True)
        for _ in range(40):
            if reachable(OLLAMA_URL + "/api/version"):
                break
            time.sleep(.25)
    if reachable(f"http://127.0.0.1:{PORT}/"):
        return
    os.chdir(ROOT)
    os.execv(str(ROOT / ".venv/bin/python"), [str(ROOT / ".venv/bin/python"), "-m", "uvicorn", "jarvis.server:app", "--host", "127.0.0.1", "--port", str(PORT), "--no-access-log"])


if __name__ == "__main__":
    main()
