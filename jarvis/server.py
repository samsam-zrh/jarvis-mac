import asyncio
import json
import os
import secrets
import time
import threading
import uuid
import logging
import base64
import re
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal

from jarvis import storage, voice
from jarvis.engine import Engine
from jarvis.paths import ROOT, STATE, RUNTIME, PORT, OLLAMA_URL, settings, save_settings

token_path = STATE / "token"
if not token_path.exists():
    descriptor = os.open(token_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(secrets.token_urlsafe(40))
TOKEN = token_path.read_text().strip()
os.chmod(token_path, 0o600)
@asynccontextmanager
async def lifespan(app):
    app.state.voice_ready = False
    # Transformers' lazy exports can fail when its first imports race across
    # the acoustic turn detector and TTS warmup threads. Resolve them first.
    from transformers import AutoTokenizer, WhisperFeatureExtractor
    from jarvis.applications import installed_apps
    (STATE/"applications.json").write_text(json.dumps(installed_apps(), ensure_ascii=False, indent=2))
    vocabulary = [a["name"] for a in installed_apps() if not a["path"].startswith("/System/Library/")]
    if (STATE/"spotify-playlists.json").exists():
        vocabulary = json.loads((STATE/"spotify-playlists.json").read_text()) + vocabulary
    if (STATE/"spotify-library.json").exists():
        vocabulary = json.loads((STATE/"spotify-library.json").read_text()) + vocabulary
    (STATE / "app-vocabulary.json").write_text(json.dumps(list(dict.fromkeys(vocabulary)), ensure_ascii=False))
    async def warm_voice():
        if settings()["speak"] and (RUNTIME / "qwen-tts/model.safetensors").exists():
            try:
                await asyncio.to_thread(voice.warmup)
                await asyncio.to_thread(voice.warm_transcription)
                app.state.voice_ready = True
            except Exception:
                logging.exception("Le préchargement de la voix locale a échoué")
    warmup = asyncio.create_task(warm_voice())
    async def warm_reasoning():
        from jarvis.engine import SYSTEM
        from jarvis.local_agent import warm_model
        try:
            current = settings()
            await warm_model(current["models"][current["profile"]], SYSTEM)
        except Exception:
            logging.exception("Le préchargement du modèle local a échoué")
    model_warmup = asyncio.create_task(warm_reasoning())
    from jarvis.turns import warmup as warm_turns
    turn_warmup = asyncio.create_task(asyncio.to_thread(warm_turns))
    yield
    await voice.stop_speech()
    warmup.cancel()
    model_warmup.cancel()
    turn_warmup.cancel()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
engine = Engine()
tasks = {}
active = None
submission_lock = asyncio.Lock()


@app.middleware("http")
async def local_auth(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0]
    if host not in ("localhost", "127.0.0.1", "testserver"):
        return JSONResponse({"detail": "Hôte refusé"}, status_code=403)
    if request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if origin and origin not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return JSONResponse({"detail": "Origine refusée"}, status_code=403)
        if not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + TOKEN):
            return JSONResponse({"detail": "Authentification locale requise"}, status_code=401)
        if int(request.headers.get("content-length", "0")) > 20_000_000:
            return JSONResponse({"detail": "Requête trop volumineuse"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    return response


class Chat(BaseModel):
    text: str = Field(min_length=1, max_length=16000)


class VoiceCommand(Chat):
    audio: str | None = Field(default=None, max_length=19_000_000)


class TurnAudio(BaseModel):
    audio: str = Field(min_length=1, max_length=4_500_000)


@app.post('/api/voice/turn')
async def voice_turn(body: TurnAudio):
    from jarvis.turns import predict_turn
    try:
        return await asyncio.to_thread(predict_turn, base64.b64decode(body.audio, validate=True))
    except (ValueError, KeyError) as error:
        raise HTTPException(422, 'Audio de fin de phrase invalide') from error


class Settings(BaseModel):
    profile: Literal["fast", "precise"] | None = None
    speak: bool | None = None
    desktop: bool | None = None


async def emit(task, event):
    task["events"].append({**event, "at": round(time.time(), 3)})
    task["changed"].set()


async def execute(task_id, text):
    global active
    task = tasks[task_id]
    from jarvis.cancellation import current_stop
    cancellation_token = current_stop.set(task["stop"])
    from jarvis.delivery import outgoing_context
    delivery_token = outgoing_context.set({'text':text,'attempts':{},'history':storage.history(8)[:-1]})
    try:
        answer = await engine.run(text, "main", storage.history(8)[:-1], lambda event: emit(task, event))
        if answer:
            storage.add_message("assistant", answer)
        task["status"] = "completed"
        await emit(task, {"kind": "done", "status": "completed", "elapsed": round(time.monotonic() - task["start"], 2)})
        if settings()["speak"] and answer:
            await voice.speak(answer)
    except asyncio.CancelledError:
        task["status"] = "cancelled"
        await emit(task, {"kind": "done", "status": "cancelled"})
    except Exception as error:
        task["status"] = "error"
        await emit(task, {"kind": "error", "text": str(error)})
        await emit(task, {"kind": "done", "status": "error"})
    finally:
        current_stop.reset(cancellation_token)
        outgoing_context.reset(delivery_token)
        active = None
        task["changed"].set()


@app.get("/api/status")
async def status():
    models, loaded, reachable = [], [], False
    try:
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            response = await client.get(OLLAMA_URL + "/api/tags")
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]
            loaded = (await client.get(OLLAMA_URL + "/api/ps")).json().get("models", [])
            reachable = True
    except (httpx.HTTPError, ValueError):
        pass
    current = settings()
    return {"settings": current, "models": models, "loaded": [m["name"] for m in loaded], "ollama": reachable,
            "ready": reachable and current["models"][current["profile"]] in models,
            "desktop_ready": (STATE / "desktop-ready").exists(), "active": active,
            "voice_ready": getattr(app.state,'voice_ready',False),
            "machine": "Apple M5 · 24 Go", "local": True}


@app.post("/api/chat")
async def chat(body: Chat):
    async with submission_lock:
        return await start_chat(body)


@app.post("/api/voice-command")
async def voice_command(body: VoiceCommand):
    from jarvis.fast_actions import match_plan
    text = body.text.strip()
    source = "apple"
    started = time.monotonic()
    alternative = None
    plan=match_plan(text)
    if body.audio and (not plan or any(a['kind']=='delivery' for a in plan)):
        try:
            audio = base64.b64decode(body.audio, validate=True)
            result = await asyncio.to_thread(voice.transcribe_audio, audio)
            candidate = re.split(r"\b(?:jarvis|jervis|jarvice)\b[\s,.!?-]*", result["text"], maxsplit=1, flags=re.I)[-1].strip()
            if candidate:
                alternative = candidate
                # Do not replace a long complete utterance with a decoder fragment.
                if len(text.split()) >= 12 and len(candidate.split()) < len(text.split()) * .65:
                    source = 'apple-complete'
                else:
                    text = candidate
                    source = "whisper"
        except (ValueError, KeyError) as error:
            raise HTTPException(422, "La demande vocale n’a pas pu être transcrite : " + str(error)) from error
    diagnostics = {"apple_text": body.text, "text": text, "alternative": alternative, "source": source, "transcription_ms": round((time.monotonic()-started)*1000), "at": time.time()}
    (STATE/"latest-voice.json").write_text(json.dumps(diagnostics, ensure_ascii=False))
    async with submission_lock:
        result = await start_chat(Chat(text=text))
    return {**result, "transcript": text, "source": source, "transcription_ms": diagnostics["transcription_ms"]}


async def start_chat(body: Chat):
    global active
    if active:
        raise HTTPException(409, "Une tâche est déjà en cours")
    if not body.text.strip():
        raise HTTPException(422, "Écris une demande")
    current = await status()
    if not current["ready"]:
        raise HTTPException(503, "Le modèle local n'est pas encore prêt. Son téléchargement peut être en cours.")
    task_id = uuid.uuid4().hex
    task = {"status": "running", "request": body.text, "events": [], "changed": asyncio.Event(), "stop": threading.Event(), "start": time.monotonic()}
    tasks[task_id] = task
    # Keep bounded in-memory event history.
    for key in list(tasks)[:-30]:
        if tasks[key]["status"] != "running":
            del tasks[key]
    active = task_id
    storage.add_message("user", body.text)
    task["job"] = asyncio.create_task(execute(task_id, body.text))
    return {"id": task_id}


@app.get("/api/tasks/{task_id}/events")
async def events(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "Tâche inconnue")
    task = tasks[task_id]
    async def stream():
        cursor = 0
        while True:
            task["changed"].clear()
            while cursor < len(task["events"]):
                yield json.dumps(task["events"][cursor], ensure_ascii=False) + "\n"
                cursor += 1
            if task["status"] != "running":
                break
            try:
                await asyncio.wait_for(task["changed"].wait(), 10)
            except asyncio.TimeoutError:
                yield '{"kind":"heartbeat"}\n'
    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.post("/api/cancel")
async def cancel():
    global active
    async with submission_lock:
        task_id = active
        task = tasks.get(task_id) if task_id else None
        if task:
            task['stop'].set()
            task['job'].cancel()
        await voice.stop_speech()
        await engine.cancel()
        if task:
            try:
                await task['job']
            except asyncio.CancelledError:
                pass
            if task['status'] == 'running':
                task['status'] = 'cancelled'
                await emit(task, {'kind':'done','status':'cancelled'})
            if active == task_id:
                active = None
    return {"cancelled": True}


@app.post("/api/voice/stop")
async def interrupt_voice():
    await voice.stop_speech()
    return {"stopped": True}


@app.get("/api/history")
async def history():
    return {"messages": storage.history()}


@app.post("/api/history/clear")
async def clear_history():
    if active:
        raise HTTPException(409, "Arrête d'abord la tâche en cours")
    storage.clear()
    return {"cleared": True}


@app.post("/api/settings")
async def change_settings(body: Settings):
    return save_settings(body.model_dump(exclude_none=True))


@app.post("/api/transcribe")
async def transcribe(request: Request):
    audio = await request.body()
    try:
        return await asyncio.to_thread(voice.transcribe_audio, audio)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/permissions")
async def permissions():
    binary = RUNTIME / "cua/cua-driver"
    if not binary.exists():
        raise HTTPException(503, "Le contrôleur de bureau n'est pas installé")
    process = await asyncio.create_subprocess_exec(str(binary), "permissions", "grant", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 15)
    except asyncio.TimeoutError:
        process.terminate()
        raise HTTPException(503, "Ouvre les Réglages Système pour autoriser CuaDriver")
    return {"output": (stdout + stderr).decode(errors="replace")[-2000:], "requested": True}


@app.post("/api/permissions/check")
async def check_permissions():
    binary = RUNTIME / "cua/cua-driver"
    if not binary.exists():
        return {"ready": False, "output": "Contrôleur absent"}
    process = await asyncio.create_subprocess_exec(str(binary), "permissions", "status", "--json", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(process.communicate(), 8)
        payload = json.loads(out)
        # Exact status schema is validated against the installed driver during setup.
        granted = payload.get("accessibility") is True and payload.get("screen_recording") is True
        if granted:
            (STATE / "desktop-ready").touch()
        else:
            (STATE / "desktop-ready").unlink(missing_ok=True)
        return {"ready": granted, "output": payload}
    except (ValueError, asyncio.TimeoutError):
        if process.returncode is None:
            process.terminate()
        return {"ready": False, "output": "Vérifie Accessibilité et Enregistrement de l'écran pour CuaDriver dans Réglages Système."}


@app.get("/api/activity")
async def activity():
    task_id = active or next(reversed(tasks), None)
    task = tasks.get(task_id, {})
    return {"id": task_id, "status": task.get("status", "idle"), "events": task.get("events", []),
            "request": task.get("request", ""), "speaking": voice.is_speaking()}


@app.get("/overlay")
async def overlay():
    return FileResponse(ROOT / "web/overlay.html")


@app.get("/")
async def index():
    return FileResponse(ROOT / "web/index.html")


app.mount("/static", StaticFiles(directory=ROOT / "web", check_dir=False), name="static")
