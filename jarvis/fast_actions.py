"""Exact, complete application commands can run without model latency."""
import re
import unicodedata

APPS = {"safari": "Safari", "pages": "Pages", "numbers": "Numbers", "keynote": "Keynote", "spotify": "Spotify",
        "word": "Word", "un word": "Word", "excel": "Excel", "powerpoint": "PowerPoint", "chrome": "Chrome", "navigateur": "Safari",
        "calculatrice": "Calculator", "calendrier": "Calendar", "notes": "Notes", "finder": "Finder",
        "terminal": "Terminal", "blender": "Blender", "discord": "Discord", "musique": "Music", "rappels": "Reminders"}


def normalized(text):
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    text = re.sub(r"^(?:ouais|oui|peux[- ]tu|tu peux|est[- ]ce que tu peux|tu vas|puis|ensuite|apres)\s*[, ]*", "", text)
    text = re.sub(r"\s+s[' ]?il te plait$", "", text.strip(" .!?"))
    return re.sub(r"\s+", " ", text).strip()


def match_action(text: str):
    value = normalized(text)
    from jarvis.delivery import allows_delivery
    delivery=re.fullmatch(r"(?:(?:tu peux|peux-tu|pourrais-tu|est-ce que tu peux)\s+)?(?:envoie|envoyer)\s+(?:un |une |le |ce )?(mail|email|e-mail|message|sms|imessage|texto)\s+[àa]\s+(.+?)\s*(?:où tu lui dis|ou tu lui dis|pour lui dire|disant|:)\s+(.+)",text.strip(),re.I)
    if delivery and allows_delivery(text):
        body=delivery[3].strip()
        if body.startswith(('«','“','"')):
            closing={'«':'»','“':'”','"':'"'}[body[0]]
            if not body.endswith(closing):return None
            body=body[1:-1].strip()
        elif re.match(r'^(?:tu peux|peux-tu|pourrais-tu|est-ce que)',text,re.I):body=body.rstrip(' ?')
        if body:return {'kind':'delivery','recipient':delivery[2].strip(),'body':body,'channel':'gmail' if delivery[1].lower() in ('mail','email','e-mail') else 'messages'}
    if value in ('pause','mets en pause','mets la musique en pause','pause spotify','mets spotify en pause'):
        return {'kind':'media','action':'pause'}
    if value in ('reprends','reprends spotify','reprends la musique','reprends la lecture'):
        return {'kind':'media','action':'resume'}
    if value in ('suivant','morceau suivant','piste suivante','chanson suivante','passe au morceau suivant'):
        return {'kind':'media','action':'next'}
    if value in ('precedent','morceau precedent','piste precedente','chanson precedente'):
        return {'kind':'media','action':'previous'}
    if value in ('coupe le son','coupe le volume','mode muet'):
        return {'kind':'audio','action':'mute'}
    if value in ('remets le son','retablis le son','active le son'):
        return {'kind':'audio','action':'unmute'}
    volume=re.fullmatch(r'(?:mets |regle )?(?:le )?(?:volume|son)(?: a| sur)? (\d{1,3})(?:\s*%| pour ?cent)?',value)
    if volume and 0<=int(volume[1])<=100:return {'kind':'audio','action':'volume','volume':int(volume[1])}
    search=re.fullmatch(r'(cherche|recherche|joue|mets)(?:[- ]moi)?\s+(?:la chanson\s+)?(.+?)\s+sur\s+(spotify|youtube|gmail|drive|maps)',text.strip(' .!?'),re.I)
    if search:
        service=search[3].lower()
        if service=='spotify':return {'kind':'music_search','query':search[2],'play':search[1].lower() in ('joue','mets')}
        if search[1].lower() in ('cherche','recherche'):return {'kind':'service_search','service':service,'query':search[2]}
    service = re.fullmatch(r"(?:ouvre|ouvrir|lance|lancer)(?:[- ]moi)?\s+(?:(?:mes|les|la|le|mon|ma)\s+)?(mails?|emails?|messagerie|gmail|google drive|drive|youtube|whatsapp|google maps)(?:\s+(?:sur|dans|avec)\s+safari)?", value)
    if service:
        return {'kind':'service','service':service[1]}
    music = re.fullmatch(r"(?:lance|lancer|joue|mets|reprends)(?:[- ]moi)?\s+(?:la |ma |une )?(?:derniere playlist|musique|lecture)(?: sur spotify)?", value)
    if music:
        return {"kind": "spotify", "playlist": ""}
    music = re.fullmatch(r"(?:lance|lancer|joue|mets)(?:[- ]moi)?\s+(?:la |ma )?playlist\s+(.+?)(?: sur spotify)?", value)
    if music:
        return {"kind": "spotify", "playlist": music[1]}
    if re.fullmatch(r"(?:quelle heure est[- ]il|il est quelle heure|donne[- ]moi l'?heure)", value):
        return {"kind": "time"}
    document = re.fullmatch(r"(?:ouvre|ouvrir)(?:[- ]moi)?\s+(?:le|mon|un)\s+(?:document|fichier|pdf)\s+(.+)", value)
    if document and not re.search(r"\b(?:dans|avec)\b", document[1]):
        return {"kind":"file", "query":document[1]}
    match = re.fullmatch(r"(?:ouvre|ouvrir|lance|lancer|demarre|demarrer)(?:[- ]moi)?\s+(?:(?:la |le |l'?application |l'?app |application )?)([a-z0-9 .+-]+)", value)
    if not match:
        return None
    name = match[1].strip()
    if name == "un word":
        return {"kind":"document"}
    if name in APPS:
        return {"kind": "open", "application": APPS[name]}
    from jarvis.applications import resolve_application
    try:
        resolved = resolve_application(name)
        return {"kind": "open", "application": resolved["name"]}
    except ValueError:
        return None


