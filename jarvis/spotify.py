"""Spotify control using fresh, verified accessibility snapshots."""
import json
import re
import subprocess
import time
from jarvis.paths import RUNTIME, STATE
from jarvis.tools import open_item
from jarvis.applications import normalize
from jarvis.cancellation import check_cancelled


def _call(name, arguments):
    check_cancelled()
    response = subprocess.run([str(RUNTIME/'cua/cua-driver'), 'call', name, json.dumps({**arguments, 'session':'jarvis-spotify'})], capture_output=True, text=True, timeout=20)
    if response.returncode:
        raise RuntimeError(response.stderr.strip() or response.stdout[:500])
    result = json.loads(response.stdout)
    if result.get('status') == 'refused' or result.get('effect') == 'refused':
        raise RuntimeError(str(result.get('refusal') or result))
    if result.get('code'):
        raise RuntimeError(result.get('detail') or result['code'])
    return result


def _buttons(snapshot):
    for line in snapshot.get('tree_markdown', '').splitlines():
        match = re.search(r'\[(\d+)\] AXButton (?:"(.*?)"|\((.*?)\))', line)
        if match:
            yield snapshot['snapshot_id']+':'+match[1], (match[2] or match[3]).strip()


def _playlist_key(value):
    return ' '.join(re.findall(r'[a-z0-9]+', normalize(value).replace('&', ' and ')))


def _control_matches(label, playlist, action):
    match = re.match(r'^(Lire|Mettre en pause|Play|Pause)\s*[:：]\s*(.+)$', label, re.I)
    return bool(match and normalize(match[1]) in action and _playlist_key(match[2]) == _playlist_key(playlist))


def _library_title(label):
    title = re.split(r'\s+(?:Playlist(?: mixée)?\s*[•·]|Épinglé|Téléchargé)', label, maxsplit=1, flags=re.I)[0]
    return title.strip() if title != label else None


def _library_matches(label, playlist):
    title = _library_title(label)
    return bool(title and _playlist_key(title) == _playlist_key(playlist))


def _remember(playlist):
    if not playlist:
        return
    path = STATE/'spotify-playlists.json'
    names = json.loads(path.read_text()) if path.exists() else []
    if playlist not in names:
        names.append(playlist)
        path.write_text(json.dumps(names[-50:], ensure_ascii=False))


def play_spotify(playlist: str = ''):
    """Jouer une playlist nommée de la bibliothèque Spotify, ou reprendre l'écoute précédente si playlist est vide. Vérifie le bouton Pause après l'action, sans inventer le résultat."""
    playlist = playlist.strip(' ,.;:!?')
    _call('start_session', {})
    open_item(application='Spotify')
    launched = _call('launch_app', {'bundle_id':'com.spotify.client'})
    pid = launched['pid']
    for _ in range(20):
        windows = _call('list_windows', {'pid':pid}).get('windows', [])
        if windows:
            break
        time.sleep(.15)
    if not windows:
        raise RuntimeError('Spotify est lancé mais sa fenêtre n’est pas disponible')
    window = max(windows, key=lambda w:w['bounds']['width']*w['bounds']['height'])
    target = {'pid':pid, 'window_id':window['window_id']}
    def read(query):
        return _call('get_window_state', {**target, 'include_screenshot':False, 'query':query, 'max_elements':1200})
    key = normalize(playlist).strip()
    if not key:
        snapshot = read('Pause')
        if any(normalize(label) == 'pause' for _,label in _buttons(snapshot)):
            return {'playing':True, 'mode':'resume', 'verified':True, 'track':window['title']}
        snapshot = read('Lecture')
        button = next((token for token,label in _buttons(snapshot) if normalize(label) in ('lecture','play')), None)
    else:
        snapshot = read('')
        names = sorted({title for _,label in _buttons(snapshot) if (title := _library_title(label))})
        if names:
            (STATE/'spotify-library.json').write_text(json.dumps(names, ensure_ascii=False))
        if any(_control_matches(label, playlist, ('mettre en pause','pause')) for _,label in _buttons(snapshot)):
            _remember(playlist)
            return {'playing':True, 'playlist':playlist, 'verified':True}
        button = next((token for token,label in _buttons(snapshot) if _control_matches(label, playlist, ('lire','play'))), None)
        if not button:
            entries = {label: token for token,label in _buttons(snapshot) if _library_matches(label, playlist)}
            if len(entries) > 1:
                raise ValueError('Plusieurs playlists portent ce nom : ' + '; '.join(entries))
            entry = next(iter(entries.values()), None)
            if not entry:
                raise ValueError('Playlist non trouvée dans la bibliothèque visible : '+playlist)
            _call('click', {**target,'element_token':entry})
            for _ in range(12):
                snapshot = read('')
                button = next((token for token,label in _buttons(snapshot) if _control_matches(label, playlist, ('lire','play'))), None)
                if button:
                    break
                time.sleep(.15)
    if not button:
        raise RuntimeError('Le bouton de lecture Spotify n’a pas été trouvé')
    _call('click', {**target,'element_token':button})
    for _ in range(16):
        snapshot = read('Pause')
        labels = [normalize(label) for _,label in _buttons(snapshot)]
        verified = any(label == 'pause' for label in labels) if not key else any(_control_matches(label, playlist, ('mettre en pause','pause')) for _,label in _buttons(snapshot))
        if verified:
            _remember(playlist)
            return {'playing':True,'playlist':playlist or None,'mode':'playlist' if key else 'resume','verified':True}
        time.sleep(.15)
    raise RuntimeError('Spotify a reçu la demande, mais la lecture n’a pas pu être confirmée')


