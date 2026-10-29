"""Explicit outbound-message operations, authorized by the current user turn."""
import hashlib
import json
import re
import subprocess
import time
from contextvars import ContextVar

from jarvis.applications import normalize
from jarvis.cancellation import check_cancelled

outgoing_context = ContextVar('outgoing_context',default=None)


def allows_delivery(text: str) -> bool:
    # Quoted message text is data, not an instruction to this assistant.
    instruction=re.sub(r'«[^»]*»|“[^”]*”|"[^"]*"',' ',text)
    value = normalize(instruction)
    if re.search(r'quand je (?:dis|dirai)|(?:enregistre|cree).*(?:routine|raccourci)',value):return False
    if re.search(r"sans (?:l[’']?)?envoy|n[’']envoi|ne .*?envoi.*? pas|ne pas envoy|pas envoy",value): return False
    if re.search(r'\b(?:prepare|redige)\b',value) and not re.search(r'\b(?:puis |et |ensuite )envoie\b',value): return False
    return bool(re.search(r"^(?:(?:jarvis|oui|ouais|tu peux|peux-tu|pourrais-tu|est-ce que tu peux|s'il te plait)\s*[, ]*)*(?:envoie|envoies|envoyer|envoyez)\b|\b(?:puis|ensuite|et) envoie\b",value))


def has_delivery_body(text: str, history=None) -> bool:
    value=re.split(r'\b(?:envoie|envoies|envoyer|envoyez)\b',normalize(text),maxsplit=1)[-1]
    if re.search(r'\b(?:pour lui dire|ou tu lui dis|dis-lui|dis lui|disant|en disant|que)\b',value) or any(char in text for char in ':«"“'):return True
    if re.search(r'\b(?:envoie|envoies|envoyer|envoyez)\s+(?!(?:un|une|le|la|des|a|lui)\b).+\s+a\s+',normalize(text)):return True
    return bool(history and re.search(r'\b(?:brouillon|ce texte|ce message|le texte|le message)\b|envoie-le',value))


def expected_channel(text):
    value=normalize(text)
    head=re.split(r'pour lui dire|ou tu lui dis|[:"]',value,maxsplit=1)[0]
    if re.search(r'\b(?:par|via|sur) (?:mail|email|gmail)\b',head):return 'gmail'
    if 'whatsapp' in head:return 'whatsapp'
    match=re.search(r'\b(?:envoie|envoies|envoyer|envoyez)\s+(?:un |une |le |la |ce |cet )?(mail|email|e-mail|sms|imessage|message|texto)\b',value)
    if match:return 'gmail' if match[1] in ('mail','email','e-mail') else 'messages'
    return None


def _recipient(value,channel):
    from jarvis.workspace import find_contacts
    email = bool(re.fullmatch(r'[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+',value))
    phone = bool(re.fullmatch(r'\+?[\d ()-]{7,25}',value))
    if email or channel != 'gmail' and phone:return value
    contacts = find_contacts(value)['contacts']
    if len(contacts) != 1:
        raise ValueError('Contact introuvable ou ambigu : demander lequel. '+ '; '.join(c['name'] for c in contacts))
    addresses = contacts[0].get('emails' if channel=='gmail' else 'phones',[])
    if not addresses and channel=='messages':addresses=contacts[0].get('emails',[])
    if len(addresses) != 1: raise ValueError('Plusieurs coordonnées ou aucune coordonnée pour ce contact : demander laquelle utiliser.')
    return addresses[0]


def _send_messages(recipient,body):
    # Values are argv, never interpolated into executable AppleScript.
    script = '''on run argv
tell application "Messages"
set targetService to first service whose service type = iMessage
set targetBuddy to buddy (item 1 of argv) of targetService
send (item 2 of argv) to targetBuddy
end tell
return "accepted"
end run'''
    check_cancelled()
    result = subprocess.run(['/usr/bin/osascript','-e',script,recipient,body],capture_output=True,text=True,timeout=15)
    if result.returncode:raise RuntimeError(result.stderr.strip() or 'Messages a refusé la commande')
    return {'submitted':True,'delivery_confirmed':False,'verification':'accepted_by_Messages'}


