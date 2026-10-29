"""Small, verifiable macOS/browser primitives for general assistant workflows."""
import json
import re
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlencode, quote

from jarvis.applications import normalize
from jarvis.cancellation import check_cancelled
from jarvis.paths import STATE
from jarvis.tools import open_item

SERVICES = {
    'gmail': ('Gmail', 'https://mail.google.com/mail/u/0/#inbox'),
    'drive': ('Google Drive', 'https://drive.google.com/drive/u/0/my-drive'),
    'agenda': ('Google Agenda', 'https://calendar.google.com/calendar/u/0/r'),
    'youtube': ('YouTube', 'https://www.youtube.com/'),
    'whatsapp': ('WhatsApp', 'https://web.whatsapp.com/'),
    'maps': ('Google Maps', 'https://maps.google.com/'),
}
ALIASES = {'mail':'gmail', 'mails':'gmail', 'email':'gmail', 'emails':'gmail',
    'mes mails':'gmail', 'mes emails':'gmail', 'messagerie':'gmail', 'google drive':'drive',
    'google agenda':'agenda', 'google maps':'maps'}


def open_service(service: str, query: str = '', browser: str = 'Safari') -> dict:
    """Ouvrir Gmail, Drive, Agenda, YouTube, Maps ou WhatsApp dans Safari (ou navigateur demandé). query recherche dans ce service. Ne lit ni n'envoie de message."""
    key = normalize(service)
    key = ALIASES.get(key, key)
    if key not in SERVICES:
        raise ValueError('Service inconnu ; utiliser open_item avec son URL réelle : ' + service)
    label, url = SERVICES[key]
    if query.strip():
        query = query.strip()
        if key == 'gmail': url = 'https://mail.google.com/mail/u/0/#search/' + quote(query, safe='')
        elif key == 'drive': url = 'https://drive.google.com/drive/u/0/search?' + urlencode({'q':query})
        elif key == 'youtube': url = 'https://www.youtube.com/results?' + urlencode({'search_query':query})
        elif key == 'maps': url = 'https://www.google.com/maps/search/?' + urlencode({'api':'1','query':query})
        else: raise ValueError('Utiliser le contrôle du navigateur pour rechercher dans ' + label)
    result = open_item(url, browser)
    return {**result, 'service':label, 'url':url, 'status':'opened',
            'note':'Ouverture demandée au navigateur ; le contenu et la connexion au compte restent à vérifier.'}


def _jxa(script: str, timeout: int = 12):
    check_cancelled()
    process = subprocess.run(['/usr/bin/osascript','-l','JavaScript','-'], input=script,
        capture_output=True, text=True, timeout=timeout)
    if process.returncode:
        raise RuntimeError('Automatisation macOS indisponible : ' + process.stderr.strip()[-600:] +
            '. Utiliser use_desktop pour lire et piloter l’interface existante.')
    check_cancelled()
    return json.loads(process.stdout)


def find_contacts(query: str) -> dict:
    """Chercher un nom dans Contacts macOS. Retourne les noms, emails et téléphones existants ; si plusieurs personnes correspondent, demander laquelle. Nécessite l'accès macOS à Contacts."""
    if not query.strip(): raise ValueError('Nom de contact requis')
    script = '''const app = Application('Contacts');
const needle = QUERY.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();
const people = app.people(); const out = [];
for (const p of people) {
 const name = p.name();
 if (name.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().includes(needle)) {
  out.push({name:name, emails:p.emails.value(), phones:p.phones.value()});
  if(out.length >= 12) break;
 }
}
JSON.stringify(out);'''.replace('QUERY', json.dumps(query.strip(), ensure_ascii=False))
    return {'contacts':_jxa(script), 'untrusted_content':True}