def _search_candidates(snapshot, title='', artist=''):
    rows = re.split(r'(?m)^\s*- \[\d+\] AXRow ', snapshot.get('tree_markdown',''))[1:]
    found = []
    for row in rows:
        local = {'snapshot_id':snapshot['snapshot_id'], 'tree_markdown':row}
        for token,label in _buttons(local):
            match = re.match(r'^(?:Lire|Play)\s*[:：]\s*(.+)$',label,re.I)
            if not match or (title and _playlist_key(match[1]) != _playlist_key(title)):
                continue
            links = re.findall(r'AXLink \((.*?)\)',row)
            if artist and not any(_playlist_key(link) == _playlist_key(artist) for link in links):
                continue
            found.append({'title':match[1], 'links':links[:4], 'element_token':token})
    return found


def search_spotify(query: str, title: str = '', artist: str = '', play: bool = False):
    """Rechercher n’importe quelle musique dans la barre Spotify. Pour jouer un titre, fournir title exact, artist si connu, play=true. Sélectionne un résultat correspondant et vérifie le titre et Pause. Sinon retourne les résultats sans lancer la lecture."""
    if not query.strip() or (play and not title.strip()):
        raise ValueError('Recherche requise ; pour jouer, préciser le titre de la chanson')
    _call('start_session', {})
    open_item(application='Spotify')
    pid = _call('launch_app', {'bundle_id':'com.spotify.client'})['pid']
    windows = _call('list_windows', {'pid':pid}).get('windows', [])
    if not windows:
        raise RuntimeError('Fenêtre Spotify indisponible')
    window = max(windows, key=lambda w:w['bounds']['width']*w['bounds']['height'])
    target = {'pid':pid, 'window_id':window['window_id']}
    _call('press_key', {**target,'key':'l','modifiers':['cmd'],'delivery_mode':'foreground'})
    _call('type_text', {**target,'text':query,'delivery_mode':'foreground','delay_ms':0})
    _call('press_key', {**target,'key':'return','delivery_mode':'foreground'})
    def read():
        return _call('get_window_state', {**target,'include_screenshot':False,'max_elements':1800,'timeout_ms':2000})
    candidates = []
    for _ in range(12):
        snapshot = read()
        # Confirm that the renderer actually received this query.
        fields = re.findall(r'AXComboBox = "(.*?)"',snapshot.get('tree_markdown',''))
        if any(_playlist_key(field) == _playlist_key(query) for field in fields):
            candidates = _search_candidates(snapshot, title if play else '', artist if play else '')
            if candidates:
                break
        time.sleep(.15)
    if not candidates:
        raise ValueError('Aucun résultat musical correspondant confirmé dans Spotify : '+query)
    if not play:
        return {'query':query,'results':candidates[:12],'searched':True,'playing':False}
    chosen = candidates[0]
    _call('click', {**target,'element_token':chosen['element_token']})
    for _ in range(16):
        current = read()
        now = _playlist_key(current.get('window_title',''))
        if any(normalize(label)=='pause' for _,label in _buttons(current)) and _playlist_key(title) in now and (not artist or _playlist_key(artist) in now):
            return {'query':query,'title':chosen['title'],'artist':artist or None,'now_playing':current['window_title'],'playing':True,'verified':True}
        time.sleep(.15)
    raise RuntimeError('La lecture du titre demandé n’a pas pu être confirmée')
