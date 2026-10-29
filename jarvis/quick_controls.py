"""Bounded direct controls; no inference and no free-form shell command."""
import subprocess
from jarvis.cancellation import check_cancelled


def _script(script):
    check_cancelled()
    result=subprocess.run(['/usr/bin/osascript','-e',script],capture_output=True,text=True,timeout=12)
    if result.returncode:raise RuntimeError(result.stderr.strip() or 'Commande macOS refusée')
    check_cancelled()
    return result.stdout.strip()


def control_media(action: str) -> dict:
    """Pause, reprise, piste suivante ou précédente dans Spotify. Vérifie l’état retourné par l’application."""
    commands={'pause':'pause','resume':'play','next':'next track','previous':'previous track'}
    if action not in commands:raise ValueError('Action : pause, resume, next ou previous')
    state=_script('if application "Spotify" is not running then error "Spotify n’est pas lancé"\n'
        'tell application "Spotify"\n'+commands[action]+'\nreturn player state as text\nend tell')
    return {'application':'Spotify','action':action,'player_state':state,'verified':True}


def set_audio(action: str, volume: int = 50) -> dict:
    """Régler le volume de sortie (0 à 100), couper ou rétablir le son. Retourne le réglage réellement lu."""
    if action=='volume':
        if type(volume) is not int or not 0<=volume<=100:raise ValueError('Volume entre 0 et 100')
        value=_script(f'set volume output volume {volume}\nget output volume of (get volume settings)')
        return {'volume':int(value),'verified':True}
    if action not in ('mute','unmute'):raise ValueError('Action : volume, mute ou unmute')
    value=_script('set volume '+('with' if action=='mute' else 'without')+' output muted\nget output muted of (get volume settings)')
    return {'muted':value=='true','verified':True}