def match_plan(text: str, allow_routines: bool = True):
    if allow_routines:
        from jarvis.routines import lookup_routine
        routine=lookup_routine(text)
        if routine:return routine
    verbs=r'ouvre|ouvrir|lance|lancer|joue|mets|reprends|demarre|demarrer|efface|supprime|cree|cherche|recherche|trouve|coupe|regle|remets|retablis|passe|pause'
    pattern=r"\s+(?:et puis|et ensuite|et après|et apres|puis|ensuite|après|apres|et)\s+(?=(?:"+verbs+r")\b)|(?<=[.!?;])\s+(?=(?:puis\s+)?(?:"+verbs+'))'
    # Quoted message bodies are data, even when they contain action keywords.
    protected=set();closing=None
    for index,char in enumerate(text):
        if closing:
            protected.add(index)
            if char==closing:closing=None
        elif char in ('«','“','"'):
            closing={'«':'»','“':'”','"':'"'}[char];protected.add(index)
    parts=[];start=0
    for separator in re.finditer(pattern,text,flags=re.I):
        if separator.start() in protected:continue
        parts.append(text[start:separator.start()].strip());start=separator.end()
    parts.append(text[start:].strip())
    if len(parts) < 2:
        action = match_action(text)
        if action:return [action]
        listed=re.fullmatch(r'(?:ouvre|lance)(?:[- ]moi)?\s+(.+)',normalized(text))
        if listed:
            names=re.split(r'\s*,\s*|\s+et\s+',listed[1])
            if 2<=len(names)<=8:
                actions=[match_action('ouvre '+name) for name in names]
                if all(a and a['kind']=='open' for a in actions):return actions
        return None
    actions=[]
    for part in parts:
        if allow_routines:
            from jarvis.routines import lookup_routine
            routine=lookup_routine(part)
            if routine:
                actions.extend(routine);continue
        action=match_action(part)
        if not action:return None
        actions.append(action)
    return actions
