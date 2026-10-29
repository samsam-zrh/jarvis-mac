# Installer la version de développement

Jarvis est encore en construction. Je le développe sur un Mac Apple Silicon avec 24 Go de mémoire ; les performances et permissions peuvent varier sur un autre Mac.

## Dépendances

Prévoir macOS 14+, Python 3.12+ et les outils de ligne de commande Apple (`xcode-select --install`). Depuis la racine :

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python scripts/bootstrap.py
```

Le bootstrap récupère les versions épinglées de Goose, Ollama et Cua Driver dans `.runtime/`, avec vérification des empreintes. Installer ensuite l’app signée CuaDriver de cette archive dans `/Applications`, sans écraser une installation existante à l’aveugle.

## Modèles

Ollama utilise un serveur séparé et un stockage propre à ce projet. Dans un terminal :

```sh
OLLAMA_HOST=127.0.0.1:11436 OLLAMA_MODELS="$PWD/.runtime/models" .runtime/ollama/ollama serve
```

Puis dans un autre, depuis la même racine :

```sh
OLLAMA_HOST=127.0.0.1:11436 .runtime/ollama/ollama pull qwen3.5:4b-q4_K_M
OLLAMA_HOST=127.0.0.1:11436 .runtime/ollama/ollama pull qwen3.5:9b-mtp-nvfp4
.venv/bin/python scripts/prepare_audio_runtime.py
```

Le profil rapide utilise le 4B, le profil précis le 9B. Le script audio récupère Qwen3-TTS VoiceDesign et Smart Turn avec les révisions indiquées dans les deux manifestes de `Documents/`, puis compile le lecteur natif. Whisper Small MLX peut être téléchargé au premier chargement. Ces téléchargements occupent plusieurs Go ; les poids ne sont pas inclus dans Git.

## App Mac

```sh
bash scripts/build_app.sh
```

Pour l’installer, quitter l’éventuelle version précédente, puis lancer :

```sh
.venv/bin/python scripts/install_app.py
```

Ce script installe `~/Applications/Jarvis.app` et active le lancement à la connexion avec `local.samuel.jarvis`. L’app référence le dossier du projet : le garder à son emplacement. Pour désactiver le lancement à la connexion :

```sh
launchctl bootout gui/$(id -u)/local.samuel.jarvis
```

Autoriser microphone et reconnaissance vocale pour Jarvis ; Accessibilité et Enregistrement de l’écran pour CuaDriver. Certaines apps demandent aussi une autorisation d’automatisation. La lecture structurée des onglets dépend des réglages Safari/Chrome. Le projet ne configure pas les comptes web à la place de l’utilisateur.

## Données et limites

L’API écoute sur `127.0.0.1:8766` et vérifie le jeton local. `.state/` contient les réglages, conversations, journaux et données personnelles ; ne pas le partager. Les modèles sont locaux, mais les recherches, pages visitées et services de messagerie contactent Internet.

La reconnaissance Apple exige le mode sur l’appareil. Les actions bureau, la compréhension vocale et les enchaînements restent expérimentaux. Tester sur des fichiers et comptes de démonstration avant de confier une action importante à l’assistant.

Les comptes rendus personnels, captures et fichiers créés pendant le développement ont été exclus de cette version publique. Les licences des composants sont dans `LICENSES/` et [THIRD_PARTY.md](../THIRD_PARTY.md).
