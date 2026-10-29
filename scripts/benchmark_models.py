#!/usr/bin/env python3
"""Mesures répétables sur cette machine ; aucun outil n'est réellement exécuté."""
import json
import time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
client = httpx.Client(base_url="http://127.0.0.1:11436", timeout=300, trust_env=False)
models = ["qwen3.5:4b-q4_K_M", "qwen3.5:9b-q4_K_M"]
tool = {"type": "function", "function": {"name": "create_document", "description": "Créer un document sur le Mac", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "title": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "title", "content"]}}}
results = []
for model in models:
    deadline = time.monotonic() + 1800
    while model not in [m["name"] for m in client.get("/api/tags").json().get("models", [])]:
        if time.monotonic() > deadline:
            raise RuntimeError("Téléchargement non terminé : " + model)
        time.sleep(5)
    cases = [
        ("francais", "Explique en trois phrases simples comment économiser la batterie de mon Mac.", False),
        ("outil", "Crée un document /tmp/bonjour.docx avec le titre Bonjour et le contenu Salut Samuel. Utilise l’outil maintenant.", True),
        ("outil_accents", "Crée le document /tmp/Résumé été.docx, titre Vacances, contenu Départ à Lyon le 12 août. Utilise l’outil.", True),
    ]
    for name, prompt, use_tool in cases:
        body = {"model": model, "messages": [{"role": "system", "content": "Tu es un assistant Mac. Réponds en français. Utilise les outils quand une action est demandée."}, {"role": "user", "content": prompt}], "think": False, "stream": False, "keep_alive": "30m", "options": {"num_ctx": 8192, "num_predict": 160, "temperature": .1}}
        if use_tool:
            body["tools"] = [tool]
        start = time.monotonic()
        response = client.post("/api/chat", json=body)
        response.raise_for_status()
        result = response.json()
        duration = time.monotonic() - start
        item = {"model": model, "case": name, "wall_seconds": round(duration, 3), "load_seconds": round(result.get("load_duration", 0) / 1e9, 3),
                "tokens_per_second": round(result.get("eval_count", 0) / max(result.get("eval_duration", 1) / 1e9, .001), 2), "message": result["message"]}
        if use_tool:
            calls = result["message"].get("tool_calls", [])
            item["correct_tool"] = bool(calls and calls[0]["function"]["name"] == "create_document" and "Samuel" in calls[0]["function"]["arguments"].get("content", "")) if name == "outil" else bool(calls and "Lyon" in calls[0]["function"]["arguments"].get("content", ""))
        results.append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)
        (ROOT / "Documents/benchmark-modeles.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
