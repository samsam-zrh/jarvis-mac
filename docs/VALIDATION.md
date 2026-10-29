# État du 29 octobre 2026

Version 0.1.0 en cours de développement, copiée pendant que le travail continue dans le projet local.

Vérifications exécutées sur cette copie :

- 90 tests Python passent avec l’environnement de développement existant.
- 6 tests de détection du nom passent en Swift.
- 6 tests d’état vocal et de fin de phrase passent en Swift.
- L’app Mac et le lecteur audio compilent ; la signature locale est créée. Des avertissements de dépréciation des API audio apparaissent sur macOS 27.

## Refaire les contrôles

Après installation des dépendances et compilation du lecteur audio :

```sh
.venv/bin/python -m pytest -q
swiftc macos/WakePhrase.swift tests/WakePhraseTest.swift -o /tmp/jarvis-wake-test
/tmp/jarvis-wake-test
swiftc -framework Cocoa -framework Speech -framework AVFoundation macos/WakePhrase.swift macos/WakeListener.swift tests/WakeListenerTest.swift -o /tmp/jarvis-listener-test
/tmp/jarvis-listener-test
bash scripts/build_app.sh
```

Le test audio génère un signal synthétique et le rend hors ligne avec le lecteur natif. Les tests d’envoi et de calendrier utilisent des outils simulés : ils n’envoient pas de message réel et ne créent pas d’événement dans un compte.

Les tests ne prouvent pas la réussite de toutes les tâches dans toutes les applications. Cette publication n’a pas relancé une conversation vocale complète, téléchargé les modèles ni réinstallé Jarvis. Une installation neuve sur un autre Mac reste à valider. Les poids, historiques, contacts, captures et documents de travail personnels sont exclus.
