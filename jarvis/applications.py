"""Installed application inventory and explicit equivalents, without launching probes."""
import subprocess
import json
import plistlib
import re
import time
import unicodedata
from pathlib import Path

GROUPS = {
    "word": ["Microsoft Word", "Pages", "LibreOffice", "TextEdit"],
    "excel": ["Microsoft Excel", "Numbers", "LibreOffice"],
    "powerpoint": ["Microsoft PowerPoint", "Keynote", "LibreOffice"],
    "chrome": ["Google Chrome", "Safari", "Firefox", "Microsoft Edge"],
    "safari": ["Safari", "Google Chrome", "Firefox", "Microsoft Edge"],
    "pdf": ["Preview", "Adobe Acrobat Reader", "Safari"],
    "spotify": ["Spotify"],
}
ALIASES = {"traitement de texte": "word", "document word": "word", "microsoft word": "word", "tableur": "excel", "microsoft excel": "excel", "presentation": "powerpoint", "navigateur": "safari", "google chrome": "chrome", "apercu": "pdf", "calculatrice": "calculator", "calendrier": "calendar", "musique": "music", "rappels": "reminders"}
_cache = (0.0, [])


def normalize(value):
    return unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode().strip()


def installed_apps():
    global _cache
    if time.monotonic() - _cache[0] < 60:
        return _cache[1]
    items = []
    paths = set()
    try:
        indexed = subprocess.run(['/usr/bin/mdfind', '-0', 'kMDItemContentType == "com.apple.application-bundle"'], capture_output=True, timeout=5)
        paths.update(Path(path) for path in indexed.stdout.decode(errors='replace').split('\0') if path and '.app/' not in path)
    except (OSError, subprocess.TimeoutExpired):
        pass
    for folder in (Path("/Applications"), Path.home()/"Applications", Path("/System/Applications"), Path("/System/Library/CoreServices")):
        if not folder.exists():
            continue
        paths.update(list(folder.glob("*.app")) + list(folder.glob("*/*.app")))
    for path in sorted(paths):
        try:
            info = plistlib.loads((path/"Contents/Info.plist").read_bytes())
            identifier = info.get("CFBundleIdentifier", "")
            canonical = {"com.apple.Pages": "Pages", "com.apple.iWork.Pages": "Pages", "com.apple.Numbers": "Numbers", "com.apple.iWork.Numbers": "Numbers", "com.apple.Keynote": "Keynote", "com.apple.iWork.Keynote": "Keynote"}.get(identifier, path.stem)
            items.append({"name": canonical, "display_name": path.stem, "path": str(path), "bundle_id": identifier})
        except (OSError, ValueError, plistlib.InvalidFileException):
            continue
    _cache = (time.monotonic(), items)
    return items


def resolve_application(requested: str, inventory=None):
    inventory = installed_apps() if inventory is None else inventory
    key = normalize(requested)
    key = ALIASES.get(key, key)
    # Exact requests always win over category preferences.
    exact = next((app for app in inventory if normalize(app["name"]) == normalize(requested)), None)
    if exact is None:
        compact = lambda value: re.sub(r'[^a-z0-9]', '', normalize(value))
        matches = [app for app in inventory if compact(requested) in {compact(app['name']), compact(app.get('display_name',app['name']))}]
        if len({app['name'] for app in matches}) == 1 and matches:
            exact = matches[0]
    candidates = GROUPS.get(key, [requested, key])
    selected = exact or next((app for name in candidates for app in inventory if normalize(app["name"]) == normalize(name)), None)
    if not selected:
        raise ValueError(f"Application absente : {requested}. Applications disponibles : " + ", ".join(app["name"] for app in inventory)[:1200])
    fallback = not exact and key in GROUPS and normalize(selected["name"]) != normalize(candidates[0])
    return {**selected, "requested": requested, "fallback": fallback}


def list_applications(query: str = ""):
    """Applications réellement installées et équivalents disponibles pour adapter une tâche."""
    apps = installed_apps()
    if query:
        apps = [app for app in apps if normalize(query) in normalize(app["name"])]
    return {"applications": [app["name"] for app in apps], "equivalents": GROUPS}