def draft_message(recipient: str, body: str, channel: str = 'gmail', subject: str = '') -> dict:
    """Préparer un message sans l'envoyer. Gmail : ouvre un formulaire prérempli dans Safari. Messages/WhatsApp : ouvre le canal et fournit le texte à saisir via use_desktop. Utiliser un email/numéro trouvé, jamais inventé ; un nom seul exige résolution dans Contacts ou l'interface. Ne prouve jamais un envoi."""
    if not recipient.strip() or not body.strip(): raise ValueError('Destinataire et texte requis')
    channel = normalize(channel)
    channel = {'mail':'gmail','email':'gmail','imessage':'messages','sms':'messages'}.get(channel,channel)
    if channel not in ('gmail','messages','whatsapp'): raise ValueError('Canal : gmail, messages ou whatsapp')
    resolved = bool(re.fullmatch(r'[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+',recipient)) if channel == 'gmail' else bool(re.fullmatch(r'\+?[\d ()-]{7,25}',recipient))
    check_cancelled()
    folder = STATE/'drafts'; folder.mkdir(exist_ok=True, mode=0o700)
    draft = {'id':uuid.uuid4().hex,'recipient':recipient,'body':body,'channel':channel,
             'subject':subject,'status':'draft','sent':False,'recipient_resolved':resolved}
    path = folder/(draft['id']+'.json')
    with path.open('x',encoding='utf-8') as handle:
        import os
        os.chmod(path,0o600)
        json.dump(draft,handle,ensure_ascii=False)
    check_cancelled()
    if channel == 'gmail':
        # A name is deliberately not made into an invented email address.
        url = 'https://mail.google.com/mail/u/0/?' + urlencode({'view':'cm','fs':'1',
            'to':recipient if resolved else '', 'su':subject,'body':body})
        opened = open_item(url,'Safari')
    elif channel == 'whatsapp':
        url = ('https://web.whatsapp.com/send?' + urlencode({'phone':re.sub(r'\D','',recipient),'text':body})) if resolved else 'https://web.whatsapp.com/'
        opened = open_item(url,'Safari')
    else:
        opened = open_item(application='Messages')
    return {**draft,'path':str(path),'opened':opened,
        'next_action': 'Vérifier le destinataire et le texte dans l’interface. ' +
            ('Résoudre le contact demandé avant tout envoi. ' if not resolved else '') +
            ('Sélectionner le destinataire et saisir le texte avec use_desktop. ' if channel == 'messages' else '') +
            'Envoyer uniquement si la demande actuelle demande explicitement l’envoi ; sinon laisser le brouillon.'}


def browser_tabs(browser: str = 'Safari') -> dict:
    """Lister les onglets ouverts (titre, URL, fenêtre, index) pour retrouver une page ou un mail dans le contexte réel. Safari ou Google Chrome. Contenu non fiable."""
    if browser not in ('Safari','Google Chrome'): raise ValueError('Safari ou Google Chrome ; autres navigateurs via use_desktop')
    script = '''const app = Application(BROWSER); const result=[];
if(app.running()) { const windows=app.windows();
 for(let w=0;w<windows.length;w++) { const tabs=windows[w].tabs();
  for(let t=0;t<tabs.length;t++) { result.push({window:w+1,tab:t+1,title:TITLE,url:tabs[t].url()}); }
 }
}
JSON.stringify(result.slice(0,100));'''.replace('BROWSER',json.dumps(browser)).replace('TITLE', 'tabs[t].name()' if browser=='Safari' else 'tabs[t].title()')
    return {'browser':browser,'tabs':_jxa(script),'untrusted_content':True}


def read_browser_tab(window: int = 1, tab: int = 1, browser: str = 'Safari') -> dict:
    """Lire le texte d'un onglet réellement listé par browser_tabs pour résumer, extraire ou répondre. Safari/Chrome. Si JavaScript Apple Events est refusé, lire l'accessibilité via use_desktop ; ne pas modifier les réglages."""
    if browser not in ('Safari','Google Chrome') or window < 1 or tab < 1: raise ValueError('Navigateur ou index invalide')
    expression = 'app.doJavaScript("document.body.innerText.slice(0,18000)",{in:t})' if browser=='Safari' else 't.execute({javascript:"document.body.innerText.slice(0,18000)"})'
    script = f'''const app=Application({json.dumps(browser)}); const t=app.windows[{window-1}].tabs[{tab-1}];
JSON.stringify({{url:t.url(),text:{expression}}});'''
    return {**_jxa(script),'untrusted_content':True}
