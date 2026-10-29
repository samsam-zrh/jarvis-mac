"""Named, user-created sequences of already-supported direct commands."""
import json
import os
import re
from jarvis.paths import STATE
from jarvis.cancellation import check_cancelled


def is_routine_definition(text):
    from jarvis.fast_actions import normalized
    value=normalized(text)
    return bool(re.search(r'\bquand je (?:dis|dirai)\b|^(?:enregistre|cree)\s+(?:un|le|ce|une|la|cette)\s+(?:(?:nouveau|nouvelle)\s+)?(?:routine|raccourci)\b',value))


def list_routines() -> dict:
    """Lister les raccourcis vocaux personnels et leurs commandes."""
    path=STATE/'voice-routines.json'
    return {'routines':json.loads(path.read_text()) if path.exists() else {}}


def save_routine(name: str, commands: list[str]) -> dict:
    """Enregistrer un raccourci vocal quand l'utilisateur demande une routine nommée. commands contient les commandes directes dans l'ordre : ouvertures d'apps, fichiers, musique, volume, recherches dans un service. Pas d'envoi externe ni de commande terminal dans une routine directe. Déclencher ensuite en disant le nom, sans modèle."""
    from jarvis.fast_actions import match_plan,normalized
    key=normalized(name)
    if not 3<=len(key)<=80 or not 1<=len(commands)<=8:raise ValueError('Nom de 3 à 80 caractères et de 1 à 8 commandes requis')
    actions=[]
    for command in commands:
        plan=match_plan(command,allow_routines=False)
        if not plan or any(a['kind']=='delivery' for a in plan):raise ValueError('Commande non directe dans une routine : '+command)
        actions.extend(plan)
    if len(actions)>20:raise ValueError('20 actions maximum par raccourci')
    records=list_routines()['routines']
    if key in records:raise ValueError('Ce raccourci existe déjà : choisir un autre nom')
    if match_plan(key,allow_routines=False):raise ValueError('Ce nom correspond déjà à une commande directe')
    records[key]={'name':name.strip(),'commands':commands,'actions':actions}
    check_cancelled()
    path=STATE/'voice-routines.json';temporary=path.with_suffix('.partial')
    with temporary.open('w') as handle:
        os.chmod(temporary,0o600);json.dump(records,handle,ensure_ascii=False,indent=2)
    temporary.replace(path)
    return {'saved':True,'name':name.strip(),'trigger':key,'actions':len(actions),'runs_without_model':True}


def lookup_routine(text):
    import re
    from jarvis.fast_actions import normalized
    key=normalized(text)
    key=re.sub(r'^(?:lance|active|execute|demarre)\s+(?:le raccourci |la routine )?','',key)
    record=list_routines()['routines'].get(key)
    return record['actions'] if record else None