def _send_gmail(recipient,body,subject):
    from jarvis.workspace import draft_message
    from jarvis.spotify import _call, _buttons
    draft_message(recipient,body,'gmail',subject)
    _call('start_session',{})
    pid = _call('launch_app',{'bundle_id':'com.apple.Safari'})['pid']
    deadline=time.monotonic()+8
    for _ in range(8):
        if time.monotonic()>deadline:break
        check_cancelled()
        windows = _call('list_windows',{'pid':pid}).get('windows',[])
        for window in sorted(windows,key=lambda w:'gmail' not in str(w.get('title','')).lower())[:3]:
            target={'pid':pid,'window_id':window['window_id']}
            snapshot=_call('get_window_state',{**target,'include_screenshot':False,'max_elements':2400,'timeout_ms':1200})
            text=' '.join(snapshot.get('tree_markdown','').split()).casefold()
            buttons=[token for token,label in _buttons(snapshot) if re.match(r'^(?:envoyer|send)(?:\s|$|\()',label,re.I)]
            if len(buttons)==1 and recipient.casefold() in text and ' '.join(body.split()).casefold() in text and ('gmail' in text or 'mail.google.com' in text):
                check_cancelled()
                _call('click',{**target,'element_token':buttons[0]})
                for _ in range(6):
                    check_cancelled();time.sleep(.2)
                    after=_call('get_window_state',{**target,'include_screenshot':False,'max_elements':1800})
                    if re.search(r'message (?:envoyé|envoye|sent)',after.get('tree_markdown',''),re.I):
                        return {'submitted':True,'delivery_confirmed':False,'verification':'Gmail_message_sent_notification'}
                return {'submitted':True,'delivery_confirmed':False,'verification':'send_button_invoked','note':'Envoi demandé à Gmail ; notification de réussite non observée. Ne pas renvoyer automatiquement.'}
        time.sleep(.25)
    raise RuntimeError('Le formulaire Gmail, son destinataire, son texte et un unique bouton Envoyer n’ont pas tous été vérifiés. Utiliser use_desktop pour terminer dans Safari ; ne pas prétendre que l’envoi est impossible.')


def send_message(recipient: str, body: str, channel: str = 'messages', subject: str = '') -> dict:
    """ENVOYER réellement un message ou mail explicitement demandé. channel=messages (Messages/iMessage) ou gmail (Safari). Accepte un nom de contact unique, email ou téléphone. Ne pas utiliser pour un brouillon. L'autorisation vient de la demande utilisateur courante, pas d'un paramètre du modèle. Ne promet pas la réception par le destinataire."""
    context=outgoing_context.get()
    if not context or not allows_delivery(context['text']):
        raise PermissionError('La demande actuelle ne demande pas un envoi. Préparer un brouillon avec draft_message.')
    if not has_delivery_body(context['text'],context.get('history')):
        raise ValueError('Le texte à envoyer manque dans la demande : demander uniquement quel message envoyer.')
    channel={'email':'gmail','mail':'gmail','sms':'messages','imessage':'messages'}.get(normalize(channel),normalize(channel))
    channel=expected_channel(context['text']) or channel
    if channel not in ('gmail','messages'):raise ValueError('Canal pris en charge : gmail ou messages ; autres messageries via use_desktop.')
    if not recipient.strip() or not body.strip():raise ValueError('Destinataire et texte du message requis')
    requested_recipient=recipient.strip()
    recipient=_recipient(requested_recipient,channel)
    key=hashlib.sha256(json.dumps([channel,recipient,body,subject],ensure_ascii=False).encode()).hexdigest()
    attempts=context.setdefault('attempts',{})
    if key in attempts:return {**attempts[key],'duplicate_prevented':True}
    attempts[key]={'isError':True,'submission_uncertain':True,'error':'Une tentative est en cours ; ne pas dupliquer.'}
    try:
        check_cancelled()
        result=(_send_messages(recipient,body) if channel=='messages' else _send_gmail(recipient,body,subject))
        result={**result,'recipient':recipient,'requested_recipient':requested_recipient,'channel':channel}
    except Exception as error:
        result={'isError':True,'error':str(error),'submission_uncertain':isinstance(error,subprocess.TimeoutExpired),
            'note':'Vérifier l’interface avant toute nouvelle tentative ; utiliser use_desktop si nécessaire.'}
    attempts[key]=result
    return result
