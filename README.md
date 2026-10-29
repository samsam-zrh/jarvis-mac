# Jarvis

**En cours de développement — version 0.1.0.** Je continue à améliorer les fonctions et la voix. Certaines actions sont encore expérimentales.

Je fais cet assistant pour utiliser mon Mac à la voix : ouvrir une app, chercher un fichier, créer un document, contrôler la musique ou enchaîner plusieurs actions.

Le modèle tourne en local avec Ollama. L’app est en Swift, le moteur en Python, et le contrôle du bureau utilise Cua Driver. La voix passe par la reconnaissance locale Apple, Whisper MLX et Qwen3-TTS.

## Ce qui est déjà dans le code

- App de barre de menus, conversation et petit panneau vocal.
- Appel « Jarvis », dictée, réponse vocale et interruption.
- Applications, fichiers, PDF, documents Word et présentations.
- Recherche web, météo, musique, calendrier et routines.
- Suivi des tâches en plusieurs étapes et outils de messagerie.

Les accès aux applications dépendent des autorisations macOS et des comptes connectés. Les envois et les actions importantes demandent une consigne explicite ; les résultats restent à vérifier.

## Essayer ou développer

Mac Apple Silicon, macOS 14+, Python 3.12+ et outils Apple. La configuration complète, les modèles et les permissions sont dans [INSTALLATION.md](docs/INSTALLATION.md).

Les modèles, binaires, conversations et réglages personnels ne sont pas dans le dépôt. Ce n’est pas encore un installateur prêt pour tout le monde.

Les tests Python et Swift sont fournis dans `tests/`. L’état vérifié de cette version est dans [VALIDATION.md](docs/VALIDATION.md).

[Crédits et licences des composants](THIRD_PARTY.md). Projet indépendant, sans affiliation avec Marvel ou Apple.
