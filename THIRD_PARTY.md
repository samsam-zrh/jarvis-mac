# Crédits et licences

Ressources gratuites uniquement. Aucune clé payante, aucun abonnement et aucun crédit de génération achetés.

| Composant | Version / identité | Licence et source |
|---|---|---|
| Goose | 1.56.0 ; source 9949cf926cd42f1d128b9991ed23a496ecace896 | Apache-2.0 — https://github.com/aaif-goose/goose |
| Ollama | 0.40.12 | MIT, dépendances avec notices propres — https://github.com/ollama/ollama |
| Cua Driver | 0.37.0 ; source 2d2f99228d4d2508dc6fcc84c176b296e146714a | Driver MIT — https://github.com/trycua/cua ; Cua Spaces n’est pas utilisé |
| Qwen 3.5 4B / 9B | Q4_K_M, distribués par Ollama ; empreintes dans les mesures/registre local | Apache-2.0 — https://ollama.com/library/qwen3.5 et https://huggingface.co/Qwen |
| Whisper Small MLX | mlx-community/whisper-small-mlx ; conversion MLX du modèle Whisper | MIT pour Whisper et MLX ; modèle et carte : https://huggingface.co/mlx-community/whisper-small-mlx |
| SDK MCP Python | 1.30.0 | MIT — https://github.com/modelcontextprotocol/python-sdk |
| FastAPI / Uvicorn | Versions dans requirements.lock | MIT / BSD-3-Clause |
| python-docx / pypdf / Beautiful Soup | Versions dans requirements.lock | MIT / BSD-3-Clause / MIT |
| DDGS | 9.16.1 | MIT ; moteurs de recherche soumis à leurs conditions — https://github.com/deedy5/ddgs |
| Playwright | 1.64.1, utilisé pour la validation et disponible pour les outils navigateur | Apache-2.0 — https://github.com/microsoft/playwright-python |
| Kokoro 82M / Siwis | Révision a71e4d38b236d968966a2002c4c895dbd12b1c3c ; MLX Audio 0.6.3 | Apache-2.0 pour Kokoro / MIT pour MLX Audio — https://huggingface.co/mlx-community/Kokoro-82M-bf16 et https://github.com/Blaizzy/mlx-audio |
| Qwen3-TTS 0.6B CustomVoice 8bit | mlx-community, révision 049ef77fe8816b536193c0c25f9a214d17921282 | Apache-2.0 modèle, MIT MLX Audio — https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit |
| Swift, AppKit, WebKit et Speech | Fournis avec macOS / outils Apple existants | Conditions Apple ; aucun modèle de voix Apple redistribué |

Les notices de licences disponibles sont conservées dans `LICENSES/` et dans les distributions de `.runtime/` et `.venv/`. La carte du modèle Whisper est conservée dans `.runtime/whisper-small-mlx/README.md`. Les modules optionnels de perception Cua (licences différentes) et le modèle de réveil openWakeWord « hey_jarvis » ne sont pas utilisés. L’écoute du nom utilise la reconnaissance locale Apple.

Jarvis est un projet indépendant, sans affiliation avec Marvel, Apple, Alibaba, Goose ou Cua.

Prévisions et géocodage météo : [Open-Meteo](https://open-meteo.com/), données CC BY 4.0, API gratuite utilisée pour cet assistant personnel ; attribution conservée dans les résultats de l’outil.

Voix active naturelle : Qwen3-TTS 1.7B VoiceDesign, conversion MLX 4bit, révision `5c390979e4b93af5f2932f90742ca99c7dd04687`, Apache-2.0. Source : https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-4bit ; manifeste et SHA dans Documents/modele-voix-naturelle.json. Voix originales décrites en mots, aucun enregistrement de personne utilisé.

Détection acoustique locale de fin de tour : Smart Turn v3.2 CPU, `pipecat-ai/smart-turn-v3`, révision `f766f81d3cfdf7737ac64aad813d91bbfd56bf93`, BSD-2-Clause. ONNX Runtime 1.24.4, MIT. Notice et manifeste SHA dans LICENSES/ et Documents/modele-fin-de-phrase.json. Sources : https://github.com/pipecat-ai/smart-turn et https://huggingface.co/pipecat-ai/smart-turn-v3.

Hauteur et tempo actifs : AVAudioUnitTimePitch et AVAudioEngine, fournis par macOS. Aucun filtre tiers de hauteur/tempo n’est chargé en production. Le lecteur natif est compilé depuis macos/VoicePlayer.swift. Les essais Rubber Band ont été retirés après les problèmes de lecture constatés ; leurs sources téléchargées restent disponibles localement mais ne sont pas intégrées au lecteur actif.
